# AWS-native Document Intelligence reference — infrastructure (Phase 2).
#
# Provisions the five deterministic Lambda nodes + the HITL-notify Lambda, the
# Step Functions state machine, and LEAST-PRIVILEGE IAM. Mirrors the suite's
# control posture: scoped Bedrock invoke, append-only audit (DynamoDB PutItem),
# Guardrails attached to inference. Illustrative reference — wire backend, VPC,
# and KMS per the customer's account standards (see infra/terraform/modules).

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name = "fsi-docintel-${var.environment}"
  lambdas = {
    pii_mask    = "lambdas.pii_mask.handler"
    extract     = "lambdas.extract.handler"
    validate    = "lambdas.validate.handler"
    route       = "lambdas.route.handler"
    finalize    = "lambdas.finalize.handler"
    hitl_notify = "lambdas.hitl_notify.handler"
  }
}

# ── Packaging (one zip for all node handlers + core/strands_agent) ────────────
data "archive_file" "code" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/build/docintel.zip"
  excludes    = ["infra", "tests", "build"]
}

# ── Execution role (least privilege) ──────────────────────────────────────────
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid     = "Logs"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    sid     = "BedrockInvokeScopedToTwoModels"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/${var.bedrock_model_id}",
      "arn:aws:bedrock:*::foundation-model/${var.bedrock_fast_model_id}"
    ]
  }
  statement {
    sid       = "ApplyGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [var.guardrail_arn != "" ? var.guardrail_arn : "*"]
  }
  statement {
    sid       = "AuditAppendOnly" # PutItem only — no Update/Delete (append-only)
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.hitl.arn, aws_dynamodb_table.audit.arn]
  }
  statement {
    sid       = "ResumeStateMachine"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ── Lambda functions ──────────────────────────────────────────────────────────
resource "aws_lambda_function" "node" {
  for_each         = local.lambdas
  function_name    = "${local.name}-${each.key}"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = each.value
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 60
  memory_size      = 512
  environment {
    variables = {
      EXTRACT_MODE          = var.extract_mode # "demo" until Bedrock access is wired
      BEDROCK_MODEL_ID      = var.bedrock_model_id
      BEDROCK_REGION        = var.region
      BEDROCK_GUARDRAIL_ID  = var.guardrail_id
      HITL_TABLE            = aws_dynamodb_table.hitl.name
      AUDIT_TABLE           = aws_dynamodb_table.audit.name
    }
  }
}

# ── Append-only data stores ───────────────────────────────────────────────────
resource "aws_dynamodb_table" "hitl" {
  name         = "${local.name}-hitl"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_id"
  attribute {
    name = "doc_id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
}

resource "aws_dynamodb_table" "audit" {
  name         = "${local.name}-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "entry_id"
  attribute {
    name = "entry_id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
}

# ── Step Functions state machine ──────────────────────────────────────────────
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.name}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [for f in aws_lambda_function.node : f.arn]
    }]
  })
}

resource "aws_sfn_state_machine" "docintel" {
  name     = local.name
  role_arn = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/../stepfunctions/document_intelligence.asl.json", {
    PiiMaskFunctionArn    = aws_lambda_function.node["pii_mask"].arn
    ExtractFunctionArn    = aws_lambda_function.node["extract"].arn
    ValidateFunctionArn   = aws_lambda_function.node["validate"].arn
    RouteFunctionArn      = aws_lambda_function.node["route"].arn
    HitlNotifyFunctionArn = aws_lambda_function.node["hitl_notify"].arn
    FinalizeFunctionArn   = aws_lambda_function.node["finalize"].arn
  })
}
