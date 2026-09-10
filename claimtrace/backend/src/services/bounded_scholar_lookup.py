"""Bound third-party retry loops without leaving background searches running."""

import subprocess
import sys
import tempfile
from pathlib import Path

from ..audit_models import LookupAttempt, LookupResult, ReferenceEntry


class BoundedScholarLookup:
    def __init__(self, timeout_seconds: float = 30):
        self.timeout_seconds = timeout_seconds

    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        try:
            # Files avoid waiting for inherited pipe handles after a timeout
            # on Windows (third-party browser helpers may retain them).
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                source.write(entry.model_dump_json().encode("utf-8"))
                source.seek(0)
                # The documented local command runs from ``backend`` and loads
                # the application as ``src.main``.  Derive the same package
                # root from this file instead of inheriting the API process's
                # current working directory (which may be the repository root,
                # backend/, or /app in Docker).
                package_root = Path(__file__).resolve().parents[2]
                subprocess.run(
                    [sys.executable, "-m", "src.services.scholar_worker"],
                    stdin=source,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=True,
                    cwd=package_root,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                output.seek(0)
                return LookupResult.model_validate_json(output.read())
        except subprocess.TimeoutExpired:
            code = "SCHOLAR_TIMEOUT"
            reason = (
                f"Google Scholar did not respond within {self.timeout_seconds:g} seconds. "
                "The search was stopped. Retry later or check network access; "
                "publication existence remains unchecked."
            )
        except (OSError, subprocess.CalledProcessError, ValueError):
            code = "SCHOLAR_WORKER_FAILED"
            reason = (
                "Google Scholar lookup could not complete. Check backend dependencies and logs."
            )
        return LookupResult(
            outcome="failed",
            reason=reason,
            attempts=[LookupAttempt(
                provider="google_scholar", outcome="failed", error_code=code, detail=reason,
            )],
        )
