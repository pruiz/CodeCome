# Notes for the Terraform IaC review sandbox baseline

## When to use

- Repository is primarily `.tf` Terraform code.
- Goal is static review: validation, formatting, and lint.

## When NOT to use

- Target needs `terraform plan` against a real provider — out of
  scope by design.
- Target uses Terragrunt — extend this baseline to install Terragrunt
  alongside Terraform.
- Target uses Pulumi or AWS CDK — create a different example.

## Common follow-up edits

- Add `tfsec` or `checkov` for security-oriented review.
- Pin a specific Terraform version to match `.terraform-version`.
- Mount real lockfiles read-only when validating module versions.
