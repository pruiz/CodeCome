# Notes for the Go sandbox baseline

## When to use

- Go modules with `go.mod` and `go.sum`.
- Go-only services without database dependencies, or those whose DBs
  can be emulated via in-process libraries (sqlite, etc.).

## When NOT to use

- Target requires Postgres / Redis / Kafka — combine with
  `multi-service-compose`.
- Target requires private Go modules behind auth — provide a
  prepared `~/.netrc` or use a vendored layout.
- Target uses GOEXPERIMENT or a custom toolchain — pin
  `__GO_VERSION__` and consider using `tip` images.
