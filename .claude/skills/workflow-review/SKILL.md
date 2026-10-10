---
name: workflow-review
description: Review grmc-invoice changes for workflow drift, regressions and end-to-end evidence. Use for PR review, pre-release checks, documentation/configuration changes, or reports that automation behaves differently from its instructions.
---

Read [AGENTS.md](../../../AGENTS.md) first. Paths and commands below are relative to the repository root. Keep this an evidence-based review; the skill does not grant permission to merge, publish, send, or change production settings.

## Review procedure
1. Establish the requested diff and base revision. Read the actual changed files and their callers/tests, not just the PR summary. Sources for this repository: README.md, invoice.py, castle_income.py, project.py, test_invoice.py, test_castle_income.py, test_project.py, and .github/workflows/.
2. Compare each changed requirement across authoritative policy, configuration, implementation, examples, tests and workflow definitions. Record a mismatch as expected behavior, observed behavior, consequence and exact file location. Do not silently choose a new policy.
3. Inspect fail-closed paths, date/time boundaries, retries, duplicate prevention, external side effects and data exposure. Trace failure after each side effect. Distinguish source code, saved snapshots and verified live state.
4. Apply [invoice-reconciliation](../invoice-reconciliation/SKILL.md) for domain-specific invariants. Reuse existing tests and add focused regressions only when behavior changes.
5. Run `python -m unittest -v` from the repository root using the README's dependencies. For relevant code changes, follow a fictional input through the changed output path and compare with an independently computed expectation. Mock external services; do not trigger production jobs as a substitute for tests.
6. Review the final diff again from a reader's perspective. Challenge implementation claims against evidence. Do not label this an independent second reviewer unless a separate reviewer actually reviewed it. Do not spawn or message another agent without authorization.

## Report
Lead with actionable findings in severity order, including location, trigger and impact. Separate verified failures from questions. State tests run, skipped checks and remaining live verification. If nothing actionable is found, say so with the scope checked; do not claim the system is risk-free. Keep findings within the requested scope and follow AGENTS.md for branch/PR handling.

## Workflow drift check
If repository documentation disagrees with a running scheduler or external application, record both states and the required reconciliation. Editing this repository alone does not update a desktop automation, deployed job, mailbox or operational schedule. Never report those systems fixed without read-back evidence.
