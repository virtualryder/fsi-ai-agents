variable "agent_key" {
  description = "Agent key, e.g. 01-financial-crime-investigation (matches the handler registry and the per-agent folder)."
  type        = string
}

variable "image_uri" {
  description = "ECR image URI for this agent's runtime container (ARM64)."
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "vpc_subnet_ids" {
  description = "Private subnet ids for the Fargate task (no public IP)."
  type        = list(string)
}

variable "security_group_ids" {
  type    = list(string)
  default = []
}

variable "audit_table_arn" {
  description = "Append-only DynamoDB audit table ARN (PutItem-only)."
  type        = string
}

variable "audit_bucket_arn" {
  description = "S3 Object Lock (WORM) audit bucket ARN."
  type        = string
  default     = ""
}

variable "bedrock_model_arns" {
  description = "Bedrock foundation-model ARNs this agent may invoke (least privilege)."
  type        = list(string)
}

variable "guardrail_arn" {
  description = "Bedrock Guardrail ARN (required in production)."
  type        = string
  default     = ""
}

variable "llm_provider" {
  description = "bedrock keeps inference in-account; anthropic for dev."
  type        = string
  default     = "bedrock"
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 1
}
