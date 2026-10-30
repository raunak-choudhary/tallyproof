# Two buckets: the lake (bronze downloads, silver and gold Parquet, Iceberg data
# files) and the witness bucket, where every checkpoint is written once and
# locked in compliance mode, so not even the root account can remove it early.

variable "name" {
  type = string
}

variable "witness_retention_days" {
  type    = number
  default = 2555 # seven years
}

resource "aws_s3_bucket" "lake" {
  bucket = "${var.name}-lake"
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "witness" {
  bucket              = "${var.name}-witness"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "witness" {
  bucket = aws_s3_bucket.witness.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "witness" {
  bucket = aws_s3_bucket.witness.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.witness_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "witness" {
  bucket                  = aws_s3_bucket.witness.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "lake_bucket" {
  value = aws_s3_bucket.lake.bucket
}

output "witness_bucket" {
  value = aws_s3_bucket.witness.bucket
}
