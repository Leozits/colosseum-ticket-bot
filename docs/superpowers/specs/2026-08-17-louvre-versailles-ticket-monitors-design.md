# Louvre + Palace of Versailles ticket availability monitors — design

## Problem

The user is in Paris 14–19 October 2026 and wants the same early-warning system
built for the Colosseum ([2026-08-12 design](2026-08-12-colosseum-ticket-monitor-design.md))
applied to two more official ticket sites: the Musée du Louvre and the Château
de Versailles. Goal is the same: know the moment a date in that window opens
up for booking on the *official* site, so the user can buy at the official
price — not auto-purchase.

## Target

- **Louvre** (`ticket.louvre.fr`): standard permanent-collections ticket
  (`/en/billetterie/3313`), any date 14–19 October 2026.
- **Versailles** (`ticket.chateauversailles.fr`): Passport ticket (château +
  gardens + Trianon Estate), any date 14–19 October 2026.

## How each site works (confirmed by inspection)

**Louvre** is behind Cloudflare bot management. A plain HTTP request to
either the ticket page or its calendar endpoint gets a 403 with
`Cf-Mitigated: challenge` and a "Just a moment..." interstitial — confirmed by
direct `curl` testing. It must be driven from inside a real, JS-executing
browser, the same constraint (and the same patchright-based solution) as the
Colosseum. Once past the challenge, the page calls
`GET /get-calendar-by-month?year=YYYY&month=MM`, which returns clean JSON:
`{"Available": ["2026,08,21", ...], "Disabled": [...], "Highlight": [...]}`.

**Versailles** has no bot-blocking on its calendar endpoint — confirmed by a
direct, cookie-less `curl POST` to `/en/api/calendar` returning a real 200
with calendar HTML. The response is an HTML fragment: each day is a
`<div>`/`<button>` with id `agenda--calendar--date-YYYY-MM-DD` and a class of
`agenda--calendar-slot open|closed|disabled` (plus `theme--*` classes for
which shows run that day, irrelevant to the Passport ticket). This site needs
no browser at all — a plain `httpx` POST is sufficient.

Neither site's calendar response was inspected for the Louvre/Versailles
equivalent of "which specific time slots are open within a day" (the
Colosseum bot grew that capability in a later iteration, not the initial
build). This design scopes both new monitors to **day-level availability
only**, matching how the Colosseum monitor itself started — see Non-goals.

## Architecture

Same repo (`colosseum-ticket-bot`), two new sibling packages:

- `louvre_monitor/` — own `state.json`, `log.txt`
- `versailles_monitor/` — own `state.json`, `log.txt`

Each has its own Windows Scheduled Task (same 5-minute cadence as the
Colosseum monitor to start), runs and fails independently, and never touches
the other's files.

### Shared library

Reading the existing `colosseum_monitor` code turned up more directly
reusable logic than initially scoped — most of it has no Colosseum-specific
content at all. Extracting it now avoids copy-pasting ~150 lines of
already-tested logic twice. New top-level package **`monitor_common/`**:

| Module | Extracted from | Contents |
|---|---|---|
| `monitor_common/state.py` | `colosseum_monitor/state.py` | `load_state`/`save_state`, verbatim |
| `monitor_common/logger.py` | `colosseum_monitor/logger.py` | all log-line formatting, verbatim |
| `monitor_common/diff.py` | `colosseum_monitor/availability.py` | `find_status_changes`/`find_newly_available` only — the DOM/CSS parsing functions (`classify_day_status`, `parse_calendar_title`, etc.) are Colosseum-specific and stay put |
| `monitor_common/notifier.py` | `colosseum_monitor/notifier.py` | `send_whatsapp_message`/`send_email_message` only — the `format_*_message` text functions are site-specific wording and stay in each site package |
| `monitor_common/engine.py` | `colosseum_monitor/run.py` | the generic `check_once()` skeleton (load state → fetch → diff → log → notify → save state → failure-threshold handling), parameterized by a `fetch_days` callable, a `format_availability_message` callable, and a small config object (ticket URL, state/log paths, monitor end date, failure threshold) |

`colosseum_monitor` is refactored to import from `monitor_common` instead of
containing its own copies — pure refactor, no behavior change, existing
tests move/adapt to cover the shared module instead of duplicating coverage.

Each site package then only contains what's actually specific to it:

- `config.py` — ticket URL, target date window, state/log paths, SMTP subject line
- `calendar_client.py` — the fetch mechanism (patchright for Louvre, `httpx` for Versailles) plus response parsing into `{"statuses": {date: "available"|"unavailable"}, "slots": {}}` (empty `slots` dict for now — see Non-goals)
- `messages.py` — the two site-specific message strings (Portuguese, matching the Colosseum bot's tone)
- `run.py` — thin entry point wiring its own config/fetcher/messages into `monitor_common.engine.check_once()`

## Data flow (one run, either site)

1. Scheduled Task runs `python -m <site>_monitor.run`.
2. `check_once()` (shared engine) loads previous `state.json`.
3. Site-specific `fetch_days()` runs:
   - **Louvre**: launch patchright (non-headless, off-screen window, same as Colosseum), navigate to the ticket page, wait past the Cloudflare interstitial, call `get-calendar-by-month` for October 2026 from inside the page context, filter the `Available`/`Disabled` lists down to the 14–19 window.
   - **Versailles**: plain `httpx.post()` to `/en/api/calendar` for October 2026 (no browser), parse the returned HTML fragment for `agenda--calendar-slot` classes on the 14–19 window's date ids.
4. Diff against previous state (`monitor_common.diff`); log the run and any changes (`monitor_common.logger`).
5. If any of the 6 target dates newly show "available", format and send the site's message via both WhatsApp and email (`monitor_common.notifier`).
6. Save updated state.

## Error handling

Identical policy to the Colosseum monitor, inherited for free via the shared
`engine.check_once()`: any fetch failure is logged every run; a
WhatsApp+email alert only fires after 3 consecutive failures (to avoid spam
from transient blips); a notification-send failure is logged but never
blocks `state.json` from being saved (otherwise a change would be
re-detected and re-alerted, and re-fail, on every subsequent run).

Both monitors no-op past 19 October 2026, same pattern as
`MONITOR_END_DATE` in the Colosseum config.

## Testing plan

1. Unit tests for the new `monitor_common` modules (moved/adapted from the
   existing Colosseum test suite) — verify the refactor didn't change
   behavior.
2. Unit tests for each site's `calendar_client.py` parsing logic, against
   fixture responses (a real captured `Available`/`Disabled` JSON payload for
   Louvre, a real captured HTML fragment for Versailles) — no live network
   calls in tests.
3. One live manual run of each site's `run.py` against the real October 2026
   calendar (expected: all 6 dates show "unavailable"/sold-out today) to
   confirm the fetch mechanism actually works end-to-end and establish the
   real baseline `state.json`.
4. Hand-edit `state.json` to simulate a prior "unavailable" state and feed a
   mocked "available" response through `check_once()` to confirm the
   WhatsApp+email message fires and reads correctly, for both sites.
5. Confirm both new Windows Scheduled Tasks are registered and complete a
   couple of real scheduled runs without error.

## Explicit non-goals

- **No time-slot-level detail for v1** — day-level "available/unavailable"
  only, for both sites. The Colosseum monitor only grew per-time-slot
  reporting after the day-level version had already been running; the same
  path is available here later if wanted, once each site's slot-detail
  response shape has actually been inspected.
- No auto-purchase/checkout automation for either site.
- No monitoring of any ticket type other than the two named above, and no
  dates outside 14–19 October 2026.
- No attempt to make the Louvre Cloudflare challenge solvable via anything
  lighter than a real browser — patchright non-headless is the proven
  approach in this repo already and is reused as-is.
