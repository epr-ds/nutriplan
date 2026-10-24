"""Publishing dietary domain events to the notification service's bus (NTF-203).

The writing half of the bus, mirroring commerce's :mod:`app.events` package: the reading half
lives in the notification service, this package's counterpart here. The port keeps Redis a
single replaceable adapter (an in-process one backs dev/CI), so the scheduler above never sees
a driver.
"""

from __future__ import annotations
