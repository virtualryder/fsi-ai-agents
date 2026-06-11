# ══════════════════════════════════════════════════════════════════════════════
# modules/security — KMS, Bedrock Guardrail, Cognito (Okta SAML), detection
#
#   KMS CMK             one customer-managed key, rotation on — encrypts
#                       Aurora, DynamoDB, S3, logs.
#   Bedrock Guardrail   the BEDROCK_GUARDRAIL_ID consumed by the platform LLM
#                       factory: PII anonymization at the model boundary as
#                       defense-in-depth behind the in-code masking layer.
#   Cognito             user pool + Okta SAML IdP; the JWT's custom:bsa_role
#                       claim is what platform_core auth.require_role enforces
#                       server-side on HITL approvals.
#   GuardDuty/SecurityHub  account-level detection, FSBP standard enabled.
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

variable "okta_saml_metadata_url" {
  type        = string
  default     = ""
  description = "Okta IdP SAML metadata URL — empty disables the IdP (local dev)"
}

variable "enable_detection" {
  type        = bool
  default     = true
  description = "GuardDuty + SecurityHub (disable when managed at the org level)"
}

# ── KMS ───────────────────────────────────────────────────────────────────────
resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} CMK — agent data, audit, checkpoints"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

# ── Bedrock Guardrail ─────────────────────────────────────────────────────────
resource "aws_bedrock_guardrail" "agents" {
  name                      = "${var.name_prefix}-guardrail"
  description               = "PII anonymization + prompt-attack screen for agent inference"
  blocked_input_messaging   = "Input blocked by content policy."
  blocked_outputs_messaging = "Output blocked by content policy."

  sensitive_information_policy_config {
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "US_SOCIAL_SECURITY_NUMBER"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "CREDIT_DEBIT_CARD_NUMBER"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "US_BANK_ACCOUNT_NUMBER"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "US_BANK_ROUTING_NUMBER"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "EMAIL"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "PHONE"
    }
  }

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }
}

resource "aws_bedrock_guardrail_version" "agents" {
  guardrail_arn = aws_bedrock_guardrail.agents.guardrail_arn
  description   = "pinned version for agent task definitions"
}

# ── Cognito + Okta SAML ───────────────────────────────────────────────────────
resource "aws_cognito_user_pool" "reviewers" {
  name = "${var.name_prefix}-reviewers"

  admin_create_user_config {
    allow_admin_create_user_only = true # federation or admin-created only
  }

  password_policy {
    minimum_length    = 14
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  schema {
    name                = "bsa_role"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 64
    }
  }
}

resource "aws_cognito_identity_provider" "okta" {
  count         = var.okta_saml_metadata_url == "" ? 0 : 1
  user_pool_id  = aws_cognito_user_pool.reviewers.id
  provider_name = "Okta"
  provider_type = "SAML"

  provider_details = {
    MetadataURL = var.okta_saml_metadata_url
  }

  attribute_mapping = {
    email           = "email"
    "custom:bsa_role" = "bsa_role" # Okta group -> claim consumed by require_role()
  }
}

resource "aws_cognito_user_pool_client" "reviewer_ui" {
  name                                 = "${var.name_prefix}-reviewer-ui"
  user_pool_id                         = aws_cognito_user_pool.reviewers.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = ["https://localhost/oauth2/idpresponse"] # replaced per env by ALB DNS
  supported_identity_providers = concat(
    ["COGNITO"],
    var.okta_saml_metadata_url == "" ? [] : ["Okta"],
  )
}

# ── Detection ─────────────────────────────────────────────────────────────────
resource "aws_guardduty_detector" "this" {
  count  = var.enable_detection ? 1 : 0
  enable = true
}

resource "aws_securityhub_account" "this" {
  count = var.enable_detection ? 1 : 0
}

resource "aws_securityhub_standards_subscription" "fsbp" {
  count         = var.enable_detection ? 1 : 0
  depends_on    = [aws_securityhub_account.this]
  standards_arn = "arn:aws:securityhub:us-east-1::standards/aws-foundational-security-best-practices/v/1.0.0"
}

output "kms_key_arn" {
  value = aws_kms_key.this.arn
}

output "guardrail_id" {
  value = aws_bedrock_guardrail.agents.guardrail_id
}

output "guardrail_version" {
  value = aws_bedrock_guardrail_version.agents.version
}

output "user_pool_id" {
  value = aws_cognito_user_pool.reviewers.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.reviewers.arn
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.reviewer_ui.id
}
