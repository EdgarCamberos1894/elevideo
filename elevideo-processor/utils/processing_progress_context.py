from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional


_active_progress_tracker: ContextVar[object] = ContextVar(
    "elevideo_active_progress_tracker",
    default=None,
)


@contextmanager
def bind_progress_tracker(tracker):
    """Vincula el tracker al contexto síncrono del job actual."""
    token = _active_progress_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _active_progress_tracker.reset(token)


def get_active_progress_tracker() -> Optional[object]:
    return _active_progress_tracker.get()
