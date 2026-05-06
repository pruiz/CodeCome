# IaC Security Skill

This skill applies when the target under `src/` is an infrastructure-as-code repository or contains significant IaC artifacts.

## Scope

File types and patterns:

- Terraform: `*.tf`, `*.tfvars`, `*.hcl`
- CloudFormation: `*.yaml`, `*.json` (with `AWSTemplateFormatVersion` or `Resources` keys)
- Kubernetes: `*.yaml`, `*.yml` (with `apiVersion` / `kind` keys)
- Helm: `Chart.yaml`, `values.yaml`, `templates/*.yaml`
- Ansible: `playbook*.yml`, `roles/`, `tasks/*.yml`, `inventory/`
- Pulumi: `Pulumi.yaml`, `__main__.py`, `index.ts`
- Docker: `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`
- CDK: `cdk.json`, `lib/*.ts`, `lib/*.py`

## Reconnaissance focus

During Phase 1, document:

- IaC tool and version,
- cloud provider(s),
- resource types deployed,
- networking model (VPC, subnets, security groups, firewalls),
- identity and access management model,
- secrets management approach,
- state storage (remote backend, encryption),
- CI/CD integration,
- module/chart dependencies,
- environment separation (dev/staging/prod).

## High-risk vulnerability classes

1. Overly permissive IAM policies (`*:*`, `arn:aws:iam::*`)
2. Public storage (S3 buckets, GCS buckets, Azure blobs with public ACLs)
3. Unencrypted storage (EBS, RDS, S3 without SSE)
4. Unencrypted transport (load balancers without TLS, HTTP listeners)
5. Exposed ports (security groups with `0.0.0.0/0` on sensitive ports)
6. Missing network policies (Kubernetes pods without NetworkPolicy)
7. Hardcoded secrets (passwords, API keys, tokens in manifests)
8. Privileged containers (`privileged: true`, `hostPID: true`, `hostNetwork: true`)
9. Container running as root (missing `runAsNonRoot`, `runAsUser`)
10. Missing resource limits (Kubernetes pods without CPU/memory limits)
11. Insecure defaults (default VPC, default security groups, default service accounts)
12. Missing audit logging (CloudTrail, VPC Flow Logs, Kubernetes audit logs disabled)
13. Overly broad RBAC (ClusterRoleBinding to `cluster-admin`)
14. State file exposure (Terraform state in public S3 or without encryption)
15. Weak TLS configuration (outdated TLS versions, weak cipher suites)
16. Missing backup configuration (RDS without automated backups)
17. Insecure ingress configuration (no WAF, missing rate limiting)
18. Cross-account or cross-tenant access without least privilege

## Review guidance

### IAM and RBAC

- Check for wildcard actions (`*`) or wildcard resources (`*`).
- Check for `AdministratorAccess` or `PowerUserAccess` managed policies.
- Check Kubernetes `ClusterRole` and `ClusterRoleBinding` for excessive permissions.
- Check service account annotations and workload identity bindings.
- Verify least privilege: does each role have only the permissions it needs?

### Networking

- Check security group ingress rules for `0.0.0.0/0` or `::/0`.
- Check for SSH (port 22) or RDP (port 3389) exposed to the internet.
- Check for databases exposed to public subnets.
- Check Kubernetes `Service` type `LoadBalancer` or `NodePort` exposure.
- Verify NetworkPolicy exists for sensitive namespaces.

### Secrets

- Grep for hardcoded passwords, API keys, tokens, connection strings.
- Check for `SecureString` or encrypted parameter store usage.
- Verify Kubernetes Secrets are not stored in plain YAML committed to Git.
- Check for sealed secrets, external secrets operators, or vault integration.

### Storage and encryption

- Check S3/GCS/Azure Blob for public access configuration.
- Verify encryption at rest for databases, disks, and object storage.
- Check for KMS key usage and rotation policies.

### Containers

- Check for `privileged: true` in pod specs.
- Check for `hostPID`, `hostNetwork`, `hostIPC`.
- Check for missing `securityContext` (`runAsNonRoot`, `readOnlyRootFilesystem`).
- Check for `latest` tag usage (no image pinning).
- Check for missing resource requests and limits.

## Validation methods

IaC findings can be validated by:

- **Static proof**: demonstrating the insecure configuration in the IaC source.
- **Policy engine**: running `tfsec`, `checkov`, `kube-score`, `kubeaudit`, `trivy config`, or `opa eval` against the manifests.
- **Plan analysis**: running `terraform plan` and examining the planned resources.
- **Dry-run**: running `kubectl apply --dry-run=server` or `helm template`.
- **Config comparison**: comparing against published benchmarks (CIS, AWS Well-Architected, Kubernetes Hardening Guide).

## Evidence to capture

- The IaC source file with the insecure configuration highlighted.
- Policy engine output (e.g., `tfsec` or `checkov` findings).
- Terraform plan output showing the insecure resource.
- Relevant cloud provider documentation or CIS benchmark reference.
- Remediated configuration for comparison.

## Counter-analysis checklist

Before confirming an IaC finding, verify:

- Is the resource actually deployed, or is it a template/example?
- Is the permissive configuration overridden by a higher-level policy (SCP, OPA)?
- Is the public access intentional and documented (e.g., a public website bucket)?
- Is the hardcoded value a placeholder or default that is overridden at deploy time?
- Is the finding in a dev/test environment where the risk is accepted?
- Is there a compensating control (WAF, VPN, bastion host)?
- Does the Kubernetes namespace have a default deny NetworkPolicy?
- Is the finding about a deprecated or unused resource?

## Reporting guidance

Good finding example:

> S3 bucket `data-exports` in `modules/storage/main.tf` has `acl = "public-read"` with no bucket policy restricting access. Sensitive export files could be read by unauthenticated users.

Bad finding example:

> The project uses S3 buckets which might be misconfigured.
