# RabbitMQ Security Skill

Use this skill when the target is RabbitMQ or a RabbitMQ-adjacent repository with broker core code, plugins, management API code, protocol adapters, CLI tools, peer discovery modules, or stream/quorum queue internals.

This skill refines the generic Erlang / OTP workflow with RabbitMQ-specific attack surfaces, trust boundaries, and validation advice.

## Primary target areas

Focus first on:

- `deps/rabbit`
- `deps/rabbit_common`
- `deps/rabbitmq_management`
- `deps/rabbitmq_management_agent`
- `deps/rabbitmq_web_dispatch`
- auth backend plugins
- peer discovery plugins
- stream, MQTT, STOMP, and WebSocket protocol implementations
- CLI tools under `deps/rabbitmq_cli`

## RabbitMQ attack surfaces

Map these explicitly during reconnaissance:

- AMQP 0-9-1 listeners
- AMQP 1.0 listeners
- MQTT listeners
- STOMP listeners
- WebSocket protocol bridges
- HTTP management API
- management UI assets and backend endpoints
- CLI commands and control-plane RPCs
- definitions import/export
- configuration files and env-driven startup
- cluster join and peer discovery
- plugin enable/disable flows
- metadata store transitions such as Mnesia and Khepri

## High-value trust boundaries

Pay attention to:

- unauthenticated network client to protocol parser
- authenticated user to vhost-scoped resources
- regular operator to administrator-only actions
- HTTP API caller to internal broker state
- plugin or auth backend response to core authorization logic
- cluster peer discovery input to node membership decisions
- imported definitions or metadata to privileged runtime configuration
- local CLI caller to remote node RPC

## High-risk vulnerability classes

Prioritize:

- authorization bypass across vhosts, exchanges, queues, streams, or policies
- management API authz inconsistencies
- parser bugs in protocol frame handling
- unsafe broker import/export or schema transitions
- trust mistakes in auth backends, peer discovery, or TLS identity handling
- denial of service through unbounded message, queue, channel, stream, or process growth
- cross-node trust failures in clustering and distribution
- management UI to backend privilege mismatches
- SSRF-like behavior in outbound auth or peer discovery integrations
- command or file handling issues in CLI and runtime scripts

## RabbitMQ review checklist

Look for:

- permission checks around configure, write, and read operations
- vhost scoping and ownership checks
- policy and parameter application paths
- management endpoints that expose node-local or cluster-global state
- plugin modules that bypass or duplicate core checks
- definitions import/export code paths
- peer discovery and cluster formation modules
- stream and quorum queue metadata transitions
- certificate and OAuth backend validation code
- CLI commands that wrap RPC or privileged node actions

## Validation guidance

Useful documented workflows include:

    gmake
    gmake ENABLED_PLUGINS="rabbitmq_management rabbitmq_stream rabbitmq_stream_management" run-broker
    ./sbin/rabbitmq-diagnostics status
    gmake ct-rabbit_mgmt_http
    gmake ct-unit_log_management
    RABBITMQ_METADATA_STORE=khepri gmake ct-quorum_queue

Prefer:

- a targeted Common Test suite for the affected component
- a local broker start plus `rabbitmq-diagnostics` or HTTP API smoke checks
- validation with and without optional plugins when the bug depends on them
- both `mnesia` and `khepri` paths when the bug touches metadata storage logic

## Good finding examples

Good:

    User-controlled management API request reaches a queue inspection path in
    `rabbit_mgmt_wm_queue.erl` that returns queue details from another vhost
    because the handler validates authentication but does not enforce the
    caller's vhost authorization before querying broker state.

Good:

    Imported definitions field `...` reaches a privileged policy application
    path in `...` without validation that the importing user is allowed to set
    runtime parameters for the target vhost.

Bad:

    RabbitMQ probably has auth bugs because it exposes many protocols.

## Counter-analysis reminders

Before keeping a finding, check whether:

- access is already gated by vhost permissions
- the path is only reachable by administrators
- the code runs only on trusted inter-node channels
- the plugin is optional and disabled by default
- the documented runtime requires stronger trust than initially assumed
- the management endpoint normalizes or filters state before returning it

Do not treat large attack surface alone as evidence.
