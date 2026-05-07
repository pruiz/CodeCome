# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

.PHONY: help venv venv-check check status next-id frontmatter reset-itemdb index report
.PHONY: phase-1 phase-2 phase-3 phase-4 phase-5 phase-6 validate-all exploit-all
.PHONY: sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-build-target sandbox-test-target
.PHONY: sandbox-list sandbox-inspect sandbox-detect sandbox-bootstrap sandbox-validate sandbox-regenerate sandbox-status show-model

PYTHON := .venv/bin/python3

help:
	@echo ""
	@echo "  CodeCome commands"
	@echo "  ================"
	@echo ""
	@echo "  Workflow phases:"
	@echo ""
	@echo "    make venv                     Create/update repo-local virtualenv"
	@echo "    make phase-1                  Run reconnaissance"
	@echo "    make phase-2                  Run hypothesis generation"
	@echo "    make phase-3                  Run counter-analysis"
	@echo "    make phase-4 FINDING=CC-0001  Validate one finding"
	@echo "    make phase-5 FINDING=CC-0001  Develop exploit for one finding"
	@echo "    make phase-6                  Generate report"
	@echo "    make validate-all             Validate all PENDING findings"
	@echo "    make exploit-all              Exploit all CONFIRMED findings"
	@echo ""
	@echo "  Wrapper controls:"
	@echo ""
	@echo "    CODECOME_USE_WRAPPER=0       Bypass styled wrapper and use raw opencode run"
	@echo "    CODECOME_THINKING=1          Enable --thinking in wrapper-driven phase runs"
	@echo "    OPENCODE_ARGS='...'          Extra flags passed through to opencode run"
	@echo "    CODECOME_MODEL=<id>          Pin the model per phase (e.g. anthropic/claude-opus-4-7)"
	@echo "    CODECOME_MODEL_VARIANT=<v>   Pin the model variant (e.g. high, max)"
	@echo ""
	@echo "    make show-model              Print the model resolution table for an agent"
	@echo "    make show-model AGENT=auditor"
	@echo ""
	@echo "  Workspace tools:"
	@echo ""
	@echo "    make check          Validate workspace structure and config"
	@echo "    make status         Show current finding status"
	@echo "    make next-id        Show next available finding id"
	@echo "    make frontmatter    Validate finding frontmatter"
	@echo "    make index          Regenerate itemdb/index.md"
	@echo "    make report         Regenerate itemdb/reports/report.md (local, no AI)"
	@echo ""
	@echo "  Sandbox runtime:"
	@echo ""
	@echo "    make sandbox-check  Run sandbox smoke test"
	@echo "    make sandbox-up     Start sandbox"
	@echo "    make sandbox-down   Stop sandbox"
	@echo "    make sandbox-shell  Open sandbox shell"
	@echo "    make sandbox-logs   Follow sandbox logs"
	@echo "    make sandbox-clean  Stop sandbox and clean tmp"
	@echo ""
	@echo "  Sandbox bootstrap (Phase 1b):"
	@echo ""
	@echo "    make sandbox-list                List curated example sandboxes"
	@echo "    make sandbox-inspect ID=python   Inspect one example"
	@echo "    make sandbox-detect              Propose ranked candidates for src/"
	@echo "    make sandbox-bootstrap ID=python Apply an example to sandbox/"
	@echo "    make sandbox-validate            Run sandbox validation tiers"
	@echo "    make sandbox-regenerate          Re-apply current example with backup"
	@echo "    make sandbox-status              Show sandbox provenance and gate result"
	@echo ""
	@echo "  Sandbox bootstrap controls:"
	@echo ""
	@echo "    CODECOME_ALLOW_NO_SANDBOX=1        Soft-override Phase 2 sandbox gate"
	@echo "    CODECOME_BOOTSTRAP_MAX_RETRIES=N   Agent remediation budget (default 3)"
	@echo "    CODECOME_BOOTSTRAP_DRY_RUN=1       Force --dry-run on apply/regenerate"
	@echo ""

# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------

venv:
	@python3 -m venv .venv
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install --no-input -r requirements.txt

venv-check:
	@test -x "$(PYTHON)" || (printf "\n[FAIL] Missing repo virtualenv at .venv\n\nRun:\n\n    make venv\n\n" && exit 1)
	@$(PYTHON) -c "import yaml, rich" >/dev/null 2>&1 || (printf "\n[FAIL] .venv is missing required Python packages\n\nRun:\n\n    make venv\n\nIf you updated requirements, rerun the same command to resync .venv.\n\n" && exit 1)

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
		printf "\n[BLOCK] Phase 2 sandbox gate failed.\n" ; \
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

reset-itemdb: venv-check
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
