"""Project GRMC income from the schedule: every open or future pay period whose months are on the schedule.

Writes one tab in the tracker spreadsheet ("Projected income", or the PROJECTION_TAB variable), creating it if needed and
replacing only its columns A:F. Nothing else in the tracker is touched, and the source schedule is never edited.
Logs never print amounts, because Actions logs on a public repository are public."""
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from invoice import ANCHOR, confirmed_rates, credentials, fetch_tabs, shifts_from_tabs

HEADER = ['GRMC pay-period end', 'Tele 1 shifts', 'Tele 2 shifts', 'Hours', 'Projected GRMC income', 'Updated']

def project(tabs, first_end, rates, max_periods=27):
    """Return one row per pay period from first_end until the schedule runs out (a month with no Tele block)."""
    rows = []
    for i in range(max_periods):
        end = first_end + timedelta(days=14 * i)
        try: shifts = shifts_from_tabs(tabs, end - timedelta(days=13), end, rates)
        except ValueError as e:
            if 'no Tele 1/Tele 2 block' in str(e): break
            raise
        rows.append([end, sum(s['shift'] == 'tele1' for s in shifts), sum(s['shift'] == 'tele2' for s in shifts),
                     sum(s['hours'] for s in shifts), sum(Decimal(s['amount']) for s in shifts)])
    return rows

def main():
    today = datetime.now(ZoneInfo('Pacific/Guam')).date()
    first_end = ANCHOR + timedelta(days=-(-(today - ANCHOR).days // 14) * 14)  # the period still open today
    rates = confirmed_rates()
    tabs = fetch_tabs(first_end - timedelta(days=13), date(today.year + 1, 12, 31))
    rows = project(tabs, first_end, rates)
    if not rows: print('Schedule has no open pay periods yet; nothing projected.'); return
    tracker_id = os.environ.get('TRACKER_ID', '').strip()
    if not tracker_id: print(f'Projected {len(rows)} pay periods; TRACKER_ID not set, so nothing written.'); return
    from googleapiclient.discovery import build
    api = build('sheets', 'v4', credentials=credentials(), cache_discovery=False)
    name = os.environ.get('PROJECTION_TAB', '').strip() or 'Projected income'
    titles = [s['properties']['title'] for s in api.spreadsheets().get(spreadsheetId=tracker_id, fields='sheets.properties.title').execute()['sheets']]
    if name not in titles:
        api.spreadsheets().batchUpdate(spreadsheetId=tracker_id, body={'requests': [{'addSheet': {'properties': {'title': name}}}]}).execute()
    q = name.replace("'", "''")
    stamp = today.isoformat()
    values = [HEADER] + [[r[0].isoformat(), r[1], r[2], r[3], float(r[4]), stamp] for r in rows]
    values.append(['TOTAL', '', '', f'=SUM(D2:D{len(rows) + 1})', f'=SUM(E2:E{len(rows) + 1})', ''])
    api.spreadsheets().values().clear(spreadsheetId=tracker_id, range=f"'{q}'!A1:F200").execute()
    api.spreadsheets().values().update(spreadsheetId=tracker_id, range=f"'{q}'!A1", valueInputOption='USER_ENTERED',
        body={'values': values}).execute()
    print(f'Projection: wrote {len(rows)} pay periods ({rows[0][0]} to {rows[-1][0]}) to the "{name}" tab.')

if __name__ == '__main__': main()
