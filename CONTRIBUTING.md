# Contributing to CodeCome

Thanks for your interest in contributing.

## How to contribute

1. Open an issue describing the change before sending substantial
   pull requests, so we can agree on scope.
2. Fork the repository, create a feature branch, and commit your
   changes with descriptive messages.
3. Run the workspace checks before opening the PR:

       make check
       make frontmatter

4. If you touched `tools/*.py`, ensure the file still compiles:

       .venv/bin/python3 -m py_compile tools/<file>.py

5. Open a pull request with a clear description of what changes,
   why, and how to verify it.

## Coding conventions

- Python: standard library first; keep dependencies in
  `requirements.txt`.
- Bash scripts under `sandbox/` and `templates/sandboxes/`: start
  with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Follow the SPDX header conventions (see "License headers"
  below).
- Markdown should keep a `## License` section at the bottom for
  user-facing documents.

## Plan files

Non-trivial changes use a plan file under `.project/<topic>-plan.md`
that is reviewed and approved before implementation. Plan files
follow the existing style in `.project/`.

## License headers

Every authored source file must carry a short SPDX header. Two
variants apply, depending on which subtree the file lives in.

**Project-licensed files** (most of the repo):

    # Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
    # SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

**MIT-licensed files** (everything under `templates/sandboxes/`):

    # Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
    # SPDX-License-Identifier: MIT

For Python and bash, place the header immediately after the
shebang. For Makefiles, Dockerfiles, and YAML, place it at the
very top.

## Contributor License Agreement

By submitting a contribution to this project (a commit, pull
request, patch, suggestion, or any other authored material), you
agree to the following:

1. **License grant for the project's terms.** Your contribution is
   licensed under the same terms as the file(s) it modifies:

   * `GPL-3.0-or-later OR AGPL-3.0-or-later` for files outside
     `templates/sandboxes/`,
   * `MIT` for files inside `templates/sandboxes/`.

2. **Relicensing grant.** You grant Pablo Ruiz García
   <pablo.ruiz@gmail.com> a perpetual, irrevocable, worldwide,
   royalty-free license to use, modify, sublicense, and relicense
   your contribution under any terms, including but not limited
   to commercial dual-licensing of CodeCome. This grant lets the
   project remain dual-licensable in the future without needing
   to chase signatures from every contributor again.

3. **Right to contribute.** You represent that you have the right
   to make the contribution under these terms. You either wrote
   the contribution yourself, or you have explicit permission from
   the rights holder to submit it under these terms.

4. **No warranty.** Contributions are provided as-is. The project
   maintainers assume no liability for your contribution.

There is no separate signing flow today. Submitting a pull request
or patch is the act of agreement.

## Scope of contributions

Welcome:

- bug fixes,
- documentation improvements,
- new sandbox seed templates under `templates/sandboxes/`,
- new validation tier scripts,
- skill / agent improvements,
- workflow ergonomics.

Out of scope (for now):

- changes to the legal text of `LICENSE` or `AGPL-LICENSE` (other
  than a fresh upstream pull from FSF),
- changes that introduce non-free dependencies or telemetry,
- changes that bypass the Phase 2 sandbox gate without a clear
  override path.

## Communication

Open an issue or comment on an existing one. For sensitive reports
(e.g. vulnerabilities found in CodeCome itself, not in the targets
it audits), email pablo.ruiz@gmail.com directly.

## License

By contributing you also accept that the contribution will be
distributed under the same dual license described above. See
`LICENSE`, `AGPL-LICENSE`, `templates/sandboxes/LICENSE`, and
`NOTICE` for the canonical license text and subtree split.
