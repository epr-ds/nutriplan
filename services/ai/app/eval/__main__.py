"""Headless entrypoint for the offline eval harness: ``python -m app.eval`` (AIA-701).

Grades :data:`~app.eval.dataset.EVAL_SET`, prints the full JSON report to stdout, and writes a
one-line summary (and any trend versus the previous run) to stderr. With ``--history PATH`` it
appends the run's metrics to a JSONL file for trending; with ``--min-constraint-respect RATE`` it
exits non-zero when the constraint-respect rate falls below ``RATE``, so the same harness can be
wired into CI as an optional quality gate without changing its default reporting behaviour.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.eval.dataset import EVAL_SET
from app.eval.harness import EvalHarness
from app.eval.history import compare_to_previous, record


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.eval",
        description="Offline AI recommendation eval harness (AIA-701).",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=None,
        metavar="PATH",
        help="append this run's metrics to a JSONL history file for trending",
    )
    parser.add_argument(
        "--min-constraint-respect",
        type=float,
        default=None,
        metavar="RATE",
        help="exit non-zero if the constraint-respect rate is below RATE (0-1)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    report = EvalHarness().run(EVAL_SET)
    trend = compare_to_previous(report, args.history) if args.history is not None else None

    print(json.dumps(report.to_dict(), indent=2))
    print(report.summary(), file=sys.stderr)
    if trend is not None:
        print(trend.describe(), file=sys.stderr)

    if args.history is not None:
        record(report, args.history)

    if (
        args.min_constraint_respect is not None
        and report.constraint_respect < args.min_constraint_respect
    ):
        print(
            f"FAIL: constraint-respect {report.constraint_respect_pct}% is below the "
            f"{args.min_constraint_respect * 100:g}% threshold",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
