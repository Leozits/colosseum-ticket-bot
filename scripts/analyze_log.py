import re
import sys
from collections import defaultdict
from datetime import datetime

LOG_PATH = "log.txt"

ok_re = re.compile(r"^(\S+) OK (.*)$")
slots_re = re.compile(r"^(\S+) SLOTS (.*)$")

# date -> list of (timestamp, status)
timeline = defaultdict(list)
# date -> list of (timestamp, {time: status})
slots_timeline = defaultdict(list)

with open(LOG_PATH, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        m = ok_re.match(line)
        if m:
            ts_str, rest = m.groups()
            ts = datetime.fromisoformat(ts_str)
            for pair in rest.split():
                date_str, status = pair.split("=")
                timeline[date_str].append((ts, status))
            continue
        m = slots_re.match(line)
        if m:
            ts_str, rest = m.groups()
            ts = datetime.fromisoformat(ts_str)
            for entry in rest.split():
                date_str, times = entry.split(":", 1)
                times = times.strip("[]")
                slots_timeline[date_str].append((ts, [t for t in times.split(",") if t]))

# Build "available" episodes per date: contiguous runs of status == available
episodes = []  # (date, start_ts, end_ts, n_checks, duration_seconds)
for date_str, points in timeline.items():
    points.sort()
    run_start = None
    run_last = None
    for ts, status in points:
        if status == "available":
            if run_start is None:
                run_start = ts
            run_last = ts
        else:
            if run_start is not None:
                episodes.append((date_str, run_start, run_last))
                run_start = None
                run_last = None
    if run_start is not None:
        episodes.append((date_str, run_start, run_last))

print(f"Total distinct 'available' episodes: {len(episodes)}")
print()

durations = []
for date_str, start, end in episodes:
    dur = (end - start).total_seconds()
    durations.append(dur)

if durations:
    durations.sort()
    print("Episode duration (time between first and last OK check that saw 'available'):")
    print(f"  min: {durations[0]/60:.1f} min")
    print(f"  median: {durations[len(durations)//2]/60:.1f} min")
    print(f"  max: {durations[-1]/60:.1f} min")
    zero = sum(1 for d in durations if d == 0)
    print(f"  episodes caught by only a single check (duration=0): {zero} of {len(durations)}")
print()

# Hour-of-day (UTC) distribution of episode starts
hour_counts = defaultdict(int)
weekday_counts = defaultdict(int)  # weekday of the check moment (real-world release day)
target_weekday_counts = defaultdict(int)  # weekday of the CALENDAR DATE that opened
for date_str, start, end in episodes:
    hour_counts[start.hour] += 1
    weekday_counts[start.strftime("%A")] += 1
    d = datetime.strptime(date_str, "%Y-%m-%d")
    target_weekday_counts[d.strftime("%A")] += 1

print("Episode start hour (UTC):")
for h in sorted(hour_counts):
    print(f"  {h:02d}:00 UTC -> {hour_counts[h]}")
print()

print("Real-world weekday when the opening was first observed:")
for wd, c in sorted(weekday_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {wd}: {c}")
print()

print("Weekday of the CALENDAR DATE that went available (which day-of-week tends to open):")
for wd, c in sorted(target_weekday_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {wd}: {c}")
print()

# Which specific time slots showed up as available, and how often
slot_counts = defaultdict(int)
for date_str, points in slots_timeline.items():
    for ts, times in points:
        for t in times:
            slot_counts[t] += 1

print("Specific time-slot appearances across all SLOTS log lines (raw count, not deduped by episode):")
for t, c in sorted(slot_counts.items(), key=lambda kv: kv[0]):
    print(f"  {t}: {c}")
print()

# Per-date summary: how many times each date flipped to available, distinct episodes
per_date_episode_count = defaultdict(int)
for date_str, start, end in episodes:
    per_date_episode_count[date_str] += 1

print("Per-date number of distinct 'available' episodes observed:")
for date_str in sorted(per_date_episode_count):
    print(f"  {date_str}: {per_date_episode_count[date_str]} episode(s)")
print()

# Check interval distribution (to know sampling granularity over time)
all_ts = sorted(set(ts for points in timeline.values() for ts, _ in points))
gaps = [(all_ts[i+1] - all_ts[i]).total_seconds() / 60 for i in range(len(all_ts)-1)]
if gaps:
    gaps.sort()
    print(f"Check interval (minutes) — min: {gaps[0]:.1f}, median: {gaps[len(gaps)//2]:.1f}, max: {gaps[-1]:.1f}")
    print(f"First check: {all_ts[0]}")
    print(f"Last check: {all_ts[-1]}")

# Has October ever appeared?
oct_dates = [d for d in timeline if d.startswith("2026-10")]
print()
print(f"October 2026 dates ever seen in calendar: {len(oct_dates)}")
