# Sample C CLI

`sample-c-cli` is a tiny command-line target used for CodeCome workflow testing.

It is intentionally small so the workflow can be exercised quickly.

## Build

    make

## Run

    ./bin/sample-c-cli --help
    ./bin/sample-c-cli greet Alice
    ./bin/sample-c-cli echo hello

## Layout

- `src/main.c` -- CLI entrypoint and argument parsing
- `src/greet.c` -- greeting functionality
- `src/util.c` -- helper functions
- `include/` -- public headers
- `tests/smoke.sh` -- tiny smoke test
