#!/usr/bin/env python3
"""
HRD-901: Full Regression Suite Runner

Runs the complete regression test corpus across all services.
Designed to be invoked from CI as a gate before release.

Usage:
    python regression/run.py --services ai commerce identity dietary notification
    python regression/run.py --all
    python regression/run.py --services ai --tags smoke
    python regression/run.py --services ai --tags regression --fail-fast
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"


@dataclass
class TestCase:
    name: str
    service: str
    severity: Severity
    tags: list[str]
    duration_ms: float = 0
    passed: bool = False
    error: str | None = None


@dataclass
class RegressionReport:
    timestamp: str
    services: list[str]
    total: int
    passed: int
    failed: int
    skipped: int
    total_duration_ms: float
    results: list[dict]
    blocked_by: list[str]  # P0/P1 failures that block release


def _service_root(service: str) -> Path:
    """Return the repository root's service directory for a service."""
    return Path(__file__).parent.parent / "services" / service


def _ensure_service_importable(service: str) -> Path:
    """Put a service's application root on ``sys.path`` so its ``app`` package resolves."""
    service_root = _service_root(service)
    if str(service_root) not in sys.path:
        sys.path.insert(0, str(service_root))
    return service_root


def _reset_service_app_modules(service: str) -> Path:
    """Point the ``app`` namespace at a service's application root and re-import it when needed.

    The release gate drives one verifier per service inside a single process (``--all``), so the
    cached ``app`` namespace must not leak from one service onto another before each import.
    """
    module = sys.modules.get("app")
    module_file = getattr(module, "__file__", None) or ""
    current = None
    for candidate in ("ai", "commerce", "identity", "dietary", "notification"):
        if module_file.startswith(str(_service_root(candidate))):
            current = candidate
            break
    if current != service:
        for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
            del sys.modules[name]
        _ensure_service_importable(service)
    return _service_root(service)


def _golden_safety_cases() -> list[TestCase]:
    """Build the release-gate cases from the AI service's fixed golden safety corpus."""
    _ensure_service_importable("ai")
    from app.regression.corpus import GOLDEN_SAFETY_CASES

    return [
        TestCase(
            name=case.name,
            service="ai",
            severity=Severity.P2,
            tags=["regression"],
        )
        for case in GOLDEN_SAFETY_CASES
    ]


def load_regression_corpus(service: str) -> list[TestCase]:
    """Load regression test cases for a service from its regression corpus."""
    if service == "ai":
        # The AI release gate drives the fixed golden safety corpus, not a JSON corpus file.
        return _golden_safety_cases()

    service_dir = _service_root(service)
    corpus_file = service_dir / "regression" / "corpus.json"

    if not corpus_file.exists():
        return []

    with open(corpus_file) as f:
        corpus = json.load(f)

    cases = []
    for item in corpus.get("cases", []):
        cases.append(
            TestCase(
                name=item["name"],
                service=service,
                severity=Severity(item.get("severity", "P2")),
                tags=item.get("tags", []),
            )
        )
    return cases


def run_regression_for_service(
    service: str, tags: list[str] | None = None
) -> list[TestCase]:
    """Run regression tests for a single service."""
    cases = load_regression_corpus(service)
    results = []

    for case in cases:
        if tags and not any(t in case.tags for t in tags):
            case.passed = True  # Skipped counts as passed
            case.error = "skipped (tag filter)"
            results.append(case)
            continue

        start = time.time()
        try:
            passed, error = _run_case(service, case)
            case.duration_ms = (time.time() - start) * 1000
            case.passed = passed
            case.error = error
        except Exception as e:  # noqa: BLE001 - a crashed case must fail the gate, not crash it
            case.duration_ms = (time.time() - start) * 1000
            case.passed = False
            case.error = str(e)

        results.append(case)

    return results


def _run_case(service: str, case: TestCase) -> tuple[bool, str | None]:
    """Run a single regression case through its service's verifier.

    The AI release gate executes the fixed golden safety corpus
    (:data:`app.regression.GOLDEN_SAFETY_CASES`) through the production allergen filter rather
    than case-name-keyed invocations, so the AI gate grades that corpus directly; every other
    service is invoked by case name.
    """
    if service == "ai":
        _reset_service_app_modules("ai")
        from app.regression import GOLDEN_SAFETY_CASES, SafetyRegressionVerifier

        report = SafetyRegressionVerifier().verify(GOLDEN_SAFETY_CASES)
        return report.ok, "; ".join(report.failures) if report.failures else None

    if service == "commerce":
        # HRD-905 release-gate follow-up: the commerce release gate must execute the commerce
        # regression corpus through the production use cases (in-process, no DB, no network).
        _reset_service_app_modules("commerce")
        from app.regression import CommerceRegressionVerifier, load_commerce_cases

        report = CommerceRegressionVerifier().verify(load_commerce_cases())
        return report.ok, "; ".join(report.failures) if report.failures else None

    _ensure_service_importable(service)
    module_path = f"services.{service}.regression.verifier"
    verifier = __import__(module_path, fromlist=["verify"])
    passed, error = verifier.verify(case.name)
    return passed, error


def generate_report(
    services: list[str],
    all_results: list[TestCase],
    timestamp: str,
) -> RegressionReport:
    """Generate a regression report."""
    failed = [r for r in all_results if not r.passed]
    skipped = [r for r in all_results if r.error and "skipped" in r.error]
    blocked = [r.name for r in failed if r.severity in (Severity.P0, Severity.P1)]

    return RegressionReport(
        timestamp=timestamp,
        services=services,
        total=len(all_results),
        passed=len([r for r in all_results if r.passed]),
        failed=len(failed),
        skipped=len(skipped),
        total_duration_ms=sum(r.duration_ms for r in all_results),
        results=[asdict(r) for r in all_results],
        blocked_by=blocked,
    )


def main():
    parser = argparse.ArgumentParser(description="Run regression suite")
    parser.add_argument(
        "--services",
        nargs="+",
        help="Services to test (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test all services",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        help="Filter by tags (e.g., smoke, regression)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first P0/P1 failure",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON report to file",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=1,
        help="Exit code on failure (default: 1)",
    )
    args = parser.parse_args()

    services = args.services or [
        "ai",
        "commerce",
        "identity",
        "dietary",
        "notification",
    ]
    if args.all:
        services = ["ai", "commerce", "identity", "dietary", "notification"]

    all_results = []
    for service in services:
        results = run_regression_for_service(service, args.tags)
        all_results.extend(results)

        if args.fail_fast:
            blocked = [
                r
                for r in results
                if not r.passed and r.severity in (Severity.P0, Severity.P1)
            ]
            if blocked:
                print(f"FAIL: {len(blocked)} P0/P1 regression(s) failed in {service}")
                for b in blocked:
                    print(f"  - {b.name}: {b.error}")
                sys.exit(args.exit_code)

    report = generate_report(services, all_results, time.strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Print summary
    print(f"\n{'=' * 60}")
    print("Regression Suite Report")
    print(f"{'=' * 60}")
    print(f"Services: {', '.join(services)}")
    print(
        f"Total: {report.total} | Passed: {report.passed} | Failed: {report.failed} | Skipped: {report.skipped}"
    )
    print(f"Duration: {report.total_duration_ms:.0f}ms")

    if report.failed > 0:
        print(f"\n{'=' * 60}")
        print("FAILED TESTS")
        print(f"{'=' * 60}")
        for r in report.results:
            if not r["passed"]:
                print(f"  [{r['severity']}] {r['name']} ({r['service']}): {r['error']}")

    if report.blocked_by:
        print(f"\n{'=' * 60}")
        print(f"RELEASE BLOCKED by {len(report.blocked_by)} P0/P1 failure(s)")
        print(f"{'=' * 60}")
        for name in report.blocked_by:
            print(f"  - {name}")

    # Write JSON report
    if args.output:
        report_path = Path(args.output)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"\nReport written to {report_path}")

    # Exit code
    if report.failed > 0:
        sys.exit(args.exit_code)
    else:
        print(f"\nAll {report.passed} regression tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
