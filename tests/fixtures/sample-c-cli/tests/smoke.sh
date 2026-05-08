#!/usr/bin/env bash
set -euo pipefail

./bin/sample-c-cli --help >/dev/null
./bin/sample-c-cli greet tester >/dev/null
./bin/sample-c-cli echo hello >/dev/null
