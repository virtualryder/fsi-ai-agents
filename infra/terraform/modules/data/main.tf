# ══════════════════════════════════════════════════════════════════════════════
# modules/data — durable state for the agent suite (pairs with agent/persistence.py)
#
#   Aurora PostgreSQL   LangGraph PostgresSaver: HITL pauses survive restarts
#                       (DATABASE_URL).
#   DynamoDB            Append-only audit entries — persistence.py writes with
#                       attribute_not_exists(entry_id); PITR on
#                       (AUDIT_DYNAMODB_TABLE).
#   S3 Object Lock      WORM audit snapshots, COMPLIANCE mode: not deletable or
#                       shortenable by ANY principal, including root, until
#                       retention expires (AUDIT_S3_BUCKET). BSA 5yr default;
#                       extend per artifact class (FCRA 7yr, SR 11-7 10yr).
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

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "vpc_cidr" {
  type = string
}

variable "kms_key_arn" {
  type        = string
  description = "CMK from modules/security — encrypts the database, table, and bucket"
}

variable "audit_retention_days" {
  type        = number
  default     = 1825 # BSA: 5 years
  description = "Object Lock COMPLIANCE retention for audit snapshots"
}

variable "db_master_username" {
  type    = string
  default = "fsi_agent"
}

# ── Aurora PostgreSQL (LangGraph checkpoints) ────────────────────────────────
resource "aws_db_subnet_group" "aurora" {
  name       = "${var.name_prefix}-aurora"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "aurora" {
  name_prefix = "${var.name_prefix}-aurora-"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from inside the VPC only"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_rds_cluster" "checkpoints" {
  cluster_identifier          = "${var.name_prefix}-checkpoints"
  engine                      = "aurora-postgresql"
  engine_mode                 = "provisioned"
  engine_version              = "16.4"
  database_name               = "langgraph"
  master_username             = var.db_master_username
  manage_master_user_password = true # credentials live in Secrets Manager, never in state/env
  storage_encrypted           = true
  kms_key_id                  = var.kms_key_arn
  db_subnet_group_name        = aws_db_subnet_group.aurora.name
  vpc_security_group_ids      = [aws_security_group.aurora.id]
  backup_retention_period     = 35
  deletion_protection         = true
  final_snapshot_identifier   = "${var.name_prefix}-checkpoints-final"

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 4
  }
}

resource "aws_rds_cluster_instance" "checkpoints" {
  count               = 1
  cluster_identifier  = aws_rds_cluster.checkpoints.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.checkpoints.engine
  engine_version      = aws_rds_cluster.checkpoints.engine_version
  publicly_accessible = false
}

# ── DynamoDB append-only audit table ─────────────────────────────────────────
resource "aws_dynamodb_table" "audit" {
  name         = "${var.name_prefix}-audit-entries"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "entry_id"

  attribute {
    name = "entry_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  deletion_protection_enabled = true

  tags = {
    Purpose = "append-only-audit"
    Note    = "writes use attribute_not_exists(entry_id) - see agent/persistence.py"
  }
}

# ── S3 WORM bucket for audit snapshots ───────────────────────────────────────
resource "aws_s3_bucket" "audit_snapshots" {
  bucket_prefix = "${var.name_prefix}-audit-worm-"

  # Object Lock MUST be enabled at creation — it cannot be retrofitted.
  object_lock_enabled = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit_snapshots.id

  rule {
    default_retention {
      # COMPLIANCE (not GOVERNANCE): no principal can shorten or delete,
      # including the account root, until retention expires. This is the
      # examiner-grade retention claim.
      mode = "COMPLIANCE"
      days = var.audit_retention_days
    }
  }
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit_snapshots.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit_snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit_snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "database_secret_arn" {
  description = "Secrets Manager ARN for the managed master credentials"
  value       = aws_rds_cluster.checkpoints.master_user_secret[0].secret_arn
}

output "database_endpoint" {
  value = aws_rds_cluster.checkpoints.endpoint
}

output "audit_table_name" {
  value = aws_dynamodb_table.audit.name
}

output "audit_table_arn" {
  value = aws_dynamodb_table.audit.arn
}

output "audit_bucket_name" {
  value = aws_s3_bucket.audit_snapshots.bucket
}

output "audit_bucket_arn" {
  value = aws_s3_bucket.audit_snapshots.arn
}
