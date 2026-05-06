# Juliet Benchmark Skill

Use this skill only when the target appears to be the NIST SARD Juliet C/C++ test suite or a derivative of it.

This skill is target-specific. It must not replace the generic CodeCome workflow.

Juliet is useful as a benchmark corpus for evaluating whether CodeCome can identify, explain, review, and validate known vulnerability patterns.

## Purpose

When auditing Juliet, the goal is not just to detect that files are labeled with CWE names.

The goal is to determine whether the agent can:

- understand the vulnerable code path,
- distinguish bad and good variants,
- explain the weakness precisely,
- avoid relying only on filenames or directory names,
- validate findings through code reasoning, build/run behavior, sanitizer output, crash reproduction, or benchmark oracle comparison.

## Juliet-specific warning

Juliet contains strong label leakage.

Many files, directories, functions, and comments reveal the intended CWE and vulnerable variant.

Do not treat these labels as proof.

Labels may guide analysis, but a finding must still explain the actual code-level weakness.

## Common Juliet signals

Juliet test cases often include:

- CWE id in directory names,
- CWE id in filenames,
- bad and good functions,
- function names ending in `_bad`,
- function names containing `_good`,
- test harnesses,
- support files,
- variant numbers,
- comments describing the intended weakness.

Use these signals to navigate the corpus, not as standalone evidence.

## Label leakage tracking

For every Juliet finding, include a note explaining how the weakness was identified.

Use this section inside the finding body:

    # Benchmark label analysis

    Explain whether the weakness was inferred from:
    - source code,
    - filename,
    - directory name,
    - function name,
    - comments,
    - benchmark metadata,
    - runtime behavior,
    - sanitizer output.

If the finding is mostly based on labels, keep confidence low until code reasoning or validation is added.

## Preferred finding scope

Prefer one finding per concrete testcase or small group of closely related variants.

Good scope:

    A specific stack buffer overflow in one testcase file.

Acceptable scope:

    Multiple nearly identical variants of the same root cause in one CWE family,
    when the source/sink pattern and remediation are the same.

Bad scope:

    The whole CWE121 directory may contain buffer overflows.

## Bad/good variant handling

When possible, identify:

- bad function,
- good function or good variants,
- difference between bad and good behavior,
- source of input,
- dangerous sink,
- intended mitigation in good variant.

Do not report the good variant as vulnerable unless the code itself is actually flawed.

## Useful Juliet notes

During reconnaissance, optional Juliet-specific notes may be created:

    itemdb/notes/benchmark-notes.md
    itemdb/notes/cwe-map.md
    itemdb/notes/juliet-build-notes.md
    itemdb/notes/juliet-validation-notes.md

These are optional and target-specific.

The generic notes are still required:

    itemdb/notes/target-profile.md
    itemdb/notes/attack-surface.md
    itemdb/notes/build-model.md
    itemdb/notes/execution-model.md
    itemdb/notes/trust-boundaries.md
    itemdb/notes/validation-model.md
    itemdb/notes/interesting-files.md

## Attack surface mapping for Juliet

Juliet is not normally a deployed app.

Map the attack surface to:

- testcase entrypoints,
- bad functions,
- good functions,
- input simulation functions,
- environment variables,
- file inputs,
- command line arguments,
- network simulation code,
- source/sink patterns,
- build and test harnesses.

## Validation methods for Juliet

Useful methods include:

- static proof,
- compile selected testcase,
- compile selected CWE subset,
- run testcase binary,
- run bad and good variants when possible,
- compile with AddressSanitizer,
- compile with UndefinedBehaviorSanitizer,
- run under Valgrind,
- reproduce crash or sanitizer output,
- compare expected bad/good behavior,
- benchmark oracle comparison.

Benchmark oracle comparison alone should not be enough for `CONFIRMED`.

## Sanitizer guidance

For memory safety testcases, try compiler flags such as:

    -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1

Capture:

- build command,
- run command,
- sanitizer output,
- affected file,
- affected function,
- stack trace if available.

## Static proof guidance

A static proof should include:

- testcase file,
- bad function,
- source of data,
- sink,
- missing or insufficient check,
- why the good variant is safe if applicable,
- reachable conditions,
- expected impact.

## Finding frontmatter suggestions

For Juliet findings, frontmatter may include generic fields plus Juliet-specific data.

Example:

    benchmark:
      provider: "NIST SARD"
      suite: "Juliet C/C++"
      cwe_from_path: "CWE-121"
      label_visible: true
      label_inferred_from:
        - "source code"
        - "filename"

Do not require these fields for non-Juliet targets.

## Counter-analysis for Juliet

Check:

- Did the agent rely only on filename?
- Is the finding actually in a bad variant?
- Is the good variant being confused with the bad variant?
- Is the sink reachable?
- Is there a bounds check or mitigation in this variant?
- Is the issue already covered by another finding?
- Is the claimed impact consistent with the code?
- Can the testcase be built or reasoned about?

## Confirmation policy

A Juliet finding may be marked `CONFIRMED` when there is strong evidence such as:

- sanitizer detects the claimed issue,
- a crash is reproduced,
- a bad/good behavioral difference is demonstrated,
- a strong static proof shows the vulnerability,
- benchmark oracle comparison supports already strong code analysis.

Do not mark confirmed based only on:

- CWE directory name,
- filename,
- comments,
- function name,
- benchmark metadata.

## Report guidance for Juliet

In reports, explain that Juliet is a synthetic benchmark corpus.

Do not imply that findings represent vulnerabilities in a production application.

Useful report wording:

    This finding was confirmed against a synthetic Juliet testcase and is used
    to evaluate the CodeCome workflow.

Avoid wording like:

    The production system is vulnerable.

unless the target is actually a production-like system.
