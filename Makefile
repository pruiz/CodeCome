# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

.PHONY: help init venv venv-check check status next-id frontmatter tests test-parity itemdb-reset index report
.PHONY: findings findings-create findings-move findings-evidence findings-package
.PHONY: phase-1 phase-2 phase-3 phase-4 phase-5 phase-6 validate-all exploit-all opencode-raw
.PHONY: sandbox-setup sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-reset sandbox-build sandbox-test
.PHONY: sandbox-list sandbox-inspect sandbox-detect sandbox-bootstrap sandbox-validate sandbox-regenerate sandbox-status show-model

PYTHON := .venv/bin/python3
export PATH := $(CURDIR)/.venv/bin:$(PATH)
export PROMPT_EXTRA
export PROMPT_EXTRA_FILE

# Pass --thinking to raw opencode run when CODECOME_THINKING=1
OPENCODE_THINKING_FLAG := $(if $(filter 1,$(CODECOME_THINKING)),--thinking,)

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
	@printf "    $(BOLD)make init$(RESET)                     Create/update repo-local virtualenv\n"
	@printf "    $(BOLD)make phase-1$(RESET)                  Run reconnaissance\n"
	@printf "    $(BOLD)make phase-2$(RESET)                  Run hypothesis generation\n"
	@printf "    $(BOLD)make phase-3$(RESET)                  Run counter-analysis\n"
	@printf "    $(BOLD)make phase-4 FINDING=CC-0001$(RESET)  Validate one finding\n"
	@printf "    $(BOLD)make phase-5 FINDING=CC-0001$(RESET)  Develop exploit for one finding\n"
	@printf "    $(BOLD)make phase-6$(RESET)                  Generate report\n"
	@printf "    $(BOLD)make validate-all$(RESET)             Validate all PENDING findings\n"
	@printf "    $(BOLD)make exploit-all$(RESET)              Exploit all CONFIRMED findings\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Deep Sweep (Optional):$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make list-risk-files$(RESET)          List top-scoring risky files from index\n"
	@printf "    $(BOLD)make sweep$(RESET)                   Run deep sweep on top-scoring files\n"
	@printf "    $(BOLD)make sweep FILE=\"src/foo.*\"$(RESET)  Run deep sweep on specific file(s)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Phase controls:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)CODECOME_THINKING=1$(RESET)          Show model reasoning/thinking blocks in output\n"
	@printf "    $(BOLD)CODECOME_MODEL=<id>$(RESET)          Pin the model per phase (e.g. anthropic/claude-opus-4-7)\n"
	@printf "    $(BOLD)CODECOME_MODEL_VARIANT=<v>$(RESET)   Pin the model variant (e.g. high, max)\n"
	@printf "    $(BOLD)PROMPT_EXTRA=\"...\"$(RESET)            Append extra instructions to phase prompt\n"
	@printf "    $(BOLD)PROMPT_EXTRA_FILE=path$(RESET)        Append file content to phase prompt\n"
	@printf "\n"
	@printf "    $(BOLD)make show-model$(RESET)              Print the model resolution table for an agent\n"
	@printf "    $(BOLD)make show-model AGENT=auditor$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Raw debug (non-workflow):$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make opencode-raw$(RESET)            Run opencode directly (bypasses harness)\n"
	@printf "        $(BOLD)AGENT=<name>$(RESET)                Required. Agent to run (e.g. auditor)\n"
	@printf "        $(BOLD)PROMPT_FILE=path$(RESET)            Required. Prompt file to send\n"
	@printf "        $(BOLD)CODECOME_THINKING=1$(RESET)         Show reasoning/thinking blocks\n"
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
	@printf "    $(BOLD)make findings-package FINDING=CC-0001$(RESET)   Package all artifacts for a finding into a zip\n"
	@printf "\n"
	@printf "  $(BOLD)$(CYAN)Sandbox runtime:$(RESET)\n"
	@printf "\n"
	@printf "    $(BOLD)make sandbox-setup$(RESET)  Set up sandbox env (setup.sh or 'docker compose build')\n"
	@printf "    $(BOLD)make sandbox-check$(RESET)  Run sandbox smoke test\n"
	@printf "    $(BOLD)make sandbox-up$(RESET)     Start sandbox\n"
	@printf "    $(BOLD)make sandbox-down$(RESET)   Stop sandbox\n"
	@printf "    $(BOLD)make sandbox-shell$(RESET)  Open sandbox shell\n"
	@printf "    $(BOLD)make sandbox-logs$(RESET)   Follow sandbox logs\n"
	@printf "    $(BOLD)make sandbox-clean$(RESET)  Stop sandbox and clean tmp\n"
	@printf "    $(BOLD)make sandbox-reset$(RESET)  Recreate sandbox from a known state\n"
	@printf "    $(BOLD)make sandbox-build$(RESET)  Build the target inside the sandbox\n"
	@printf "    $(BOLD)make sandbox-test$(RESET)   Test the target inside the sandbox\n"
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

init:
	@python3 -m venv .venv
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install --no-input -r requirements.txt
	@if [ "$$CODEQL" != "0" ] && [ "$$CODEQL_SKIP_INSTALL" != "1" ]; then \
		printf "$(BOLD)$(CYAN)[CodeQL]$(RESET) Managed CodeQL install not yet implemented — coming in a future PR.\n"; \
	fi

venv: init

venv-check:
	@test -x "$(PYTHON)" || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) Missing repo virtualenv at .venv\n\nRun:\n\n    make init\n\n" && exit 1)
	@$(PYTHON) -c "import yaml, rich" >/dev/null 2>&1 || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) .venv is missing required Python packages\n\nRun:\n\n    make init\n\nIf you updated requirements, rerun the same command to resync .venv.\n\n" && exit 1)

# ---------------------------------------------------------------------------
# Workflow phases
# ---------------------------------------------------------------------------

phase-1: venv-check
	@$(PYTHON) tools/gate-check.py 1
	@$(PYTHON) tools/run-agent.py --phase 1 --label "Phase 1: Reconnaissance" --agent recon

phase-2: venv-check
	@$(PYTHON) tools/gate-check.py 2
	@$(PYTHON) tools/sandbox-bootstrap.py status --gate || ( \
		printf "\n$(BOLD)$(YELLOW)[BLOCK]$(RESET) Phase 2 sandbox gate failed.\n" ; \
		printf "Run: make sandbox-status\n" ; \
		printf "Or override (not recommended): CODECOME_ALLOW_NO_SANDBOX=1 make phase-2\n\n" ; \
		exit 1 )
	@$(PYTHON) tools/run-agent.py --phase 2 --label "Hypothesis Generation" --agent auditor --prompt-file prompts/phase-2-audit.md

phase-3: venv-check
	@$(PYTHON) tools/gate-check.py 3
	@$(PYTHON) tools/run-agent.py --phase 3 --label "Counter-analysis" --agent reviewer --prompt-file prompts/phase-3-review.md

phase-4: venv-check
	@test -n "$(FINDING)" || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) Missing required FINDING argument for Phase 4 (Validation).\n\nSpecify which finding you want to validate:\n\n    $(BOLD)make phase-4 FINDING=CC-0001$(RESET)\n\nTo list available pending findings: $(BOLD)make findings STATUS=PENDING$(RESET)\n\n" && exit 1)
	@$(PYTHON) tools/gate-check.py 4 $(FINDING)
	@$(PYTHON) tools/run-agent.py --phase 4 --label "Validation" --agent validator --prompt-file prompts/phase-4-validate.md --finding "$(FINDING)"

phase-5: venv-check
	@test -n "$(FINDING)" || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) Missing required FINDING argument for Phase 5 (Exploitation).\n\nSpecify which finding you want to exploit:\n\n    $(BOLD)make phase-5 FINDING=CC-0001$(RESET)\n\nTo list available confirmed findings: $(BOLD)make findings STATUS=CONFIRMED$(RESET)\n\n" && exit 1)
	@$(PYTHON) tools/gate-check.py 5 $(FINDING)
	@$(PYTHON) tools/run-agent.py --phase 5 --label "Exploit Development" --agent exploiter --prompt-file prompts/phase-5-exploit.md --finding "$(FINDING)"

phase-6: venv-check
	@$(PYTHON) tools/gate-check.py 6
	@$(PYTHON) tools/run-agent.py --phase 6 --label "Reporting" --agent reporter --prompt-file prompts/phase-6-report.md

chat: venv-check
	@$(PYTHON) tools/run-agent.py --chat --label "Interactive Chat" --agent $(or $(AGENT),chat) --prompt-file prompts/chat-initial.md $(if $(DEBUG),--debug,)

list-risk-files: venv-check
	@$(PYTHON) tools/list-risk-files.py

sweep: venv-check
	@if [ -n "$(FILE)" ]; then \
		$(PYTHON) tools/run-sweep.py --file "$(FILE)"; \
	else \
		$(PYTHON) tools/run-sweep.py; \
	fi

# ---------------------------------------------------------------------------
# Raw opencode debug target (non-workflow)
# ---------------------------------------------------------------------------

opencode-raw:
	@test -n "$(AGENT)" || (echo "AGENT is required. Usage: make opencode-raw AGENT=auditor PROMPT_FILE=prompts/foo.md" && exit 1)
	@test -n "$(PROMPT_FILE)" || (echo "PROMPT_FILE is required. Usage: make opencode-raw AGENT=auditor PROMPT_FILE=prompts/foo.md" && exit 1)
	@opencode run --agent "$(AGENT)" $(OPENCODE_THINKING_FLAG) "$$(cat "$(PROMPT_FILE)")"

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

test-parity: venv-check
	$(PYTHON) -m pytest tests/test_mock_llm_parity.py -v

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
	@test -n "$(strip $(TITLE))" || (printf "TITLE is required. Usage: make findings-create TITLE=\"Short descriptive title\" [ARGS='...']\n" && exit 2)
	$(PYTHON) tools/create-finding.py "$(TITLE)" $(ARGS)

findings-move: venv-check
	$(PYTHON) tools/move-finding.py $(FINDING) $(STATUS)

findings-evidence: venv-check
	$(PYTHON) tools/create-evidence.py $(FINDING)

findings-package:
	@test -n "$(FINDING)" || (printf "\n$(BOLD)$(RED)[FAIL]$(RESET) Missing FINDING argument for packaging.\n\n    make findings-package FINDING=CC-0001\n\n" && exit 1)
	@$(PYTHON) tools/package-finding.py "$(FINDING)"

# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

SANDBOX_SCRIPT_HINT := "No sandbox helper script found. Run 'make phase-1' (sub-stage 1b) to bootstrap sandbox/ from templates/sandboxes/, or place the helper script under sandbox/scripts/ manually."

sandbox-setup:
	@if [ -x sandbox/scripts/setup.sh ]; then \
		./sandbox/scripts/setup.sh; \
	elif [ -f sandbox/docker-compose.yml ]; then \
		docker compose -f sandbox/docker-compose.yml build; \
	else \
		echo $(SANDBOX_SCRIPT_HINT); \
		exit 1; \
	fi

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

sandbox-build:
	@test -x sandbox/scripts/build.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/build.sh

sandbox-test:
	@test -x sandbox/scripts/test.sh || (echo $(SANDBOX_SCRIPT_HINT) && exit 1)
	./sandbox/scripts/test.sh

# ---------------------------------------------------------------------------
# Sandbox bootstrap (Phase 1b)
# ---------------------------------------------------------------------------

sandbox-list: venv-check
	@$(PYTHON) tools/sandbox-bootstrap.py list

sandbox-inspect: venv-check
	@test -n "$(ID)" || (echo "Usage: make sandbox-inspect ID=<example-id>" && exit 1)
	@$(PYTHON) tools/sandbox-bootstrap.py inspect $(ID)

sandbox-detect: venv-check
	@$(PYTHON) tools/sandbox-bootstrap.py detect

sandbox-bootstrap: venv-check
	@test -n "$(ID)" || (echo "Usage: make sandbox-bootstrap ID=<example-id>" && exit 1)
	@$(PYTHON) tools/sandbox-bootstrap.py apply $(ID) $(BOOTSTRAP_ARGS)

sandbox-validate: venv-check
	@$(PYTHON) tools/sandbox-bootstrap.py validate $(BOOTSTRAP_ARGS)

sandbox-regenerate: venv-check
	@$(PYTHON) tools/sandbox-bootstrap.py regenerate $(BOOTSTRAP_ARGS)

sandbox-status: venv-check
	@$(PYTHON) tools/sandbox-bootstrap.py status

# Print the model that would be picked for a given AGENT (default: recon).
# Usage:
#   make show-model
#   make show-model AGENT=auditor
show-model: venv-check
	@$(PYTHON) tools/run-agent.py --show-model --agent $(or $(AGENT),recon)
