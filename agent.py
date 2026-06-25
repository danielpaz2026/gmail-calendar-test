"""Gmail & Calendar Meeting Agent (`danitzik`).

Reads recent Gmail messages, detects meeting requests written in natural
language (via Google Gemini), and either books them into Google Calendar or
replies that the meeting cannot be held. See PRD.md / PLAN.md for the spec.

Manually invoked:  uv run agent.py
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# Local timezone for all scheduling reasoning and calendar writes.
TZ = datetime.now().astimezone().tzinfo

LOOKBACK_HOURS = 48
WORKDAY_START = time(9, 0)
WORKDAY_END = time(17, 0)
DEFAULT_DURATION_MIN = 60

GEMINI_MODEL = "gemini-2.5-flash"

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# --------------------------------------------------------------------------- #
# auth  (reused from the assignment's test script)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# gmail_read
# --------------------------------------------------------------------------- #

@dataclass
class Email:
    msg_id: str
    thread_id: str
    subject: str
    from_addr: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body(payload: dict[str, Any]) -> tuple[str, bool]:
    """Return (plain-text body, is_formal_calendar_invite)."""
    plain: str | None = None
    html: str | None = None
    is_invite = False

    def walk(part: dict[str, Any]) -> None:
        nonlocal plain, html, is_invite
        mime = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})
        data = body.get("data")

        if mime == "text/calendar" or filename.lower().endswith(".ics"):
            is_invite = True
        if mime == "text/plain" and data and plain is None:
            plain = _decode_part(data)
        elif mime == "text/html" and data and html is None:
            html = _decode_part(data)

        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    text = plain if plain is not None else (_strip_html(html) if html else "")
    return text.strip(), is_invite


def fetch_recent_emails(gmail) -> list[Email]:
    """Fetch regular free-text emails from the last 48h (formal invites dropped)."""
    cutoff = datetime.now(tz=TZ) - timedelta(hours=LOOKBACK_HOURS)
    resp = gmail.users().messages().list(
        userId="me", q="newer_than:2d -in:chats", maxResults=50,
    ).execute()

    emails: list[Email] = []
    for ref in resp.get("messages", []):
        full = gmail.users().messages().get(
            userId="me", id=ref["id"], format="full",
        ).execute()

        # Precise 48h window check via internalDate (ms epoch).
        internal = datetime.fromtimestamp(int(full["internalDate"]) / 1000, tz=TZ)
        if internal < cutoff:
            continue

        payload = full.get("payload", {})
        headers = payload.get("headers", [])
        body, is_invite = _extract_body(payload)

        # FR-2: drop formal calendar invites; keep free-text mail only.
        method = ""
        ctype = _header(headers, "Content-Type")
        m = re.search(r"method=(\w+)", ctype, re.IGNORECASE)
        if m:
            method = m.group(1).upper()
        if is_invite or method == "REQUEST":
            print(f"  · skipped (formal invite): {_header(headers, 'Subject')!r}")
            continue

        emails.append(Email(
            msg_id=full["id"],
            thread_id=full["threadId"],
            subject=_header(headers, "Subject"),
            from_addr=_header(headers, "From"),
            headers={"Message-ID": _header(headers, "Message-ID"),
                     "References": _header(headers, "References")},
            body=body,
        ))
    return emails


# --------------------------------------------------------------------------- #
# llm (Gemini)
# --------------------------------------------------------------------------- #

SYSTEM_INSTRUCTION = """You classify emails and extract meeting details.
Decide whether the email is a request to schedule a meeting, written in natural
language. Reply with ONLY a single JSON object, no prose, no markdown fences.

JSON shape (include every field; use null when unknown):
{
  "is_meeting_request": boolean,
  "weekday": one of monday..sunday or null,
  "date": "YYYY-MM-DD" or null,
  "time": "HH:MM" (24h) or null,
  "duration_minutes": integer or null,
  "participants": [email addresses] or [],
  "location": string or null,
  "title": string or null
}

If is_meeting_request is false, the other fields may be null/empty."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def classify_and_extract(client: genai.Client, email: Email) -> dict[str, Any]:
    """One Gemini call per email. Fail-safe to 'not a meeting request'."""
    prompt = (
        f"From: {email.from_addr}\n"
        f"Subject: {email.subject}\n\n"
        f"{email.body}"
    )
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        data = json.loads(_strip_fences(resp.text or ""))
        if not isinstance(data, dict):
            raise ValueError("LLM did not return a JSON object")
    except Exception as exc:  # noqa: BLE001
        print(f"  · LLM parse failed ({exc}); treating as non-meeting")
        return {"is_meeting_request": False}

    data.setdefault("is_meeting_request", False)
    return data


# --------------------------------------------------------------------------- #
# schedule  (PRD.md §5)
# --------------------------------------------------------------------------- #

def resolve_weekday(name: str, today: date | None = None) -> date | None:
    today = today or datetime.now(tz=TZ).date()
    idx = WEEKDAYS.get((name or "").strip().lower())
    if idx is None:
        return None
    delta = (idx - today.weekday()) % 7
    if delta == 0:  # today is that weekday → next occurrence, 7 days out
        delta = 7
    return today + timedelta(days=delta)


def resolve_date(extracted: dict[str, Any]) -> date | None:
    if extracted.get("date"):
        try:
            return date.fromisoformat(extracted["date"])
        except ValueError:
            pass
    if extracted.get("weekday"):
        return resolve_weekday(extracted["weekday"])
    return None


def find_slot(
    calendar, target: date, time_str: str | None, duration_min: int,
) -> tuple[datetime, datetime] | None:
    """Specific-time path (single slot) or 09:00-17:00 first-fit scan."""
    dur = timedelta(minutes=duration_min)

    if time_str:
        try:
            hh, mm = (int(x) for x in time_str.split(":")[:2])
        except (ValueError, IndexError):
            return None
        start = datetime.combine(target, time(hh, mm), tzinfo=TZ)
        end = start + dur
        return (start, end) if is_free(calendar, start, end) else None

    cursor = datetime.combine(target, WORKDAY_START, tzinfo=TZ)
    day_end = datetime.combine(target, WORKDAY_END, tzinfo=TZ)
    while cursor + dur <= day_end:
        end = cursor + dur
        if is_free(calendar, cursor, end):
            return (cursor, end)
        cursor += dur
    return None


# --------------------------------------------------------------------------- #
# calendar
# --------------------------------------------------------------------------- #

def is_free(calendar, start: datetime, end: datetime) -> bool:
    resp = calendar.freebusy().query(body={
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "items": [{"id": "primary"}],
    }).execute()
    busy = resp["calendars"]["primary"]["busy"]
    return len(busy) == 0


def event_exists(calendar, start: datetime, end: datetime, title: str) -> bool:
    """Idempotency: skip if an event with same title already overlaps the slot."""
    resp = calendar.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
    ).execute()
    return any(e.get("summary") == title for e in resp.get("items", []))


def create_event(
    calendar, start: datetime, end: datetime, summary: str,
    description: str, attendees: list[str], location: str | None,
) -> tuple[str, str]:
    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    created = calendar.events().insert(calendarId="primary", body=body).execute()
    return created["id"], created.get("htmlLink", "")


# --------------------------------------------------------------------------- #
# gmail_write
# --------------------------------------------------------------------------- #

def send_reply(gmail, email: Email, body_text: str) -> str:
    to_addr = parseaddr(email.from_addr)[1]
    msg = EmailMessage()
    msg["To"] = to_addr
    subject = email.subject or ""
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if email.headers.get("Message-ID"):
        msg["In-Reply-To"] = email.headers["Message-ID"]
        refs = email.headers.get("References", "")
        msg["References"] = (refs + " " + email.headers["Message-ID"]).strip()
    msg.set_content(body_text)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = gmail.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": email.thread_id},
    ).execute()
    return sent["id"]


def busy_specific_time_body(target: date, time_str: str) -> str:
    day = target.strftime("%A %d %b")
    return (
        f"Thanks for the note. You suggested {day} at {time_str}, but I'm "
        f"already booked then — could we reschedule to another time?"
    )


def day_full_body(target: date) -> str:
    day = target.strftime("%A %d %b")
    return (
        f"Thanks for the note. {day} is fully booked for me — "
        f"let's find another day that works."
    )


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def handle_email(gmail, calendar, client: genai.Client, email: Email) -> None:
    print(f"\n▶ {email.subject!r} from {email.from_addr}")
    extracted = classify_and_extract(client, email)

    if not extracted.get("is_meeting_request"):
        print("  · not a meeting request → ignored")
        return

    target = resolve_date(extracted)
    if target is None:
        print("  · meeting request but no resolvable date → skipped")
        return

    time_str = extracted.get("time")
    duration = extracted.get("duration_minutes") or DEFAULT_DURATION_MIN
    title = extracted.get("title") or "Meeting"
    location = extracted.get("location")
    attendees = extracted.get("participants") or []
    sender = parseaddr(email.from_addr)[1]
    if sender and sender not in attendees:
        attendees.append(sender)

    slot = find_slot(calendar, target, time_str, duration)

    if slot:
        start, end = slot
        if event_exists(calendar, start, end, title):
            print(f"  · event {title!r} already exists at {start} → skipped")
            return
        description = f"Auto-booked from email: {email.subject}"
        event_id, link = create_event(
            calendar, start, end, title, description, attendees, location)
        print(f"  ✓ booked {title!r} {start:%a %d %b %H:%M}-{end:%H:%M}  {link}")
    else:
        if time_str:
            body = busy_specific_time_body(target, time_str)
        else:
            body = day_full_body(target)
        reply_id = send_reply(gmail, email, body)
        print(f"  ✗ slot unavailable → reply sent ({reply_id})")


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set (see .env.example).")

    creds = get_credentials()
    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    client = genai.Client(api_key=api_key)

    print(f"Fetching mail from the last {LOOKBACK_HOURS}h …")
    emails = fetch_recent_emails(gmail)
    print(f"{len(emails)} regular email(s) to process.")

    for email in emails:
        try:
            handle_email(gmail, calendar, client, email)
        except Exception as exc:  # noqa: BLE001 — one bad email must not crash the run
            print(f"  ! error handling {email.subject!r}: {exc}")

    print("\nDone.")


if __name__ == "__main__":
    main()
