"""Tests for the headless eval entrypoint ``python -m app.eval`` (AIA-701).

The CLI grades the real :data:`~app.eval.dataset.EVAL_SET`. These tests exercise the default
reporting path, the optional constraint-respect gate (exit code), and the ``--history`` trending
side effect, capturing stdout/stderr rather than touching the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.__main__ import main


def test_default_run_prints_a_json_report_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])

    assert code == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report["constraint_respect"] == 0.8667
    assert "constraint-respect" in out.err  # the summary goes to stderr


def test_min_constraint_respect_gate_fails_below_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--min-constraint-respect", "0.99"])

    assert code == 1
    assert "below the" in capsys.readouterr().err


def test_min_constraint_respect_gate_passes_above_threshold() -> None:
    assert main(["--min-constraint-respect", "0.5"]) == 0


def test_history_is_written_and_trended(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "history.jsonl"

    first = main(["--history", str(path)])
    capsys.readouterr()
    second = main(["--history", str(path)])

    assert first == 0
    assert second == 0
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert "constraint-respect" in capsys.readouterr().err  # trend line on the second run
