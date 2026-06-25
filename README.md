# Gmail & Calendar Meeting Agent (`danitzik`)

An AI agent that reads recent Gmail messages, detects **meeting requests
written in natural language**, and books them into Google Calendar — or
replies that the meeting can't be held when the slot is taken.

Built for the L08 bonus assignment. Reasoning is delegated to Google Gemini;
all Gmail/Calendar actions run locally via OAuth2.

---

## What it does

1. Fetches Gmail messages from the last **48 hours**.
2. Filters to **regular emails** (formal calendar invites are ignored).
3. Sends each to **Gemini**, which decides whether it's a meeting request and
   extracts the details as JSON.
4. Resolves the proposed date/time (see scheduling rule below).
5. Checks **Google Calendar** for availability.
6. **Free** → creates the event. **Busy** → sends a reply suggesting a
   reschedule.

It runs as a manually-invoked script — no daemon, no scheduler required.
** The idea is to invoke it as scheduled job every 48H

---

## Scheduling rule

- Deterministic date and time, use it.
- Weekday names resolve to the **next future occurrence**.
- Default meeting length is **1 hour**.
- **Specific time given:** check that slot; book if free, reply (echoing the
  time) if busy.
- **No time given:** scan **09:00–17:00** first-fit for a free hour; book the
  first opening, or reply suggesting another day if the window is full.

This is an intentional "auto-schedule" choice rather than skipping
under-specified emails — see `PRD.md §5`.

---

## Setup

> **Prerequisite:** A Google Cloud project with the Gmail API and Google
> Calendar API enabled, an OAuth Desktop client, and your account added as a
> Test User. See the assignment's Appendix A for the full console walkthrough.
> Place the downloaded `credentials.json` in the project root.

```bash
# 1. Install uv (if not already installed)
#    Windows:  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
#    macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Provide your Gemini API key (do NOT hardcode it)
cp .env.example .env
#    then edit .env and set GEMINI_API_KEY=...

# 3. Sync dependencies and run
uv sync
uv run agent.py
```

On the first run a browser window opens for Google sign-in; afterwards a
`token.json` is created and reused.

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Hosted LLM key, loaded from `.env` / environment. |

OAuth scopes used: `gmail.modify`, `calendar`.

---

## Security

`.env`, `token.json`, and `credentials.json` are git-ignored and must **never**
be committed. They contain credentials for a live Google account.

---

## Project files

| File | Purpose |
|------|---------|
| `PRD.md` | Full product/requirements spec — the source of record. |
| `PLAN.md` | Implementation plan and architecture. |
| `TODO.md` | Task checklist. |
| `agent.py` | The agent (to be implemented). |
| `pyproject.toml` | Dependencies / uv project file. |

---

## Status

Specification complete; implementation in complete.
