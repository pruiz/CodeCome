# .NET sandbox example

Baseline image for .NET (C# / F# / VB) projects.

## What's included

- `mcr.microsoft.com/dotnet/sdk:__DOTNET_SDK_TAG__` SDK image
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name used in messages and script comments. |
| `__DOTNET_SDK_TAG__` | SDK tag (e.g. `8.0`, `9.0`). Match the target's `global.json`. |
| `__APP_PORT__` | Exposed Kestrel port. |

## Build heuristics

`scripts/build.sh` chooses a `.sln` if present, otherwise
falls back to scanning `.csproj`. `dotnet restore` runs before
`dotnet build --no-restore`.

## Notes

- For ASP.NET Core projects with HTTPS dev certs, set
  `ASPNETCORE_URLS=http://+:__APP_PORT__` and avoid the dev-cert
  bootstrap.
- For projects using NuGet feeds with auth, mount the feed config
  rather than baking secrets into the image.
