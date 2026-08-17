# One-time: run the Louvre monitor once after a cooldown from suspected
# Cloudflare blocking, and only resume regular 5-min monitoring
# (LouvreTicketMonitor) if that single check actually succeeded. Silent
# either way -- the user asked not to be alerted about monitor failures,
# only about real ticket availability. Removes itself after running once.
Set-Location "C:\Users\leonardosiqueira\colosseum-ticket-bot"
python -m louvre_monitor.run
$lastLine = Get-Content "louvre_monitor\log.txt" -Tail 1
if ($lastLine -match " OK ") {
    Enable-ScheduledTask -TaskName "LouvreTicketMonitor"
}
Unregister-ScheduledTask -TaskName "LouvreTicketMonitor-Retest" -Confirm:$false
