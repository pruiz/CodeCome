# Security Controls and Assets Reference

Use this reference during CodeCome Phase 1b. It provides lightweight checklists
for asset identification and control discovery. Do not copy categories blindly —
only include repository-specific items supported by evidence or explicitly
marked as assumptions.

## Asset categories

Consider whether the target manages or interacts with:

- user data (PII, credentials, tokens, session state, billing information),
- authentication artifacts (password hashes, OAuth tokens, API keys, JWTs, session cookies),
- authorization state (RBAC roles, ACLs, permission flags, policy documents),
- secrets and keys (encryption keys, signing keys, TLS certificates, API secrets, seed values),
- configuration and feature flags (environment variables, feature toggles, build-time configs that change security behavior),
- source/build artifacts (signatures, checksums, provenance metadata, SBOMs),
- audit logs and telemetry (security events, access logs, error logs containing sensitive data),
- availability-critical resources (database connections, rate-limit state, circuit-breaker state, queue depth),
- tenant isolation boundaries (database-per-tenant, schema-per-tenant, row-level security, namespace isolation),
- integrity-critical state (financial records, ledger entries, vote tallies, medical records, compliance data),
- privileged execution context (sudo, setuid, container breakouts, kernel modules, admin APIs),
- internal service reachability (admin panels, management APIs, debug endpoints, health checks exposing internals).

## Control categories

When documenting existing controls (`itemdb/notes/threat-model.md`, Existing controls section), consider:

### Identity and access

- Authentication mechanisms (password, OAuth, SSO, mTLS, API keys).
- Authorization models (RBAC, ABAC, ReBAC, policy engines).
- Session management (token lifecycle, refresh, revocation, binding).
- Multi-factor authentication.

### Input protection

- Input validation and sanitization (allowlists, schema validation, parameterized queries).
- Output encoding (HTML, JS, URL, SQL context-aware encoding).
- Content Security Policy, XSS protections.
- CSRF tokens, SameSite cookies, Origin/Referer checks.

### Network safeguards

- TLS/HTTPS enforcement, certificate pinning.
- Network segmentation, firewalls, security groups.
- Rate limiting, throttling, DoS protection.
- Web Application Firewalls.

### Data protection

- Encryption at rest and in transit.
- Key management, key rotation, HSM usage.
- Data masking, tokenization, redaction.
- Secure deletion, data retention policies.

### Isolation

- Container/sandbox boundaries.
- Process/user separation.
- Tenant isolation (database, schema, row-level, namespace).
- Privilege separation (least privilege, capability dropping).

### Observability

- Audit logging of security-relevant events.
- Intrusion detection, anomaly detection.
- Alerting on security policy violations.
- Integrity monitoring (file integrity, configuration drift).

### Supply chain

- Dependency scanning, SBOM generation.
- Signed commits, signed releases, artifact provenance.
- Build reproducibility, hermetic builds.
- Pinned dependencies, lockfiles, vendoring.

### Change control

- Code review requirements for security-sensitive paths.
- Deployment approvals, change windows.
- Configuration change auditing.
- Secret rotation procedures.

### Resource controls

- Connection pooling limits.
- Request size limits, payload limits.
- Timeout configuration.
- Memory/CPU quotas, cgroup limits.

## Concrete phrasing patterns

When documenting a control, prefer this structure:

```
## Control: <name>

- Location: <file:line or configuration key>
- Protects: <asset or boundary>
- Mechanism: <how it works, 1-2 sentences>
- Evidence: <configuration, code reference, or observable behavior>
- Gaps / uncertainty: <known limitations or untested assumptions>
```

Avoid copying these control categories verbatim into threat-model.md. Only
document controls actually observed in the repository.
