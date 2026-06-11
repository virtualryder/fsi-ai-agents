variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "extract_mode" {
  description = "Set to 'demo' until Bedrock model access is enabled; '' for live inference."
  type        = string
  default     = "demo"
}

variable "bedrock_model_id" {
  type    = string
  default = "us.anthropic.claude-sonnet-4-20250514-v1:0"
}

variable "bedrock_fast_model_id" {
  type    = string
  default = "anthropic.claude-haiku-4-5-20251001"
}

variable "guardrail_id" {
  description = "Bedrock Guardrail id (required in production — see infra/terraform/modules/security)."
  type        = string
  default     = ""
}

variable "guardrail_arn" {
  type    = string
  default = ""
}
