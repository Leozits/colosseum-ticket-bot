# Colosseum ticket availability monitor — design

## Problem

The official Colosseum ticket site (`ticketing.colosseo.it`) shows every date as sold out through at least September 2026, while third-party resellers sell the same visit dates (including October) at ~3.5x the official price (€63 vs €18-25). The user wants to know the moment the official site opens availability for one of three specific dates, so they can buy at the official price before/if it sells out again — not to auto-purchase (the checkout flow, including a Cloudflare Turnstile challenge, is unexplored and out of scope).

## Target

- **Ticket type**: "FULL EXPERIENCE - SOTTERRANEI E ARENA" (`https://ticketing.colosseo.it/eventi/full-experience-sotterranei-e-arena/`, internal `page` id `225`)
- **Dates**: 23, 24, or 25 October 2026 (any one of the three — user is flexible, visiting Rome Oct 22-27, Vatican locked in for Oct 26)

## How the site works (confirmed by inspection)

- The ticket page loads a jQuery UI datepicker calendar. Selecting/viewing a month triggers `POST https://ticketing.colosseo.it/mtajax/calendars_month` with body `{action: "midaabc_calendars_month", page: <ticket id>, year, month}`.
- The response is JSON: `{success: true, data: [{startDateTime, endDateTime, originalCapacity, capacity, ...}, ...]}` — one entry per bookable time slot. `capacity: 0` means that slot is sold out; `capacity > 0` means seats remain.
- **This endpoint is behind an Octofence WAAP firewall.** A bare HTTP request (no real browser session) gets a 403 block page — confirmed by testing directly. It must be called from inside a real browser session (e.g., via `page.evaluate` after the ticket page has loaded), not via a plain HTTP client library.
- A Cloudflare Turnstile challenge exists somewhere in the purchase flow, but not on this read-only calendar call — irrelevant to monitoring, only relevant if this project is later extended to auto-purchase (it will not be, per scope below).

## Architecture

**Language/runtime**: Python + Playwright (headless Chromium), run as a scheduled GitHub Actions workflow.

**Why GitHub Actions instead of the user's PC**: the user only has a work laptop, which hibernates behind a BitLocker pre-boot PIN — Windows' "wake this computer to run a scheduled task" does not work across hibernation, and corporate policy likely disables wake timers anyway. GitHub Actions runs independently of any of the user's machines, on a cron schedule, for free (public repo = unlimited free minutes).

**Notification**: Discord webhook (user has no Telegram). A webhook URL is created once in a personal Discord server/channel and stored as a GitHub Actions secret (`DISCORD_WEBHOOK_URL`) — never committed to the repo.

**State persistence across runs**: GitHub Actions runners are ephemeral, so the workflow commits `state.json` and appends to `log.txt` back to the repo at the end of each run, using the automatic `GITHUB_TOKEN` (no extra secret needed).

## Data flow (one run)

1. Workflow triggers on a cron schedule (every 15 minutes).
2. Script checks today's date; if past 2026-10-25, exit immediately without hitting the site (the monitoring window is over — avoids needing to remember to disable the workflow manually).
3. Launch headless Chromium via Playwright, navigate to the ticket's event page.
4. Inside the page context, issue the same `calendars_month` request the site itself uses (`page: 225, year: 2026, month: 10`), reusing the page's real session/cookies so the WAF sees it as a normal browser request.
5. Parse the returned slots, group by calendar date, and for each of Oct 23/24/25 compute total remaining capacity (sum of `capacity` across that date's slots).
6. Load `state.json` (previous run's per-date capacity). For each of the 3 target dates, if capacity changed from 0 (or absent) to >0, that date just opened up.
7. If any date opened up: send a Discord message naming the date(s) and capacity found, with a direct link to the ticket page.
8. Append one line to `log.txt` with timestamp + capacity per date (kept even when nothing changed — this is the evidence log the user can look back on).
9. Write updated `state.json`, commit both files, push.

## Error handling

- If navigation fails, the response isn't the expected shape (e.g., a WAF block page came back instead of JSON), or any step throws: log an error line to `log.txt` (not a silent skip) and exit non-zero. The next scheduled run tries again independently.
- To avoid Discord spam from transient blips (site hiccup, one bad run), only send a Discord *failure* alert after 3 consecutive failed runs — but every individual failure still gets logged.

## Testing plan

1. Run once against a month already known to be fully sold out (e.g., September 2026) and confirm the script reports zero capacity for all days and sends no notification — sanity-checks parsing without relying on a lucky real opening.
2. Run once against October 2026 to see and log the real current state (expected: also sold out, consistent with the user's report) — this becomes the baseline in `state.json`.
3. Temporarily hand-edit `state.json` to simulate a prior "sold out" state, then feed the script a mocked "available" response to confirm the Discord message fires correctly and reads clearly.
4. Verify the GitHub Actions workflow itself runs on schedule and successfully commits state back (check Actions run history + repo commits after the first couple of scheduled runs).

## Explicit non-goals

- No auto-purchase / checkout automation (Turnstile + payment flow are out of scope, and the user doesn't want this — heads-up only).
- No monitoring of other ticket types or other dates — scoped to the one ticket type and 3 dates above. Easy to extend later if needed, not built generically now.
- No attempt to confirm or disprove the "bots/reseller deal" theory beyond the evidence log — that would require access the user doesn't have (reseller inventory, site internals).
