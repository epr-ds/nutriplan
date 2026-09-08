"""The dead-letter queue's operator interface (NTF-204, AC2).

The CLI is what an operator actually touches during an incident, so the properties worth
pinning are the ones a runbook depends on: that the exit code distinguishes "drained" from
"still broken", that ``--json`` is machine-readable, and that nothing destructive happens
without being asked for explicitly.

Everything runs against an in-process backend. ``main`` builds its collaborators from
:class:`Settings`, and a blank ``NOTIFICATION_REDIS_URL`` -- which the isolation fixture in
``conftest`` guarantees -- selects the in-memory queue, so the whole command surface is
exercised end to end without a server.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.events import dlq
from app.events.consumer import DeliveredEvent
from app.events.dead_letter import DeadLetterQueue
from app.events.dlq import EXIT_FAILED, EXIT_OK
from app.events.envelope import EventEnvelope
from app.events.factory import build_event_dispatcher
from app.events.registry import ORDER_CONFIRMED
from tests.test_event_envelope import COMMERCE_ORDER_CONFIRMED

EXIT_USAGE = 2
"""argparse's own convention for a bad invocation -- a runbook can tell it from a failure."""


class RecordingHandler:
    """Accepts everything and remembers what it saw."""

    def __init__(self) -> None:
        self.seen: list[EventEnvelope] = []

    def handle(self, event: EventEnvelope) -> None:
        self.seen.append(event)


class Console:
    """One CLI invocation's queue, handler and captured output."""

    def __init__(self, queue: DeadLetterQueue, handler: RecordingHandler) -> None:
        self.queue = queue
        self.handler = handler
        self.code = EXIT_OK
        self.out = ""
        self.err = ""

    @property
    def json(self) -> dict:
        """The ``--json`` document, parsed."""
        return json.loads(self.out)


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Run CLI invocations against one in-process queue that survives between them.

    The dispatcher is built once and pinned, because ``main`` builds its own per
    invocation: with an in-memory queue, a second dispatcher would hand the CLI an empty
    queue and every ``replay`` test would pass against nothing.
    """
    settings = Settings()
    handler = RecordingHandler()
    dispatcher = build_event_dispatcher(settings, handlers={ORDER_CONFIRMED: handler})
    console = Console(dispatcher.dead_letters, handler)

    monkeypatch.setattr(dlq, "build_event_dispatcher", lambda *a, **k: dispatcher)

    def run(*argv: str) -> Console:
        console.code = dlq.main(list(argv), settings=settings)
        captured = capsys.readouterr()
        console.out, console.err = captured.out, captured.err
        return console

    run.console = console  # type: ignore[attr-defined]
    return run


def park(queue: DeadLetterQueue, delivery_id: str, *, payload: str | None = None) -> None:
    """Put one entry in the queue, as the dispatcher's error path would."""
    body = payload if payload is not None else json.dumps(COMMERCE_ORDER_CONFIRMED)
    queue.park(
        DeliveredEvent(delivery_id=delivery_id, payload=body, attempt=5),
        reason=f"handler rejected {delivery_id}",
    )


class TestList:
    def test_an_empty_queue_reports_itself_as_empty(self, cli) -> None:
        console = cli("list")

        assert console.code == EXIT_OK
        assert "0 parked" in console.out

    def test_it_shows_the_parked_entries(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("list")

        assert "d-1" in console.out
        assert "order.confirmed" in console.out
        assert "handler rejected d-1" in console.out

    def test_it_shows_the_depth(self, cli) -> None:
        for index in range(3):
            park(cli.console.queue, f"d-{index}")

        console = cli("list")

        assert "3 parked" in console.out

    def test_a_limit_caps_the_listing(self, cli) -> None:
        for index in range(3):
            park(cli.console.queue, f"d-{index}")

        console = cli("list", "--limit", "1")

        assert "d-2" in console.out
        assert "d-0" not in console.out

    def test_the_payload_is_truncated(self, cli) -> None:
        """A listing is for choosing what to look at; whole payloads would push the entries
        an operator is scanning for off the screen."""
        park(
            cli.console.queue,
            "d-1",
            payload=json.dumps({**COMMERCE_ORDER_CONFIRMED, "filler": "x" * 500}),
        )

        console = cli("list")

        assert "x" * 500 not in console.out
        assert len(max(console.out.splitlines(), key=len)) < 300

    def test_json_mode_reports_depth_and_entries(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("--json", "list")

        document = console.json
        assert document["depth"] == 1
        assert document["entries"][0]["deliveryId"] == "d-1"
        assert document["entries"][0]["eventType"] == "order.confirmed"

    def test_json_mode_on_an_empty_queue_is_still_valid_json(self, cli) -> None:
        """A runbook piping into ``jq`` must not have to special-case the good outcome."""
        console = cli("--json", "list")

        assert console.json == {"depth": 0, "entries": []}


class TestShow:
    def test_it_prints_the_payload_in_full(self, cli) -> None:
        """``show`` is the one place the evidence is not abbreviated."""
        payload = json.dumps({**COMMERCE_ORDER_CONFIRMED, "filler": "x" * 300})
        park(cli.console.queue, "d-1", payload=payload)

        console = cli("show", "d-1")

        assert console.code == EXIT_OK
        assert payload in console.out

    def test_it_prints_the_context_an_operator_needs(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("show", "d-1")

        assert "d-1" in console.out
        assert "order.confirmed" in console.out
        assert "handler rejected d-1" in console.out
        assert "5" in console.out

    def test_an_unknown_entry_fails(self, cli) -> None:
        """Non-zero so a runbook step that shows before replaying stops on a typo."""
        console = cli("show", "never-parked")

        assert console.code == EXIT_FAILED
        assert "never-parked" in console.err

    def test_an_unparseable_payload_is_labelled_rather_than_blank(self, cli) -> None:
        """The entries most worth showing are the ones that could not be read."""
        park(cli.console.queue, "d-1", payload="{not json")

        console = cli("show", "d-1")

        assert "unparseable" in console.out
        assert "{not json" in console.out

    def test_json_mode_carries_the_payload(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("--json", "show", "d-1")

        assert console.json["found"] is True
        assert json.loads(console.json["payload"])["type"] == "order.confirmed"

    def test_json_mode_says_so_when_it_is_missing(self, cli) -> None:
        console = cli("--json", "show", "never-parked")

        assert console.code == EXIT_FAILED
        assert console.json == {"deliveryId": "never-parked", "found": False}


class TestReplay:
    def test_it_reruns_the_handler(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("replay", "d-1")

        assert console.code == EXIT_OK
        assert len(cli.console.handler.seen) == 1

    def test_a_replayed_entry_leaves_the_queue(self, cli) -> None:
        park(cli.console.queue, "d-1")

        cli("replay", "d-1")

        assert cli.console.queue.depth() == 0

    def test_an_unknown_entry_fails(self, cli) -> None:
        console = cli("replay", "never-parked")

        assert console.code == EXIT_FAILED
        assert "not_found" in console.out

    def test_replaying_everything_drains_the_queue(self, cli) -> None:
        for index in range(3):
            park(cli.console.queue, f"d-{index}")

        console = cli("replay", "--all")

        assert console.code == EXIT_OK
        assert cli.console.queue.depth() == 0
        assert "replayed 3 of 3" in console.out

    def test_a_limit_caps_the_drain(self, cli) -> None:
        for index in range(4):
            park(cli.console.queue, f"d-{index}")

        cli("replay", "--all", "--limit", "2")

        assert cli.console.queue.depth() == 2

    def test_an_entry_that_still_fails_makes_the_command_fail(self, cli) -> None:
        """The property a runbook is built on: replaying after a deploy must fail loudly
        rather than report success over a queue that did not drain."""
        park(cli.console.queue, "d-1", payload=json.dumps({"schemaVersion": 1, "nonsense": True}))

        console = cli("replay", "--all")

        assert console.code == EXIT_FAILED
        assert cli.console.queue.depth() == 1

    def test_a_partial_drain_still_fails(self, cli) -> None:
        park(cli.console.queue, "d-good")
        park(cli.console.queue, "d-bad", payload="{not json")

        console = cli("replay", "--all")

        assert console.code == EXIT_FAILED
        assert "replayed 1 of 2" in console.out
        assert cli.console.queue.depth() == 1

    def test_json_mode_reports_each_outcome(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("--json", "replay", "--all")

        document = console.json
        assert document["replayed"] == 1
        assert document["outcomes"][0]["deliveryId"] == "d-1"
        assert document["outcomes"][0]["status"] == "replayed"

    def test_an_id_and_all_together_are_a_usage_error(self, cli) -> None:
        """They mean different things and one would have to silently win."""
        with pytest.raises(SystemExit) as exit_info:
            cli("replay", "d-1", "--all")

        assert exit_info.value.code == EXIT_USAGE

    def test_replay_with_no_target_is_a_usage_error(self, cli) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli("replay")

        assert exit_info.value.code == EXIT_USAGE


class TestPurge:
    def test_it_empties_the_queue(self, cli) -> None:
        for index in range(3):
            park(cli.console.queue, f"d-{index}")

        console = cli("purge", "--yes")

        assert console.code == EXIT_OK
        assert cli.console.queue.depth() == 0
        assert "purged 3" in console.out

    def test_it_refuses_without_confirmation(self, cli) -> None:
        """Purging destroys the only remaining copy of every parked event, so it cannot be
        something a mistyped command does."""
        park(cli.console.queue, "d-1")

        with pytest.raises(SystemExit) as exit_info:
            cli("purge")

        assert exit_info.value.code == EXIT_USAGE
        assert cli.console.queue.depth() == 1

    def test_json_mode_reports_the_count(self, cli) -> None:
        park(cli.console.queue, "d-1")

        console = cli("--json", "purge", "--yes")

        assert console.json == {"purged": 1}


class TestUsage:
    def test_no_command_is_a_usage_error(self, cli) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli()

        assert exit_info.value.code == EXIT_USAGE

    def test_an_unknown_command_is_a_usage_error(self, cli) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli("frobnicate")

        assert exit_info.value.code == EXIT_USAGE

    def test_every_documented_command_is_implemented(self) -> None:
        """The module docstring is the runbook; a command it names that does not parse
        would be discovered by an operator, mid-incident."""
        parser = dlq.build_parser()
        subparsers = next(
            action for action in parser._actions if hasattr(action, "choices") and action.choices
        )

        assert set(subparsers.choices) == {"list", "show", "replay", "purge"}


class TestTheReplayerAndTheDispatcherShareAQueue:
    def test_they_are_the_same_object(self) -> None:
        """Building a second one would have the replayer draining a queue the dispatcher
        never fills -- which, with an in-memory backend, is silently always empty."""
        from app.events.factory import build_dead_letter_replayer

        settings = Settings()
        dispatcher = build_event_dispatcher(settings)

        replayer = build_dead_letter_replayer(settings, dispatcher=dispatcher)

        assert replayer._queue is dispatcher.dead_letters  # noqa: SLF001
