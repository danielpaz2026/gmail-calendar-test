# PLAN — Implementation

This is the build plan for `agent.py`, derived from `PRD.md`. It's structured
so a coding agent (Claude Code) can implement it module by module.

---

## Architecture

A single orchestrator script with clearly separated concerns. The existing
test script from the assignment already provides the auth + service-build
boilerplate; this plan extends it.

```
agent.py
├── auth            get_credentials()            [reuse from test script]
├── gmail_read      fetch_recent_emails(48h)
│                   is_formal_invite(msg) → bool  (filter)
├── llm             classify_and_extract(email) → dict   (Gemini call)
├── schedule        resolve_weekday(name) → date
│                   find_slot(date, time, duration) → (slot | None)
├── calendar        is_free(start, end) → bool
│                   create_event(...)
├── gmail_write     send_reply(thread, to, body)
└── main            orchestration loop
```

---

## Component notes

### auth
- Reuse `get_credentials()` from the assignment's test script verbatim.
- Scopes: `gmail.modify`, `calendar`.

### gmail_read
- Use a Gmail query to bound the window, e.g. `newer_than:2d`, then
  double-check each message's internal date against a precise 48h cutoff.
- **Filter (FR-2):** drop formal calendar invites. Detect by the presence of a
  `text/calendar` MIME part or an `.ics` attachment, and/or a `method=REQUEST`
  calendar header. Only plain free-text mail proceeds.
- Extract a clean text body (prefer `text/plain`; strip HTML if only
  `text/html` is present) to send to the LLM.

### llm (Gemini)
- One call per candidate email.
- System instruction: return **only** JSON, matching the contract in
  `PRD.md §6`. No prose, no markdown fences.
- Defensive parse: strip ```` ```json ```` / ```` ``` ```` fences if present,
  then `json.loads` inside try/except. On any failure → treat as
  `is_meeting_request: false`, log, continue.
- Read `GEMINI_API_KEY` from the environment.

### schedule  (implements PRD.md §5)
- `resolve_weekday(name)` → next future date strictly after today; if today
  is that weekday, +7 days.
- `find_slot(date, time, duration)`:
  - if `time` is present → return that single candidate slot.
  - if `time` is None → iterate 09:00→17:00 in `duration` steps, return the
    first slot that `is_free`. Return None if none free.
- Default `duration` = 60 min.

### calendar
- `is_free(start, end)`: use the freebusy query (or events.list over the
  window) on the primary calendar; free = no overlapping events.
- `create_event(...)`: as in the test script (summary, description, start,
  end, timezone-aware ISO).

### gmail_write
- `send_reply`: build a MIME reply, base64url-encode, send via
  `users().messages().send`. Reply in-thread where possible.
- Two body variants:
  - specific-time-busy → echo the requested time.
  - whole-day-full → suggest another day.

### main
For each fetched + filtered email:
1. `result = classify_and_extract(email)`
2. if not `result["is_meeting_request"]` → continue.
3. resolve date via `schedule`.
4. `slot = find_slot(...)`
5. if `slot` → `create_event(...)`; else → `send_reply(...)`.
6. log the decision for each email (audit trail / demo output).

---

## Build order

1. Wire up auth + `fetch_recent_emails`; print subjects to verify the window.
2. Add the formal-invite filter; verify invites are dropped.
3. Add the Gemini call with the JSON contract; print parsed results.
4. Add `schedule` + `calendar.is_free`; test slot resolution in isolation.
5. Wire the free → create branch.
6. Wire the busy → reply branch (both message variants).
7. End-to-end test with the two seed emails (meeting + non-meeting).

---

## Test data

Seed the inbox (or mock) with at least:
- A free-text meeting request **with** a time (e.g. "Tuesday at 2pm?").
- A free-text meeting request **without** a time (e.g. "let's meet Tuesday").
- A non-meeting email (e.g. a newsletter / report) — must be ignored.
- (Optional) A formal calendar invite — must be filtered out before the LLM.

---

## Open considerations (non-blocking)

- **Idempotency:** to avoid duplicate events on re-run, optionally label
  processed emails (Gmail label) or check for an existing event with the same
  title/time before creating.
- **Timezone:** all datetimes should be timezone-aware and consistent between
  availability check and event creation.
- **Partial-past day:** avoided by "next future occurrence," but if a same-day
  case ever arises, skip already-elapsed slots.
