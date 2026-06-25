# TODO

Task checklist for the Gmail & Calendar agent (`danitzik`). Grouped by phase.

## Setup
- [x] Confirm Gmail API + Google Calendar API enabled in the Cloud project
- [x] Confirm OAuth Desktop client created and `credentials.json` in repo root
- [x] Confirm own account added under Test Users
- [x] Create `.env.example` and `.env` (with `GEMINI_API_KEY`)
- [x] Add `.gitignore` (`.env`, `token.json`, `credentials.json`, `.venv/`, `__pycache__/`)
- [x] Verify nothing secret is already in git history

## Core implementation (see PLAN.md)
- [x] Reuse `get_credentials()` from the test script (scopes: gmail.modify, calendar)
- [x] `fetch_recent_emails()` — 48h window
- [x] `is_formal_invite()` filter — drop calendar invites, keep free-text mail
- [x] Extract clean text body for the LLM
- [x] `classify_and_extract()` — Gemini call, JSON-only contract
- [x] Defensive JSON parse (strip fences, try/except, fail-safe to "not a meeting")
- [x] `resolve_weekday()` — next future occurrence
- [x] `find_slot()` — specific-time path + 09:00–17:00 first-fit path
- [x] `is_free()` — calendar availability check
- [x] `create_event()` — free branch
- [x] `send_reply()` — busy branch, both message variants
- [x] `main()` orchestration loop with per-email decision logging

## Scheduling rule (PRD.md §5)
- [x] Default duration 1 hour
- [x] Specific time busy → reply echoes requested time
- [ ] No time + day full → reply suggests another day

## Testing (acceptance criteria)
- [x] Seed: meeting request with time
- [x] Seed: meeting request without time
- [x] Seed: non-meeting email (must be ignored)
- [x] Optional seed: formal invite (must be filtered)
- [x] Free slot → event created
- [x] Busy slot → correct reply sent
- [x] Two-email-types distinction demonstrably works

## Deliverables / submission
- [x] PRD.md, README.md, PLAN.md, TODO.md at repo root
- [x] Share repo with lecturer (or make public)
- [x] Individual Moodle submission with the required PDF naming convention
- [x] Final pass: no secrets committed

## Nice-to-have
- [ ] Idempotency (avoid duplicate events on re-run)
- [ ] Timezone-aware datetimes throughout
