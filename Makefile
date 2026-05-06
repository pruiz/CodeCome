.PHONY: help check status next-id frontmatter index report
.PHONY: phase-1 phase-2 phase-3 phase-4 phase-5 validate-all
.PHONY: sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-build-target sandbox-test-target

help:
	@echo ""
	@echo "  CodeCome commands"
	@echo "  ================"
	@echo ""
	@echo "  Workflow phases:"
	@echo ""
	@echo "    make phase-1                  Run reconnaissance"
	@echo "    make phase-2                  Run hypothesis generation"
	@echo "    make phase-3                  Run counter-analysis"
	@echo "    make phase-4 FINDING=CC-0001  Validate one finding"
	@echo "    make phase-5                  Generate report"
	@echo "    make validate-all             Validate all NEEDS_VALIDATION findings"
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
# Workflow phases
# ---------------------------------------------------------------------------

phase-1:
	@./tools/gate-check.py 1
	opencode run --agent recon "$$(cat prompts/phase-1-recon.md)"

phase-2:
	@./tools/gate-check.py 2
	opencode run --agent auditor "$$(cat prompts/phase-2-audit.md)"

phase-3:
	@./tools/gate-check.py 3
	opencode run --agent reviewer "$$(cat prompts/phase-3-review.md)"

phase-4:
	@test -n "$(FINDING)" || (echo "Usage: make phase-4 FINDING=CC-0001" && exit 1)
	@./tools/gate-check.py 4 $(FINDING)
	opencode run --agent validator "$$(sed 's#FINDING_PATH_OR_ID#$(FINDING)#g' prompts/phase-4-validate.md)"

phase-5:
	@./tools/gate-check.py 5
	opencode run --agent reporter "$$(cat prompts/phase-5-report.md)"

validate-all:
	@ids=$$(./tools/list-findings.py --status NEEDS_VALIDATION --format ids 2>/dev/null); \
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

# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------

check:
	./tools/codecome.py check

status:
	./tools/codecome.py status

next-id:
	./tools/codecome.py next-id

frontmatter:
	./tools/check-frontmatter.py

index:
	./tools/render-index.py

report:
	./tools/render-report.py

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
