# The checkpoint signing key. Ed25519 in KMS, used with ED25519_SHA_512 on raw
# messages: the pre-hash variant produces signatures standard verifiers reject.
# The private key never leaves KMS; the checkpointer's role may only Sign.

variable "name" {
  type = string
}

resource "aws_kms_key" "signing" {
  description              = "${var.name} checkpoint signing key"
  customer_master_key_spec = "ECC_NIST_EDWARDS25519" # gitleaks:allow - an AWS key type name, not a secret
  key_usage                = "SIGN_VERIFY"
  deletion_window_in_days  = 30
}

resource "aws_kms_alias" "signing" {
  name          = "alias/${var.name}-checkpoints"
  target_key_id = aws_kms_key.signing.key_id
}

output "signing_key_arn" {
  value = aws_kms_key.signing.arn
}
