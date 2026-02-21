# personal-dev-bench

Developer tools and experiments for productivity and workflow optimization.

A CLI utility that provides task timing, command benchmarking, productivity reporting, daily streak tracking, and scratch-pad notes — all persisted locally.

## Quick Start

```bash
# Initialize
python main.py setup

# Time a task
python main.py timer start refactoring auth module --tags code python
python main.py timer status
python main.py timer stop

# Benchmark a command
python main.py benchmark python -c "sum(range(1000000))" -n 10 -l sum_bench

# View productivity report
python main.py report --days 14

# Daily check-in for streaks
python main.py streak checkin
python main.py streak show

# Quick notes
python main.py notes add "Remember to review the caching strategy"
python main.py notes list
python main.py notes clear
```

## Commands

| Command | Description |
|---|---|
| `setup` | Initialize data directory and display configuration |
| `timer start/stop/status` | Track time spent on tasks with optional tags |
| `benchmark` | Run a command multiple times, record min/max/mean stats |
| `report` | Generate a productivity report from logged task data |
| `streak checkin/show` | Track daily work streaks |
| `notes add/list/clear` | Quick scratch-pad notes stored locally |

## Data Storage

All data is stored in `~/.personal-dev-bench/` by default. Override with the `PDBENCH_DATA` environment variable.

```
~/.personal-dev-bench/
├── task_times.csv        # Logged task durations
├── metrics.json          # Streak and session data
├── notes.txt             # Scratch-pad notes
├── active_timer.json     # Current timer state (auto-managed)
└── benchmarks/           # Individual benchmark result files
```

## Configuration

- **Data directory**: Set `PDBENCH_DATA` to change where data is stored.
- **Report window**: Use `--days` to adjust the report lookback period (default: 30).
- **Benchmark iterations**: Use `-n` to set how many times to run a command (default: 5).
- **Benchmark label**: Use `-l` to name benchmark result files.

## Requirements

- Python 3.7+
- No external dependencies

## License

MIT
