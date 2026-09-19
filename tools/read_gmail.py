import base64
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Strict Read-Only scope for F.R.E.D. 
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# JSON credentials in the home directory
FRED_DIR = Path.cwd() / 'credentials'
FRED_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = FRED_DIR / "credentials.json"
TOKEN_FILE = FRED_DIR / "token.json"

console = Console()

def authenticate_gmail():
    creds = None
    # Check if have token.json -> for persistent login, dn to keep logging in
    if TOKEN_FILE.exists(): creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                console.print(
                    '[bold red]Error:[/bold red] credentials.json not found in the current directory.\n'
                    'Please download your OAuth client credentials from Google Cloud Console.'
                )
                exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            
            # Opens a local browser tab for one-time login
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as token: token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def get_email_body(payload):
    """
    Extracts plain text body from the Multi Purpose Mail Extension (MIME) payload.
    MINE -> Text + HTML + Attachments
    """
    body_text = ''
    # Check for multi-part email
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                # decode the base64 data 
                # SMTP can only safely transmit 128 characters (a-zA-Z0-9)
                # Emojis are not within these 128 so they need to be encrypted
                if data:
                    body_text = base64.urlsafe_b64decode(data).decode(
                        'utf-8', errors='ignore'
                    )
                    break
                
    # Fallback for simple eamils
    elif 'body' in payload and 'data' in payload['body']:
        data = payload['body']['data']
        # decode the base64 data
        body_text = base64.urlsafe_b64decode(data).decode(
            'utf-8', errors='ignore'
        )

    return body_text.strip()


def list_recent_emails(query="in:inbox", max_count=10):
    """Fetches and displays the most recent emails from your inbox."""
    
    console.print('[dim cyan]Connecting to Gmail API...[/dim cyan]')
    service = authenticate_gmail()

    # Retrieve message IDs from the inbox
    results = service.users().messages().list(
        userId='me',
        q = query,
        maxResults = max_count
    ).execute()
    messages = results.get('messages', [])

    if not messages:
        console.print('[yellow]No messages found in your inbox.[/yellow]')
        return

    table = Table(title=f'Results for {query} -> max {max_count} emails.', show_lines=True)
    table.add_column('#', style='bold cyan', width=3)
    table.add_column('Date', style='green', width=16)
    table.add_column('From', style='bold blue', width=25)
    table.add_column('Subject & Snippet', style='white')

    for idx, msg in enumerate(messages, 1):
        detail = (service.users().messages().get(userId='me', id=msg['id'], format='full').execute())
        headers = detail.get('payload', {}).get('headers', [])
        # labels = detail.get('labelIds', [])

        subject = next(
            (h['value'] for h in headers if h['name'].lower() == 'subject'),
            '(No Subject)',
        )
        sender = next(
            (h['value'] for h in headers if h['name'].lower() == 'from'),
            'Unknown',
        )
        date = next(
            (h['value'] for h in headers if h['name'].lower() == 'date'),
            'Unknown',
        )
        snippet = detail.get('snippet', '')
        
        # clean up sender email
        clean_sender = sender.split('<')[0].strip() if '<' in sender else sender

        # Clean up date display (drops extra timezone text if long)
        clean_date = date.split('(')[0].strip() if '(' in date else date
        
        clean_date = date.split(' ')[0:3] 
        clean_date_str = " ".join(clean_date) if len(clean_date) >= 3 else date[:12]

        content_preview = f'[bold]{subject}[/bold]\n[dim]{snippet[:140]}...[/dim]' if len(snippet) > 140 else f'[bold]{subject}[/bold]\n[dim]{snippet}[/dim]'

        table.add_row(
            str(idx),
            # clean_date[:20],
            clean_date_str,
            clean_sender[:25],
            content_preview,
            # ', '.join(labels),
        )

    console.print(table)


if __name__ == '__main__':
    console.print(
        Panel.fit(
            '[bold green]F.R.E.D. Gmail Reader[/bold green]',
            border_style='green',
        )
    )
    list_recent_emails(query="label:Reading OR label:Github" ,max_count=10)