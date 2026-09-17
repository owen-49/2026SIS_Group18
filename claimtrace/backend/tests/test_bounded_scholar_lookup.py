import io
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.src.audit_models import LookupAttempt, LookupResult, ReferenceEntry
from backend.src.models import BibEntryRecord
from backend.src.services import scholar_worker
from backend.src.services.bounded_scholar_lookup import (
    WORKER_LOG_LIMIT,
    BoundedScholarLookup,
)
from backend.src.services.scholar_worker import deadline_result, run_with_deadline


def entry(title="Example"):
    return ReferenceEntry(entry_id="test", metadata=BibEntryRecord(key="test", title=title))


def backend_dir():
    return Path(__file__).resolve().parents[1]


def not_found():
    return LookupResult(
        outcome="not_found",
        reason="No result",
        attempts=[LookupAttempt(provider="google_scholar", outcome="not_found")],
    )


def reported_failure(error_code="SCHOLAR_WORKER_TIMEOUT", detail="deadline reached"):
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


def worker_that(writes=b"", result=None, raises=None):
    """A stand-in for ``subprocess.run`` that behaves like the worker process."""

    def run(command, **kwargs):
        if writes:
            kwargs["stderr"].write(writes)
        if raises is not None:
            raise raises
        kwargs["stdout"].write((result or not_found()).model_dump_json().encode())
        return subprocess.CompletedProcess(command[0], 0)

    return run


def test_worker_roundtrip_without_network():
    result = BoundedScholarLookup().lookup(entry(""))
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_SEARCH_FAILED"


def test_worker_starts_from_documented_backend_directory(monkeypatch):
    """The real child process must work with ``cd backend; uvicorn src.main``."""
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    result = BoundedScholarLookup().lookup(entry(""))
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_SEARCH_FAILED"


def test_timeout_terminates_real_worker(monkeypatch):
    original_run = subprocess.run

    def stalled_worker(command, **kwargs):
        return original_run([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)

    monkeypatch.setattr(subprocess, "run", stalled_worker)
    result = BoundedScholarLookup(timeout_seconds=0.2).lookup(entry())
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_TIMEOUT"
    assert not result.records


@pytest.mark.parametrize("failure", [OSError(), subprocess.CalledProcessError(1, "worker")])
def test_worker_failure_is_not_no_match(monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    result = BoundedScholarLookup().lookup(entry())
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_WORKER_FAILED"


def test_valid_worker_result_is_preserved(monkeypatch):
    result = LookupResult(
        outcome="not_found", reason="No result",
        attempts=[LookupAttempt(provider="google_scholar", outcome="not_found")],
    )

    def run(*args, **kwargs):
        assert b"Example" in kwargs["stdin"].read()
        kwargs["stdout"].write(result.model_dump_json().encode())
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert BoundedScholarLookup().lookup(entry()) == result


def test_throttle_spaces_out_consecutive_lookups(monkeypatch):
    clock = [0.0]
    sleeps = []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(time, "sleep", fake_sleep)

    lookup = BoundedScholarLookup(min_interval_seconds=2.0)
    lookup._throttle()
    assert sleeps == []  # first lookup is not delayed
    lookup._throttle()
    assert sleeps == [2.0]  # second is spaced a full interval apart


def test_scholarly_diagnostics_are_configured_to_reach_stderr():
    """Without this the captured log is empty however the parent reads it.

    ``scholarly`` states why it is retrying -- an access-denied page, a captcha,
    a response code -- at INFO, and its logger inherits the root WARNING level.
    The records are then never even built, so ``stderr`` stays empty and every
    failure is indistinguishable. A subprocess, because logger state is global
    to a process and the worker is where it has to be configured.
    """
    program = (
        "import logging;"
        "from src.services.scholar_worker import configure_scholarly_logging;"
        "configure_scholarly_logging();"
        "logging.getLogger('scholarly').info('Got an access denied error (403).')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=backend_dir(),
        capture_output=True,
        text=True,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert "Got an access denied error (403)." in completed.stderr
    assert completed.stdout == ""  # stdout is the result protocol, and nothing else


def test_a_stuck_search_cannot_hold_the_worker_process_open():
    """The deadline mechanism end to end, offline.

    A search blocked inside one of ``scholarly``'s sleeps must not be able to
    delay the exit: the parent has to receive the worker's own result instead of
    killing it. Runs the real module, with only the search itself replaced.
    """
    program = (
        "import io, sys, time\n"
        "from types import SimpleNamespace\n"
        "from src.services import scholar_worker\n"
        "payload = sys.argv[1]\n"
        "scholar_worker.GoogleScholarLookup.lookup = lambda self, entry: time.sleep(60)\n"
        "sys.stdin = SimpleNamespace(buffer=io.BytesIO(payload.encode()))\n"
        "sys.argv = ['scholar_worker', '--deadline-seconds', '0.5']\n"
        "scholar_worker.main()\n"
    )
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-c", program, entry().model_dump_json()],
        cwd=backend_dir(),
        capture_output=True,
        text=True,
        timeout=30,  # a process that waits for the search would blow this
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert time.monotonic() - started < 30
    result = LookupResult.model_validate_json(completed.stdout)
    assert result.outcome == "failed"
    assert result.attempts[0].error_code == "SCHOLAR_WORKER_TIMEOUT"


def test_a_search_inside_its_deadline_is_returned_unchanged():
    assert run_with_deadline(not_found, 5.0) == not_found()


def test_a_search_past_its_deadline_is_abandoned():
    stuck = threading.Event()  # never set: the search never returns
    assert run_with_deadline(lambda: stuck.wait(30) or not_found(), 0.05) is None


def test_an_error_inside_the_search_reaches_the_calling_thread():
    def boom():
        raise ValueError("no network")

    with pytest.raises(ValueError, match="no network"):
        run_with_deadline(boom, 5.0)


def test_the_deadline_result_differs_from_the_parent_timeout():
    """``SCHOLAR_TIMEOUT`` must now mean the deadline itself failed (a bug)."""
    result = deadline_result(25, 25.4)
    assert result.outcome == "failed"
    attempt = result.attempts[0]
    assert attempt.error_code == "SCHOLAR_WORKER_TIMEOUT"
    assert attempt.error_code != "SCHOLAR_TIMEOUT"
    assert "25-second deadline" in attempt.detail  # this worker's own budget
    assert "25.4s" in attempt.detail  # when it actually stopped


def test_main_reports_the_deadline_and_leaves_without_waiting(monkeypatch):
    """``main`` must print its result and exit rather than await the search."""
    stuck = threading.Event()
    printed = []

    class LeftProcessError(Exception):
        pass

    def exit_now(code):
        raise LeftProcessError(code)

    monkeypatch.setattr(sys, "argv", ["scholar_worker", "--deadline-seconds", "0.05"])
    monkeypatch.setattr(
        sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(entry().model_dump_json().encode())),
    )
    monkeypatch.setattr(
        scholar_worker.GoogleScholarLookup,
        "lookup",
        lambda self, entry: stuck.wait(30) or not_found(),
    )
    monkeypatch.setattr(scholar_worker, "_emit", printed.append)
    monkeypatch.setattr(scholar_worker.os, "_exit", exit_now)

    with pytest.raises(LeftProcessError) as exit_code:
        scholar_worker.main()
    assert exit_code.value.args[0] == 0  # the parent must read a clean exit
    assert printed[0].attempts[0].error_code == "SCHOLAR_WORKER_TIMEOUT"


@pytest.mark.parametrize("timeout_seconds", [30.0, 3.0, 0.2])
def test_the_worker_deadline_is_strictly_inside_the_parent_timeout(
    monkeypatch, timeout_seconds
):
    """The parent's kill is a safety net, so it must never be the normal path."""
    command = []

    def run(argv, **kwargs):
        command.extend(argv)
        kwargs["stdout"].write(not_found().model_dump_json().encode())
        return subprocess.CompletedProcess(argv[0], 0)

    monkeypatch.setattr(subprocess, "run", run)
    BoundedScholarLookup(timeout_seconds=timeout_seconds).lookup(entry())
    flag = command.index("--deadline-seconds") + 1
    assert 0 < float(command[flag]) < timeout_seconds


def test_a_worker_that_reports_its_own_failure_carries_its_log(monkeypatch):
    """The normal path: the parent's except branches never run here."""
    monkeypatch.setattr(
        subprocess,
        "run",
        worker_that(
            writes=b"INFO scholarly: Got an access denied error (403).\n",
            result=reported_failure(),
        ),
    )
    result = BoundedScholarLookup().lookup(entry())
    attempt = result.attempts[0]
    assert attempt.error_code == "SCHOLAR_WORKER_TIMEOUT"
    assert "Got an access denied error (403)." in attempt.detail
    assert "Worker log:" in attempt.detail
    assert result.reason == "deadline reached"  # the summary stays machine-facing


def test_a_parent_timeout_carries_the_worker_log(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        worker_that(
            writes=b"INFO scholarly: Response code 429. Retrying...\n",
            raises=subprocess.TimeoutExpired("worker", 0.2),
        ),
    )
    result = BoundedScholarLookup(timeout_seconds=0.2).lookup(entry())
    attempt = result.attempts[0]
    assert attempt.error_code == "SCHOLAR_TIMEOUT"
    assert "Response code 429. Retrying..." in attempt.detail


def test_a_crashed_worker_carries_its_traceback(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        worker_that(
            writes=b"Traceback (most recent call last):\nValueError: boom\n",
            raises=subprocess.CalledProcessError(1, "worker"),
        ),
    )
    result = BoundedScholarLookup().lookup(entry())
    attempt = result.attempts[0]
    assert attempt.error_code == "SCHOLAR_WORKER_FAILED"
    assert "ValueError: boom" in attempt.detail


def test_unreadable_worker_output_still_carries_the_log(monkeypatch):
    """Read while the temporary files are open: the caller's except is too late."""

    def run(command, **kwargs):
        kwargs["stdout"].write(b"not the result protocol at all")
        kwargs["stderr"].write(b"Traceback (most recent call last):\nMemoryError\n")
        return subprocess.CompletedProcess(command[0], 0)

    monkeypatch.setattr(subprocess, "run", run)
    attempt = BoundedScholarLookup().lookup(entry()).attempts[0]
    assert attempt.error_code == "SCHOLAR_WORKER_FAILED"
    assert "MemoryError" in attempt.detail


def test_a_completed_search_is_never_decorated(monkeypatch):
    """A usable result is returned as the worker wrote it."""
    monkeypatch.setattr(
        subprocess,
        "run",
        worker_that(
            writes=b"INFO scholarly: Got an access denied error (403).\n",
            result=not_found(),
        ),
    )
    assert BoundedScholarLookup().lookup(entry()) == not_found()


def test_an_empty_worker_log_changes_nothing(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", worker_that(result=reported_failure(detail="no reason"))
    )
    result = BoundedScholarLookup().lookup(entry())
    assert result.attempts[0].detail == "no reason"


def test_the_captured_log_keeps_its_tail_and_stays_bounded(monkeypatch):
    """Reports are persisted and returned, and the last lines are the reason."""
    monkeypatch.setattr(
        subprocess,
        "run",
        worker_that(
            writes=b"INFO scholarly: opening session\n" + b"x" * (WORKER_LOG_LIMIT * 2),
            raises=subprocess.CalledProcessError(1, "worker"),
        ),
    )
    detail = BoundedScholarLookup().lookup(entry()).attempts[0].detail
    assert detail.startswith("Google Scholar lookup could not complete.")
    assert "..." in detail  # the head of the log was dropped, not the tail
    assert len(detail) < WORKER_LOG_LIMIT + 200
