# Colosseum ticket availability monitor

Watches the official Colosseum ticketing site's booking calendar and posts to
a Discord channel the moment any date's status changes to "available" — in
particular the trip dates, Oct 23/24/25 2026, for the "Full Experience -
Sotterranei e Arena" ticket.

See `docs/superpowers/specs/2026-08-12-colosseum-ticket-monitor-design.md` for
the original design and `docs/superpowers/plans/2026-08-12-colosseum-ticket-monitor-plan.md`
for how it was built. Two things changed after the initial build (not yet
reflected in those docs) — both explained in detail in this file:

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

As of 2026-08-12, the site's calendar for this ticket doesn't extend past
September 2026 at all yet ("next month" is disabled beyond September) — Oct
23-25 aren't a real option on the official site yet for anyone, which is
probably why resellers already selling October dates are able to undercut
the "sold out" appearance (separate allocation, not necessarily bots). The
bot logs every day's status on every run, so it also doubles as a way to see
whether dates open up already sold out or genuinely bookable for a while
first.

## One-time setup

1. **Create a Discord webhook** in a server/channel you control:
   Discord → server → channel settings (gear icon) → Integrations → Webhooks → New Webhook → copy the URL.

2. **Store the webhook URL as a user environment variable** (read by the script, never committed):
   ```powershell
   [Environment]::SetEnvironmentVariable('DISCORD_WEBHOOK_URL', '<paste your webhook URL>', 'User')
   ```

3. **Install dependencies and the patchright browser binary**:
   ```bash
   pip install -r requirements.txt
   python -m patchright install chromium
   ```

4. **Register the Windows Scheduled Task** (repeats every 15 min while the PC is on/unlocked; catches up automatically if a run is missed while asleep):
   ```powershell
   $action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m colosseum_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 200)
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
   Register-ScheduledTask -TaskName "ColosseumTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Colosseum ticket calendar every 15 min while this PC is on; notifies via Discord."
   ```

The script itself no-ops (does nothing, touches no files) once run after
`MONITOR_END_DATE` in `colosseum_monitor/config.py`, so there's no need to
remember to disable the task after the trip.

**Known limitation:** this only checks while the laptop is on and unlocked
(corporate laptops here fully hibernate on sleep, so there's no reliable way
to wake it on a timer) — it won't catch something opening in the middle of
the night if the machine is asleep, only whenever it's next used or on the
next 15-minute tick while awake.

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
DISCORD_WEBHOOK_URL="<webhook url>" python -m colosseum_monitor.run
```

## GitHub Actions (disabled)

`.github/workflows/check.yml` is kept as `workflow_dispatch`-only (manual
trigger) for debugging — its scheduled cron trigger was removed because
GitHub-hosted runners get the same WAF block described above.
