# The Glue Data Catalog in place of the local SQLite Iceberg catalog, and the
# Glue Schema Registry in place of Redpanda's. Event schemas are already JSON
# Schema draft-07 with internal references only, which Glue accepts as is.

variable "name" {
  type = string
}

variable "lake_bucket" {
  type = string
}

resource "aws_glue_catalog_database" "lake" {
  name         = "${var.name}_lake"
  location_uri = "s3://${var.lake_bucket}/warehouse"
}

resource "aws_glue_registry" "events" {
  registry_name = "${var.name}-events"
}

resource "aws_glue_schema" "events" {
  schema_name       = "fin.events.raw.v1-value"
  registry_arn      = aws_glue_registry.events.arn
  data_format       = "JSON"
  compatibility     = "BACKWARD"
  schema_definition = file("${path.module}/../../../../../backend/schemas/events.v2.json")
}

output "catalog_database" {
  value = aws_glue_catalog_database.lake.name
}
