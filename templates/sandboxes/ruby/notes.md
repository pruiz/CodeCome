# Notes for the Ruby sandbox baseline

## When to use

- Ruby projects with `Gemfile`.
- Rails, Sinatra, Sidekiq workers.
- Library gems with a `*.gemspec`.

## When NOT to use

- Target needs Postgres / Redis — combine with
  `multi-service-compose`.
- Target needs Webpacker, jsbundling-rails, or cssbundling-rails
  with Node.js — use `multi-service-compose`.
- Target depends on private gem servers — provide credentials via
  bundler config rather than baking them into the image.
