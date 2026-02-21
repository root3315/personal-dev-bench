#!/usr/bin/env python3
"""Tests for personal-dev-bench data pipeline and core functionality."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

import main as pdbench


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory with initialized files."""
    data_dir = tmp_path / "pdbench_data"
    data_dir.mkdir()
    with mock.patch.object(pdbench, "DATA_DIR", data_dir), \
         mock.patch.object(pdbench, "TIMES_FILE", data_dir / "task_times.csv"), \
         mock.patch.object(pdbench, "METRICS_FILE", data_dir / "metrics.json"), \
         mock.patch.object(pdbench, "BENCHMARKS_DIR", data_dir / "benchmarks"):
        pdbench.ensure_dirs()
        yield data_dir


@pytest.fixture
def seeded_task_times(tmp_data_dir):
    """Seed task_times.csv with sample rows and return the file path."""
    times_file = tmp_data_dir / "task_times.csv"
    rows = [
        {
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
            "task": "refactor auth",
            "duration_seconds": "120.5",
            "tags": "code,python",
        },
        {
            "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
            "task": "write docs",
            "duration_seconds": "300.0",
            "tags": "docs",
        },
        {
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
            "task": "refactor auth",
            "duration_seconds": "60.0",
            "tags": "code,python",
        },
    ]
    with open(times_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "task", "duration_seconds", "tags"])
        writer.writeheader()
        writer.writerows(rows)
    return times_file


# ---------------------------------------------------------------------------
# ensure_dirs
# ---------------------------------------------------------------------------

class TestEnsureDirs:
    def test_creates_data_directory(self, tmp_path):
        data_dir = tmp_path / "fresh"
        with mock.patch.object(pdbench, "DATA_DIR", data_dir), \
             mock.patch.object(pdbench, "TIMES_FILE", data_dir / "task_times.csv"), \
             mock.patch.object(pdbench, "METRICS_FILE", data_dir / "metrics.json"), \
             mock.patch.object(pdbench, "BENCHMARKS_DIR", data_dir / "benchmarks"):
            pdbench.ensure_dirs()
        assert data_dir.exists()
        assert (data_dir / "benchmarks").exists()
        assert (data_dir / "task_times.csv").exists()
        assert (data_dir / "metrics.json").exists()

    def test_idempotent(self, tmp_path):
        data_dir = tmp_path / "fresh"
        with mock.patch.object(pdbench, "DATA_DIR", data_dir), \
             mock.patch.object(pdbench, "TIMES_FILE", data_dir / "task_times.csv"), \
             mock.patch.object(pdbench, "METRICS_FILE", data_dir / "metrics.json"), \
             mock.patch.object(pdbench, "BENCHMARKS_DIR", data_dir / "benchmarks"):
            pdbench.ensure_dirs()
            pdbench.ensure_dirs()  # second call should not raise
        assert (data_dir / "task_times.csv").exists()


# ---------------------------------------------------------------------------
# log_task
# ---------------------------------------------------------------------------

class TestLogTask:
    def test_appends_row(self, tmp_data_dir):
        times_file = tmp_data_dir / "task_times.csv"
        pdbench.log_task("unit test", 42.5, tags=["test"])
        with open(times_file, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["task"] == "unit test"
        assert float(rows[0]["duration_seconds"]) == 42.5
        assert rows[0]["tags"] == "test"

    def test_no_tags(self, tmp_data_dir):
        times_file = tmp_data_dir / "task_times.csv"
        pdbench.log_task("no-tag task", 10.0)
        with open(times_file, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["tags"] == ""


# ---------------------------------------------------------------------------
# cmd_timer
# ---------------------------------------------------------------------------

class TestCmdTimer:
    def _make_args(self, action="status", task=None, tags=None):
        args = mock.MagicMock()
        args.action = action
        args.task = task or ["untitled"]
        args.tags = tags or []
        return args

    def test_start_creates_marker(self, tmp_data_dir):
        args = self._make_args("start", task=["build", "project"], tags=["code"])
        pdbench.cmd_timer(args)
        marker = tmp_data_dir / "active_timer.json"
        assert marker.exists()
        entry = json.loads(marker.read_text())
        assert entry["task"] == "build project"
        assert entry["tags"] == ["code"]

    def test_stop_logs_and_removes_marker(self, tmp_data_dir):
        # start first
        marker = tmp_data_dir / "active_timer.json"
        entry = {"task": "test task", "start": datetime.now().isoformat(), "tags": []}
        marker.write_text(json.dumps(entry))
        args = self._make_args("stop")
        pdbench.cmd_timer(args)
        assert not marker.exists()

    def test_stop_no_active_timer(self, tmp_data_dir, capsys):
        args = self._make_args("stop")
        pdbench.cmd_timer(args)
        captured = capsys.readouterr()
        assert "[error]" in captured.out

    def test_status_no_active(self, tmp_data_dir, capsys):
        args = self._make_args("status")
        pdbench.cmd_timer(args)
        captured = capsys.readouterr()
        assert "no active timer" in captured.out


# ---------------------------------------------------------------------------
# cmd_benchmark
# ---------------------------------------------------------------------------

class TestCmdBenchmark:
    def _make_args(self, cmd, iterations=2, label="test_bench"):
        args = mock.MagicMock()
        args.cmd = cmd
        args.iterations = iterations
        args.label = label
        return args

    def test_runs_and_saves_results(self, tmp_data_dir):
        # Use 'true' command which exists on all POSIX systems and takes no args
        args = self._make_args(["true"], iterations=2, label="quick")
        pdbench.cmd_benchmark(args)
        result_file = tmp_data_dir / "benchmarks" / "quick.json"
        assert result_file.exists()
        stats = json.loads(result_file.read_text())
        assert stats["iterations"] == 2
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats


# ---------------------------------------------------------------------------
# cmd_report
# ---------------------------------------------------------------------------

class TestCmdReport:
    def _make_args(self, days=30):
        args = mock.MagicMock()
        args.days = days
        return args

    def test_empty_data(self, tmp_data_dir, capsys):
        args = self._make_args()
        pdbench.cmd_report(args)
        captured = capsys.readouterr()
        assert "no task data" in captured.out

    def test_recent_tasks_summarized(self, tmp_data_dir, seeded_task_times, capsys):
        args = self._make_args(days=7)
        pdbench.cmd_report(args)
        captured = capsys.readouterr()
        assert "Productivity Report" in captured.out
        assert "Total tasks logged: 3" in captured.out


# ---------------------------------------------------------------------------
# cmd_streak
# ---------------------------------------------------------------------------

class TestCmdStreak:
    def _make_args(self, action="show"):
        args = mock.MagicMock()
        args.action = action
        return args

    def test_checkin_adds_session(self, tmp_data_dir, capsys):
        args = self._make_args("checkin")
        pdbench.cmd_streak(args)
        metrics_file = tmp_data_dir / "metrics.json"
        metrics = json.loads(metrics_file.read_text())
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in metrics["sessions"]
        captured = capsys.readouterr()
        assert "checked in" in captured.out

    def test_double_checkin_warns(self, tmp_data_dir, capsys):
        args = self._make_args("checkin")
        pdbench.cmd_streak(args)
        pdbench.cmd_streak(args)
        captured = capsys.readouterr()
        assert "already checked in" in captured.out

    def test_show_empty(self, tmp_data_dir, capsys):
        args = self._make_args("show")
        pdbench.cmd_streak(args)
        captured = capsys.readouterr()
        assert "total check-ins: 0" in captured.out


# ---------------------------------------------------------------------------
# cmd_notes
# ---------------------------------------------------------------------------

class TestCmdNotes:
    def _make_args(self, action="list", text=None, count=10):
        args = mock.MagicMock()
        args.action = action
        args.text = text or []
        args.count = count
        return args

    def test_add_and_list(self, tmp_data_dir, capsys):
        pdbench.cmd_notes(self._make_args("add", text=["hello world"]))
        pdbench.cmd_notes(self._make_args("list"))
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_clear(self, tmp_data_dir, capsys):
        pdbench.cmd_notes(self._make_args("add", text=["temp note"]))
        pdbench.cmd_notes(self._make_args("clear"))
        pdbench.cmd_notes(self._make_args("list"))
        captured = capsys.readouterr()
        assert "no notes yet" in captured.out


# ---------------------------------------------------------------------------
# cmd_setup
# ---------------------------------------------------------------------------

class TestCmdSetup:
    def test_prints_config(self, tmp_data_dir, capsys):
        args = mock.MagicMock()
        pdbench.cmd_setup(args)
        captured = capsys.readouterr()
        assert "initialized" in captured.out
        assert "data directory:" in captured.out


# ---------------------------------------------------------------------------
# main / dispatch
# ---------------------------------------------------------------------------

class TestMain:
    def test_no_command_exits(self):
        with mock.patch.object(sys, "argv", ["pdbench"]), \
             pytest.raises(SystemExit):
            pdbench.main()

    def test_invalid_command_exits(self):
        with mock.patch.object(sys, "argv", ["pdbench", "bogus"]), \
             pytest.raises(SystemExit):
            pdbench.main()


# ---------------------------------------------------------------------------
# Data pipeline integration — end-to-end via CLI
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    """End-to-end tests that exercise the full data pipeline through subprocess calls."""

    @pytest.fixture
    def cli(self, tmp_path):
        """Return a helper that runs `python main.py ...` with an isolated data dir."""
        data_dir = tmp_path / "e2e_data"
        data_dir.mkdir()
        env = os.environ.copy()
        env["PDBENCH_DATA"] = str(data_dir)

        def run(*args):
            return subprocess.run(
                [sys.executable, str(Path(__file__).parent / "main.py"), *args],
                capture_output=True, text=True, env=env,
            )
        return run

    def test_full_lifecycle(self, cli):
        # setup
        result = cli("setup")
        assert result.returncode == 0
        assert "initialized" in result.stdout

        # timer start → stop
        result = cli("timer", "start", "integration", "task", "--tags", "e2e")
        assert result.returncode == 0
        assert "started" in result.stdout

        time.sleep(0.1)

        result = cli("timer", "stop")
        assert result.returncode == 0
        assert "logged" in result.stdout

        # report should show data
        result = cli("report", "--days", "1")
        assert result.returncode == 0
        assert "Productivity Report" in result.stdout
        assert "Total tasks logged: 1" in result.stdout

        # streak checkin
        result = cli("streak", "checkin")
        assert result.returncode == 0
        assert "checked in" in result.stdout

        # notes
        result = cli("notes", "add", "e2e note")
        assert result.returncode == 0
        result = cli("notes", "list")
        assert result.returncode == 0
        assert "e2e note" in result.stdout

        # benchmark
        result = cli("benchmark", "-n", "1", "-l", "e2e_bench", "true")
        assert result.returncode == 0
        assert "results saved" in result.stdout
