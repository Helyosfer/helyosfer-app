"""Short, transient user notices, independent of the UI toolkit.

The UI layer registers a presenter at startup. Without one (headless tests,
command-line tools) a toast is silently dropped.
"""

from __future__ import annotations

_presenter = None


def set_toast_presenter(presenter) -> None:
    """Registers `presenter(text, duration)`; pass `None` to disable toasts."""
    global _presenter
    _presenter = presenter


def toast(text, duration=2.5, **kwargs):
    if _presenter is None:
        return None
    return _presenter(str(text), duration)
