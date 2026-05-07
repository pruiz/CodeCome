# Notes for the Terraform IaC review sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/`, including authoring missing canonical scripts:

    check.sh   up.sh   down.sh   shell.sh   logs.sh
    clean.sh   reset.sh

The agent should also adapt the starter `build-target.sh` and
`test-target.sh` to the actual project layout, and add
target-specific scripts when they help. Document any extras in
`itemdb/notes/sandbox-plan.md`. See
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
