# Colosseum ticket availability monitor

Watches the official Colosseum ticketing site's booking calendar and sends a
WhatsApp message and an email the moment any date's status changes to
"available" — including exactly which visit times are bookable that day —
in particular the trip dates, Oct 23/24/25 2026, for the "Full Experience -
Sotterranei e Arena" ticket.

See `docs/superpowers/specs/2026-08-12-colosseum-ticket-monitor-design.md` for
the original design and `docs/superpowers/plans/2026-08-12-colosseum-ticket-monitor-plan.md`
for how it was built. Several things changed after the initial build (not yet
reflected in those docs) — all explained in detail in this file:

1. **It runs locally (Windows Task Scheduler), not on GitHub Actions.** The
   site's WAF (Octofence) blocks GitHub-hosted runners' datacenter IPs.
2. **It reads the calendar's day-cell status directly (via [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python)
   and real mouse clicks), not the site's internal AJAX endpoint.** The WAF
   also blocks any network request triggered by injected script (e.g. a
   `page.evaluate` calling `fetch()`), even from an otherwise-legitimate,
   already-loaded page — but does *not* block requests fired by the page's
   own JS in response to a genuine, CDP-dispatched mouse click. So the bot
   drives the calendar exactly like a person would: it clicks the real
   "next month" arrow and reads back the resulting day-cell CSS classes
   (`soldout_day`, `closing_day`, or a plain clickable link = available).
   Plain Playwright wasn't enough on its own either — patchright specifically
   patches CDP-level leaks that this WAF was fingerprinting, and it must run
   **non-headless** (headless Chromium gets blocked outright); the browser
   window is positioned off-screen (`--window-position=-32000,-32000`) so it
   doesn't pop up in front of you.
3. **Notifications go by WhatsApp (via [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)) *and* email, not Discord.**
   `discord.com` doesn't even resolve on this network — a corporate DNS/firewall
   block, not something fixable in code. Both channels fire on every
   notification, independently — CallMeBot's free tier has confirmed
   "Message queued" for a message that never actually arrived, so email
   stays as a backup rather than WhatsApp being the sole channel.
4. **It also reports which specific visit times are open, not just that the
   day is "available".** Clicking a bookable day (a genuine click, same
   WAF-safe pattern as month navigation — soldout/closing days aren't even
   clickable) reveals a per-time-slot radio list; each carries a `disabled`
   attribute and a "Vendita chiusa o sold out" label when that exact time is
   unavailable. Only fetched for days already "available" at the day level.

As of 2026-08-12, the site's calendar for this ticket doesn't extend past
September 2026 at all yet ("next month" is disabled beyond September) — Oct
23-25 aren't a real option on the official site yet for anyone, which is
probably why resellers already selling October dates are able to undercut
the "sold out" appearance (separate allocation, not necessarily bots). The
bot logs every day's status on every run, so it also doubles as a way to see
whether dates open up already sold out or genuinely bookable for a while
first.

## One-time setup

1. **Activate CallMeBot for your WhatsApp number**: follow
   https://www.callmebot.com/blog/free-api-whatsapp-messages/ (add their
   number as a contact, send the activation message, they reply with an API key).

2. **Store your phone number and the API key as user environment variables** (read by the script, never committed):
   ```powershell
   [Environment]::SetEnvironmentVariable('WHATSAPP_PHONE', '<your number, country code, no +, e.g. 5511999999999>', 'User')
   [Environment]::SetEnvironmentVariable('CALLMEBOT_API_KEY', '<the API key CallMeBot sent you>', 'User')
   ```

3. **Generate a Gmail app password** for the email backup channel: needs
   2-Step Verification turned on first (Google Account → Security), then
   https://myaccount.google.com/apppasswords → create one for this. Store it too:
   ```powershell
   [Environment]::SetEnvironmentVariable('GMAIL_ADDRESS', '<your gmail address>', 'User')
   [Environment]::SetEnvironmentVariable('GMAIL_APP_PASSWORD', '<the 16-char app password, no spaces>', 'User')
   ```
   Optionally set `NOTIFY_TO_EMAIL` too if you want alerts sent somewhere other than the Gmail address itself.

4. **Install dependencies and the patchright browser binary**:
   ```bash
   pip install -r requirements.txt
   python -m patchright install chromium
   ```

5. **Register the Windows Scheduled Task** (repeats every 5 min while the PC is on/unlocked; catches up automatically if a run is missed while asleep):
   ```powershell
   $action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m colosseum_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
   Register-ScheduledTask -TaskName "ColosseumTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Colosseum ticket calendar every 5 min while this PC is on; notifies by WhatsApp and email."
   ```

   A real check takes ~20s end to end, so there's no risk of overlapping runs
   at this interval. The interval was originally 15 min; tightened to 5 min
   on request to reduce the chance of missing a short opening window.
   **Don't go much tighter than this** — the site actively fights automation
   (see WAF notes above), and hitting it dramatically more often than a real
   person would increases the chance it blocks this session again.

6. **(Optional but recommended) Register the keep-awake task**, so 5-min
   coverage survives this laptop's aggressive sleep whenever it's plugged in
   (see "Sleep / keep-awake" below for what it does and doesn't affect):
   ```powershell
   $action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "<path to>\colosseum-ticket-bot\scripts\keep_awake.py" -WorkingDirectory "<path to>\colosseum-ticket-bot"
   $trigger = New-ScheduledTaskTrigger -AtLogOn
   $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
   Register-ScheduledTask -TaskName "KeepAwakeOnAC" -Action $action -Trigger $trigger -Settings $settings -Description "Prevents sleep while on AC power so ColosseumTicketMonitor keeps running every 5 min; does not affect screen lock."
   ```

The script itself no-ops (does nothing, touches no files) once run after
`MONITOR_END_DATE` in `colosseum_monitor/config.py`, so there's no need to
remember to disable the task after the trip.

## Sleep / keep-awake

This laptop hibernates behind a BitLocker pre-boot PIN on sleep (not just a
screen lock), and Windows can't be told to wake it on a timer for that. The
`KeepAwakeOnAC` task works around this with `SetThreadExecutionState`, which
only suppresses the *system sleep* idle timer — it does **not** touch the
screen lock/screensaver timeout, so the machine still locks normally for
security. It only holds this while plugged into AC power (checked every 60s);
on battery it releases the hold and the laptop sleeps normally.

**With `KeepAwakeOnAC` running and the laptop plugged in**: real 15-minute
coverage, all day, even with the screen locked.

**On battery, or without that task registered**: checks only happen while
the laptop is actually awake and in use. Windows still runs the missed check
as soon as possible once you resume using it (`StartWhenAvailable`), so
there's always a catch-up check right when you sit back down — there's just
a gap for however long it was actually asleep.

## Local development

```bash
python -m venv .venv
source .venv/Scripts/activate     # Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements-dev.txt
python -m patchright install chromium
python -m pytest tests/ -v
```

## Running a check manually

```bash
WHATSAPP_PHONE="<your number>" CALLMEBOT_API_KEY="<api key>" GMAIL_ADDRESS="<your gmail>" GMAIL_APP_PASSWORD="<app password>" python -m colosseum_monitor.run
```

## GitHub Actions (disabled)

`.github/workflows/check.yml` is kept as `workflow_dispatch`-only (manual
trigger) for debugging — its scheduled cron trigger was removed because
GitHub-hosted runners get the same WAF block described above.

## Louvre monitor

Same idea as the Colosseum monitor above, watching
`https://ticket.louvre.fr/en/billetterie/3313` for dates 14–19 October 2026
(the user's Paris trip window) instead. Shares the same WhatsApp/email
credentials and setup — no new one-time setup needed beyond what's above.

The Louvre site is behind Cloudflare bot management rather than Octofence,
but the fix is identical: patchright, non-headless, off-screen window. Its
calendar exposes each day as a checkbox with a `disabled` attribute rather
than day-cell CSS classes, but the underlying "drive it like a real user"
approach carries over unchanged. Calendar month navigation is driven by
clicking the real "next"/"previous" arrows and then polling the visible
month header until it actually shows the expected month — a fixed delay
after each click was intermittently too short, and waiting on the site's
own network response event proved unreliable in practice.

Register its own Scheduled Task (independent of the Colosseum one, same
5-minute cadence):

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m louvre_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "LouvreTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Louvre ticket calendar every 5 min while this PC is on; notifies by WhatsApp and email."
```

State and logs live in `louvre_monitor/state.json` and `louvre_monitor/log.txt`
(kept separate from the Colosseum monitor's files at the repo root).

## Versailles monitor

Same idea again, watching `https://ticket.chateauversailles.fr` (Passport
ticket: château + gardens + Trianon Estate) for dates 14–19 October 2026.
Shares the same WhatsApp/email credentials and setup — no new one-time setup
needed.

Unlike the other two monitors, Versailles's calendar endpoint has **no
bot-blocking at all** — confirmed by a direct, cookie-less request returning
real data. This monitor makes a plain HTTP call and never opens a browser,
so it's much lighter and faster than the Colosseum/Louvre ones.

Register its own Scheduled Task (independent of the other two, same 5-minute
cadence):

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m versailles_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "VersaillesTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Versailles ticket calendar every 5 min; notifies by WhatsApp and email."
```

State and logs live in `versailles_monitor/state.json` and
`versailles_monitor/log.txt`.

**Note on what "open" means:** the calendar endpoint's `open` class reflects
whether the château accepts visitors that day at all, not necessarily
confirmed remaining quota for the Passport ticket specifically (that would
only be knowable further into the booking flow, which this monitor does not
drive). Day-level only, same scope as the other two monitors — see the
design doc for details.
