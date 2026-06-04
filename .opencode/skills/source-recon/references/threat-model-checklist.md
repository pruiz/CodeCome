<!--
Some guidance in this reference was informed by OpenAI's curated
security-threat-model skill and adapted for CodeCome's phased workflow.
-->

# Threat Model Checklist for Source Recon

Use this reference during CodeCome Phase 1b.

The goal is not to produce a standalone threat-modeling report. The goal is to
produce a durable operational model that improves later hypothesis generation,
counter-analysis, validation, exploitation, and reporting.

## Grounding rules

- Do not invent components, data stores, endpoints, flows, controls, or deployment properties.
- Anchor important architectural and security claims to repository evidence.
- Mark missing context as assumptions.
- Separate runtime behavior from CI/build/dev/test behavior.
- Separate attacker-controlled, operator-controlled, developer-controlled, and trusted internal inputs.

## Required model elements

### System model

Identify primary runtime components, relevant data stores, external integrations,
entrypoints, build/release artifacts that materially affect security, deployment
assumptions, and out-of-scope components.

### Trust boundaries

For each important boundary, document source actor/component, destination
component, data/control crossing, channel/protocol, authentication,
authorization, encryption or transport protection, validation/normalization,
schema enforcement, rate/resource controls, evidence anchors, and uncertainty.

### Assets and security objectives

For each relevant asset, document asset name, where it appears, why it matters,
security objective (confidentiality, integrity, availability), related attack
surfaces or trust boundaries, and evidence anchors.

### Attacker model

Document realistic attacker capabilities and explicit non-capabilities.
Non-capabilities are required to avoid inflated severity.

### Existing controls

Document observed controls with evidence: what the control protects, where it is
enforced, what assumptions it relies on, and known uncertainty or gaps.

### Abuse-path themes

Record review leads, not findings. Each theme should include attacker goal,
entrypoint, boundary crossed, impacted asset, existing controls, assumptions,
relevant files, and suggested Phase 2 focus.

### Risk calibration

Use qualitative risk only to prioritize review focus. Consider exposure,
attacker control, affected asset, privilege boundary, tenant boundary, exploit
preconditions, existing controls, and validation feasibility.
