# Semgrep Interesting Files

Date: YYYY-MM-DDTHH:MM:SSZ

These files are Phase 2 leads, not findings.

## `src/example/app.php`

- Risk score hint: 4
- Semgrep results: 1
- `php.lang.security.sql-injection` at `src/example/app.php:42`: Possible SQL injection from request input.

# Usage

Use this file to prioritize Phase 2 review. Do not copy entries directly into `itemdb/findings/`; Phase 2 must create proper CodeCome findings with source, sink, trust boundary, impact, validation plan, and counter-analysis.
