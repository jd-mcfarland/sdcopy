from __future__ import annotations

import fcntl
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from sdcopy.config import state_dir


@contextmanager
def ingest_lock() -> Iterator[None]:
    path = state_dir() / "sdcopy.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
