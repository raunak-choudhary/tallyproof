# AWS reference architecture as Terraform

A sketch of how Tallyproof would run on AWS, written as Terraform so the mapping in [the AWS reference architecture](../../../docs/aws-reference-architecture.md) is concrete. It has never been applied, and it was not validated with Terraform when it was written, because Terraform wasn't installed on the machine. Before using it:

```bash
terraform -chdir=infra/terraform/aws init -backend=false
terraform -chdir=infra/terraform/aws validate
```

It assumes an existing VPC and private subnets, passed in as variables, and leaves out what every AWS account sets up its own way: DNS, certificates, CI roles, and alarms.

| Module | Replaces locally | Limitation it lifts |
|---|---|---|
| `modules/kms` | The Ed25519 signing key in a file | The signing key never leaves a key management service |
| `modules/s3` | Bronze downloads and lake files on disk; witness copies | An object store, with Object Lock in compliance mode for checkpoints |
| `modules/msk` | One Redpanda broker | Three brokers across availability zones, IAM authentication |
| `modules/aurora` | One Postgres in a 3 GiB VM | A writer and a read replica, the replica serving the analyst's read-only role |
| `modules/ecs` | The API and workers as host processes | Each process as its own Fargate service behind a load balancer |
| `modules/glue` | The SQLite Iceberg catalog and Redpanda's schema registry | The Glue Data Catalog for the lake's tables and the Glue Schema Registry for events |
