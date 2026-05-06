# .NET Security Skill

Use this skill when the target contains .NET, C#, ASP.NET Core, ASP.NET MVC, Web API, worker services, desktop apps, libraries, or related .NET projects.

This skill supports reconnaissance, vulnerability hypothesis generation, counter-analysis, validation, and reporting for .NET targets.

## Scope

Relevant files include:

- `.sln`
- `.csproj`
- `.fsproj`
- `.vbproj`
- `.props`
- `.targets`
- `Program.cs`
- `Startup.cs`
- `appsettings.json`
- `appsettings.*.json`
- `web.config`
- `*.cs`
- Razor files
- controller classes
- minimal API definitions
- hosted services
- middleware
- authorization policies
- dependency injection registration
- Entity Framework / NHibernate repositories
- serializers
- background jobs
- message consumers

## Reconnaissance focus

During reconnaissance, identify:

- project type,
- target framework,
- package dependencies,
- web entrypoints,
- API controllers,
- minimal APIs,
- Razor pages,
- authentication configuration,
- authorization policies,
- middleware order,
- dependency injection graph,
- database access layer,
- ORM usage,
- file handling,
- serialization/deserialization,
- background services,
- message handlers,
- external HTTP clients,
- cryptographic operations,
- certificate handling,
- signing operations,
- configuration and secrets.

## Common build and run commands

Useful commands:

    dotnet --info
    dotnet restore
    dotnet build
    dotnet test
    dotnet run --project path/to/project.csproj

If the sandbox image does not include the .NET SDK, document that the sandbox must be extended.

## High-risk vulnerability classes

Prioritize:

- missing authorization checks,
- broken object-level authorization,
- tenant isolation flaws,
- authentication misconfiguration,
- JWT/OIDC/SAML validation mistakes,
- insecure cookie/session configuration,
- CSRF in cookie-authenticated apps,
- SQL injection through raw SQL or string concatenation,
- unsafe dynamic LINQ or expression construction,
- path traversal,
- unsafe file upload/download,
- SSRF through `HttpClient`,
- unsafe deserialization,
- XML external entity processing,
- template injection,
- command injection,
- secrets exposure,
- weak crypto,
- certificate validation bypass,
- insecure signature validation,
- mass assignment / overposting,
- model binding abuse,
- insecure CORS,
- missing antiforgery protection,
- background job trust-boundary issues.

## ASP.NET Core review

Look for:

- `Program.cs`
- `Startup.cs`
- `MapGet`, `MapPost`, `MapPut`, `MapDelete`
- `MapControllers`
- `UseAuthentication`
- `UseAuthorization`
- `AddAuthentication`
- `AddAuthorization`
- `[Authorize]`
- `[AllowAnonymous]`
- policy definitions
- endpoint filters
- middleware ordering
- route groups
- minimal API handlers.

Important middleware order:

    UseRouting
    UseAuthentication
    UseAuthorization
    MapControllers / Map endpoints

Incorrect ordering may cause security controls not to apply.

## Authorization review

Check:

- controller-level `[Authorize]`,
- action-level `[Authorize]`,
- `[AllowAnonymous]`,
- policy names,
- role checks,
- claims checks,
- resource-based authorization,
- tenant checks,
- ownership checks,
- repository-level filters,
- service-layer checks,
- admin-only endpoints,
- background job authorization assumptions.

Good finding example:

    `DocumentsController.Download(id)` requires authentication but calls
    `documentRepository.GetById(id)` and returns the file without verifying that
    the current user owns the document or belongs to the same tenant.

Bad finding example:

    This controller might have authorization issues.

## Authentication review

Check:

- cookie auth configuration,
- JWT bearer configuration,
- OIDC/SAML configuration,
- issuer validation,
- audience validation,
- signing key validation,
- token lifetime validation,
- clock skew,
- claim mapping,
- external identity trust,
- logout behavior,
- password reset flow,
- MFA assumptions.

JWT/OIDC red flags:

- disabled issuer validation,
- disabled audience validation,
- disabled lifetime validation,
- trusting client-supplied claims,
- custom token parsing,
- accepting unsigned tokens,
- weak signing keys,
- missing algorithm restrictions.

## Entity Framework and SQL review

Check for raw SQL:

- `FromSqlRaw`
- `ExecuteSqlRaw`
- `SqlQueryRaw`
- string interpolation passed to raw SQL
- concatenated SQL strings
- dynamic `ORDER BY`
- dynamic table or column names
- stored procedure calls with concatenated parameters.

Safer APIs:

- `FromSqlInterpolated`
- parameterized queries
- LINQ with controlled expressions.

Do not report SQL injection merely because EF is used.

Show exact unsafe construction.

## NHibernate review

Check:

- `CreateSQLQuery`
- `CreateQuery`
- HQL string concatenation,
- dynamic order clauses,
- raw SQL fragments,
- criteria built from user-controlled property names,
- filters for tenant isolation,
- session lifetime assumptions,
- lazy loading across authorization boundaries.

Look for user-controlled input reaching query strings, property names, aliases, or raw SQL snippets.

## Model binding and overposting

Check public DTOs and entity binding.

Risky patterns:

- binding directly to entity models,
- accepting role/admin fields from request body,
- mass assignment of sensitive fields,
- patch/update DTOs that allow unintended properties,
- reflection-based patching,
- generic update endpoints.

Look for fields like:

- `IsAdmin`
- `Role`
- `TenantId`
- `UserId`
- `OwnerId`
- `Status`
- `Permissions`
- `Price`
- `Approved`
- `Verified`

## File handling

Check:

- `IFormFile`,
- file upload paths,
- download endpoints,
- path joins,
- `Path.Combine`,
- `Path.GetFullPath`,
- user-controlled filenames,
- extension checks,
- content type checks,
- public static file serving,
- authorization before download,
- archive extraction.

Path traversal red flags:

- user-controlled path passed to `File.Open`,
- user-controlled path passed to `PhysicalFile`,
- insufficient canonicalization,
- checking prefix before normalization,
- using original upload filename directly.

## SSRF and HTTP clients

Check uses of:

- `HttpClient`
- `IHttpClientFactory`
- `WebClient`
- `HttpWebRequest`
- external callback URLs,
- webhook registration,
- import URLs,
- metadata fetching,
- preview generation.

Look for user-controlled URLs or hosts.

Consider redirects, DNS rebinding, internal IPs, localhost, IPv6, and cloud metadata endpoints.

## XML and serialization

Check:

- `XmlDocument`
- `XmlReader`
- `XDocument`
- `DataContractSerializer`
- `NetDataContractSerializer`
- `BinaryFormatter`
- `LosFormatter`
- `SoapFormatter`
- `JavaScriptSerializer`
- Newtonsoft.Json TypeNameHandling,
- System.Text.Json polymorphism,
- YAML deserialization packages.

Red flags:

- DTD enabled,
- external entity resolution,
- insecure type name handling,
- deserializing untrusted data into arbitrary types,
- binary formatters.

## Crypto and certificate handling

Check:

- custom crypto,
- weak algorithms,
- ECB mode,
- static IVs,
- predictable randomness,
- incorrect signature verification,
- comparing signatures with normal equality,
- ignoring certificate chain errors,
- accepting all server certificates,
- custom `ServerCertificateCustomValidationCallback`,
- `DangerousAcceptAnyServerCertificateValidator`,
- private key handling,
- signing operations reachable by lower-trust users.

## Secrets and configuration

Check:

- `appsettings.json`,
- environment variables,
- user secrets references,
- connection strings,
- API keys,
- certificates,
- private keys,
- hardcoded passwords,
- logging of secrets,
- debug endpoints.

Do not include real secrets in reports. Mask values.

## Background services and queues

Check:

- `IHostedService`,
- `BackgroundService`,
- message consumers,
- queue handlers,
- scheduled jobs,
- retry handlers,
- webhook processors.

Look for trust boundaries where external messages trigger privileged internal actions.

## Validation methods

Useful validation methods for .NET targets include:

- `dotnet test`,
- integration tests with test server,
- HTTP requests against local app,
- crafted JSON bodies,
- two-user / two-tenant scenarios,
- local database fixtures,
- log inspection,
- static proof for missing authorization,
- unit tests around service-layer checks.

## Evidence to capture

For confirmed .NET findings, capture:

- request or test input,
- response or test output,
- relevant logs,
- relevant database state,
- affected controller/service/repository code,
- authentication/authorization context,
- expected safe behavior,
- observed vulnerable behavior.

## Counter-analysis checklist

Before keeping a .NET finding open, check:

- Is `[Authorize]` applied globally, at controller level, route group level, or action level?
- Is there an authorization policy?
- Is ownership checked in service or repository layer?
- Is tenant filtering applied globally?
- Does EF/NHibernate parameterize the query?
- Is model validation applied?
- Does middleware enforce the missing control?
- Is the path reachable in production?
- Is the code test-only or sample-only?
- Is the finding duplicated elsewhere?

## Reporting guidance

Be precise.

Mention:

- endpoint, controller, handler, service, or repository,
- affected user/tenant/role,
- attacker-controlled input,
- missing or insufficient control,
- impact,
- validation method,
- evidence path.

Avoid broad claims such as:

    Authorization is broken in the API.

Prefer:

    `GET /api/documents/{id}` reaches `DocumentRepository.GetById(id)` and
    returns the document without checking that the authenticated user belongs to
    the owning tenant.
