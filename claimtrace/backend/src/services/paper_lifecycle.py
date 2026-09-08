"""Process-level coordination for operations that read or delete one paper."""

from contextlib import contextmanager
from threading import RLock
from typing import Iterator

_PAPER_LOCKS = [RLock() for _ in range(64)]


@contextmanager
def paper_lifecycle_lock(paper_id: str) -> Iterator[None]:
    """Serialize lifecycle-sensitive work for one paper within this process."""
    lock = _PAPER_LOCKS[hash(paper_id) % len(_PAPER_LOCKS)]
    with lock:
        yield
