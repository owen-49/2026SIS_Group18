import subprocess
import sys
import time
from pathlib import Path

import pytest
from backend.src.audit_models import LookupAttempt, LookupResult, ReferenceEntry
from backend.src.models import BibEntryRecord
from backend.src.services.bounded_scholar_lookup import BoundedScholarLookup


def entry(title="Example"):
    return ReferenceEntry(entry_id="test", metadata=BibEntryRecord(key="test", title=title))


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
