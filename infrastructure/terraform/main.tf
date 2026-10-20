# Unapplied sketch. Account 000000000000 is a placeholder. Do not apply this stack.
# There is no remote backend and no committed plan.

variable "account_id" {
  type    = string
  default = "000000000000"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "No default. This stack is not applied."
}

output "account_id" {
  value = var.account_id
}
