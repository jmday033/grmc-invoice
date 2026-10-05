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

def credentials():
    from google.oauth2.credentials import Credentials
    return Credentials.from_authorized_user_info(json.loads(os.environ['GOOGLE_TOKEN_JSON']))

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
    rates={'tele2':(os.environ.get('TELE2_RATE') or '75'),'tele1':os.environ.get('TELE1_RATE') or '75'}
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
        key=f'<grmc-{end.isoformat()}@invoice.local>'
        existing=gmail.users().messages().list(userId='me',q=f'in:anywhere rfc822msgid:{key}').execute()
        if existing.get('messages'): print('Invoice already drafted or sent; skipped.'); return
        msg=EmailMessage(); to=required_env('INVOICE_TO'); msg['To']=to; msg['Subject']=f'GRMC invoice PPE {end.isoformat()}'; msg['Message-ID']=key
        greeting=to.split('@')[0].split('.')[0].title(); signoff=os.environ.get('SIGNOFF','').strip() or required_env('PROVIDER_NAME')
        msg.set_content(f'Hi {greeting},\n\nAttached is my invoice for this pay period.\n\nThank you,\n{signoff}\n\n[Review hours and signature before sending.]')
        msg.add_attachment(pdf.read_bytes(),maintype='application',subtype='pdf',filename=pdf.name)
        gmail.users().drafts().create(userId='me',body={'message':{'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()}}).execute()
        print('Gmail draft created; nothing sent.')

if __name__=='__main__': main()
