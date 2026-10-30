# Three brokers across availability zones, IAM authentication, TLS in transit.
# The same Kafka client code the local Redpanda broker uses; partition counts
# come from the load test (docs/load-test.md).

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

resource "aws_security_group" "brokers" {
  name   = "${var.name}-msk"
  vpc_id = var.vpc_id
}

resource "aws_msk_cluster" "events" {
  cluster_name           = "${var.name}-events"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.m7g.large"
    client_subnets  = slice(var.subnet_ids, 0, 3)
    security_groups = [aws_security_group.brokers.id]
    storage_info {
      ebs_storage_info {
        volume_size = 500
      }
    }
  }

  client_authentication {
    sasl {
      iam = true
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }
}

output "bootstrap_brokers_iam" {
  value = aws_msk_cluster.events.bootstrap_brokers_sasl_iam
}
