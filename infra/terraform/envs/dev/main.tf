# ══════════════════════════════════════════════════════════════════════════════
# envs/dev — composition root for a development deployment
#
# Usage:
#   cd infra/terraform/envs/dev
#   terraform init
#   terraform plan  -var acm_certificate_arn=arn:aws:acm:...
#   terraform apply -var acm_certificate_arn=arn:aws:acm:...
#
# Pilot scoping: `agents` below deploys the pilot wedge (02, 09, 06 — see
# offerings/PILOT-OFFERING.md). Add entries to scale out; each agent is an
# independent service with its own least-privilege task role.
#
# State backend: configure your org's S3+DynamoDB backend before first apply —
# `backend "s3" {}` left partial deliberately so no one applies from a laptop
# with local state by accident.
# ══════════════════════════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.7"

  backend "s3" {
    # Supplied via -backend-config; never commit bucket/key/lock-table values.
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "fsi-ai-agents"
      Environment = "dev"
      ManagedBy   = "terraform"
      DataClass   = "confidential"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "acm_certificate_arn" {
  type        = string
  description = "TLS certificate for reviewer UI ALBs"
}

variable "okta_saml_metadata_url" {
  type    = string
  default = ""
}

variable "agents" {
  type = map(object({
    image = string
  }))
  default = {
    "02-aml-tms-enhancement-agent"     = { image = "REPLACE.dkr.ecr.us-east-1.amazonaws.com/fsi/agent-02:latest" }
    "09-document-intelligence-agent"   = { image = "REPLACE.dkr.ecr.us-east-1.amazonaws.com/fsi/agent-09:latest" }
    "06-regulatory-change-agent"       = { image = "REPLACE.dkr.ecr.us-east-1.amazonaws.com/fsi/agent-06:latest" }
  }
}

locals {
  name_prefix = "fsi-agents-dev"
}

module "network" {
  source      = "../../modules/network"
  name_prefix = local.name_prefix
}

module "security" {
  source                 = "../../modules/security"
  name_prefix            = local.name_prefix
  okta_saml_metadata_url = var.okta_saml_metadata_url
}

module "data" {
  source             = "../../modules/data"
  name_prefix        = local.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  vpc_cidr           = module.network.vpc_cidr
  kms_key_arn        = module.security.kms_key_arn
}

resource "aws_cognito_user_pool_domain" "reviewers" {
  domain       = local.name_prefix
  user_pool_id = module.security.user_pool_id
}

module "agent" {
  source   = "../../modules/agent_service"
  for_each = var.agents

  name_prefix         = local.name_prefix
  agent_id            = each.key
  container_image     = each.value.image
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  public_subnet_ids   = module.network.public_subnet_ids
  vpc_cidr            = module.network.vpc_cidr
  kms_key_arn         = module.security.kms_key_arn
  audit_table_arn     = module.data.audit_table_arn
  audit_bucket_arn    = module.data.audit_bucket_arn
  database_secret_arn = module.data.database_secret_arn
  guardrail_id        = module.security.guardrail_id
  guardrail_version   = module.security.guardrail_version
  user_pool_arn       = module.security.user_pool_arn
  user_pool_client_id = module.security.user_pool_client_id
  user_pool_domain    = aws_cognito_user_pool_domain.reviewers.domain
  acm_certificate_arn = var.acm_certificate_arn
}

output "agent_endpoints" {
  value = { for k, m in module.agent : k => m.alb_dns_name }
}

output "audit_table" {
  value = module.data.audit_table_name
}

output "audit_bucket" {
  value = module.data.audit_bucket_name
}
