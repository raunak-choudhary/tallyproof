# Aurora PostgreSQL with a writer and a read replica. The same migrations run
# here; the analyst's read-only role connects to the reader endpoint, so its
# queries never compete with ingestion for the writer.

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

resource "aws_db_subnet_group" "ledger" {
  name       = "${var.name}-ledger"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "ledger" {
  name   = "${var.name}-aurora"
  vpc_id = var.vpc_id
}

resource "aws_rds_cluster" "ledger" {
  cluster_identifier          = "${var.name}-ledger"
  engine                      = "aurora-postgresql"
  engine_version              = "16.4"
  database_name               = "tallyproof"
  master_username             = "postgres"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.ledger.name
  vpc_security_group_ids      = [aws_security_group.ledger.id]
  storage_encrypted           = true
  deletion_protection         = true
  backup_retention_period     = 14
}

resource "aws_rds_cluster_instance" "ledger" {
  count              = 2 # the first is the writer, the second the analyst's reader
  identifier         = "${var.name}-ledger-${count.index}"
  cluster_identifier = aws_rds_cluster.ledger.id
  instance_class     = "db.r7g.large"
  engine             = aws_rds_cluster.ledger.engine
  engine_version     = aws_rds_cluster.ledger.engine_version
}

output "writer_endpoint" {
  value = aws_rds_cluster.ledger.endpoint
}

output "reader_endpoint" {
  value = aws_rds_cluster.ledger.reader_endpoint
}
