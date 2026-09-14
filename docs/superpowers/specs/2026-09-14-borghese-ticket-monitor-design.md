# Galleria Borghese ticket availability monitor — design

## Problem

Extend the same early-warning approach to a fourth official ticket site: the
Galleria Borghese in Rome, part of the same trip as the Colosseum monitor
(22–27 October 2026, excluding 26 October which is already booked for the
Vatican). Unlike the other three monitors, the primary goal here is
explicitly **understanding the availability pattern over time** (when slots
open, how long they last), not necessarily catching a sub-5-minute window —
the user asked for this framing directly, given the site's stronger
anti-bot protection makes an aggressive polling cadence riskier.

## Target

- **Site**: `tosc.it` (the TicketOne platform), specifically
  `https://www.tosc.it/artist/galleria-borghese/galleria-borghese-2253937/`
- **Ticket type**: standard/full-price entry ticket
- **Dates**: 22, 23, 24, 25, 27 October 2026 (26 excluded — already committed
  to the Vatican)

## How the site works (confirmed by inspection)

- The site is protected by **Akamai Bot Manager** — a materially different
  (and generally tougher) WAF than Octofence (Colosseum) or Cloudflare
  (Louvre). Confirmed by direct testing: a bare `curl` request gets no HTTP
  response at all — the TCP connection is reset immediately after the
  request is sent (`Recv failure: Connection was reset`) — and the resolved
  IP (`23.201.217.233`) is in Akamai's address space. The page also loads
  obfuscated Akamai sensor/telemetry endpoints (`/akam/13/...` and several
  randomized-looking paths that POST browser telemetry). This is a
  behavioral/fingerprinting system, not just a one-time JS challenge page —
  there is no guaranteed way to defeat it, only to look as close to a real,
  infrequent human visit as possible.
- As currently on sale (mid-September 2026), each day in the calendar is a
  `<div class="cal-month-day">`; the day number is a
  `<span class="day-number" data-cal-date="YYYY-MM-DD">` carrying a
  `cal-event-status-available` or `cal-event-status-unavailable` class. Days
  with no event on sale yet (outside the current sale window, or Mondays —
  the Galleria is closed Mondays) have no status class at all.
- Inside each day, an `.events-list` contains one `.event-time-pill` span
  per bookable time slot, e.g.
  `<span class="event-time-pill" data-availability-indicator="2" aria-label="Disponibilità moderata">19:00</span>`.
  `data-availability-indicator` and the human-readable `aria-label`
  ("Disponibilità alta/moderata/ridotta") together carry a 3-tier
  availability level (not just open/closed) — richer than any of the other
  three sites.
- As of 2026-09-14 the site's own sale window only extends through
  2026-10-18 (per the page's own "15/09/2026 – 18/10/2026" banner) — the
  22–27 October target window isn't on sale yet, same situation the other
  three monitors started from.
- Not yet confirmed: whether reaching October requires clicking a
  "next month" control (like the Colosseum/Louvre calendars) or whether the
  currently-loaded page already reflects the site's full current sale
  horizon on every fresh load. This will be established with a single
  careful live check during implementation, not through further
  exploration now.

## Architecture

Same repo, new sibling package `borghese_monitor/`, following the Louvre
monitor's shape exactly:

- `config.py` — ticket URL, target dates, state/log paths (own
  `borghese_monitor/state.json` and `borghese_monitor/log.txt`)
- `calendar_client.py` — patchright-driven DOM reading (site-specific)
- `messages.py` — availability message wording
- `run.py` — thin wiring into `monitor_common.engine.check_once()`

`monitor_common` (state, logger, diff, engine) is reused completely
unchanged.

### Collapsing the 3-tier availability signal

The day- and slot-level status stored in `state.json`/logged to
`log.txt` uses the same binary `"available"` / `"unavailable"` (day) and
`"available"` / `"closed"` (slot) vocabulary already used by the Colosseum
and Louvre monitors — `data-availability-indicator="0"` (no `aria-label`,
`aria-hidden="true"`) maps to `"unavailable"`/`"closed"`; any of the three
non-zero indicator values (alta/moderata/ridotta) maps to `"available"`.
This is a deliberate simplification, not an oversight: it lets
`monitor_common`'s existing diff/logging/alerting logic work completely
unmodified, and it still fully serves the stated goal — the `SLOTS` log
line already records the exact time each slot opened
(e.g. `SLOTS 2026-10-23:[19:00]`), which is the raw material for a
pattern analysis exactly like the one already done for the Colosseum log.
The finer alta/moderata/ridotta distinction is discarded for now; it's a
small, separate addition later if actually wanted, not built speculatively
here.

### Notification: email only

`_real_send_message` for this monitor calls only `send_email_message` —
not `send_whatsapp_message`. CallMeBot's free-tier quota is currently
exhausted (confirmed exhausted for the other monitors already), so
attempting WhatsApp here would just add guaranteed-failing noise to the
log for no benefit. Easy to add back once the quota situation is resolved.

### Check cadence: a deployment setting, not a code change

Like the other three monitors, the poll interval isn't hardcoded in
`run.py` — it's whatever the Windows Scheduled Task's repetition interval
is set to. **Recommended: 30 minutes**, materially gentler than the other
monitors' 5-minute cadence, given Akamai's tougher and more
behaviorally-aware protection and the goal being pattern observation
rather than sub-5-minute sniping. This is a one-line difference in the
`Register-ScheduledTask` command in the README, not a code difference.

## Data flow (one run)

1. Scheduled Task runs `python -m borghese_monitor.run` every 30 minutes.
2. `_real_fetch_days()` launches patchright (non-headless, off-screen
   window — same proven pattern as Colosseum/Louvre), navigates to the
   ticket page, and reads every `.day-number[data-cal-date]` currently
   rendered plus each day's `.event-time-pill` children.
3. Filters down to the 5 target dates; for each, day status is
   `"available"` if any of its time-slot pills has a non-zero
   `data-availability-indicator`, else `"unavailable"`.
4. `monitor_common.engine.check_once()` handles the rest exactly as for
   the other monitors: diff against previous state, log the run, alert by
   email only on a date newly becoming available, log (not alert) on
   failure.

## Error handling

Identical to the other three monitors via the shared engine: failures are
logged and counted in `state.json`, never alerted on. If Akamai blocks this
monitor the way Cloudflare blocked the Louvre one, the response is the
same precedent already set: disable the Scheduled Task, wait, retest
manually later — no automated guessing of cooldown duration this time
(that already proved unreliable for Louvre).

## Testing plan

1. Unit tests for `calendar_client.py`'s pure parsing logic (day/slot
   status classification from CSS classes and `data-availability-indicator`
   values) against fixture HTML/DOM fakes — no live network calls in tests,
   same as the other monitors.
2. Unit tests for `messages.py` and `run.py` wiring (email-only sending),
   mirroring the Louvre monitor's test structure.
3. One live manual run against the real site to confirm the fetch
   mechanism actually works end-to-end (including resolving whether month
   navigation is needed) and to establish the real baseline `state.json`.
4. Register the Scheduled Task at a 30-minute interval; watch
   `borghese_monitor/log.txt` for a stretch of clean `OK` lines before
   considering it healthy, same lesson learned from the Louvre monitor's
   rocky rollout.

## Explicit non-goals

- No attempt to preserve or act on the alta/moderata/ridotta distinction —
  collapsed to available/unavailable, as explained above.
- No WhatsApp notifications for this monitor while CallMeBot's quota is
  exhausted.
- No guarantee of evading Akamai's behavioral detection — if it gets
  blocked, the monitor is paused, not fought.
- No purchase automation, same as every other monitor in this repo.
