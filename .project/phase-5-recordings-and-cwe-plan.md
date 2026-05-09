# Phase 5/6 enhancements: exploit recordings, CWE classification, richer finding/report content

## Goal

Extend Phase 5 to require reproducible exploit demonstration recordings, CWE
classification, and richer finding sections (root cause, data flow,
preconditions, recording reference, remediation diff). Update Phase 6 to
surface this new content (recording + CWE columns, vulnerable-code excerpts,
root-cause summaries). Add tooling availability check for the recording
stack. Keep the recording methodology in a generic skill, with paths and
integration pinned in the Phase 5 prompt.

## Confirmed decisions

- Recording layout:
  `itemdb/evidence/<finding-id>/exploits/recordings/{exploit.cast,exploit.gif,exploit.mp4?,reproduce.sh,env.txt,README.md}`.
- Recording is **mandatory effort** when a working PoC exists. Failure to
  produce a recording does **not** block `EXPLOITED` status; the agent must
  document why under a Limitations section in `exploits/README.md` and the
  finding's `# Recording` section.
- CWE: required for `EXPLOITED`, recommended for `CONFIRMED`.
- Data flow section is conditional (only when input-driven); use
  `Not applicable.` otherwise.
- Vulnerable-code excerpts in Phase 6: cap at ~15 lines, include
  `file:line` header.
- `tmp/kk.md` content is captured in this plan and in the new skill, then
  the file is deletable.

## Files to create

### 1. `.opencode/skills/exploit-recording/SKILL.md`

Generic, target/path-agnostic recording methodology.

Content outline:

- Purpose: recordings are first-class evidence; deterministic; replayable.
- Tool selection ladder (lightest first):
  1. `asciinema` + `agg` — preferred for any TTY-driven exploit.
  2. `asciinema` + containerized `agg`
     (`docker run --rm -v "$PWD:/data" ghcr.io/asciinema/agg`).
  3. `ffmpeg` + `x11grab` — GUI/browser exploits only.
  4. `ffmpeg` + `x11grab` over `Xvfb` — last-resort headless GUI.
- Recording rules:
  - Driven by `reproduce.sh` (no live typing).
  - `reproduce.sh` is self-contained; prints `EXPLOIT SUCCESSFUL` on
    success; non-zero exit on failure.
  - Target length 15–90 s, hard cap 3 min, idle pauses capped.
  - Must visibly show: target version/commit, trigger command, observable
    impact, success marker.
  - No real credentials, customer data, or production hostnames; redact in
    `reproduce.sh` so the recording stays reproducible.
- `asciinema rec` reference command (with
  `--cols 100 --rows 30 --idle-time-limit 2`).
- `agg` rendering reference command (font, theme, `--fps-cap 12`).
- Optional MP4 path (when GIF > ~3 MB or motion matters).
- ffmpeg/Xvfb fallback reference command (1280x720, 12 fps, ≥18 px effective
  font, target file size <5 MB).
- Required outputs: `exploit.cast`, `exploit.gif`, optional `exploit.mp4`,
  `reproduce.sh`, `env.txt`, `README.md`.
- `env.txt` minimum: kernel, libc, runtime versions, target commit,
  recording tool version.
- Verification: replay cast, check GIF size; re-render with adjusted
  parameters if not.
- **Skip protocol**: never substitute a hand-written transcript for a real
  recording. If tooling is unavailable, document in `exploits/README.md`
  under Limitations with the missing tool list and exact install hint.

## Files to modify

### 2. `prompts/phase-5-exploit.md`

- **Required reading**: add `.opencode/skills/exploit-recording/SKILL.md`.
- New section **`## Exploit demonstration recording`**:
  - Pin path: `itemdb/evidence/<finding-id>/exploits/recordings/`.
  - List required artifacts.
  - Delegate methodology to the skill.
  - State: mandatory effort if PoC works; if not produced, document why in
    `# Limitations` of `exploits/README.md` and in the finding's
    `# Recording` section. Does not block `EXPLOITED`.
- New section **`## CWE classification`**:
  - Identify best-matching CWE id(s) for the demonstrated vulnerability.
  - Populate `cwe: ["CWE-NNN", ...]` in frontmatter.
  - Required for `EXPLOITED`.
- New section **`## Required finding content updates`** (must be filled
  before/at EXPLOITED):
  - `# Root cause analysis` (2–6 sentences).
  - `# Data flow` (when input-driven; ordered
    `source → propagator(s) → sink` with `file:line` per step; else
    `Not applicable.`).
  - `# Inputs and preconditions` (attacker-controlled inputs +
    preconditions).
  - `# Recording` (relative paths to cast/gif/mp4/reproduce.sh/README +
    one-line description, or rationale for absence).
  - `# Remediation idea` (must include corrected-code excerpt or unified
    diff).
- Extend **PoC self-validation checklist** with:
  - `[ ] Recording produced under exploits/recordings/ OR absence
        documented in Limitations and finding # Recording.`
  - `[ ] CWE id(s) assigned in frontmatter.`
  - `[ ] Root cause, data flow (or "Not applicable"), preconditions,
        recording reference, and remediation excerpt/diff are filled in
        the finding.`
- Update **Final response** summary to mention recording artifacts and CWE.

### 3. `.opencode/agents/exploiter.md`

- Add `.opencode/skills/exploit-recording/SKILL.md` to required reading.
- Extend Artifact requirements with `recordings/` artifacts.
- Extend Finding update procedure: frontmatter must include `cwe`; the four
  new sections must be populated.
- Extend completion checklist: recording attempted/documented, CWE assigned,
  new sections filled.

### 4. `.opencode/skills/exploit-development/SKILL.md`

- Cross-reference `exploit-recording/SKILL.md` in **Outputs** and
  **Evidence capture**.
- Update Completion checklist: recording produced or absence documented;
  CWE assigned.

### 5. `.opencode/skills/finding-format/SKILL.md`

- CWE: required for `EXPLOITED`; recommended for `CONFIRMED`.
- Required sections list grows with `# Root cause analysis`, `# Data flow`,
  `# Inputs and preconditions`, `# Recording`. For non-EXPLOITED, `Pending.`
  (or `Not applicable.` for `# Data flow`) is acceptable.
- Tighten `# Remediation idea`: must include code excerpt or unified diff
  for `CONFIRMED`/`EXPLOITED`.

### 6. `templates/finding.md`

- Insert four new sections with `Pending.` placeholders and short guidance
  comments, in this order after `# Demonstrated Impact`:
  - `# Root cause analysis`
  - `# Data flow` (with note that `Not applicable.` is OK for non-input-driven
    bugs)
  - `# Inputs and preconditions`
  - `# Recording`
- Tighten `# Remediation idea` text to require corrected code or diff for
  confirmed/exploited.

### 7. `templates/exploit-readme.md`

- Add `# CWE` field near top.
- Add `# Recording` subsection listing `recordings/` artifacts and a
  one-line "how to play" hint (`asciinema play recordings/exploit.cast`).
- Add `# Limitations` notes block for documenting absent recording when
  applicable (or extend the existing Limitations section).

### 8. `prompts/phase-6-report.md`

- **Reporting rules** updates:
  - "Reference recordings by relative path; never embed binary blobs
    (`.gif`, `.mp4`) inline."
  - "For each CONFIRMED/EXPLOITED finding, include a short vulnerable-code
    excerpt (≤ ~15 lines) read from the finding's `# Affected code` or
    evidence directory; quote with the `file:line` header."
  - "For each CONFIRMED/EXPLOITED finding, include a 1–3 sentence root
    cause analysis summary distilled from the finding's `# Root cause
    analysis`, and reference the relevant Phase 5 artifacts."
- **Finding summary table** schema (Recording last):

  ```
  | ID | Status | Severity | Confidence | CWE | Target area | Title | Evidence | Recording |
  ```

  Recording cell: relative path to `exploits/recordings/README.md` or
  `exploits/recordings/exploit.gif`; `—` if none.
- **Exploited findings section** — add per-finding required items:
  - `CWE`
  - `Vulnerable code excerpt` (fenced block with `file:line` header)
  - `Root cause` (1–3 sentences referencing the artifact)
  - `Recording references` (cast / gif / mp4 / reproduce.sh / recordings
    README, or absence note)
- **Confirmed findings section** — add per-finding required items: `CWE`
  (if known), `Vulnerable code excerpt`, `Root cause`.

### 9. `templates/report.md`

- Update **Findings summary** table header to:

  ```
  | ID | Status | Severity | Confidence | CWE | Target area | Title | Evidence | Recording |
  ```

- Per-finding scaffolding under **Exploited findings**: add `CWE`,
  `Vulnerable code excerpt` placeholder, `Root cause` subsection,
  `Recording` line.
- Per-finding scaffolding under **Confirmed findings**: add `CWE`,
  `Vulnerable code excerpt` placeholder, `Root cause` subsection.

### 10. `.opencode/skills/report-writing/SKILL.md`

- Update **Finding summary table** snippet with the new schema.
- Add **Recording handling** paragraph: reference by relative path, never
  embed binaries, link `recordings/README.md` for play instructions.
- Add **Vulnerable-code excerpts** paragraph: keep short, include
  `file:line` header, no secrets.

### 11. `tools/codecome.py` (the `check` command)

- Detect optional recording stack tools and warn when missing:
  - Required for primary path: `asciinema`, `agg` (or Docker for
    containerized agg).
  - Fallback path: `ffmpeg`, `xvfb-run` / `Xvfb`.
- Output format: warning lines, not failure (so `make check` stays green).
- Include short install hints per OS family. Examples:
  - macOS: `brew install asciinema agg ffmpeg`
  - Debian/Ubuntu: `sudo apt-get install asciinema ffmpeg xvfb`
    (note `agg` is not packaged; suggest
    `cargo install --git https://github.com/asciinema/agg` or use the
    Docker fallback).
  - Generic Docker fallback: `docker pull ghcr.io/asciinema/agg`.
- Wire output behind a section header in `make check` like
  "Optional recording tools".

### 12. Cleanup

- Delete `tmp/kk.md` after the skill content is in place (its substance is
  captured in the new SKILL.md and this plan).

## Out of scope (explicit)

- No changes to Phase 1–4 prompts/agents.
- No changes to the gate-check tool (Phase 5 still proceeds even if
  recording tools are missing — only `make check` warns).
- No automatic recording invocation by `make` targets; the agent drives
  recording inside the sandbox.

## Validation steps after implementation

- `make check` shows the new optional-tools section (warns when tools
  missing, silent when present).
- `make tests` (pytest + frontmatter check) passes; if
  `check-frontmatter.py` validates the `cwe` field strictness, ensure
  existing fixtures comply (likely no change needed since the field
  already exists).
- Manually re-render an existing EXPLOITED finding through
  `make phase-6` and verify the new columns/excerpt/root-cause render
  correctly without binary embedding.
- Confirm `.opencode/skills/exploit-recording/SKILL.md` is reachable via
  `make phase-5 FINDING=…` (prompt now references it in required reading).

## Risks / watch-outs

- Existing EXPLOITED findings (`CC-0001..0007`) lack the new sections and
  recordings. They are not auto-migrated; we document this as a known gap
  and let the user re-run Phase 5 if desired. Phase 6 must tolerate missing
  fields gracefully (`—` placeholders) so it does not regress on legacy
  findings.
- `agg` is harder to install than `asciinema`; Docker fallback mitigates
  that, but the skill should make this explicit.
- The recording skill must not encourage capturing real secrets; explicit
  redaction guidance is part of the skill.

## Reference: snippets carried over from `tmp/kk.md`

Preserved here so `tmp/kk.md` can be deleted without information loss.

### asciinema commands (preferred path)

Record:

    asciinema rec \
        --cols 100 --rows 30 \
        --idle-time-limit 2 \
        --command "bash reproduce.sh" \
        --title "<finding-id> — <short title>" \
        --overwrite exploit.cast

Render to GIF with legible defaults:

    agg \
        --font-family "JetBrains Mono,DejaVu Sans Mono,monospace" \
        --font-size 20 \
        --line-height 1.4 \
        --theme monokai \
        --speed 1.0 \
        --fps-cap 12 \
        exploit.cast exploit.gif

Optional MP4 (only if GIF exceeds ~3 MB or motion smoothness matters):

    agg --font-size 20 --theme monokai exploit.cast /tmp/exploit.gif
    ffmpeg -y -i /tmp/exploit.gif \
        -movflags +faststart \
        -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
        -c:v libx264 -preset slow -crf 28 \
        exploit.mp4

`--cols 100 --rows 30` keeps `.cast` small while remaining readable in
agg at font-size 20. Do not exceed 120 columns; long output should be
paged or filtered inside `reproduce.sh`.

### ffmpeg fallback (GUI / browser exploits)

Use only when the exploit cannot be expressed in a TTY (DOM XSS in a real
browser, native GUI client, etc.).

Headless capture with Xvfb:

    Xvfb :99 -screen 0 1280x720x24 &
    XVFB_PID=$!
    DISPLAY=:99 bash reproduce.sh &
    ffmpeg -y \
        -video_size 1280x720 \
        -framerate 12 \
        -f x11grab -i :99 \
        -t 90 \
        -c:v libx264 -preset slow -crf 30 \
        -pix_fmt yuv420p \
        -movflags +faststart \
        exploit.mp4
    kill "$XVFB_PID"

Legibility requirements for ffmpeg captures:

- Minimum capture resolution 1280x720.
- Force the target application or terminal to render at least 18 px
  effective font size in the captured frame (configure browser zoom or
  terminal font explicitly inside `reproduce.sh`).
- High-contrast theme; no translucent windows; no animated wallpapers.
- 12 fps is sufficient for exploit demos and keeps the file small. Do
  not exceed 24 fps.
- Target file size below 5 MB. If exceeded, increase `-crf` or reduce
  duration.

## Suggested commit grouping

1. `feat(phase-5): add exploit-recording skill and recording requirements`
2. `feat(phase-5): require CWE and add root-cause/data-flow/preconditions/recording finding sections`
3. `feat(phase-6): add CWE & recording columns, vulnerable-code excerpts, root-cause summaries`
4. `chore(check): warn when recording tools are missing`
5. `chore: drop tmp/kk.md (content folded into exploit-recording skill)`
