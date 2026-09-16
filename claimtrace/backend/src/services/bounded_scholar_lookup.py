"""Bound third-party retry loops without leaving background searches running.

The worker gets a deadline of its own, strictly inside the timeout enforced
here, so it stops itself and reports a reason; the subprocess timeout below is
the safety net for a worker that somehow ignores it. The worker's stderr is
captured rather than discarded, because that is where ``scholarly`` states why
it is retrying (a 403 page, a captcha, a response code) and it is the only
explanation available for a lookup that never completes.
"""

import logging
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO

from ..audit_models import LookupAttempt, LookupResult, ReferenceEntry

logger = logging.getLogger(__name__)

# How much of this class's timeout is held back so the worker can stop itself
# and still report. It covers interpreter start-up plus the worker's imports,
# measured at well under a second, so the subprocess timeout stays a safety net
# rather than the normal path.
WORKER_STARTUP_ALLOWANCE_SECONDS = 5.0

# Cap on captured worker stderr copied into a lookup attempt: reports are
# persisted and returned by the API, so this cannot be unbounded.
WORKER_LOG_LIMIT = 1000


def _worker_log_tail(stream: IO[bytes] | None) -> str:
    """Read the tail of a captured worker stream, or ``""`` when there is none.

    The tail rather than the head: ``scholarly`` logs each retry reason as it
    goes, so the last lines say what the search was doing when it stopped.
    """
    if stream is None:
        return ""
    try:
        stream.seek(0)
        text = stream.read().decode("utf-8", "replace").strip()
    except (OSError, ValueError):
        return ""
    if len(text) > WORKER_LOG_LIMIT:
        return "..." + text[-WORKER_LOG_LIMIT:]
    return text


def _with_worker_log(detail: str, worker_log: str) -> str:
    """Append the captured worker log to an attempt's detail."""
    if not worker_log:
        return detail
    return f"{detail}\nWorker log: {worker_log}" if detail else f"Worker log: {worker_log}"


class BoundedScholarLookup:
    def __init__(self, timeout_seconds: float = 30, min_interval_seconds: float = 0.0):
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self._last_requested_at: float | None = None
        self._throttle_lock = threading.Lock()

    @property
    def worker_deadline_seconds(self) -> float:
        """The search budget handed to the worker process.

        Strictly below ``timeout_seconds``, so the worker stops itself and
        reports a diagnosable failure instead of being killed. Halving keeps the
        deadline positive if someone configures a deliberately tiny timeout.
        """
        return max(
            self.timeout_seconds - WORKER_STARTUP_ALLOWANCE_SECONDS,
            self.timeout_seconds / 2,
        )

    def _throttle(self) -> None:
        """Space consecutive lookups at least ``min_interval_seconds`` apart.

        Google Scholar rate-limits bursts of queries with HTTP 429; a small gap
        between lookups keeps a multi-reference audit from tripping it. A
        non-positive interval disables the delay entirely.
        """
        if self.min_interval_seconds <= 0:
            return
        with self._throttle_lock:
            now = time.monotonic()
            if self._last_requested_at is not None:
                remaining = self.min_interval_seconds - (now - self._last_requested_at)
                if remaining > 0:
                    time.sleep(remaining)
                    now = time.monotonic()
            self._last_requested_at = now

    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        self._throttle()
        try:
            # Files avoid waiting for inherited pipe handles after a timeout
            # on Windows (third-party browser helpers may retain them).
            with (
                tempfile.TemporaryFile() as source,
                tempfile.TemporaryFile() as output,
                tempfile.TemporaryFile() as errors,
            ):
                source.write(entry.model_dump_json().encode("utf-8"))
                source.seek(0)
                # The documented local command runs from ``backend`` and loads
                # the application as ``src.main``.  Derive the same package
                # root from this file instead of inheriting the API process's
                # current working directory (which may be the repository root,
                # backend/, or /app in Docker).
                package_root = Path(__file__).resolve().parents[2]
                try:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "src.services.scholar_worker",
                            "--deadline-seconds",
                            f"{self.worker_deadline_seconds:g}",
                        ],
                        stdin=source,
                        stdout=output,
                        stderr=errors,
                        timeout=self.timeout_seconds,
                        check=True,
                        cwd=package_root,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.TimeoutExpired:
                    # The safety net: the worker should have stopped itself and
                    # reported SCHOLAR_WORKER_TIMEOUT well before this.
                    return self._failed(
                        "SCHOLAR_TIMEOUT",
                        f"Google Scholar did not respond within "
                        f"{self.timeout_seconds:g} seconds. The search was stopped. "
                        "Retry later or check network access; "
                        "publication existence remains unchecked.",
                        errors,
                    )
                except (OSError, subprocess.CalledProcessError):
                    return self._failed(
                        "SCHOLAR_WORKER_FAILED",
                        "Google Scholar lookup could not complete. "
                        "Check backend dependencies and logs.",
                        errors,
                    )
                return self._worker_result(output, errors)
        except (OSError, ValueError):
            # Temporary-file I/O failed. A worker that writes unreadable output
            # is handled in ``_worker_result`` instead, where its log is still
            # readable — these streams are already closed by the time we get here.
            return self._failed(
                "SCHOLAR_WORKER_FAILED",
                "Google Scholar lookup could not complete. "
                "Check backend dependencies and logs.",
                None,
            )

    def _worker_result(self, output: IO[bytes], errors: IO[bytes]) -> LookupResult:
        """Read the worker's own result, decorating a failure with its log.

        A worker that stops itself at its deadline reports a failure and exits
        zero without raising here, so this — not the exception branches above —
        is the path that carries scholarly's explanation out of the child
        process. Successful lookups are returned untouched.
        """
        output.seek(0)
        try:
            result = LookupResult.model_validate_json(output.read())
        except ValueError:
            # Read here rather than in the caller's except: that one runs after
            # these temporary files are closed, so the log would be lost.
            return self._failed(
                "SCHOLAR_WORKER_FAILED",
                "Google Scholar lookup could not complete. "
                "Check backend dependencies and logs.",
                errors,
            )
        if result.outcome == "failed" and result.attempts:
            worker_log = _worker_log_tail(errors)
            if worker_log:
                logger.warning("Scholar lookup failed, worker log: %s", worker_log)
                result.attempts[0].detail = _with_worker_log(
                    result.attempts[0].detail, worker_log
                )
        return result

    def _failed(self, code: str, reason: str, errors: IO[bytes] | None) -> LookupResult:
        worker_log = _worker_log_tail(errors)
        if worker_log:
            logger.warning("Scholar worker %s: %s", code, worker_log)
        return LookupResult(
            outcome="failed",
            reason=reason,
            attempts=[
                LookupAttempt(
                    provider="google_scholar",
                    outcome="failed",
                    error_code=code,
                    detail=_with_worker_log(reason, worker_log),
                )
            ],
        )
