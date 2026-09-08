"""The dead-letter queue's operator interface (NTF-204, AC2).

Run it with ``python -m app.events.dlq``::

    python -m app.events.dlq list                 # what is parked, newest first
    python -m app.events.dlq show <delivery-id>   # one entry, payload included
    python -m app.events.dlq replay <delivery-id> # re-run one, after the fix is deployed
    python -m app.events.dlq replay --all         # drain everything that now works
    python -m app.events.dlq purge --yes          # give up on the lot

**Why a CLI and not an HTTP endpoint.** The obvious alternative is ``GET /admin/dead-letters``
alongside the feed API, and it is the wrong shape for this service as it stands. Notification
is a resource server whose every authenticated request is scoped to one end user: a token
carries a ``sub`` and nothing else -- no roles, no scopes, no service identity (NTF-105). An
admin surface would therefore need an entire authorisation concept invented for it, and until
that existed, "replay an arbitrary event" and "read every user's raw event payloads" would be
two of the most dangerous endpoints in the system sitting behind the same check as "list my
notifications".

The worker already establishes ``python -m ...`` as this service's operational entry point, and
a CLI inherits its authorisation from the deployment: whoever can exec into the container can
already read the Redis it would query. That is a defensible boundary today, and it can be
promoted to an HTTP surface when NTF-702 gives the platform something to authorise against.

Exit codes are meant for a runbook, not just a human: ``0`` for success, ``1`` for a failed
replay or a missing entry, ``2`` for a usage error (argparse's own convention).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from app.application.dead_letter_replay import DeadLetterReplayer, ReplayStatus
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.dead_letter import DeadLetter, DeadLetterQueue
from app.events.factory import build_dead_letter_replayer, build_event_dispatcher

EXIT_OK = 0
EXIT_FAILED = 1

PAYLOAD_PREVIEW = 120
"""How much of a payload the listing shows before truncating.

A listing is for choosing which entry to look at; ``show`` is for looking at it. Printing
whole payloads here would push the entries an operator is scanning for off the screen.
"""


def build_parser() -> argparse.ArgumentParser:
    """Define the command surface."""
    parser = argparse.ArgumentParser(
        prog="python -m app.events.dlq",
        description="Inspect and replay the notification service's dead-letter queue.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable output, for a runbook that pipes into jq",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="show parked events, newest first")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--offset", type=int, default=0)

    show = commands.add_parser("show", help="show one parked event in full")
    show.add_argument("delivery_id")

    replay = commands.add_parser("replay", help="re-run parked events through the handler")
    target = replay.add_mutually_exclusive_group(required=True)
    target.add_argument("delivery_id", nargs="?", help="the entry to replay")
    target.add_argument("--all", action="store_true", help="replay everything, oldest first")
    replay.add_argument("--limit", type=int, default=100, help="cap for --all")

    purge = commands.add_parser("purge", help="discard every parked event")
    purge.add_argument(
        "--yes",
        action="store_true",
        required=True,
        help="required: purging destroys the only copy of every parked event",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, settings: Settings | None = None) -> int:
    """Run one CLI invocation and return its exit code."""
    logging.basicConfig(level=logging.WARNING)
    args = build_parser().parse_args(argv)
    settings = settings or default_settings

    # One dispatcher for the whole invocation: it owns the queue instance, and building a
    # second one would have the replayer draining a different object than the one it listed.
    dispatcher = build_event_dispatcher(settings)
    queue = dispatcher.dead_letters
    replayer = build_dead_letter_replayer(settings, dispatcher=dispatcher)

    if args.command == "list":
        return _list(queue, limit=args.limit, offset=args.offset, as_json=args.json)
    if args.command == "show":
        return _show(queue, args.delivery_id, as_json=args.json)
    if args.command == "replay":
        return _replay(replayer, args, as_json=args.json)
    return _purge(queue, as_json=args.json)


def _list(queue: DeadLetterQueue, *, limit: int, offset: int, as_json: bool) -> int:
    """Print the parked entries and the queue's depth."""
    entries = queue.list(limit=limit, offset=offset)
    depth = queue.depth()
    if as_json:
        _emit({"depth": depth, "entries": [_summary(entry) for entry in entries]})
        return EXIT_OK

    print(f"dead-letter queue: {depth} parked")
    if not entries:
        print("  (empty)")
        return EXIT_OK
    for entry in entries:
        print(
            f"  {entry.delivery_id}  {entry.failed_at.isoformat()}  "
            f"type={entry.event_type or '(unparseable)'}  attempt={entry.attempt}"
        )
        print(f"      reason: {entry.reason}")
        print(f"      payload: {_preview(entry.payload)}")
    return EXIT_OK


def _show(queue: DeadLetterQueue, delivery_id: str, *, as_json: bool) -> int:
    """Print one entry with its payload in full."""
    entry = queue.get(delivery_id)
    if entry is None:
        if as_json:
            _emit({"deliveryId": delivery_id, "found": False})
        else:
            print(f"no parked entry {delivery_id!r}", file=sys.stderr)
        return EXIT_FAILED

    if as_json:
        _emit({**_summary(entry), "payload": entry.payload, "found": True})
        return EXIT_OK

    print(f"delivery id : {entry.delivery_id}")
    print(f"failed at   : {entry.failed_at.isoformat()}")
    print(f"attempt     : {entry.attempt}")
    print(f"event type  : {entry.event_type or '(unparseable)'}")
    print(f"event id    : {entry.event_id or '(unparseable)'}")
    print(f"reason      : {entry.reason}")
    print("payload     :")
    print(entry.payload)
    return EXIT_OK


def _replay(replayer: DeadLetterReplayer, args: argparse.Namespace, *, as_json: bool) -> int:
    """Replay one entry or drain the queue, reporting what is left."""
    if args.all:
        report = replayer.replay_all(limit=args.limit)
        outcomes = list(report.outcomes)
    else:
        outcomes = [replayer.replay(args.delivery_id)]

    if as_json:
        _emit(
            {
                "replayed": sum(1 for outcome in outcomes if outcome.succeeded),
                "outcomes": [
                    {
                        "deliveryId": outcome.delivery_id,
                        "status": outcome.status.value,
                        "eventType": outcome.event_type,
                        "detail": outcome.detail,
                    }
                    for outcome in outcomes
                ],
            }
        )
    else:
        for outcome in outcomes:
            detail = f" -- {outcome.detail}" if outcome.detail else ""
            print(f"{outcome.delivery_id}  {outcome.status.value}{detail}")
        replayed = sum(1 for outcome in outcomes if outcome.succeeded)
        print(f"replayed {replayed} of {len(outcomes)}")

    # Non-zero when anything is still parked, so a runbook step that replays after a deploy
    # fails loudly rather than reporting success over a queue that did not drain.
    still_failing = [outcome for outcome in outcomes if outcome.status is not ReplayStatus.REPLAYED]
    return EXIT_FAILED if still_failing else EXIT_OK


def _purge(queue: DeadLetterQueue, *, as_json: bool) -> int:
    """Empty the queue."""
    discarded = queue.purge()
    if as_json:
        _emit({"purged": discarded})
    else:
        print(f"purged {discarded} parked event(s)")
    return EXIT_OK


def _summary(entry: DeadLetter) -> dict[str, object]:
    """The JSON shape of one entry, payload excluded."""
    return {
        "deliveryId": entry.delivery_id,
        "failedAt": entry.failed_at.isoformat(),
        "attempt": entry.attempt,
        "eventType": entry.event_type,
        "eventId": entry.event_id,
        "reason": entry.reason,
    }


def _preview(payload: str) -> str:
    """Truncate a payload for the listing."""
    collapsed = " ".join(payload.split())
    if len(collapsed) <= PAYLOAD_PREVIEW:
        return collapsed
    return f"{collapsed[:PAYLOAD_PREVIEW]}..."


def _emit(document: object) -> None:
    """Write one JSON document to stdout."""
    print(json.dumps(document, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
