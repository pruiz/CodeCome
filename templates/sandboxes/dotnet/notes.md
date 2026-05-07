# Notes for the .NET sandbox baseline

## When to use

- C#, F#, or VB.NET targets.
- Any project with `*.sln`, `*.csproj`, `*.fsproj`, or `*.vbproj`.

## When NOT to use

- Target requires Windows-only frameworks (.NET Framework 4.x).
  Use a Windows-based sandbox or static-only review.
- Target requires SQL Server / Postgres / Redis — combine with
  `multi-service-compose`.
- Target relies on Identity provider auth in production — do not
  bring real secrets into the sandbox.
