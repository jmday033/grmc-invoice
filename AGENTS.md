# AGENTS.md

Instructions for AI agents (Claude Code, Codex) working in this repository. `CLAUDE.md` points here.

## This repository is public
Anything committed, printed in an Actions log, or written in a pull request is visible to anyone.
- Never commit or print: dollar amounts, rates, invoice totals, names, email addresses, badge numbers, spreadsheet IDs, tokens or `credentials.json`/`token.json`.
- Identity, recipients and spreadsheet IDs come from Actions secrets; rates come from the `TELE1_RATE`/`TELE2_RATE` variables. Never hard-code them or add defaults.
- Never upload run artifacts. The PDF reaches the user only as a Gmail draft attachment.
- Tests use made-up values only.
- If a secret is ever committed, deleting it in a later commit does not remove it from history. Stop and tell James Day so the token can be revoked.

## Behavior that must not change without approval
- The automation **never sends email**. It creates drafts only.
- Missing rates, mixed or unrecognized Tele assignments, and duplicates stop the run. Keep failures closed.
- In the tracker, rows marked `Confirmed? = Y` are never changed, and only the documented columns are written.
- Keep the duplicate check on the subject `GRMC invoice PPE YYYY-MM-DD`.

## Working on the code
- State assumptions and ask when a billing rule is unclear. Do not guess pay periods, hours or rates.
- Do only the requested change. Report other issues instead of fixing them unasked.
- Ask before creating new files, workflows or tracker tabs.
- Done means `python -m unittest -v` passes, and a changed rule has a test.
- Update README.md in the same commit as any change to billing, tracker or schedule behavior.
- Keep actions pinned to commit SHAs. Change dependencies in `requirements.in`, then regenerate the hashed `requirements.txt` as README.md describes.

## Git
- Work on a branch and open a pull request; do not push to `main` directly. Merging to `main` changes what the scheduled runs do.
- Commit messages say what changed and why. Never "update".
- American English spelling.

## Repository skills
- [Workflow review](.claude/skills/workflow-review/SKILL.md): consistency checks, regression review and end-to-end verification for relevant changes.
- [invoice-reconciliation](.claude/skills/invoice-reconciliation/SKILL.md): domain-specific audit and evidence requirements.
Use these when the task matches their descriptions. They reference the existing rules; they do not replace them or authorize production actions.
