# Erlang / OTP Security Skill

Use this skill when the target contains Erlang, OTP, Elixir-on-BEAM, `rebar.config`, `erlang.mk`, `mix.exs`, `.erl`, `.hrl`, `.app.src`, Common Test suites, Dialyzer, Xref, Eqwalizer, or ELP configuration.

This skill supports reconnaissance, vulnerability hypothesis generation, counter-analysis, validation, and reporting for BEAM targets.

## Scope

Relevant files include:

- `.erl`
- `.hrl`
- `.app.src`
- `rebar.config`
- `rebar.lock`
- `erlang.mk`
- `Makefile`
- `mix.exs`
- `mix.lock`
- `.elp.toml`
- `sys.config`
- `advanced.config`
- `vm.args`
- Common Test suites such as `*_SUITE.erl`
- EUnit modules
- release and runtime scripts
- protocol handlers
- plugin modules

## Reconnaissance focus

During reconnaissance, identify:

- OTP applications and supervision trees
- entry modules and listeners
- protocol parsers and frame decoders
- external interfaces such as TCP, TLS, HTTP, WebSocket, CLI, RPC, or distribution
- authn and authz modules
- config translation and runtime config loading
- filesystem access
- command execution or OS interaction
- dynamic module loading or plugin enablement
- clustering and node trust assumptions
- serialization or term parsing boundaries
- test model: Common Test, EUnit, PropEr, QuickCheck
- static analysis support: Dialyzer, Xref, Eqwalizer, ELP

## Build and analysis signals

Common commands include:

    gmake
    make
    rebar3 compile
    rebar3 eunit
    rebar3 ct
    mix compile
    mix test
    gmake dialyze
    gmake xref

When the repository documents specific `ct-*` targets, prefer those over broad test runs.

## High-risk vulnerability classes

Prioritize:

- missing or inconsistent authorization checks
- trust-boundary mistakes between protocol sessions and internal state
- unsafe config-to-runtime transitions
- parser bugs in binary, term, JSON, XML, or protocol frame handling
- denial of service through atom exhaustion, process explosion, queue growth, or resource amplification
- unsafe filesystem access and path traversal
- command execution through helper scripts or OS adapters
- TLS and certificate validation mistakes
- unsafe distributed-node trust assumptions
- cross-tenant or cross-vhost isolation flaws
- unsafe import/export, restore, or replication flows
- plugin/module loading mistakes

## OTP review checklist

Look for:

- `gen_server`, `gen_statem`, `supervisor`, `application` behaviors
- public APIs that accept binaries, maps, or terms from external callers
- `binary_to_term`, `term_to_binary`, `file:consult`, `erl_scan`, `erl_parse`
- direct `rpc`, `erpc`, `net_kernel`, `slave`, or distribution helpers
- `open_port`, `os:cmd`, shell wrappers, or external process adapters
- `file:read_file`, `file:write_file`, path joins, temp file helpers
- ACL and policy checks split across multiple modules
- listener setup and TLS options
- dynamic atoms from untrusted input
- ETS, Mnesia, or replicated state used as authorization truth

## Erlang-specific review notes

### Atom exhaustion

Do not report atom exhaustion just because atoms exist.

Look for attacker-influenced calls such as:

- `list_to_atom`
- `binary_to_atom`
- `erlang:binary_to_existing_atom` with weak fallback logic
- dynamic module, function, or queue names normalized into atoms

Explain reachability and whether repeated requests can create unbounded atoms.

### Unsafe term handling

Review any use of external term formats carefully.

Important sinks include:

- `binary_to_term/1`
- `binary_to_term/2`
- config imports that deserialize Erlang terms
- message stores or replication payloads that trust node-local provenance

If `safe` options or trusted-only channels exist, document them in counter-analysis.

### Distribution and clustering

Check:

- node naming and cookie assumptions
- whether a lower-trust actor can influence cluster membership
- whether control-plane APIs indirectly trigger privileged RPCs
- import/export or sync flows between nodes
- whether mixed-version logic weakens validation

### Resource exhaustion

Look for attacker-controlled values driving:

- process creation
- mailbox growth
- queue or stream retention
- large binaries held off-heap or in ETS
- repeated retries without backoff
- expensive parsing or fan-out loops

## Validation guidance

Prefer the narrowest reproducible proof:

- static proof for authz gaps or unsafe sinks
- targeted Common Test suite when one already exists
- targeted `rebar3 eunit` or `mix test`
- local listener smoke test for network-facing components
- runtime reproduction inside `sandbox/`
- `dialyzer` or `xref` as supporting evidence, not sole proof of exploitation

If the target uses GNU Make as the primary build path, follow the repository's documented `gmake` workflows instead of forcing `rebar3`.
