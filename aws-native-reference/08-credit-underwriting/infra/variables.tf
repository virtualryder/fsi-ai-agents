variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "extract_mode" {
  type    = string
  default = "demo"
}

variable "bedrock_model_id" {
  type    = string
  default = "us.anthropic.claude-sonnet-4-20250514-v1:0"
}

variable "guardrail_id" {
  type    = string
  default = ""
}

variable "guardrail_arn" {
  type    = string
  default = ""
}
