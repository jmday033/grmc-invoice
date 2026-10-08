import argparse, base64, csv, io, json, os, re
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ANCHOR = date(2026, 10, 3)
MONTHS = {m.lower(): i for i, m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], 1)}

def last_period(today):
    return ANCHOR + timedelta(days=((today - ANCHOR).days // 14) * 14)

SHIFT_TYPES = [('tele1', r'tele\s*1\b', 5, '19:00-24:00'), ('tele2', r'tele\s*2\b', 7, '00:00-07:00')]
SHEETS_EPOCH = date(1899, 12, 30)

def month_marker(value):
    """Return (year, month) from a block's month cell: a date, a Sheets serial number, or text like 'Oct 26'."""
    if isinstance(value, (date, datetime)): return value.year, value.month
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 40000 <= value <= 60000:
        d = SHEETS_EPOCH + timedelta(days=int(value)); return d.year, d.month
    match = re.fullmatch(r'([A-Za-z]{3,9})\.?\s+(\d{2}|\d{4})', str(value or '').strip())
    if match and match[1][:3].lower() in MONTHS:
        year = int(match[2]); return (year + 2000 if year < 100 else year), MONTHS[match[1][:3].lower()]
    return None

def header_layout(row):
    """If row is a month-block header, return ({kind: column}, (year, month)). Columns are found by header text."""
    cols = {}
    for kind, pattern, _, _ in SHIFT_TYPES:
        found = [i for i, v in enumerate(row) if isinstance(v, str) and re.match(pattern, v.strip(), re.I)]
        if len(found) > 1: raise ValueError(f'Multiple {kind} columns in header row')
        if found: cols[kind] = found[0]
    if not cols: return None
    if set(cols) != {k for k, *_ in SHIFT_TYPES}: raise ValueError('Header row has Tele 1 or Tele 2 but not both')
    # The month marker is the first date-like cell to the right of the Tele columns.
    for v in row[max(cols.values()) + 1:]:
        marker = month_marker(v)
        if marker: return cols, marker
    raise ValueError('Header row has no month marker to the right of the Tele columns')

def day_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if float(value).is_integer() and 1 <= value <= 31 else None
    match = re.fullmatch(r'(?:Mon\s+)?(\d{1,2})(?:\.0)?', str(value or '').strip())
    return int(match[1]) if match else None

def shifts(values, start, end, rates):
    """Parse one schedule tab. Each month block's header row decides where Tele 1/Tele 2 are."""
    return shifts_from_tabs([values], start, end, rates)

def shifts_from_tabs(tabs, start, end, rates):
    result = []
    seen = set()
    covered = set()
    for tab in tabs:
        layout = marker = None  # never carry a layout from one tab into the next
        for row in tab:
            row = list(row)
            header = header_layout(row)
            if header:
                layout, marker = header
                covered.add(marker)
                continue
            if layout is None: continue
            num = day_number(row[0] if row else '')
            if num is None: continue
            day = date(marker[0], marker[1], num)
            if not start <= day <= end: continue
            for kind, _, hours, time in SHIFT_TYPES:
                col = layout[kind]
                name = str(row[col] if col < len(row) and row[col] is not None else '').strip()
                if not re.search(r'\bDay\b', name, re.I): continue
                if name.lower() != 'day': raise ValueError(f'Ambiguous {kind} assignment on {day} (cell mentions Day with other text) requires review')
                rate = rates.get(kind)
                if rate is None: raise ValueError(f'Missing confirmed {kind} rate')
                key = (day, kind)
                if key in seen: raise ValueError(f'Duplicate schedule assignment {kind} on {day}')
                seen.add(key)
                result.append(dict(date=day.isoformat(),shift=kind,time=time,hours=hours,rate=str(rate),amount=str(Decimal(str(rate))*hours)))
    needed = {(d.year, d.month) for d in (start + timedelta(days=i) for i in range((end - start).days + 1))}
    if needed - covered:
        missing = ', '.join(f'{y}-{m:02d}' for y, m in sorted(needed - covered))
        raise ValueError(f'Schedule has no Tele 1/Tele 2 block for {missing}; check tab titles and headers')
    return sorted(result, key=lambda x:(x['date'], x['shift']))

_CREDS = None
def credentials():
    global _CREDS
    if _CREDS is None:
        from google.oauth2.credentials import Credentials
        _CREDS = Credentials.from_authorized_user_info(json.loads(os.environ['GOOGLE_TOKEN_JSON']))
    return _CREDS

def make_pdf(rows, start, end, path, provider, badge):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    styles = getSampleStyleSheet()
    data = [['Date','Shift (Guam)','Hours','Rate','Amount']]
    for r in rows: data.append([r['date'],r['time'],str(r['hours']),f"${Decimal(r['rate']):,.2f}",f"${Decimal(r['amount']):,.2f}"])
    data.append(['TOTAL','',str(sum(r['hours'] for r in rows)),'',f"${sum(Decimal(r['amount']) for r in rows):,.2f}"])
    table = Table(data, colWidths=[85,115,55,85,95], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.5,colors.grey),('PADDING',(0,0),(-1,-1),7)]))
    SimpleDocTemplate(str(path)).build([Paragraph('GRMC Hospitalist Invoice — DRAFT',styles['Title']),Paragraph(f'Provider: {provider} | Badge: {badge}<br/>Bill to: Guam Regional Medical City<br/>Invoice: GRMC-{end.isoformat()}<br/>Period: {start.isoformat()} through {end.isoformat()}<br/>Pay period ending: {end.isoformat()}',styles['Normal']),Spacer(1,16),table,Spacer(1,16),Paragraph('Review scheduled versus actual hours before sending. Provider signature/date: __________________',styles['Normal'])])

def col_letter(i):
    s = ''
    i += 1
    while i: i, r = divmod(i - 1, 26); s = chr(65 + r) + s
    return s

def tracker_cells(values, ppe):
    """Locate the GRMC income and Confirmed? cells for the row whose 'GRMC pay-period end' equals ppe.
    Returns (row_number, income_col, confirmed_col, income_value, confirmed_value) or None. Found by header text."""
    for h, row in enumerate(values):
        labels = [str(v).strip().lower() for v in row]
        if 'grmc pay-period end' in labels and 'grmc income' in labels:
            date_col = labels.index('grmc pay-period end'); income_col = labels.index('grmc income')
            conf = [i for i, v in enumerate(labels) if v.startswith('confirmed') and i > income_col]
            if not conf: raise ValueError('Tracker header has no Confirmed? column after GRMC income')
            conf_col = conf[0]
            for r, data in enumerate(values[h + 1:], start=h + 2):
                data = list(data) + [''] * (max(date_col, income_col, conf_col) + 1 - len(data))
                d = data[date_col]
                if isinstance(d, (int, float)) and not isinstance(d, bool) and SHEETS_EPOCH + timedelta(days=int(d)) == ppe:
                    return r, income_col, conf_col, data[income_col], data[conf_col]
            return None
    raise ValueError('Tracker tab has no "GRMC pay-period end" / "GRMC income" header')

def plan_row_update(income, confirmed, amount, paid):
    """Decide how to record an amount in a tracker row. Returns ({'income': x, 'confirmed': y}, status).
    Rows marked Confirmed? = Y are never changed. An unconfirmed (N or blank) amount is a projection, so
    the real amount replaces it; a paid amount also sets Confirmed? = Y. Non-numeric cells are left for review."""
    if str(confirmed).strip().upper() == 'Y':
        return {}, 'already confirmed; left unchanged'
    raw = str(income).strip()
    writes = {}
    if raw in ('', '0', '0.0'):
        writes['income'] = float(amount); status = 'recorded'
    else:
        try: current = Decimal(raw.replace('$', '').replace(',', ''))
        except Exception: return {}, 'has a non-numeric amount; left for review'
        if current == Decimal(amount): status = 'matches the projected amount'
        else: writes['income'] = float(amount); status = 'replaced the projected amount'
    if paid: writes['confirmed'] = 'Y'
    elif str(confirmed).strip() == '': writes['confirmed'] = 'N'
    return writes, status

def update_tracker(creds, ppe, total):
    """Record an invoiced (not yet paid) amount in the family cash-flow tracker. Confirmed rows are never changed;
    an unconfirmed projected amount is replaced by the invoiced total.
    Messages avoid amounts because Actions logs of a public repository are public."""
    tracker_id = os.environ.get('TRACKER_ID', '').strip()
    if not tracker_id: print('Tracker: TRACKER_ID not set; skipped.'); return
    from googleapiclient.discovery import build
    api = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    titles = [s['properties']['title'] for s in api.spreadsheets().get(spreadsheetId=tracker_id, fields='sheets.properties.title').execute()['sheets']]
    wanted = os.environ.get('TRACKER_TAB', '').strip().lower() or 'goal 1099 income'
    tabs = [t for t in titles if t.strip().lower() == wanted]
    if not tabs: print('Tracker: tab not found; skipped.'); return
    q = tabs[0].replace("'", "''")
    values = api.spreadsheets().values().get(spreadsheetId=tracker_id, range=f"'{q}'!A1:Z200",
        valueRenderOption='UNFORMATTED_VALUE', dateTimeRenderOption='SERIAL_NUMBER').execute().get('values', [])
    cell = tracker_cells(values, ppe)
    if cell is None: print(f'Tracker: no row for pay period ending {ppe}; skipped.'); return
    row, income_col, conf_col, income, confirmed = cell
    writes, status = plan_row_update(income, confirmed, total, paid=False)
    data = []
    if 'income' in writes: data.append({'range': f"'{q}'!{col_letter(income_col)}{row}", 'values': [[writes['income']]]})
    if 'confirmed' in writes: data.append({'range': f"'{q}'!{col_letter(conf_col)}{row}", 'values': [[writes['confirmed']]]})
    if data:
        api.spreadsheets().values().batchUpdate(spreadsheetId=tracker_id, body={'valueInputOption': 'USER_ENTERED', 'data': data}).execute()
    print(f'Tracker: pay period ending {ppe}: invoiced total {status}.')

def confirmed_rates(env=None):
    """Hourly rates must be set explicitly (Actions variables TELE1_RATE and TELE2_RATE).
    There is no default, so a rate change can never be billed silently at an old rate."""
    env = os.environ if env is None else env
    rates = {}
    for kind, name in (('tele1', 'TELE1_RATE'), ('tele2', 'TELE2_RATE')):
        raw = (env.get(name) or '').strip()
        if not raw: raise SystemExit(f'Missing confirmed rate {name}; set it as a GitHub Actions variable')
        try: value = Decimal(raw)
        except Exception: raise SystemExit(f'{name} is not a number')
        if not value.is_finite() or value <= 0: raise SystemExit(f'{name} must be a positive amount')
        rates[kind] = raw
    return rates

def required_env(name):
    value=os.environ.get(name,'').strip()
    if not value: raise SystemExit(f'Missing required setting {name} (set it as a GitHub Actions secret)')
    return value

def fetch_tabs(start,end):
    """Read every tab whose title names a year in the period. Columns shift between tabs, so read wide and unformatted
    (dates arrive as serial numbers, not display text whose format varies by block)."""
    from googleapiclient.discovery import build
    sheet_id=required_env('SCHEDULE_ID')
    api=build('sheets','v4',credentials=credentials(),cache_discovery=False)
    meta=api.spreadsheets().get(spreadsheetId=sheet_id,fields='sheets.properties.title').execute()
    tabs=[]
    for s in meta['sheets']:
        title=s['properties']['title']
        if any(str(y) in title for y in {start.year,end.year}):
            escaped=title.replace("'","''")
            tabs.append(api.spreadsheets().values().get(spreadsheetId=sheet_id,range=f"'{escaped}'!A1:BZ260",
                valueRenderOption='UNFORMATTED_VALUE',dateTimeRenderOption='SERIAL_NUMBER').execute().get('values',[]))
    if not tabs: raise ValueError(f'No schedule tab title mentions {start.year} or {end.year}')
    return tabs

def main():
    p=argparse.ArgumentParser(); p.add_argument('--ppe'); p.add_argument('--draft',action='store_true'); p.add_argument('--fixture'); a=p.parse_args()
    today=datetime.now(ZoneInfo('Pacific/Guam')).date()
    end=date.fromisoformat(a.ppe) if a.ppe else last_period(today)
    if (end-ANCHOR).days % 14: raise ValueError('PPE is not on the confirmed fortnightly cycle')
    if end >= today: raise ValueError('Pay period has not closed in Guam')
    start=end-timedelta(days=13)
    rates=confirmed_rates()
    if a.fixture:
        data=json.loads(Path(a.fixture).read_text())
        tabs=data['tabs'] if isinstance(data,dict) else [data]
    else:
        tabs=fetch_tabs(start,end)
    rows=shifts_from_tabs(tabs,start,end,rates)
    if not rows: print('No shifts in closed period; no invoice created.'); return
    out=Path('output'); out.mkdir(exist_ok=True)
    pdf=out/f'GRMC-{end.isoformat()}.pdf'; make_pdf(rows,start,end,pdf,required_env('PROVIDER_NAME'),required_env('PROVIDER_BADGE'))
    with (out/'hours.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    if a.draft:
        from googleapiclient.discovery import build
        gmail=build('gmail','v1',credentials=credentials(),cache_discovery=False)
        subject=f'GRMC invoice PPE {end.isoformat()}'
        # Gmail replaces a custom Message-ID on drafts, so look for an existing draft or sent invoice by its exact subject.
        existing=gmail.users().messages().list(userId='me',q=f'in:anywhere subject:"{subject}"',includeSpamTrash=False).execute()
        if existing.get('messages'): print(f'Invoice "{subject}" already drafted or sent; skipped.')
        else:
            msg=EmailMessage(); to=required_env('INVOICE_TO'); msg['To']=to; msg['Subject']=subject
            greeting=to.split('@')[0].split('.')[0].title(); signoff=os.environ.get('SIGNOFF','').strip() or required_env('PROVIDER_NAME')
            msg.set_content(f'Hi {greeting},\n\nAttached is my invoice for this pay period.\n\nThank you,\n{signoff}\n\n[Review hours and signature before sending.]')
            msg.add_attachment(pdf.read_bytes(),maintype='application',subtype='pdf',filename=pdf.name)
            gmail.users().drafts().create(userId='me',body={'message':{'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()}}).execute()
            print('Gmail draft created; nothing sent.')
        update_tracker(credentials(),end,sum(Decimal(r['amount']) for r in rows))

if __name__=='__main__': main()
