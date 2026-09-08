"""The consumer process: poll, reclaim, settle, repeat (NTF-201).

Run it with ``python -m app.events.worker``.

**Why this is a separate process from the API.** The obvious alternative is a background task
in the FastAPI lifespan, and it is wrong in both directions. The API scales on request
latency and the consumer on event volume, so sharing a replica count means neither can be
sized honestly -- and a slow handler would then be competing for the same event loop that has
to answer ``/health/ready`` promptly, so a backlog of order events would present as the API
pod failing its probes and being restarted, which is about the least informative symptom that
particular fault could produce.

The loop itself is deliberately dull: read a batch, settle each message, occasionally sweep
for messages a dead consumer left behind. The interesting decisions are all in
:mod:`app.events.dispatcher`; what this module owns is staying alive.

**Staying alive means not dying of a broker outage.** A raised connection error escapes to
the top, and the process exits, and the orchestrator restarts it into the same outage -- a
crash loop that adds nothing but noise to an incident whose cause is elsewhere. So a failed
cycle is logged and backed off instead, and the worker is still there when Redis returns.
The failure is not swallowed: nothing was acked, so every unsettled message is still pending.
"""

from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable
from types import FrameType

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.events.dispatcher import BatchResult, EventDispatcher
from app.events.factory import build_event_dispatcher

logger = logging.getLogger(__name__)

RECLAIM_EVERY_CYCLES = 10
"""Sweep for stranded messages every N cycles rather than every one.

A reclaim is two extra round trips and finds nothing the overwhelming majority of the time,
because stranded messages come from a consumer dying -- a rare event. Sweeping every cycle
would spend most of its budget confirming that nothing is wrong.
"""

ERROR_BACKOFF_SECONDS = 5.0
"""How long to wait after a failed cycle, so an outage does not become a busy loop."""


class EventWorker:
    """Drives a :class:`~app.events.dispatcher.EventDispatcher` in a loop."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        *,
        batch_size: int,
        block_ms: int,
        reclaim_every: int = RECLAIM_EVERY_CYCLES,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._batch_size = max(1, batch_size)
        self._block_ms = max(0, block_ms)
        self._reclaim_every = max(1, reclaim_every)
        self._sleep = sleep or time.sleep
        self._cycles = 0

    @classmethod
    def from_settings(
        cls, settings: Settings | None = None, *, dispatcher: EventDispatcher | None = None
    ) -> EventWorker:
        """Build a worker from configuration, with an optional pre-wired dispatcher.

        NTF-202 passes a dispatcher that already has its order handlers registered.
        """
        settings = settings or default_settings
        return cls(
            dispatcher or build_event_dispatcher(settings),
            batch_size=settings.event_batch_size,
            block_ms=settings.event_block_ms,
        )

    def run_once(self) -> BatchResult:
        """Run one cycle: a reclaim sweep when due, then a batch of new messages.

        The sweep no longer carries an idle threshold of its own: NTF-204 moved that decision
        into the dispatcher's :class:`~app.events.backoff.RetrySchedule`, so how long a given
        entry waits depends on how many times it has already failed rather than on a single
        number the worker holds.
        """
        result = BatchResult()
        if self._cycles % self._reclaim_every == 0:
            result += self._dispatcher.reclaim_once(count=self._batch_size)
        result += self._dispatcher.poll_once(count=self._batch_size, block_ms=self._block_ms)
        self._cycles += 1
        return result

    def run(self, should_stop: Callable[[], bool]) -> BatchResult:
        """Cycle until ``should_stop`` returns true, surviving broker failures.

        The predicate is checked *before* each cycle, so a worker asked to stop never begins
        a batch it would then abandon mid-flight -- messages already delivered but not yet
        acked would be left to the next reclaim, which is correct but slow, and easy to avoid.
        """
        self._dispatcher.ensure_subscribed()
        total = BatchResult()
        while not should_stop():
            try:
                total += self.run_once()
            except Exception:
                logger.exception("notification.event.cycle_failed")
                self._sleep(ERROR_BACKOFF_SECONDS)
        logger.info(
            "notification.event.worker_stopped handled=%d dropped=%d dead_lettered=%d "
            "retried=%d deferred=%d dlq_depth=%d",
            total.handled,
            total.dropped,
            total.dead_lettered,
            total.retried,
            total.deferred,
            self._dispatcher.dead_letters.depth(),
        )
        return total


class StopSignal:
    """A flag set by SIGTERM/SIGINT, so a shutdown finishes the current batch first.

    Kubernetes sends SIGTERM and then waits before SIGKILL. Using that grace period to finish
    the batch in flight means its messages are acked normally instead of being left pending
    for the next consumer's reclaim sweep -- the difference between a clean rolling deploy and
    one that redelivers a handful of events each time.
    """

    def __init__(self) -> None:
        self._stopped = False

    def install(self) -> StopSignal:
        """Register the handler for the signals an orchestrator actually sends."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle)
        return self

    def _handle(self, signum: int, _frame: FrameType | None) -> None:
        logger.info("notification.event.stop_requested signal=%s", signum)
        self._stopped = True

    def __call__(self) -> bool:
        """True once a stop signal has been received."""
        return self._stopped


def main() -> None:
    """Entry point: build from configuration and consume until told to stop."""
    logging.basicConfig(level=logging.INFO)
    settings = default_settings
    logger.info(
        "notification.event.worker_starting stream=%s group=%s consumer=%s",
        settings.order_event_stream,
        settings.consumer_group,
        settings.consumer_name,
    )
    EventWorker.from_settings(settings).run(StopSignal().install())


if __name__ == "__main__":
    main()
