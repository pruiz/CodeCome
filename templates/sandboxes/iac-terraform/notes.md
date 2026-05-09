# Notes for the Terraform IaC review sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/` with durable ways to:

    sandbox setup
    sandbox start
    sandbox sanity
    target build
    target test
    sandbox stop

Use the canonical helper set under `sandbox/scripts/`:
`setup.sh`, `up.sh`, `check.sh`, `build.sh`, `test.sh`, `down.sh`.
Add operational helpers such as `shell.sh`, `logs.sh`, `clean.sh`,
and `reset.sh` when they make sense for the target. Document any
extras or omitted helpers in `itemdb/notes/sandbox-plan.md`. See
`.opencode/skills/sandbox-bootstrap/SKILL.md`.

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
