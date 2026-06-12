# Reusable runtime module: deploys ONE FSI agent's runtime container on ECS
# Fargate (ARM64) with least-privilege IAM, in-account Bedrock inference +
# Guardrails, and append-only audit. Instantiate once per agent (see
# aws-native-reference/<agent>/ and envs/all-agents). The same image also
# deploys to Amazon Bedrock AgentCore Runtime — see the deploy guide; that path
# uses the AgentCore control plane rather than this Fargate task.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.0" }
  }
}

locals {
  name = "fsi-${var.agent_key}-${var.environment}"
}

# ── Least-privilege task role ─────────────────────────────────────────────────
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "BedrockInvokeLeastPrivilege"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = var.bedrock_model_arns
  }
  dynamic "statement" {
    for_each = var.guardrail_arn != "" ? [1] : []
    content {
      sid       = "ApplyGuardrail"
      actions   = ["bedrock:ApplyGuardrail"]
      resources = [var.guardrail_arn]
    }
  }
  statement {
    sid       = "AuditAppendOnly" # PutItem only — no Update/Delete
    actions   = ["dynamodb:PutItem"]
    resources = [var.audit_table_arn]
  }
  dynamic "statement" {
    for_each = var.audit_bucket_arn != "" ? [1] : []
    content {
      sid       = "AuditWormPut"
      actions   = ["s3:PutObject"]
      resources = ["${var.audit_bucket_arn}/*"]
    }
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Cluster, logs, task, service ──────────────────────────────────────────────
resource "aws_ecs_cluster" "this" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/fsi/${var.agent_key}/${var.environment}"
  retention_in_days = 365
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "ARM64" # match the AgentCore-compatible image
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name      = "agent"
    image     = var.image_uri
    essential = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "AGENT", value = var.agent_key },
      { name = "LLM_PROVIDER", value = var.llm_provider },
      { name = "ENVIRONMENT", value = var.environment },
      { name = "AUDIT_DYNAMODB_TABLE", value = var.agent_key },
      { name = "CONNECTOR_MODE", value = "fixture" } # flip to "live" when systems wired
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "agent"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/ping').status==200 else 1)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_ecs_service" "this" {
  name            = local.name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.vpc_subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false # private subnets + VPC endpoints only
  }
}
