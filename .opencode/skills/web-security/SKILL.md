# Web Security Skill

Use this skill when the target appears to expose HTTP, API, browser, webhook, or web-service attack surfaces.

This skill supports reconnaissance, hypothesis generation, counter-analysis, validation, and reporting for web applications and HTTP services.

## Scope

Relevant targets include:

- web applications,
- REST APIs,
- GraphQL APIs,
- RPC-over-HTTP services,
- webhook receivers,
- admin panels,
- backend services,
- reverse-proxy exposed services,
- browser-facing applications,
- file upload/download services.

## Reconnaissance focus

During reconnaissance, identify:

- routes,
- controllers,
- handlers,
- middleware,
- filters,
- authentication flows,
- authorization checks,
- session management,
- CSRF protections,
- CORS configuration,
- file upload/download paths,
- API schemas,
- GraphQL resolvers,
- webhook endpoints,
- template rendering,
- static file serving,
- redirects,
- SSRF-capable HTTP clients,
- deserialization boundaries,
- database access paths,
- tenant isolation boundaries,
- admin-only functionality.

## Common files and patterns

Look for:

- route definitions,
- controller classes,
- handler functions,
- middleware registration,
- auth policy configuration,
- OpenAPI/Swagger specs,
- GraphQL schemas,
- templates,
- serializers/deserializers,
- ORM repositories,
- file storage abstractions,
- reverse proxy configuration,
- Docker Compose services,
- environment variable config,
- application settings.

Examples by stack:

- ASP.NET Core: `Program.cs`, `Startup.cs`, controllers, minimal APIs, authorization policies.
- Java Spring: `@Controller`, `@RestController`, `@RequestMapping`, filters, security config.
- Node/Express: `app.get`, `router.post`, middleware, passport/session config.
- Python FastAPI/Flask/Django: routes, dependencies, decorators, middleware, settings.
- PHP Laravel/Symfony: routes, controllers, middleware, guards, policies.

## High-risk vulnerability classes

Prioritize:

- authentication bypass,
- authorization bypass,
- IDOR / broken object-level authorization,
- tenant isolation flaws,
- SQL/query injection,
- command injection,
- path traversal,
- arbitrary file upload,
- unsafe file download,
- SSRF,
- open redirect,
- XSS,
- CSRF,
- insecure deserialization,
- XXE,
- template injection,
- request smuggling-related config issues,
- insecure CORS,
- session fixation,
- weak password reset flows,
- token validation mistakes,
- business logic flaws,
- secrets exposure,
- insecure debug endpoints.

## Attack surface model

For each web attack surface, record:

- HTTP method,
- route/path,
- handler/controller/function,
- authentication requirement,
- authorization requirement,
- request parameters,
- request body model,
- file inputs,
- headers/cookies used,
- tenant/user context,
- backend service calls,
- database access,
- filesystem access,
- external network calls,
- response behavior.

## Authentication review

Check:

- login flow,
- session creation,
- token issuance,
- token validation,
- password reset,
- email verification,
- MFA flow,
- OAuth/OIDC/SAML integration,
- JWT validation,
- cookie flags,
- session expiration,
- logout behavior,
- remember-me behavior,
- auth middleware coverage.

Look for:

- unsigned or weakly validated tokens,
- missing issuer/audience checks,
- accepting `alg=none`,
- missing expiration checks,
- trusting client-controlled identity fields,
- inconsistent auth enforcement across routes,
- password reset token leakage,
- account enumeration,
- session fixation.

## Authorization review

Check every sensitive operation for:

- user ownership checks,
- tenant checks,
- role checks,
- permission checks,
- object-level authorization,
- function-level authorization,
- admin-only restrictions,
- repository-layer filters,
- database row-level security,
- middleware and decorator coverage.

Good finding example:

    `GET /documents/{id}` requires authentication but loads the document by id
    and returns it without checking that the current user owns the document.

Bad finding example:

    This API might have IDOR issues.

## Injection review

Check whether user-controlled input reaches:

- raw SQL,
- dynamic query builders,
- ORM raw query APIs,
- shell commands,
- LDAP queries,
- XPath queries,
- template engines,
- dynamic code evaluation.

Do not report injection only because input reaches a database.

Show the unsafe construction and why parameterization or allowlisting is missing.

## File handling review

Check:

- upload validation,
- extension checks,
- MIME checks,
- content inspection,
- storage path construction,
- download authorization,
- path normalization,
- archive extraction,
- symlink handling,
- public file serving,
- overwrite behavior,
- executable uploads,
- temporary files.

## SSRF review

Check whether user-controlled URLs, hostnames, callbacks, webhooks, or import URLs reach HTTP clients.

Consider:

- internal IP ranges,
- DNS rebinding,
- redirects,
- alternate URL schemes,
- IPv6,
- localhost aliases,
- cloud metadata endpoints,
- proxy behavior,
- allowlist mistakes.

## XSS review

Check:

- template rendering,
- raw HTML injection,
- markdown rendering,
- rich text sanitization,
- JSON embedded in HTML,
- user-controlled attributes,
- unsafe DOM sinks,
- CSP limitations.

Consider whether auto-escaping applies.

## CSRF review

Check state-changing browser-accessible routes.

Consider:

- cookie-based authentication,
- missing CSRF tokens,
- SameSite cookie settings,
- CORS interaction,
- JSON endpoints reachable by browser forms or fetch,
- method override behavior.

Do not report CSRF for pure bearer-token APIs unless browser credential behavior makes it relevant.

## CORS review

Check:

- wildcard origins with credentials,
- reflecting arbitrary Origin,
- overly broad trusted origins,
- missing Vary headers,
- development origins in production config.

## Validation methods

Useful web validation methods include:

- local HTTP request reproduction,
- integration tests,
- route-level tests,
- two-user or two-tenant test cases,
- crafted request bodies,
- file upload/download tests,
- SSRF callback listener inside sandbox,
- log inspection,
- database state inspection,
- static proof for missing authorization paths.

## Evidence to capture

For confirmed web findings, capture:

- request,
- response,
- authentication context,
- user/tenant ids used,
- relevant logs,
- database state if needed,
- expected safe response,
- observed vulnerable response,
- reproduction steps.

Do not include real secrets.

Use placeholders for tokens when needed.

## Counter-analysis checklist

Before keeping a web finding open, check:

- Is the route reachable?
- Is authentication required?
- Is authorization enforced by middleware, decorator, policy, filter, repository, or database?
- Is input validation applied by framework/model binding?
- Is output encoding or template auto-escaping effective?
- Is SQL parameterized?
- Is filesystem access constrained by safe storage APIs?
- Is the finding duplicated elsewhere?
- Is the attack scenario realistic?

## Reporting guidance

Be precise.

Mention:

- endpoint or handler,
- affected role/user/tenant,
- attacker-controlled input,
- missing or insufficient control,
- impact,
- validation method,
- evidence path.

Avoid broad claims such as:

    The API has broken access control.

Prefer:

    `GET /api/documents/{documentId}` loads documents by id and returns them
    to any authenticated user without checking tenant ownership.
