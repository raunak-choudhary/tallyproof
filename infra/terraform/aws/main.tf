# Tallyproof on AWS: a reference sketch, never applied. See README.md.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  description = "Prefix for every resource"
  type        = string
  default     = "tallyproof"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  description = "At least three, one per availability zone"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "For the API's load balancer"
  type        = list(string)
}

variable "image" {
  description = "The backend container image, the same one for the API and every worker"
  type        = string
}

module "kms" {
  source = "./modules/kms"
  name   = var.name
}

module "s3" {
  source = "./modules/s3"
  name   = var.name
}

module "msk" {
  source     = "./modules/msk"
  name       = var.name
  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids
}

module "aurora" {
  source     = "./modules/aurora"
  name       = var.name
  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids
}

module "glue" {
  source      = "./modules/glue"
  name        = var.name
  lake_bucket = module.s3.lake_bucket
}

module "ecs" {
  source             = "./modules/ecs"
  name               = var.name
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  public_subnet_ids  = var.public_subnet_ids
  image              = var.image
  signing_key_arn    = module.kms.signing_key_arn
  kafka_bootstrap    = module.msk.bootstrap_brokers_iam
  database_endpoint  = module.aurora.writer_endpoint
  analyst_endpoint   = module.aurora.reader_endpoint
}

output "api_url" {
  value = module.ecs.api_url
}
