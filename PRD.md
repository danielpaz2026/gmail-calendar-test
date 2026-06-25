# PRD — Gmail & Calendar Meeting Agent

**Group code:** `danitzik`
**Assignment:** L08 Bonus — Gmail & Calendar Agent
**Status:** Specification (pre-implementation)

---

## 1. Purpose

An AI agent that monitors a Gmail inbox for **meeting requests expressed in
natural language**, and—when it finds one—checks Google Calendar for
availability and either books the meeting or replies that it cannot be held.

The agent operates on a single Gmail account via OAuth2. It runs as a
manually-invoked Python script. The reasoning step (detecting a meeting
request in free text and extracting its details) is delegated to a hosted LLM
(Google Gemini). All Gmail and Calendar actions are performed locally using
the user's stored `token.json`.

This document is the specification of record. It is intended to be handed to a
coding agent (Claude Code) to drive implementation.

---

## 2. Scope

### In scope
- Reading recent Gmail messages (rolling 48-hour window).
- Filtering to **regular emails only** — formal Calendar invitations are
  excluded.
- Sending each candidate email to Gemini for classification + extraction.
- Checking Google Calendar availability for a proposed slot.
- Creating a Calendar event when the slot is free.
- Sending a reply email when the slot is busy.

### Out of scope
- Reactive/push triggering (Gmail watch + Pub/Sub). Manual invocation only.
- Local LLM inference. Reasoning is via the hosted Gemini API.
- Handling formal `Calendar Invite` emails — these are deliberately filtered
  out; the task is specifically about free-text detection.
- Multi-account support.

---

## 3. Agent Workflow

```
fetch last 48h of mail
      │
      ▼
filter to regular emails (drop formal calendar invites)
      │
      ▼
for each email → Gemini: classify + extract  → JSON
      │
      ├─ not a meeting request → ignore
      │
      └─ meeting request
              │
              ▼
        resolve target date/time (ambiguity rule, §5)
              │
              ▼
        check Calendar availability for the slot
              │
              ├─ free → create Calendar event
              │
              └─ busy → send "can't make it" reply
```

---

## 4. Functional Requirements

| # | Requirement |
|---|-------------|
| FR-1 | Fetch Gmail messages from now back to 48 hours ago. |
| FR-2 | Exclude formal calendar-invite emails; process only regular free-text mail. |
| FR-3 | For each email, call Gemini once to classify (meeting request? yes/no) and extract structured details. |
| FR-4 | Distinguish at least two email types: a meeting-request email (acted on) and a non-meeting email (ignored). This must be demonstrable with test data. |
| FR-5 | Detect meeting intent in **natural language**, not only via sender/keyword rules. |
| FR-6 | Apply the ambiguity rule (§5) to resolve date and time. |
| FR-7 | Query Calendar availability for the resolved slot before booking. |
| FR-8 | If the slot is free, create a Calendar event. |
| FR-9 | If the slot is busy, send a reply email stating the meeting cannot be held. |
| FR-10 | Never hardcode secrets; load the Gemini key from the environment. |

---

## 5. Ambiguity & Scheduling Rule (Design Decision)

The assignment leaves under-specified emails (e.g. *"let's meet Tuesday"*) to
the implementer's judgment. We chose to **auto-schedule** rather than skip or
ask, in order to demonstrate end-to-end calendar reasoning. This is a more
aggressive interpretation than the spec's suggested "make date+time
mandatory" default, and is an intentional choice.

The rule:

1. **Resolve the weekday** to the next future occurrence (strictly after
   today; if today is the named weekday, use the occurrence 7 days out).
2. **Default duration:** 1 hour, unless the email states otherwise.
3. **If a specific time was given:** check that exact slot.
   - Free → book it.
   - Busy → reply, echoing the requested time
     (e.g. *"You suggested Tuesday at 14:00 but I'm booked then — can we
     reschedule?"*).
4. **If no time was given:** scan **09:00–17:00 first-fit** for a free 1-hour
   slot.
   - Book the first opening.
   - Whole window full → reply suggesting another day
     (e.g. *"Tuesday is fully booked — let's find another day."*).

Both entry points (specific time / no time) use the same availability
machinery; the presence of a time in the extracted JSON selects which path is
taken.

---

## 6. LLM Contract (Gemini)

One call per candidate email. The system instruction must require the model to
return **only** a JSON object — no prose, no markdown fences. The script must
still strip fences defensively and parse inside a try/except, treating any
unparseable response as "not a meeting request."

Expected JSON shape:

```json
{
  "is_meeting_request": true,
  "weekday": "tuesday",
  "date": null,
  "time": "14:00",
  "duration_minutes": 60,
  "participants": ["alice@example.com"],
  "location": "Zoom",
  "title": "Design review"
}
```

Field notes:
- `is_meeting_request` — boolean gate. If false, all other fields may be null.
- `weekday` / `date` — the model may return either a named weekday or an
  explicit date; the script resolves to a concrete date via §5.
- `time` — `null` when absent. Null selects the first-fit-scan path.
- `duration_minutes` — defaults to 60 if not stated.
- Missing fields → `null`, never omitted.

---

## 7. Non-Functional Requirements

- **Secrets:** Gemini API key from env var / `.env`. `.env`, `token.json`,
  and `credentials.json` must be in `.gitignore` before the first push.
- **Resilience:** a malformed LLM response for one email must not crash the
  run; it is logged and the email is treated as non-meeting.
- **Determinism:** given the same inbox and calendar, the agent produces the
  same actions (first-fit scanning is deterministic).
- **Idempotency (nice-to-have):** avoid creating duplicate events if run twice
  on the same email.

---

## 8. Tech Stack

- Python ≥ 3.10, managed with `uv`.
- `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`
  for Gmail + Calendar.
- Google Gemini API for reasoning.
- OAuth scopes: `gmail.modify`, `calendar`.

---

## 9. Acceptance Criteria

- Running the agent on a test inbox containing (a) a free-text meeting request
  and (b) a non-meeting email results in: an event or reply for (a), and no
  action for (b).
- A meeting request for a free slot creates a Calendar event.
- A meeting request for a busy slot sends an appropriate reply.
- A "weekday only, no time" email books the first free 09:00–17:00 hour, or
  replies if the day is full.
- No secrets are present in the repository history.
