# Ruby sandbox example

Baseline image for Ruby projects, including Rails and Sinatra.

## What's included

- `ruby:__RUBY_VERSION__-bookworm` base image
- Recent `bundler` + `rake`
- `build-essential`, `libssl-dev`, `libyaml-dev` for native gems
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__RUBY_VERSION__` | Ruby tag (e.g. `3.3`, `3.2`). |
| `__APP_PORT__` | Exposed port (default 3000). |

## Build heuristics

Requires a `Gemfile`. Runs `bundle install`. Tests run via Rake or
RSpec when available.

## When to extend

- For Rails projects with Postgres / Redis: combine with
  `multi-service-compose`.
- For projects requiring `nodejs` for Webpacker / esbuild: extend the
  Dockerfile with a Node.js install or use `multi-service-compose`.
