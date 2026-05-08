# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

.PHONY: help venv venv-check check status next-id frontmatter tests itemdb-reset index report
.PHONY: findings findings-create findings-move findings-evidence
.PHONY: phase-1 phase-2 phase-3 phase-4 phase-5 phase-6 validate-all exploit-all
.PHONY: sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-reset sandbox-build-target sandbox-test-target
.PHONY: sandbox-list sandbox-inspect sandbox-detect sandbox-bootstrap sandbox-validate sandbox-regenerate sandbox-status show-model

PYTHON := .venv/bin/python3
export PATH := $(CURDIR)/.venv/bin:$(PATH)
export PROMPT_EXTRA
export PROMPT_EXTRA_FILE

ifndef NO_COLOR
RED := \033[31m
YELLOW := \033[33m
CYAN := \033[36m
BOLD := \033[1m
RESET := \033[0m
else
RED :=
YELLOW :=
CYAN :=
BOLD :=
RESET :=
endif

help:
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)CodeCome commands$(RESET)\n"
	@printf "  $(BOLD)$(CYAN)=================$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Workflow phases:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make venv$(RESET)                     Create/update repo-local virtualenv\n"
	@printf "    $(BOLD)make phase-1$(RESET)                  Run reconnaissance\n"
	@printf "    $(BOLD)make phase-2$(RESET)                  Run hypothesis generation\n"
	@printf "    $(BOLD)make phase-3$(RESET)                  Run counter-analysis\n"
	@printf "    $(BOLD)make phase-4 FINDING=CC-0001$(RESET)  Validate one finding\n"
	@printf "    $(BOLD)make phase-5 FINDING=CC-0001$(RESET)  Develop exploit for one finding\n"
	@printf "    $(BOLD)make phase-6$(RESET)                  Generate report\n"
	@printf "    $(BOLD)make validate-all$(RESET)             Validate all PENDING findings\n"
	@printf "    $(BOLD)make exploit-all$(RESET)              Exploit all CONFIRMED findings\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Wrapper controls:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)CODECOME_USE_WRAPPER=0$(RESET)       Bypass styled wrapper and use raw opencode run\n"
	@printf "    $(BOLD)CODECOME_THINKING=1$(RESET)          Enable --thinking in wrapper-driven phase runs\n"
	@printf "    $(BOLD)OPENCODE_ARGS='...'$(RESET)          Extra flags passed through to opencode run\n"
	@printf "    $(BOLD)CODECOME_MODEL=<id>$(RESET)          Pin the model per phase (e.g. anthropic/claude-opus-4-7)\n"
	@printf "    $(BOLD)CODECOME_MODEL_VARIANT=<v>$(RESET)   Pin the model variant (e.g. high, max)\n"
	@printf "    $(BOLD)PROMPT_EXTRA=\"...\"$(RESET)            Append extra instructions to phase prompt\n"
	@printf "    $(BOLD)PROMPT_EXTRA_FILE=path$(RESET)        Append file content to phase prompt\n"
	@printf "\n"
	@printf "    $(BOLD)make show-model$(RESET)              Print the model resolution table for an agent\n"
	@printf "    $(BOLD)make show-model AGENT=auditor$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Workspace tools:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make check$(RESET)          Validate workspace structure and config\n"
	@printf "    $(BOLD)make status$(RESET)         Show current finding status\n"
	@printf "    $(BOLD)make next-id$(RESET)        Show next available finding id\n"
	@printf "    $(BOLD)make frontmatter$(RESET)    Validate finding frontmatter\n"
	@printf "    $(BOLD)make tests$(RESET)          Run dev test suite + frontmatter gate\n"
	@printf "    $(BOLD)make itemdb-reset$(RESET)   Remove local audit artifacts and recreate .gitkeep files\n"
	@printf "    $(BOLD)make index$(RESET)          Regenerate itemdb/index.md\n"
	@printf "    $(BOLD)make report$(RESET)         Regenerate itemdb/reports/report.md (local, no AI)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Finding management:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make findings$(RESET)                     List all findings\n"
	@printf "    $(BOLD)make findings STATUS=PENDING$(RESET)      List findings by status\n"
	@printf "    $(BOLD)make findings-create TITLE=\"...\"$(RESET)    Create a new finding from template\n"
	@printf "    $(BOLD)make findings-move FINDING=CC-0001 STATUS=CONFIRMED$(RESET)\n"
	@printf "    $(BOLD)make findings-evidence FINDING=CC-0001$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Sandbox runtime:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make sandbox-check$(RESET)  Run sandbox smoke test\n"
	@printf "    $(BOLD)make sandbox-up$(RESET)     Start sandbox\n"
	@printf "    $(BOLD)make sandbox-down$(RESET)   Stop sandbox\n"
	@printf "    $(BOLD)make sandbox-shell$(RESET)  Open sandbox shell\n"
	@printf "    $(BOLD)make sandbox-logs$(RESET)   Follow sandbox logs\n"
	@printf "    $(BOLD)make sandbox-clean$(RESET)  Stop sandbox and clean tmp\n"
	@printf "    $(BOLD)make sandbox-reset$(RESET)  Recreate sandbox from a known state\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Sandbox bootstrap (Phase 1b):$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make sandbox-list$(RESET)                List curated example sandboxes\n"
	@printf "    $(BOLD)make sandbox-inspect ID=python$(RESET)   Inspect one example\n"
	@printf "    $(BOLD)make sandbox-detect$(RESET)              Propose ranked candidates for src/\n"
	@printf "    $(BOLD)make sandbox-bootstrap ID=python$(RESET) Apply an example to sandbox/\n"
	@printf "    $(BOLD)make sandbox-validate$(RESET)            Run sandbox validation tiers\n"
	@printf "    $(BOLD)make sandbox-regenerate$(RESET)          Re-apply current example with backup\n"
	@printf "    $(BOLD)make sandbox-status$(RESET)              Show sandbox provenance and gate result\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Sandbox bootstrap controls:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)CODECOME_ALLOW_NO_SANDBOX=1$(RESET)        Soft-override Phase 2 sandbox gate\n"
	@printf "    $(BOLD)CODECOME_BOOTSTRAP_MAX_RETRIES=N$(RESET)   Agent remediation budget (default 3)\n"
	@printf "    $(BOLD)CODECOME_BOOTSTRAP_DRY_RUN=1$(RESET)       Force --dry-run on apply/regenerate\n"
	@printf "\n"

# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------

venv:
	@python3 -m venv .venv
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install --no-input -r requirements.txt

venv-check:
	@test -x "$(PYTHON)" || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) Missing repo virtualenv at .venv\n\nRun:\n\n    make venv\n\n" && exit 1)
	@$(PYTHON) -c "import yaml, rich" >/dev/null 2>&1 || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) .venv is missing required Python packages\n\nRun:\n\n    make venv\n\nIf you updated requirements, rerun the same command to resync .venv.\n\n" && exit 1)

# ---------------------------------------------------------------------------
# Workflow phases
# ---------------------------------------------------------------------------

phase-1: venv-check
	@$(PYTHON) tools/gate-check.py 1
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent recon "$$(cat prompts/phase-1-recon.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 1 --label "Target Reconnaissance + Sandbox Bootstrap" --agent recon --prompt-file prompts/phase-1-recon.md; \
	fi

phase-2: venv-check
	@$(PYTHON) tools/gate-check.py 2
	@$(PYTHON) tools/sandbox-bootstrap.py status --gate || ( \
		printf "\n$(BOLD)$(YELLOW)[BLOCK]$(RESET) Phase 2 sandbox gate failed.\n" ; \
		printf "Run: make sandbox-status\n" ; \
		printf "Or override (not recommended): CODECOME_ALLOW_NO_SANDBOX=1 make phase-2\n\n" ; \
		exit 1 )
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent auditor "$$(cat prompts/phase-2-audit.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 2 --label "Hypothesis Generation" --agent auditor --prompt-file prompts/phase-2-audit.md; \
	fi

phase-3: venv-check
	@$(PYTHON) tools/gate-check.py 3
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent reviewer "$$(cat prompts/phase-3-review.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 3 --label "Counter-analysis" --agent reviewer --prompt-file prompts/phase-3-review.md; \
	fi

phase-4: venv-check
	@test -n "$(FINDING)" || (echo "Usage: make phase-4 FINDING=CC-0001" && exit 1)
	@$(PYTHON) tools/gate-check.py 4 $(FINDING)
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent validator "$$(sed 's#FINDING_PATH_OR_ID#$(FINDING)#g' prompts/phase-4-validate.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 4 --label "Validation" --agent validator --prompt-file prompts/phase-4-validate.md --finding "$(FINDING)"; \
	fi

phase-5: venv-check
	@test -n "$(FINDING)" || (echo "Usage: make phase-5 FINDING=CC-0001" && exit 1)
	@$(PYTHON) tools/gate-check.py 5 $(FINDING)
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent exploiter "$$(sed 's#FINDING_PATH_OR_ID#$(FINDING)#g' prompts/phase-5-exploit.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 5 --label "Exploit Development" --agent exploiter --prompt-file prompts/phase-5-exploit.md --finding "$(FINDING)"; \
	fi

phase-6: venv-check
	@$(PYTHON) tools/gate-check.py 6
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent reporter "$$(cat prompts/phase-6-report.md)"; \
	else \
		$(PYTHON) tools/run-agent.py --phase 6 --label "Reporting" --agent reporter --prompt-file prompts/phase-6-report.md; \
	fi

validate-all: venv-check
	@ids=$$($(PYTHON) tools/list-findings.py --status PENDING --format ids 2>/dev/null); \
	if [ -z "$$ids" ]; then \
		echo "No PENDING findings to validate."; \
		exit 0; \
	fi; \
	for f in $$ids; do \
		echo ""; \
		echo "Validating $$f..."; \
		echo ""; \
		$(MAKE) phase-4 FINDING=$$f; \
	done

exploit-all: venv-check
	@ids=$$($(PYTHON) tools/list-findings.py --status CONFIRMED --eligible-for-exploit --format ids 2>/dev/null); \
	if [ -z "$$ids" ]; then \
		echo "No eligible CONFIRMED findings to exploit."; \
		exit 0; \
	fi; \
	for f in $$ids; do \
		echo ""; \
		echo "Developing exploit for $$f..."; \
		echo ""; \
		$(MAKE) phase-5 FINDING=$$f; \
	done

# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------

check: venv-check
	$(PYTHON) tools/codecome.py check

status: venv-check
	$(PYTHON) tools/codecome.py status

next-id: venv-check
	$(PYTHON) tools/codecome.py next-id

frontmatter: venv-check
	$(PYTHON) tools/check-frontmatter.py

tests: venv-check
	$(PYTHON) -m pytest -q tests
	$(PYTHON) tools/check-frontmatter.py

itemdb-reset: venv-check
	rm -f itemdb/notes/*.md
	rm -rf itemdb/evidence/CC-*
	rm -f itemdb/reports/*.md
	rm -f itemdb/findings/PENDING/CC-*.md
	rm -f itemdb/findings/CONFIRMED/CC-*.md
	rm -f itemdb/findings/EXPLOITED/CC-*.md
	rm -f itemdb/findings/REJECTED/CC-*.md
	rm -f itemdb/findings/DUPLICATE/CC-*.md
	rm -f runs/*.md
	rm -rf tmp/*
	touch itemdb/notes/.gitkeep
	touch itemdb/evidence/.gitkeep
	touch itemdb/reports/.gitkeep
	touch itemdb/findings/PENDING/.gitkeep
	touch itemdb/findings/CONFIRMED/.gitkeep
	touch itemdb/findings/EXPLOITED/.gitkeep
	touch itemdb/findings/REJECTED/.gitkeep
	touch itemdb/findings/DUPLICATE/.gitkeep
	touch runs/.gitkeep
	touch tmp/.gitkeep
	$(PYTHON) tools/render-index.py

index: venv-check
	$(PYTHON) tools/render-index.py

report: venv-check
	$(PYTHON) tools/render-report.py

findings: venv-check
ifdef STATUS
	$(PYTHON) tools/list-findings.py --status $(STATUS)
else
	$(PYTHON) tools/list-findings.py
endif

findings-create: venv-check
	$(PYTHON) tools/create-finding.py $(TITLE) $(ARGS)

findings-move: venv-check
	$(PYTHON) tools/move-finding.py $(FINDING) $(STATUS)

findings-evidence: venv-check
	$(PYTHON) tools/create-evidence.py $(FINDING)

# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

SANDBOX_SCRIPT_HINT := "Run 'make phase-1' (sub-stage 1b) to bootstrap sandbox/ from templates/sandboxes/."

sandbox-check:
	@test -x sandbox/scripts/check.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/check.sh

sandbox-up:
	@test -x sandbox/scripts/up.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/up.sh

sandbox-down:
	@test -x sandbox/scripts/down.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/down.sh

sandbox-shell:
	@test -x sandbox/scripts/shell.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/shell.sh

sandbox-logs:
	@test -x sandbox/scripts/logs.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/logs.sh

sandbox-clean:
	@test -x sandbox/scripts/clean.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/clean.sh

sandbox-reset:
	@test -x sandbox/scripts/reset.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/reset.sh

sandbox-build-target:
	@test -x sandbox/scripts/build-target.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/build-target.sh

sandbox-test-target:
	@test -x sandbox/scripts/test-target.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/test-target.sh

# ---------------------------------------------------------------------------
# Sandbox bootstrap (Phase 1b)
# ---------------------------------------------------------------------------

sandbox-list: venv-check
	$(PYTHON) tools/sandbox-bootstrap.py list

sandbox-inspect: venv-check
	@test -n "$(ID)" || (echo "Usage: make sandbox-inspect ID=<example-id>" && exit 1)
	$(PYTHON) tools/sandbox-bootstrap.py inspect $(ID)

sandbox-detect: venv-check
	$(PYTHON) tools/sandbox-bootstrap.py detect

sandbox-bootstrap: venv-check
	@test -n "$(ID)" || (echo "Usage: make sandbox-bootstrap ID=<example-id>" && exit 1)
	$(PYTHON) tools/sandbox-bootstrap.py apply $(ID) $(BOOTSTRAP_ARGS)

sandbox-validate: venv-check
	$(PYTHON) tools/sandbox-bootstrap.py validate $(BOOTSTRAP_ARGS)

sandbox-regenerate: venv-check
	$(PYTHON) tools/sandbox-bootstrap.py regenerate $(BOOTSTRAP_ARGS)

sandbox-status: venv-check
	$(PYTHON) tools/sandbox-bootstrap.py status

# Print the model that would be picked for a given AGENT (default: recon).
# Usage:
#   make show-model
#   make show-model AGENT=auditor
show-model: venv-check
	@$(PYTHON) tools/run-agent.py --show-model --agent $(or $(AGENT),recon)
