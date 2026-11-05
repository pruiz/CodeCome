<!--
Adapted from Cloudflare's security-audit skill, file `DESKTOP-MOBILE-AND-LOCAL-IPC.md`:
https://github.com/cloudflare/security-audit-skill/tree/c1c8a8c1471069fb0e188eeaff69b8e8db6564a8/skills/security-audit
Copyright (c) 2025-2026 Cloudflare, Inc. Licensed under the MIT License; see
`third_party/cloudflare-security-audit-skill/LICENSE`.
Changes: cross-file links rewritten to CodeCome skill paths, Cloudflare
sub-agent role labels removed, and the CodeCome mapping section below added.
The hunting content itself is unchanged.
-->

# Desktop, Mobile and Local IPC Security Skill

## How this skill maps to CodeCome

This skill is a domain companion for **Phase 2** (hypothesis generation, both
the global audit and file sweeps), **Phase 3** (counter-analysis) and
**Phase 4** (validation). Select it only when Phase 1 reconnaissance found the
trust-sensitive boundary described under *When to use this file*, not merely
because a language or dependency name appears.

Terminology:

- "candidate" = a finding under `itemdb/findings/PENDING/`.
- "confirmed" = `CONFIRMED` (or `EXPLOITED` after Phase 5).
- "`needs_validation`" = `NEEDS_VALIDATION`: a source-grounded lead blocked on a
  fact the repository and the CodeCome sandbox cannot show. Fill
  `needs_validation.blockers` and at least one of `local_check` /
  `owner_check`, and do not present its `severity` as a confirmed rating.
- "rejected" = `REJECTED`.
- "fingerprint" = the `fingerprint` frontmatter field (same root cause, same
  value, in every status and across re-runs).
- "local check" / "bounded local evidence" = validation inside `sandbox/` per
  `.opencode/skills/sandbox-validation/SKILL.md`.

Never send traffic to deployed, shared or production systems. Where the text
below says to stop at the minimum observed effect, that governs Phases 2–4;
impact escalation belongs to Phase 5 under
`.opencode/skills/exploit-development/SKILL.md`, still inside the sandbox.

---

#### When to use this file

Reach for this file when the target is a desktop or mobile app, privileged helper, updater, local daemon, webview host, deep-link handler, browser native-messaging host, or local IPC client/server. Relevant untrusted actors may be a downloaded document, remote web content, another local app, another OS user, a sandboxed process, or a lower-privilege account. State that starting capability instead of treating all local users as equivalent.

Use `.opencode/skills/client-side-security/SKILL.md` for browser-side webview behavior, `.opencode/skills/memory-safety-binary/SKILL.md` for native memory and loader safety, and `.opencode/skills/supply-chain-security/SKILL.md` for update authenticity.

## Core discipline (include in every agent prompt for this domain)

```
- Establish the realistic local or remote-content attacker: another app, another OS user, a sandboxed child, an untrusted document, or a remote origin. Self-harm within the same account and authority is not a boundary violation.
- Paths, process names, bundle/package IDs, and claimed sender fields are not peer authentication. Use OS peer credentials, code identity, capability handles, or protected channel state.
- The native bridge or helper must authorize each operation and final resource after parsing. A trusted UI or broker does not make attacker-influenceable arguments trusted.
- OS sandbox, signing, entitlements, permissions, keychain ACLs, exported-component policy, and prompt behavior are real controls when pinned and visible.
- Use `confirmed` for source evidence plus bounded local/emulator tests. Use `needs_validation` when signing, manifest merge, OS version, device policy, installer ACL, or packaging is required but not observable.
```

## Deep-link, callback, and navigation attack classes

**Custom-scheme and deep-link ambiguity**
Another app or page can invoke a route that mutates state, imports data, completes authentication, or selects an account without a current-session and one-time callback binding. Review URI normalization, duplicate query fields, scheme/host/path matching, exported activity/handler policy, and stale/replayed links.

**App and account handoff confusion**
OAuth, SSO, magic-link, invite, device pairing, passwordless, or payment callbacks return to the wrong installed app, profile, tenant, or pending transaction. Bind state to the initiating app identity, current session, account, provider, operation, and expiry.

**File-open and intent authority confusion**
An associated file, share intent, drag/drop item, pasteboard/clipboard record, notification action, or open-file event triggers a privileged operation without confirming content type, sender trust where applicable, current user intent, and final target.

## Webview and native-bridge attack classes

**Navigation-origin to bridge confusion**
Remote or attacker-controlled frames can reach a JavaScript/native bridge intended only for packaged content. Validate origin at call time and after every navigation, redirect, subframe creation, popup, and error/fallback page. URL-prefix checks and initial-load checks are insufficient.

**Over-broad native bridge capabilities**
Web content can select arbitrary files, commands, IPC methods, credentials, or system actions through a generic bridge. Check method allowlists, normalized arguments, user/tenant authority, gesture/confirmation requirements, and return-value disclosure.

**Webview file and universal access**
Remote content can read app-local files, privileged custom schemes, or internal origins because file access, universal access, mixed content, debug interfaces, or custom protocol handlers join origins unexpectedly. Missing a restrictive setting without reachable protected content is hardening.

## Local IPC and exported-component attack classes

**IPC peer-authentication gaps**
Unix sockets, named pipes, XPC, Binder, D-Bus, native messaging, RPC, shared memory, or loopback listeners accept a lower-trust peer without checking OS credentials, code identity, sandbox token, or channel ownership. Require a meaningful method or disclosure behind the channel.

**Claimed principal versus channel identity**
The authenticated process/channel belongs to one app or user, but request fields select another user, tenant, profile, or capability. Bind each method and resource to the peer credential rather than a caller-declared identifier.

**Exported service, activity, receiver, or provider overreach**
A mobile component or local automation endpoint is externally invokable and performs an operation intended for the app itself. Review final merged manifests, intent filters, permission/signature level, path grants, and alternate aliases. Manifest status unknown after packaging requires `needs_validation`.

**IPC lifecycle and correlation confusion**
Predictable request IDs, reused handles, stale channels, inherited descriptors, world-writable socket paths, or restart behavior lets one peer answer, cancel, or reuse another peer's operation. Review creation permissions and cleanup of socket files, locks, ports, and shared mappings.

## Privileged-helper and local-file attack classes

**Privileged helper as confused deputy**
A low-privilege caller can select a privileged command, file, service, user, or system setting without per-operation authorization. Review sudo/polkit/UAC/XPC helper rules and ensure the helper independently validates normalized arguments.

**Install, update, and repair path trust**
A privileged installer/helper reads manifests, scripts, packages, symlinks, working directories, or repair state writable by a lower-trust actor after authorization. Bind authorization to immutable content and safe destination paths.

**Local file ownership and TOCTOU**
The app checks a file/path then follows replacement, symlink, mount, or case/normalization changes during a privileged read/write. Use descriptor-relative operations and verify final ownership. Focus `.opencode/skills/memory-safety-binary/SKILL.md` on parsing after the file is opened.

**Credential-store and local-secret boundary mismatch**
A keychain/keystore item, token file, backup, log, clipboard, notification preview, or local config is readable by another app/profile/user with less authority. Plaintext readable only by the same intended OS account is not automatically a vulnerability; state the lower-trust reader and credential power.

## Application-state and device-lifecycle attack classes

**Account switch, logout, and device restore leakage**
Cached data, background tasks, widgets, notifications, local databases, webview storage, or biometric approvals survive logout/account change and appear under a later account. Review backup/restore and multi-profile behavior.

**Pending-action and user-presence confusion**
Notification, widget, shortcut, share sheet, biometric prompt, or deferred operation authorizes a different action than displayed, executes after expiry, or uses another profile's pending state. Bind confirmation to normalized action, resource, account, and current foreground state.

## Universal moves (apply across the above)

- Enumerate every process, app component, local endpoint, URI scheme, file association, webview origin, and helper. Record OS identity, runtime privilege, caller, and callable operation.
- Read final packaging inputs: merged manifest, entitlements, installer rules, native-messaging registration, protocol handlers, and ACL creation. Source declarations can be overwritten downstream.
- Validate with dummy profiles and non-sensitive local fixtures on an isolated machine/emulator. Do not interact with other users' apps, credentials, or production services.

## Validation rules (apply before reporting ANY finding here)

1. Name the attacker starting capability, OS/app principal crossed, entry channel, accepted argument or state, and unauthorized operation or disclosure.
2. Confirm OS sandbox, peer credential, signing, entitlement, permission, user-consent, and installer controls that apply. Unknown packaging/runtime facts require `needs_validation`.
3. For webview bridges, cite both navigation/origin control and privileged native sink. For IPC, cite peer authentication and per-resource authorization. For helpers, verify final normalized destination.
4. Keep local tests bounded and use dummy content/accounts. Stop after proving the boundary result; do not extend proof into persistence or broader system modification.
5. Return `confirmed` only with a complete source and local evidence chain. Return `needs_validation` with the exact OS, manifest, signing, ACL, or device-lifecycle fact required.
