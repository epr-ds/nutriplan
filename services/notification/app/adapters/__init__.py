"""Store adapters for the notification domain.

The Redis adapter is the production one; the in-memory adapter backs dev, CI, and tests.
Both are held to the same contract suite, and :mod:`app.adapters.factory` is the only place
that decides which one runs.
"""
