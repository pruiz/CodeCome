# Terraform IaC review sandbox example

Static-review oriented sandbox for HashiCorp Terraform IaC targets.
No provider authentication is configured. No real cloud calls.

## What's included

- `hashicorp/terraform:__TERRAFORM_VERSION__` base image (Alpine)
- `tflint` (best-effort install via official installer script)
- Common Linux utilities: `bash`, `git`, `make`, `python3`,
  `ripgrep`, `jq`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__TERRAFORM_VERSION__` | Terraform tag (e.g. `1.9`, `1.8`, `latest`). |

## What it does

- `build-target.sh`: `terraform init -backend=false`, then
  `terraform fmt -check` and `terraform validate`.
- `test-target.sh`: optional `tflint --recursive` if tflint installed.

## Why no provider auth

Provider credentials, state backends, and apply operations belong to
the user's real environment. CodeCome's sandbox is for static
review and validate-only checks.
