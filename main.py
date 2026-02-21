#!/usr/bin/env python3
"""
personal-dev-bench: Developer tools and experiments for productivity
and workflow optimization.

Provides benchmarking utilities, task timing, habit tracking,
and workflow analysis from the command line.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("PDBENCH_DATA", Path.home() / ".personal-dev-bench"))
TIMES_FILE = DATA_DIR / "task_times.csv"
METRICS_FILE = DATA_DIR / "metrics.json"
BENCHMARKS_DIR = DATA_DIR / "benchmarks"


def ensure_dirs():
    """Create data directories and initialize files if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    if not TIMES_FILE.exists():
        with open(TIMES_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "task", "duration_seconds", "tags"])
    if not METRICS_FILE.exists():
        with open(METRICS_FILE, "w") as f:
            json.dump({"sessions": [], "streaks": {}, "totals": {}}, f, indent=2)


def log_task(task, duration, tags=None):
    """Record a completed task with its duration."""
    ensure_dirs()
    now = datetime.now().isoformat()
    tag_str = ",".join(tags or [])
    with open(TIMES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([now, task, round(duration, 2), tag_str])
    print(f"[logged] task='{task}' duration={duration:.1f}s tags=[{tag_str}]")


def cmd_timer(args):
    """Simple task timer: start/stop workflow timing."""
    if args.action == "start":
        ensure_dirs()
        marker = DATA_DIR / "active_timer.json"
        if marker.exists():
            existing = json.loads(marker.read_text())
            print(f"[warn] timer already running for '{existing['task']}' since {existing['start']}")
            return
        task_name = " ".join(args.task)
        entry = {"task": task_name, "start": datetime.now().isoformat(), "tags": args.tags or []}
        marker.write_text(json.dumps(entry, indent=2))
        print(f"[timer] started: '{task_name}'")
    elif args.action == "stop":
        marker = DATA_DIR / "active_timer.json"
        if not marker.exists():
            print("[error] no active timer found. run 'main.py timer start <task>'")
            return
        entry = json.loads(marker.read_text())
        start_dt = datetime.fromisoformat(entry["start"])
        duration = (datetime.now() - start_dt).total_seconds()
        log_task(entry["task"], duration, entry.get("tags"))
        marker.unlink()
    elif args.action == "status":
        marker = DATA_DIR / "active_timer.json"
        if not marker.exists():
            print("[timer] no active timer")
            return
        entry = json.loads(marker.read_text())
        elapsed = (datetime.now() - datetime.fromisoformat(entry["start"])).total_seconds()
        print(f"[timer] '{entry['task']}' — {elapsed:.0f}s elapsed")
    else:
        print("[error] use start|stop|status")


def cmd_benchmark(args):
    """Run command benchmarks and record results."""
    ensure_dirs()
    command = args.cmd
    iterations = args.iterations
    results = []
    print(f"[bench] running {iterations} iterations of: {' '.join(command)}")
    for i in range(1, iterations + 1):
        start = time.perf_counter()
        proc = subprocess.run(command, capture_output=True, text=True)
        elapsed = time.perf_counter() - start
        results.append(elapsed)
        print(f"  [{i}/{iterations}] {elapsed:.4f}s (rc={proc.returncode})")
    stats = {
        "command": " ".join(command),
        "iterations": iterations,
        "min": round(min(results), 6),
        "max": round(max(results), 6),
        "mean": round(sum(results) / len(results), 6),
        "total": round(sum(results), 6),
        "timestamp": datetime.now().isoformat(),
    }
    label = args.label or f"bench_{int(time.time())}"
    output_file = BENCHMARKS_DIR / f"{label}.json"
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n[bench] min={stats['min']}s  max={stats['max']}s  mean={stats['mean']}s")
    print(f"[bench] results saved to {output_file}")


def cmd_report(args):
    """Generate a productivity report from logged data."""
    ensure_dirs()
    if not TIMES_FILE.exists() or TIMES_FILE.stat().st_size <= 50:
        print("[report] no task data available yet. log some tasks first.")
        return
    rows = []
    with open(TIMES_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        print("[report] no records found.")
        return
    lookback_days = args.days
    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
            if ts >= cutoff:
                recent.append(row)
        except (ValueError, KeyError):
            continue
    total_time = sum(float(r["duration_seconds"]) for r in recent)
    task_counts = {}
    for r in recent:
        task = r["task"]
        task_counts[task] = task_counts.get(task, 0) + 1
    top_tasks = sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    tag_freq = {}
    for r in recent:
        for tag in r.get("tags", "").split(","):
            tag = tag.strip()
            if tag:
                tag_freq[tag] = tag_freq.get(tag, 0) + 1
    top_tags = sorted(tag_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\n{'=' * 50}")
    print(f"  Productivity Report — last {lookback_days} days")
    print(f"{'=' * 50}")
    print(f"  Total tasks logged: {len(recent)}")
    print(f"  Total time logged:  {total_time / 3600:.2f} hours")
    if recent:
        print(f"  Avg per task:         {total_time / len(recent):.1f}s")
    print(f"{'=' * 50}")
    if top_tasks:
        print("\n  Top tasks (by frequency):")
        for task, count in top_tasks:
            bar = "#" * min(count, 40)
            print(f"    {task:<30s} {count:>4d} {bar}")
    if top_tags:
        print("\n  Top tags:")
        for tag, count in top_tags:
            bar = "*" * min(count, 40)
            print(f"    {tag:<20s} {count:>4d} {bar}")
    print()


def cmd_streak(args):
    """Track daily work streaks."""
    ensure_dirs()
    metrics = json.loads(METRICS_FILE.read_text()) if METRICS_FILE.exists() else {}
    if args.action == "checkin":
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in metrics.get("sessions", []):
            metrics.setdefault("sessions", []).append(today)
            metrics.setdefault("totals", {})["checkins"] = metrics["totals"].get("checkins", 0) + 1
            with open(METRICS_FILE, "w") as f:
                json.dump(metrics, f, indent=2)
            print(f"[streak] checked in for {today}")
        else:
            print(f"[streak] already checked in today ({today})")
        sessions = sorted(metrics.get("sessions", []))
        streak = 0
        current = datetime.now().date()
        for s in reversed(sessions):
            expected = current - timedelta(days=streak)
            if s == expected.isoformat():
                streak += 1
            else:
                break
        print(f"[streak] current streak: {streak} day(s)")
    elif args.action == "show":
        sessions = sorted(metrics.get("sessions", []))
        total = len(sessions)
        print(f"\n[streak] total check-ins: {total}")
        if sessions:
            print(f"[streak] first:  {sessions[0]}")
            print(f"[streak] latest: {sessions[-1]}")
    else:
        print("[error] use checkin|show")


def cmd_notes(args):
    """Quick scratch-pad notes stored in the data directory."""
    ensure_dirs()
    notes_file = DATA_DIR / "notes.txt"
    if args.action == "add":
        note = " ".join(args.text)
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note}\n"
        with open(notes_file, "a") as f:
            f.write(line)
        print(f"[notes] added: {note[:60]}{'...' if len(note) > 60 else ''}")
    elif args.action == "list":
        if not notes_file.exists():
            print("[notes] no notes yet.")
            return
        lines = notes_file.read_text().strip().split("\n")
        for line in lines[-args.count:]:
            print(f"  {line}")
    elif args.action == "clear":
        if notes_file.exists():
            notes_file.unlink()
            print("[notes] cleared all notes")
        else:
            print("[notes] nothing to clear")
    else:
        print("[error] use add|list|clear")


def cmd_setup(args):
    """Initialize the data directory and display configuration."""
    ensure_dirs()
    print("[setup] personal-dev-bench initialized")
    print(f"  data directory: {DATA_DIR}")
    print(f"  task times:     {TIMES_FILE}")
    print(f"  metrics:        {METRICS_FILE}")
    print(f"  benchmarks:     {BENCHMARKS_DIR}/")
    files_count = sum(1 for _ in BENCHMARKS_DIR.iterdir()) if BENCHMARKS_DIR.exists() else 0
    print(f"  benchmark files: {files_count}")


def main():
    parser = argparse.ArgumentParser(
        prog="pdbench",
        description="Personal dev bench — productivity tools and workflow experiments",
    )
    sub = parser.add_subparsers(dest="command")

    p_timer = sub.add_parser("timer", help="Task timer (start/stop/status)")
    p_timer.add_argument("action", choices=["start", "stop", "status"])
    p_timer.add_argument("task", nargs="*", default=["untitled"])
    p_timer.add_argument("--tags", nargs="*", default=[])

    p_bench = sub.add_parser("benchmark", help="Benchmark a command")
    p_bench.add_argument("cmd", nargs="+")
    p_bench.add_argument("-n", "--iterations", type=int, default=5)
    p_bench.add_argument("-l", "--label", default=None)

    p_report = sub.add_parser("report", help="Productivity report")
    p_report.add_argument("-d", "--days", type=int, default=30)

    p_streak = sub.add_parser("streak", help="Daily work streaks")
    p_streak.add_argument("action", choices=["checkin", "show"])

    p_notes = sub.add_parser("notes", help="Scratch-pad notes")
    p_notes.add_argument("action", choices=["add", "list", "clear"])
    p_notes.add_argument("text", nargs="*")
    p_notes.add_argument("-n", "--count", type=int, default=10)

    sub.add_parser("setup", help="Initialize and show configuration")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "timer": cmd_timer,
        "benchmark": cmd_benchmark,
        "report": cmd_report,
        "streak": cmd_streak,
        "notes": cmd_notes,
        "setup": cmd_setup,
    }
    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
