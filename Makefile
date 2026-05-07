.PHONY: help venv venv-check check status next-id frontmatter reset-itemdb index report
.PHONY: phase-1 phase-2 phase-3 phase-4 phase-5 phase-6 validate-all exploit-all
.PHONY: sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-build-target sandbox-test-target

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
	@echo "    make validate-all             Validate all NEEDS_VALIDATION findings"
	@echo "    make exploit-all              Exploit all CONFIRMED findings"
	@echo ""
	@echo "  Wrapper controls:"
	@echo ""
	@echo "    CODECOME_USE_WRAPPER=0       Bypass styled wrapper and use raw opencode run"
	@echo "    CODECOME_THINKING=1          Enable --thinking in wrapper-driven phase runs"
	@echo "    OPENCODE_ARGS='...'          Extra flags passed through to opencode run"
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
	@echo "  Sandbox:"
	@echo ""
	@echo "    make sandbox-check  Run sandbox smoke test"
	@echo "    make sandbox-up     Start sandbox"
	@echo "    make sandbox-down   Stop sandbox"
	@echo "    make sandbox-shell  Open sandbox shell"
	@echo "    make sandbox-logs   Follow sandbox logs"
	@echo "    make sandbox-clean  Stop sandbox and clean tmp"
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
		$(PYTHON) tools/run-agent.py --phase 1 --label "Target Reconnaissance" --agent recon --prompt-file prompts/phase-1-recon.md; \
	fi

phase-2: venv-check
	@$(PYTHON) tools/gate-check.py 2
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
	@ids=$$($(PYTHON) tools/list-findings.py --status NEEDS_VALIDATION --format ids 2>/dev/null); \
	if [ -z "$$ids" ]; then \
		echo "No NEEDS_VALIDATION findings to validate."; \
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
	rm -f itemdb/findings/NEEDS_VALIDATION/CC-*.md
	rm -f itemdb/findings/CONFIRMED/CC-*.md
	rm -f itemdb/findings/REJECTED/CC-*.md
	rm -f itemdb/findings/DUPLICATE/CC-*.md
	rm -f runs/*.md
	rm -rf tmp/*
	touch itemdb/notes/.gitkeep
	touch itemdb/evidence/.gitkeep
	touch itemdb/reports/.gitkeep
	touch itemdb/findings/NEEDS_VALIDATION/.gitkeep
	touch itemdb/findings/CONFIRMED/.gitkeep
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

sandbox-check:
	./sandbox/scripts/check.sh

sandbox-up:
	./sandbox/scripts/up.sh

sandbox-down:
	./sandbox/scripts/down.sh

sandbox-shell:
	./sandbox/scripts/shell.sh

sandbox-logs:
	./sandbox/scripts/logs.sh

sandbox-clean:
	./sandbox/scripts/clean.sh

sandbox-build-target:
	./sandbox/scripts/build-target.sh

sandbox-test-target:
	./sandbox/scripts/test-target.sh
