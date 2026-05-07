#!/usr/bin/env bash
# CodeCome Ruby test hook. Marker: __TARGET_NAME__.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace/src

echo "CodeCome Ruby test hook"

if [ -f Rakefile ]; then
  echo "Detected Rakefile. Running: bundle exec rake test"
  bundle exec rake test || bundle exec rake spec || true
elif command -v rspec >/dev/null 2>&1; then
  echo "Running: bundle exec rspec"
  bundle exec rspec
else
  echo "No Rakefile or RSpec binary detected for target __TARGET_NAME__."
fi
'
