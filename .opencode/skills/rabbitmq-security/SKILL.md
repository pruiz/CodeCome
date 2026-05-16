# RabbitMQ Security Skill

Use this skill when the target is an application that uses RabbitMQ (or other AMQP 0-9-1 brokers) for messaging, queuing, background jobs, or pub/sub. This includes clients using libraries like Pika, Celery, Spring AMQP, amqplib, MassTransit, Broadway, or similar.

This skill guides you to identify and validate client-side and architecture-level vulnerabilities related to how the application uses RabbitMQ.

*Note: If you are auditing the source code of the RabbitMQ broker itself, use the generic `erlang-security` skill instead.*

## Scope

Relevant files include:

- Files interacting with RabbitMQ (publishers, consumers, configuration)
- Worker scripts or background job processors
- Files declaring connections, channels, queues, exchanges, and bindings
- Message payload definitions and parsers

## Reconnaissance focus

During reconnaissance, identify:

- How the application connects to RabbitMQ (URI, authentication, TLS)
- Which exchanges, queues, and routing keys are used
- What type of data is passed in messages (JSON, XML, Pickle, plain text)
- Where and how messages are consumed and processed
- Whether the application acknowledges (ack) or rejects (nack/reject) messages explicitly
- Whether prefetch counts (QoS) are configured
- Trust boundaries: Does a message cross from an untrusted source to a trusted processor?

## High-risk vulnerability classes

Prioritize:

- **Unsafe Deserialization:** Parsing queue payloads (e.g., Pickle, YAML, unchecked XML/JSON) leading to RCE.
- **Message Spoofing / Lack of Integrity:** The consumer blindly trusts the contents or origin of a message without verifying its signature or ensuring the exchange topology enforces origin.
- **Routing Key / Topic Injection:** Attackers controlling routing keys to misroute messages, bypass queues, or intercept sensitive data.
- **Consumer Denial of Service (DoS):**
  - **Poison-Message Requeue Loops:** A malformed message causes an unhandled exception before an `ack`, leading the consumer to `nack` with `requeue=True` endlessly.
  - **Missing Prefetch Limits (QoS):** Consumers without `prefetch_count` can be overwhelmed by too many messages, leading to OOM (Out Of Memory) crashes.
- **Insecure Transport:** Hardcoded credentials, using `amqp://` instead of `amqps://` over untrusted networks, or disabling TLS certificate validation.

## Review checklist

Look for:

- `pickle.loads()`, `yaml.load()`, or dangerous parsers applied directly to message bodies.
- Code dynamically building routing keys or exchange names from user input without validation.
- Connection strings in plaintext config files or version control.
- `basic.consume` or `basic_consume` handlers that lack broad exception catching around message processing.
- `basic.reject` or `basic.nack` with `requeue=true` in error-handling blocks.
- Explicitly missing or disabled `basic.qos(prefetch_count=...)`.
- Consumers performing privileged actions (e.g., executing commands, writing files) based on message fields without verifying the message sender.

## Validation guidance

- **Deserialization:** Look for ways an attacker can push a message onto the queue (e.g., via a web endpoint that publishes messages). Prove that the parser is vulnerable.
- **Poison Message Loop:** Inject a syntactically invalid message (e.g., bad JSON). Show that the consumer crashes or constantly requeues it without dead-lettering or dropping it.
- **Routing Injection:** Demonstrate that manipulating user input changes the routing key, allowing an attacker to bypass authorization, pollute another queue, or trigger unintended actions.
- **Spoofing:** If an attacker has access to a low-privilege exchange or queue, show that they can craft a message that a high-privilege consumer will process as trusted.

## Good finding examples

Good:

    The `process_report` consumer uses `pickle.loads(message.body)` directly. 
    An attacker can submit a crafted report via the public `POST /api/reports` 
    endpoint, which publishes the user input to the `reports` queue. When the 
    background worker picks it up, it leads to Remote Code Execution.

Good:

    The `image_resize` worker catches `ImageFormatError` but calls 
    `channel.basic_reject(delivery_tag, requeue=True)`. An attacker can 
    upload a malformed image, causing the worker to repeatedly fail and 
    requeue the message, pegging the CPU at 100% and preventing other 
    images from being processed.

Bad:

    RabbitMQ credentials are used in the application.

## Counter-analysis reminders

Before keeping a finding, check whether:

- The message queue is purely internal and cannot be influenced by any external input path.
- The consumer framework (e.g., Celery) already handles serialization safely (e.g., using JSON by default) or drops bad messages.
- The routing topology (exchange types, bindings) prevents messages from crossing tenant or privilege boundaries regardless of routing key injection.
