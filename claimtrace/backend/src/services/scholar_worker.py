"""One isolated Scholar lookup, stopped by its own deadline or by the parent.

The parent runs this as a subprocess and kills it on a hard timeout. That kill
is meant to be a safety net: ``scholarly`` retries a blocked request on its own
and sleeps 60-120 seconds on a 403 or captcha page *without* ever advancing its
retry counter, so a worker with no budget of its own would always be killed
instead of reporting why. This module gives the search a deadline it can honour,
so the failure carries a reason and the parent's timeout stays exceptional.
"""

import argparse
import logging
import os
import sys
import threading
import time
from collections.abc import Callable

from ..audit_models import LookupAttempt, LookupResult, ReferenceEntry
from .google_scholar_lookup import GoogleScholarLookup

# Only used when this module is launched directly. The parent always passes its
# own value, derived so that it stays strictly below the parent's timeout.
DEFAULT_DEADLINE_SECONDS = 25.0


def configure_scholarly_logging() -> None:
    """Route ``scholarly``'s own diagnostics to stderr.

    Those records are the only account of *why* a lookup keeps retrying (an
    access-denied page, a captcha, a response code), and the library emits them
    at INFO. Left alone, its logger inherits the root WARNING level, the records
    are never even built, and a captured stderr stays empty no matter what the
    parent does with it — so this has to be set here, in the process that runs
    the search.

    stderr, never stdout: stdout carries this worker's result.
    """
    logger = logging.getLogger("scholarly")
    logger.setLevel(logging.INFO)
    # The worker exists only to run this one lookup, so its diagnostics should
    # not also travel up to whatever the embedding application configured.
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)


def _failure(error_code: str, detail: str) -> LookupResult:
    """Build the failure result reported on stdout."""
    return LookupResult(
        outcome="failed",
        reason=detail,
        attempts=[
            LookupAttempt(
                provider="google_scholar",
                outcome="failed",
                error_code=error_code,
                detail=detail,
            )
        ],
    )


def deadline_result(deadline_seconds: float, elapsed_seconds: float) -> LookupResult:
    """The result reported when the search outlives its own deadline.

    Deliberately a different code from the parent's ``SCHOLAR_TIMEOUT``: this one
    says the worker stopped itself, so a parent timeout now means the deadline
    itself is broken rather than that Scholar was slow.
    """
    return _failure(
        "SCHOLAR_WORKER_TIMEOUT",
        f"Google Scholar did not answer within this worker's own "
        f"{deadline_seconds:g}-second deadline (stopped after {elapsed_seconds:.1f}s). "
        "The search was abandoned; publication existence remains unchecked.",
    )


def run_with_deadline(
    search: Callable[[], LookupResult], deadline_seconds: float
) -> LookupResult | None:
    """Run ``search`` on a daemon thread, abandoning it after ``deadline_seconds``.

    Returns ``None`` when the deadline passed first; an exception raised by
    ``search`` is re-raised here, on the calling thread, so the caller's exit
    path stays ordinary.

    A thread rather than ``signal.alarm``: alarms do not exist on Windows, and
    this worker already carries Windows accommodations. The thread is a daemon
    because a search blocked inside one of ``scholarly``'s sleeps must not be
    able to hold the process open once the deadline has passed.
    """
    outcome: list[LookupResult] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            outcome.append(search())
        except BaseException as exc:  # re-raised on the calling thread
            failure.append(exc)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(deadline_seconds)
    if worker.is_alive():
        return None
    if failure:
        raise failure[0]
    return outcome[0]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One isolated Google Scholar lookup.")
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=DEFAULT_DEADLINE_SECONDS,
        help=(
            "Wall-clock budget for the search itself. The parent passes its own "
            "configured value, always below the timeout it enforces on this process."
        ),
    )
    return parser.parse_args(argv)


def _emit(result: LookupResult) -> None:
    """Write the result to stdout — this is the worker's entire protocol.

    ASCII JSON works with Windows redirected pipes regardless of code page.
    """
    print(result.model_dump_json().encode("ascii", "backslashreplace").decode("ascii"))
    sys.stdout.flush()


def main() -> None:
    args = _parse_args()
    configure_scholarly_logging()
    entry = ReferenceEntry.model_validate_json(sys.stdin.buffer.read())
    started = time.monotonic()
    result = run_with_deadline(
        lambda: GoogleScholarLookup().lookup(entry), args.deadline_seconds
    )
    if result is not None:
        _emit(result)
        return
    # The search is still inside scholarly's retry loop. Report the deadline and
    # leave at once: only os._exit guarantees that a sleep the abandoned thread
    # is inside cannot delay interpreter shutdown, so the parent always receives
    # this result instead of killing the process. Both streams are flushed first
    # because os._exit skips it, and the last log lines are the diagnostic ones.
    _emit(deadline_result(args.deadline_seconds, time.monotonic() - started))
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
