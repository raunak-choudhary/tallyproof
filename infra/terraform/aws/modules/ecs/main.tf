# Every process in its own Fargate service from one image: the API behind an
# Application Load Balancer, and the workers scaled by consumer group. Only the
# checkpointer's task role may use the signing key, and only to Sign.

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "image" {
  type = string
}

variable "signing_key_arn" {
  type = string
}

variable "kafka_bootstrap" {
  type = string
}

variable "database_endpoint" {
  type = string
}

variable "analyst_endpoint" {
  type = string
}

locals {
  workers = {
    ingest       = { command = ["python", "manage.py", "ingest"], count = 3 }
    checkpointer = { command = ["python", "manage.py", "checkpointer"], count = 1 }
    project      = { command = ["python", "manage.py", "project"], count = 1 }
    relay        = { command = ["python", "manage.py", "relay_outbox"], count = 1 }
  }
  environment = [
    { name = "KAFKA_BOOTSTRAP_SERVERS", value = var.kafka_bootstrap },
    { name = "DB_HOST", value = var.database_endpoint },
    { name = "DB_ANALYST_HOST", value = var.analyst_endpoint },
  ]
}

resource "aws_ecs_cluster" "main" {
  name = var.name
}

resource "aws_iam_role" "task" {
  for_each = merge(local.workers, { api = { command = [], count = 2 } })
  name     = "${var.name}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sign_only" {
  name = "${var.name}-sign-checkpoints"
  role = aws_iam_role.task["checkpointer"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["kms:Sign", "kms:GetPublicKey"]
      Resource = var.signing_key_arn
    }]
  })
}

resource "aws_ecs_task_definition" "worker" {
  for_each                 = local.workers
  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.task[each.key].arn
  container_definitions = jsonencode([{
    name        = each.key
    image       = var.image
    command     = each.value.command
    essential   = true
    environment = local.environment
  }])
}

resource "aws_security_group" "tasks" {
  name   = "${var.name}-tasks"
  vpc_id = var.vpc_id
}

resource "aws_ecs_service" "worker" {
  for_each        = local.workers
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker[each.key].arn
  desired_count   = each.value.count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.tasks.id]
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.task["api"].arn
  container_definitions = jsonencode([{
    name         = "api"
    image        = var.image
    command      = ["gunicorn", "config.wsgi", "-c", "config/gunicorn_conf.py", "--bind", "0.0.0.0:8000"]
    essential    = true
    environment  = local.environment
    portMappings = [{ containerPort = 8000 }]
    healthCheck = {
      command = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz')\""]
    }
  }])
}

resource "aws_lb" "api" {
  name               = "${var.name}-api"
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path = "/readyz"
  }
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.tasks.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
}

output "api_url" {
  value = "http://${aws_lb.api.dns_name}"
}
