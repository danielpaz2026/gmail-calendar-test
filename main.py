from __future__ import annotations
import base64
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def get_credentials() -> Credentials:
    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")
    return creds


def create_gmail_draft(gmail_service):
    msg = EmailMessage()
    msg["To"] = "danielpazz2026@gmail.com"
    msg["Subject"] = "Test draft from Python"
    msg.set_content("This is a minimal test draft created by Python.")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = gmail_service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()
    return draft["id"]


def create_calendar_event(calendar_service):
    start = datetime.now().astimezone() + timedelta(hours=4)
    end = start + timedelta(hours=1)
    event = {
        "summary": "Python API test event",
        "description": "Minimal test event created by Python.",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    created = calendar_service.events().insert(
        calendarId="primary",
        body=event,
    ).execute()
    return created["id"], created.get("htmlLink")


def main():
    creds = get_credentials()
    gmail_service = build("gmail", "v1", credentials=creds)
    calendar_service = build("calendar", "v3", credentials=creds)
    draft_id = create_gmail_draft(gmail_service)
    event_id, event_link = create_calendar_event(calendar_service)
    print(f"Draft created: {draft_id}")
    print(f"Calendar event created: {event_id}")
    print(f"Event link: {event_link}")


if __name__ == "__main__":
    main()