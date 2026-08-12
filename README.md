# Colosseum ticket availability monitor

Checks the official Colosseum ticketing site every 15 minutes for openings on
Oct 23/24/25, 2026 for the "Full Experience - Sotterranei e Arena" ticket, and
posts to a Discord channel the moment one opens up. Runs entirely on GitHub
Actions — no computer of yours needs to stay on.

See `docs/superpowers/specs/2026-08-12-colosseum-ticket-monitor-design.md` for
the full design and `docs/superpowers/plans/2026-08-12-colosseum-ticket-monitor-plan.md`
for how it was built.

## One-time setup

1. **Create a Discord webhook** in a server/channel you control:
   Discord → server → channel settings (gear icon) → Integrations → Webhooks → New Webhook → copy the URL.

2. **Push this repo to GitHub** (public, so Actions minutes are free and unlimited):
   ```bash
   gh repo create colosseum-ticket-bot --public --source=. --push
   ```

3. **Add the webhook URL as a repo secret**:
   ```bash
   gh secret set DISCORD_WEBHOOK_URL --body "<paste your webhook URL>"
   ```

4. **The workflow starts running automatically** on its 15-minute schedule once
   pushed (GitHub Actions is on by default for a new repo). You can also
   trigger it manually from the repo's Actions tab ("Run workflow") to test it.

## Local development

```bash
python -m venv .venv
source .venv/Scripts/activate     # Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements-dev.txt
playwright install chromium
python -m pytest tests/ -v
```

## Running a check manually

```bash
DISCORD_WEBHOOK_URL="<webhook url>" python -m colosseum_monitor.run
```
