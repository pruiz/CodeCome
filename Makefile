.PHONY: help check status next-id frontmatter index report sandbox-check sandbox-up sandbox-down sandbox-shell sandbox-logs sandbox-clean sandbox-build-target sandbox-test-target

help:
	@echo "CodeCome commands:"
	@echo ""
	@echo "  make check          Validate workspace structure and config"
	@echo "  make status         Show current finding status"
	@echo "  make next-id        Show next available finding id"
	@echo "  make index          Regenerate itemdb/index.md"
	@echo "  make report         Regenerate itemdb/reports/report.md"
	@echo ""
	@echo "  make sandbox-check  Run sandbox smoke test"
	@echo "  make sandbox-up     Start sandbox"
	@echo "  make sandbox-down   Stop sandbox"
	@echo "  make sandbox-shell  Open sandbox shell"
	@echo "  make sandbox-logs   Follow sandbox logs"
	@echo "  make sandbox-clean  Stop sandbox and clean tmp"
	@echo ""

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

create-evidence:
	@echo "Usage: ./tools/create-evidence.py CC-0001"


sandbox-build-target:
	./sandbox/scripts/build-target.sh

sandbox-test-target:
	./sandbox/scripts/test-target.sh
