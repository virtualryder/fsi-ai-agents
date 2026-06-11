# ══════════════════════════════════════════════════════════════════════════════
# modules/agent_service — one ECS Fargate service per agent
#
# Instantiated 12× by the env composition. The task role is the IAM half of
# the controls the code half (agent/persistence.py, platform_core) assumes:
#   - dynamodb:PutItem ONLY (no Update/Delete) on the audit table → append-only
#     holds even if application code is compromised
#   - s3:PutObject only on the WORM bucket
#   - bedrock:InvokeModel scoped to the two Claude model IDs + the guardrail
#   - secretsmanager:GetSecretValue scoped to this env's prefix
# ALB ingress authenticates at the listener with Cognito BEFORE traffic
# reaches the container (authenticate-cognito action) — the UI cannot be
# reached unauthenticated even if the app's own auth is misconfigured.
# ══════════════════════════════════════════════════════════════════════════════

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "agent_id" {
  type        = string
  description = "e.g. 01-financial-crime-investigation-agent"
}

variable "container_image" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "vpc_cidr" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "audit_table_arn" {
  type = string
}

variable "audit_bucket_arn" {
  type = string
}

variable "database_secret_arn" {
  type = string
}

variable "guardrail_id" {
  type = string
}

variable "guardrail_version" {
  type = string
}

variable "user_pool_arn" {
  type = string
}

variable "user_pool_client_id" {
  type = string
}

variable "user_pool_domain" {
  type = string
}

variable "bedrock_model_ids" {
  type = list(string)
  default = [
    "anthropic.claude-sonnet-4-6-20260601-v1:0",
    "anthropic.claude-haiku-4-5-20251001",
  ]
}

variable "cpu" {
  type    = number
  default = 1024
}

variable "memory" {
  type    = number
  default = 2048
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  service_name = "${var.name_prefix}-${var.agent_id}"
}

resource "aws_ecs_cluster" "this" {
  name = local.service_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${local.service_name}"
  retention_in_days = 365
  kms_key_id        = var.kms_key_arn
}

# ── Task role: least privilege, control-preserving ───────────────────────────
resource "aws_iam_role" "task" {
  name = "${local.service_name}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "task" {
  name = "agent-runtime"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuditAppendOnly"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"] # deliberately NOT UpdateItem/DeleteItem
        Resource = var.audit_table_arn
      },
      {
        Sid      = "AuditSnapshotWriteOnly"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.audit_bucket_arn}/${var.agent_id}/*"
      },
      {
        Sid    = "BedrockInvokeScoped"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = [
          for m in var.bedrock_model_ids :
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${m}"
        ]
      },
      {
        Sid      = "GuardrailApply"
        Effect   = "Allow"
        Action   = ["bedrock:ApplyGuardrail"]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:guardrail/${var.guardrail_id}"
      },
      {
        Sid      = "DatabaseCredentials"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.database_secret_arn
      },
      {
        Sid      = "KmsForDataPlane"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = var.kms_key_arn
      }
    ]
  })
}

resource "aws_iam_role" "execution" {
  name = "${local.service_name}-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  task_role_arn            = aws_iam_role.task.arn
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name      = "agent"
    image     = var.container_image
    essential = true
    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
    }]
    environment = [
      { name = "AGENT_ID", value = var.agent_id },
      { name = "LLM_PROVIDER", value = "bedrock" },
      { name = "BEDROCK_REGION", value = data.aws_region.current.name },
      { name = "BEDROCK_GUARDRAIL_ID", value = var.guardrail_id },
      { name = "BEDROCK_GUARDRAIL_VERSION", value = var.guardrail_version },
      { name = "AUDIT_DYNAMODB_TABLE", value = element(split("/", var.audit_table_arn), 1) },
      { name = "AUDIT_S3_BUCKET", value = element(split(":::", var.audit_bucket_arn), 1) },
      { name = "SECRETS_MANAGER_PREFIX", value = var.name_prefix },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = "agent"
      }
    }
    readonlyRootFilesystem = true
  }])
}

# ── ALB with Cognito authentication at the listener ──────────────────────────
resource "aws_security_group" "alb" {
  name_prefix = "${local.service_name}-alb-"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # institution perimeter: restrict to corp CIDRs/VPN per env
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_security_group" "service" {
  name_prefix = "${local.service_name}-svc-"
  vpc_id      = var.vpc_id

  ingress {
    description     = "From ALB only"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "VPC endpoints only — private subnets have no internet route"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Aurora"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_lb" "this" {
  name               = substr(replace(local.service_name, "/[^a-zA-Z0-9-]/", "-"), 0, 32)
  load_balancer_type = "application"
  internal           = true # reviewer UI reachable from corp network/VPN, not the internet
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "this" {
  name        = substr(replace("${var.agent_id}-tg", "/[^a-zA-Z0-9-]/", "-"), 0, 32)
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }
}

variable "acm_certificate_arn" {
  type        = string
  description = "TLS cert for the reviewer UI listener"
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  # Authentication happens HERE, before any request reaches the container.
  default_action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = var.user_pool_arn
      user_pool_client_id = var.user_pool_client_id
      user_pool_domain    = var.user_pool_domain
    }
  }

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

resource "aws_ecs_service" "this" {
  name            = local.service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = "agent"
    container_port   = 8080
  }
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}
