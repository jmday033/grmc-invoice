"""Record Castle (Inpatient Medicine Services, LLC) pay from Gusto "you've been paid" emails in the 1099 income tracker.

Gusto offers no API to the person being paid, so the Gusto notification email is the source: it gives the pay date and
amount. Each payment goes in the tracker row with the latest "IMS pay-period end" before the pay date, with
Confirmed? = Y because the money has been paid. Existing amounts are never overwritten.
Logs never print amounts, because Actions logs on a public repository are public."""
import argparse, base64, html, os, re
from datetime import date, datetime, timedelta
from decimal import Decimal

from invoice import SHEETS_EPOCH, col_letter, credentials

EMPLOYER = 'Inpatient Medicine Services'
GMAIL_QUERY = f'from:gustonoreply@gusto.com subject:"been paid" "{EMPLOYER}"'

def serial_date(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 40000 <= v <= 60000:
        return SHEETS_EPOCH + timedelta(days=int(v))
    return None

def parse_payment(subject, body):
    """Return (paid_on, amount) from a Gusto paid email, or raise ValueError for review."""
    if EMPLOYER.lower() not in body.lower(): raise ValueError('not an Inpatient Medicine Services payment')
    m = re.search(r'\((\d{2})/(\d{2})/(\d{4})\)', subject) or re.search(r'(\d{2})/(\d{2})/(\d{4})', body)
    if not m: raise ValueError('no pay date found')
    paid_on = date(int(m[3]), int(m[1]), int(m[2]))
    # Gusto puts the payment total in a heading ("## $1,750.00 ##"); otherwise every amount shown must agree.
    totals = re.findall(r'##\s*\$([\d,]+\.\d{2})\s*##', body)
    found = totals or re.findall(r'\$([\d,]+\.\d{2})', body)
    amounts = {Decimal(a.replace(',', '')) for a in found}
    if len(amounts) != 1: raise ValueError('payment amount missing or ambiguous')
    return paid_on, amounts.pop()

def ims_cells(values, paid_on):
    """Find the IMS row for a payment: the latest 'IMS pay-period end' strictly before paid_on.
    Returns (row_number, income_col, confirmed_col, period_end, income_value, confirmed_value) or None."""
    for h, row in enumerate(values):
        labels = [str(v).strip().lower() for v in row]
        if 'ims pay-period end' in labels and 'ims income' in labels:
            date_col = labels.index('ims pay-period end'); income_col = labels.index('ims income')
            conf = [i for i, v in enumerate(labels) if v.startswith('confirmed') and i > income_col]
            if not conf: raise ValueError('Tracker header has no Confirmed? column after IMS income')
            conf_col = conf[0]
            best = None
            for r, data in enumerate(values[h + 1:], start=h + 2):
                data = list(data) + [''] * (max(date_col, income_col, conf_col) + 1 - len(data))
                d = serial_date(data[date_col])
                if d and d < paid_on and (best is None or d > best[3]):
                    best = (r, income_col, conf_col, d, data[income_col], data[conf_col])
            return best
    raise ValueError('Tracker tab has no "IMS pay-period end" / "IMS income" header')

def message_text(msg):
    """Plain text of a Gmail API message (format=full), falling back to stripped HTML."""
    plain, rich = [], []
    def walk(part):
        data = part.get('body', {}).get('data')
        if data:
            text = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', 'replace')
            (plain if part.get('mimeType') == 'text/plain' else rich if part.get('mimeType') == 'text/html' else []).append(text)
        for p in part.get('parts', []): walk(p)
    walk(msg['payload'])
    if plain: return '\n'.join(plain)
    return html.unescape(re.sub(r'<[^>]+>', ' ', '\n'.join(rich)))

def gusto_payments(gmail, days):
    after = (date.today() - timedelta(days=days)).strftime('%Y/%m/%d')
    found, token = [], None
    while True:
        res = gmail.users().messages().list(userId='me', q=f'{GMAIL_QUERY} after:{after}', pageToken=token).execute()
        for ref in res.get('messages', []):
            msg = gmail.users().messages().get(userId='me', id=ref['id'], format='full').execute()
            subject = next((h['value'] for h in msg['payload'].get('headers', []) if h['name'].lower() == 'subject'), '')
            try: found.append(parse_payment(subject, message_text(msg)))
            except ValueError as e: print(f'Gusto email {ref["id"]}: skipped ({e}).')
        token = res.get('nextPageToken')
        if not token: break
    return sorted(found)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--days', type=int, default=60)
    p.add_argument('--dry-run', action='store_true', help='show which rows would change without writing'); a = p.parse_args()
    tracker_id = os.environ.get('TRACKER_ID', '').strip()
    if not tracker_id: print('Tracker: TRACKER_ID not set; skipped.'); return
    from googleapiclient.discovery import build
    gmail = build('gmail', 'v1', credentials=credentials(), cache_discovery=False)
    payments = gusto_payments(gmail, a.days)
    if not payments: print(f'No Gusto payments from {EMPLOYER} in the last {a.days} days.'); return
    api = build('sheets', 'v4', credentials=credentials(), cache_discovery=False)
    titles = [s['properties']['title'] for s in api.spreadsheets().get(spreadsheetId=tracker_id, fields='sheets.properties.title').execute()['sheets']]
    wanted = os.environ.get('TRACKER_TAB', '').strip().lower() or 'goal 1099 income'
    tabs = [t for t in titles if t.strip().lower() == wanted]
    if not tabs: print('Tracker: tab not found; skipped.'); return
    q = tabs[0].replace("'", "''")
    values = api.spreadsheets().values().get(spreadsheetId=tracker_id, range=f"'{q}'!A1:Z200",
        valueRenderOption='UNFORMATTED_VALUE', dateTimeRenderOption='SERIAL_NUMBER').execute().get('values', [])
    data, claimed = [], set()
    for paid_on, amount in payments:
        cell = ims_cells(values, paid_on)
        if cell is None: print(f'Payment of {paid_on}: no IMS pay-period end before it; skipped.'); continue
        row, income_col, conf_col, period_end, income, confirmed = cell
        if row in claimed:
            print(f'Payment of {paid_on}: period ending {period_end} already matched another payment this run; skipped for review.'); continue
        claimed.add(row)
        if str(income).strip() not in ('', '0', '0.0'):
            print(f'Payment of {paid_on}: period ending {period_end} already has an amount; left unchanged.'); continue
        data.append({'range': f"'{q}'!{col_letter(income_col)}{row}", 'values': [[float(amount)]]})
        if str(confirmed).strip().upper() != 'Y':
            data.append({'range': f"'{q}'!{col_letter(conf_col)}{row}", 'values': [['Y']]})
        print(f'Payment of {paid_on}: {"would record" if a.dry_run else "recording"} in period ending {period_end} (Confirmed? = Y).')
    if data and not a.dry_run:
        api.spreadsheets().values().batchUpdate(spreadsheetId=tracker_id, body={'valueInputOption': 'USER_ENTERED', 'data': data}).execute()

if __name__ == '__main__': main()
