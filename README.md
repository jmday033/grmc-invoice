# GRMC invoice preparation

Reads a shared hospitalist schedule in Google Sheets, selects the provider's Tele 1 / Tele 2 assignments for a closed two-week pay period, builds an invoice PDF, and creates a Gmail draft with it attached. It **never sends email**; every draft is reviewed and sent by hand. The PDF is a draft layout, not a replica of any signed form.

This repository is public. It contains no personal data, rates history, or credentials: identity, recipient, and source spreadsheet come from GitHub Actions secrets, and run artifacts are not uploaded.

## Setup
1. In a Google Cloud project, enable the Google Sheets API and Gmail API. Configure the Google Auth Platform (External audience, **In production** so refresh tokens don't expire after 7 days) and create a **Desktop app** OAuth client. Download it locally as `credentials.json`.
2. Install requirements and run `python authorize.py` on your own computer, signing in with the Google account that can read the schedule. It writes `token.json`. Both files are git-ignored; never commit or share them.
3. Add GitHub Actions **secrets**:
   - `GOOGLE_TOKEN_JSON` — contents of `token.json`
   - `SCHEDULE_ID` — the schedule spreadsheet ID
   - `INVOICE_TO` — invoice recipient address
   - `PROVIDER_NAME`, `PROVIDER_BADGE` — shown on the PDF
   - `SIGNOFF` (optional) — email sign-off; defaults to `PROVIDER_NAME`
   - `TRACKER_ID` (optional) — a cash-flow spreadsheet to record each invoice in (see below)
4. Optional Actions **variables** `TELE1_RATE` / `TELE2_RATE` override the $75/hour default.
5. Set the Actions **variable** `INVOICING_ENABLED=true`. This enables manual runs (Actions → GRMC invoices → Run workflow, optional PPE date) and the weekly schedule, Sunday 01:17 UTC, which prepares the latest **closed** fortnight. Before drafting, it searches Gmail for a message with the exact subject `GRMC invoice PPE YYYY-MM-DD`; if a draft or sent copy exists, the run skips. Keep that subject when you send, and don't delete a draft you still want the automation to treat as done.

## Billing rules
- Tele 1 (19:00–24:00): 5 hours. Tele 2 (00:00–07:00): 7 hours. Both $75/hour by default.
- Pay periods are 14 days, Sunday–Saturday, anchored on the period ending October 3, 2026. A period counts as closed once its ending Saturday has passed in Guam.
- Each Tele 2 shift is billed on its schedule row's date, including nights with both Tele 1 and Tele 2.
- No shifts means no invoice. Mixed or unrecognized assignments in a Tele cell, missing rates, and duplicate assignments stop the run for review.

## Income tracker (optional)
When `TRACKER_ID` is set, each run also opens that spreadsheet's `Goal 1099 Income` tab (override with the `TRACKER_TAB` variable), finds the row whose **GRMC pay-period end** equals the invoice's pay period, and writes the invoice total into **GRMC income** with **Confirmed?** = `N`. Change it to `Y` once paid. Columns are found by header text. A row that already has an amount is never overwritten, and nothing else in the sheet is touched. Run logs never print amounts, because Actions logs on a public repository are public.

Writing to a sheet requires the full `spreadsheets` scope in `authorize.py`; Google offers no single-file Sheets scope.

## Castle income from Gusto
`castle_income.py` (workflow **Castle income from Gusto**) records pay from Inpatient Medicine Services, LLC in the same tracker tab. Gusto has no API for the person being paid, so it reads Gusto's "you've been paid" emails, which give the pay date and amount. It runs on the 11th and 26th of each month at 08:23 Hawaii time, or manually (with an optional dry run), and needs only the existing `GOOGLE_TOKEN_JSON` and `TRACKER_ID` secrets and `INVOICING_ENABLED`.

Each payment goes in the row with the latest **IMS pay-period end** before the pay date (for example, paid 09/25 → period ending 09/15), writing **IMS income** and **Confirmed?** = `Y`. A row that already has an amount is never overwritten; two payments matching one row stop for review. Each run looks back 60 days, so a missed run is caught next time. Amounts never appear in logs.

## GRMC income projection
`project.py` (workflow **GRMC income projection**, weekly on Sunday and on demand) runs the schedule parser over the pay period still open and every later one the schedule covers, stopping at the first month with no Tele block. It writes Tele 1/Tele 2 counts, hours and projected income per period to a `Projected income` tab in the tracker (override with `PROJECTION_TAB`), creating the tab if needed and replacing only its columns A:F. Columns G onward are free for your own notes, such as Castle (IMS) shifts.

## Schedule parser
Reads `A1:BZ260` as unformatted values from every tab whose title contains a year in the period. Columns are found by header text in each month block: the row containing "Tele 1" and "Tele 2" sets those columns, and the first date cell to its right sets the month. The columns have moved between half-year tabs and are re-detected per block. A period whose months have no Tele block (for example, a tab not yet built) is an error rather than a silent zero-shift result. The source sheet is never edited.

## Validation
Run `python -m unittest -v`. Tests cover Gusto email parsing and IMS row matching, the 56-hour fortnight, month and year boundaries, header-based column detection across three layouts, Sheets serial dates, missing rates, mixed assignments, and fortnight selection.

## OAuth consent pages
`docs/` holds the homepage and privacy policy that the Google consent screen links to, served by GitHub Pages.
