# TODO

Task checklist for the Gmail & Calendar agent (`danitzik`). Grouped by phase.

## Setup
- [ ] Confirm Gmail API + Google Calendar API enabled in the Cloud project
- [ ] Confirm OAuth Desktop client created and `credentials.json` in repo root
- [ ] Confirm own account added under Test Users
- [ ] Create `.env.example` and `.env` (with `GEMINI_API_KEY`)
- [ ] Add `.gitignore` (`.env`, `token.json`, `credentials.json`, `.venv/`, `__pycache__/`)
- [ ] Verify nothing secret is already in git history

## Core implementation (see PLAN.md)
- [ ] Reuse `get_credentials()` from the test script (scopes: gmail.modify, calendar)
- [ ] `fetch_recent_emails()` — 48h window
- [ ] `is_formal_invite()` filter — drop calendar invites, keep free-text mail
- [ ] Extract clean text body for the LLM
- [ ] `classify_and_extract()` — Gemini call, JSON-only contract
- [ ] Defensive JSON parse (strip fences, try/except, fail-safe to "not a meeting")
- [ ] `resolve_weekday()` — next future occurrence
- [ ] `find_slot()` — specific-time path + 09:00–17:00 first-fit path
- [ ] `is_free()` — calendar availability check
- [ ] `create_event()` — free branch
- [ ] `send_reply()` — busy branch, both message variants
- [ ] `main()` orchestration loop with per-email decision logging

## Scheduling rule (PRD.md §5)
- [ ] Default duration 1 hour
- [ ] Specific time busy → reply echoes requested time
- [ ] No time + day full → reply suggests another day

## Testing (acceptance criteria)
- [ ] Seed: meeting request with time
- [ ] Seed: meeting request without time
- [ ] Seed: non-meeting email (must be ignored)
- [ ] Optional seed: formal invite (must be filtered)
- [ ] Free slot → event created
- [ ] Busy slot → correct reply sent
- [ ] Two-email-types distinction demonstrably works

## Deliverables / submission
- [ ] PRD.md, README.md, PLAN.md, TODO.md at repo root
- [ ] Share repo with lecturer (or make public)
- [ ] Individual Moodle submission with the required PDF naming convention
- [ ] Final pass: no secrets committed

## Nice-to-have
- [ ] Idempotency (avoid duplicate events on re-run)
- [ ] Timezone-aware datetimes throughout
