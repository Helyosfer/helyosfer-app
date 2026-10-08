"""Hands a callback back to the UI thread without knowing which toolkit runs it.

Services finish work on worker threads and must not touch widgets from there.
The UI layer registers its own scheduler once at startup; until it does, the
callback simply runs on the calling thread, which is what headless tests and
command-line tools want.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

_lock = threading.Lock()
_scheduler: Optional[Callable[[Callable[[], None]], None]] = None


def set_main_thread_scheduler(scheduler) -> None:
    """Registers `scheduler(callback)`; pass `None` to restore direct calls."""
    global _scheduler
    with _lock:
        _scheduler = scheduler


def run_on_main_thread(callback) -> None:
    with _lock:
        scheduler = _scheduler
    if scheduler is None:
        callback()
    else:
        scheduler(callback)
