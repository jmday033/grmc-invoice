from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path
scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/gmail.compose','https://www.googleapis.com/auth/gmail.readonly']
creds=InstalledAppFlow.from_client_secrets_file('credentials.json',scopes).run_local_server(port=0)
Path('token.json').write_text(creds.to_json())
print('Saved token.json. Add its contents as GOOGLE_TOKEN_JSON in GitHub Actions secrets. Do not commit it.')
