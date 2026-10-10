---
name: invoice-reconciliation
description: Audit GRMC invoice and income-tracker calculations, period boundaries, schedule parsing, duplicate prevention and draft-only delivery. Use for billing changes, invoice discrepancies, or verification before a finance release.
---

Read [README.md](../../../README.md) for the billing and tracker contract and [AGENTS.md](../../../AGENTS.md) for public-repository data restrictions.

1. Trace the closed pay-period calculation in Guam, schedule-row dates, detected month blocks and Tele columns. Independently calculate synthetic shift counts, hours and totals from the documented rules. Include month/year transitions and ambiguous or duplicate assignments.
2. Verify rate inputs are required and validated. Never substitute a remembered rate, a guessed default or a historical invoice. Keep real rates, amounts, identities and spreadsheet details out of public code, PRs and logs.
3. Follow each invoice total through the PDF, draft attachment and tracker write. Audit exact pay-period matching, protected confirmed rows, permitted columns and handling of projected values. Separate projected income from invoiced and paid income.
4. Inspect duplicate detection for existing drafts and sent messages. Test retries after each possible partial failure, including draft creation succeeding before a tracker write fails; report what actually persists rather than claiming the whole run is atomic.
5. Review Castle payment-to-period matching and multiple-payment ambiguity separately from GRMC invoice dates. Verify projection writes preserve columns outside their documented range.
6. Check that workflows only create drafts, use the documented enablement gate, pin actions/dependencies and avoid public artifacts or sensitive log output. Inspect runtime failures without printing secret values.

Run tests below with fictional data and mocked external services. Use the test cases as the safe entry point; do not run invoice.py, castle_income.py or project.py against production merely to test a code change. A green unit test does not prove a live draft or tracker write succeeded.

Return a reconciliation of expected versus actual behavior, test evidence and unresolved delivery risks. Use synthetic examples in public findings. Keep real reconciliation details in the authorized private environment.

Repository test command: `python -m unittest -v` (from the repository root; dependencies in README.md).

