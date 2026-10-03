"""Validate the runtime, then replace this process with one Uvicorn worker."""

import json
import os
import sys

from backend.src.services.runtime_checks import runtime_checks


def main() -> None:
    checks = runtime_checks(create_directories=True)
    print(json.dumps({"runtime_checks": checks}), flush=True)
    if not all(checks.values()):
        sys.exit("Runtime preflight failed; check Java, packages and volume permissions.")
    if len(sys.argv) > 1:
        sys.exit("The production entrypoint accepts no overrides; run one worker only.")
    os.execvp(
        "uvicorn",
        [
            "uvicorn", "backend.src.main:app", "--host", "0.0.0.0",
            "--port", "8000", "--workers", "1", "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
