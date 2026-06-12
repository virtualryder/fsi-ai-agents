# AWS-native Credit Underwriting — infrastructure.
# Deterministic Lambda nodes + Strands/Bedrock SAR drafting + a Step Functions
# state machine with a waitForTaskToken BSA-Officer gate. Illustrative reference
# — wire backend/VPC/KMS per the customer account (see infra/terraform/modules).
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = ">= 5.0" }
    archive = { source = "hashicorp/archive", version = ">= 2.4" }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name = "fsi-credit-${var.environment}"
  lambdas = {
    verify                  = "lambdas.verify.handler"
    evaluate                = "lambdas.evaluate.handler"
    fair_lending            = "lambdas.fair_lending.handler"
    route                   = "lambdas.route.handler"
    generate_adverse_action = "lambdas.generate_adverse_action.handler"
    underwriter_notify      = "lambdas.underwriter_notify.handler"
    auto_approve            = "lambdas.auto_approve.handler"
    finalize                = "lambdas.finalize.handler"
  }
}

data "archive_file" "code" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/build/fincrime.zip"
  excludes    = ["infra", "tests", "build"]
}

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
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    sid       = "BedrockInvokeScoped"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:*::foundation-model/${var.bedrock_model_id}"]
  }
  statement {
    sid       = "ApplyGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [var.guardrail_arn != "" ? var.guardrail_arn : "*"]
  }
  statement {
    sid       = "AuditAppendOnly"
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
      EXTRACT_MODE         = var.extract_mode
      BEDROCK_MODEL_ID     = var.bedrock_model_id
      BEDROCK_REGION       = var.region
      BEDROCK_GUARDRAIL_ID = var.guardrail_id
      HITL_TABLE           = aws_dynamodb_table.hitl.name
      AUDIT_TABLE          = aws_dynamodb_table.audit.name
    }
  }
}

resource "aws_dynamodb_table" "hitl" {
  name         = "${local.name}-hitl"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "application_id"
  attribute {
    name = "application_id"
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

resource "aws_sfn_state_machine" "credit" {
  name     = local.name
  role_arn = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/../stepfunctions/credit_underwriting.asl.json", {
    VerifyFunctionArn                = aws_lambda_function.node["verify"].arn
    EvaluateFunctionArn              = aws_lambda_function.node["evaluate"].arn
    FairLendingFunctionArn           = aws_lambda_function.node["fair_lending"].arn
    RouteFunctionArn                 = aws_lambda_function.node["route"].arn
    GenerateAdverseActionFunctionArn = aws_lambda_function.node["generate_adverse_action"].arn
    UnderwriterNotifyFunctionArn     = aws_lambda_function.node["underwriter_notify"].arn
    AutoApproveFunctionArn           = aws_lambda_function.node["auto_approve"].arn
    FinalizeFunctionArn              = aws_lambda_function.node["finalize"].arn
  })
}
