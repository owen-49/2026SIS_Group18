"""Build and exercise isolated deployment projects; never use the live data volume.

Requires Python 3.11+ and a running Docker Linux engine. No Python packages, AI
keys or external publication lookups are needed. All test containers and data
volumes created by this script are removed when the test finishes.
"""

import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent


def _pdf() -> bytes:
    """Small, genuine text PDF, constructed without a PDF library."""
    text = (
        b"BT /F1 16 Tf 72 740 Td (Deployment acceptance paper) Tj "
        b"0 -40 Td /F1 11 Tf "
        b"(A persistent data volume keeps uploaded papers after a container restart.) Tj "
        b"0 -20 Td (This document validates the Java PDF to Markdown pipeline.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n".encode()
    return data + f"startxref\n{xref}\n%%EOF\n".encode()


def _http(base: str, path: str, *, file: tuple[str, bytes] | None = None) -> dict:
    headers = {}
    body = None
    if file:
        filename, content = file
        boundary = "claimtrace-" + uuid.uuid4().hex
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(base + path, data=body, headers=headers)
    # Local acceptance requests must not be sent through a system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=180) as response:
        return json.load(response)


def _wait_ready(base: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if _http(base, "/ready")["status"] == "ready":
                return
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    raise RuntimeError("Backend did not become ready within 120 seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Use the existing local image.")
    parser.add_argument("--image", default="claimtrace-backend:smoke", help="Image to test.")
    parser.add_argument(
        "--port", type=int, default=18080, help="Unused loopback port for the test.",
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535.")
    project = "claimtrace-smoke-" + uuid.uuid4().hex[:8]
    restore_project = project + "-restore"
    base = f"http://127.0.0.1:{args.port}"
    owned_projects = []
    with tempfile.TemporaryDirectory(prefix="claimtrace-deploy-smoke-") as backup_dir:
        # The archive contains only generated fixtures, and UID 10001 must write it.
        if os.name != "nt":
            Path(backup_dir).chmod(0o777)
        env = os.environ.copy()
        env.update(
            BACKEND_PORT=str(args.port), BACKUP_DIR=Path(backup_dir).as_posix(),
            BACKEND_IMAGE=args.image,
            CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
            MAX_UPLOAD_SIZE_MB="50", METADATA_LOOKUP_TIMEOUT_SECONDS="10",
            REFERENCE_METADATA_TIMEOUT_SECONDS="30",
        )

        def run(command: list[str], *, capture: bool = False) -> str:
            result = subprocess.run(
                command, env=env, check=True, text=True, capture_output=capture,
                timeout=1200 if "build" in command else 180,
            )
            return result.stdout.strip() if capture else ""

        def compose(name: str, *arguments: str, capture: bool = False) -> str:
            return run([
                "docker", "compose", "--project-name", name,
                "--env-file", str(DEPLOY_DIR / ".env.example"),
                "-f", str(DEPLOY_DIR / "compose.yaml"), *arguments,
            ], capture=capture)

        try:
            run(["docker", "info"], capture=True)
            for name in (project, restore_project):
                label = f"label=com.docker.compose.project={name}"
                for resource in ("container", "volume", "network"):
                    if run(["docker", resource, "ls", "-q", "--filter", label], capture=True):
                        raise RuntimeError("Test project name already exists; no data was touched.")
            compose(project, "config", "--quiet")
            if not args.skip_build:
                compose(project, "build", "backend")
            owned_projects.append(project)
            compose(project, "up", "-d", "--no-build", "backend")
            _wait_ready(base)
            pdf = _http(base, "/api/parse", file=("acceptance.pdf", _pdf()))
            if pdf["status"] != "completed" or pdf["paragraph_count"] < 1:
                raise RuntimeError("The genuine PDF did not produce parsed paragraphs.")
            bib = _http(base, "/api/parse", file=(
                "acceptance.bib", b"@article{test,title={Deployment acceptance},year={2026}}",
            ))
            if bib["status"] != "completed" or bib["entry_count"] != 1:
                raise RuntimeError("BibTeX upload failed.")
            expected_ids = {pdf["paper_id"], bib["paper_id"]}

            def check_data() -> None:
                ids = {paper["paper_id"] for paper in _http(base, "/api/papers")["papers"]}
                if ids != expected_ids:
                    raise RuntimeError("Library records were not preserved.")
                for paper_id in expected_ids:
                    if _http(base, f"/api/parse/{paper_id}")["status"] != "completed":
                        raise RuntimeError("Persisted parse status changed.")
                claims = _http(base, f"/api/papers/{pdf['paper_id']}/claims")
                # An empty claims list is expected for this no-citation fixture,
                # but the persisted manuscript still has to be loaded from disk.
                if claims.get("status") != "completed" or not claims.get("manuscript_document"):
                    raise RuntimeError("The restored manuscript could not be loaded.")

            check_data()
            compose(project, "up", "-d", "--force-recreate", "--no-build", "backend")
            _wait_ready(base)
            check_data()
            compose(project, "stop", "backend")
            compose(project, "run", "--rm", "--no-deps", "maintenance", "backup",
                    "--archive", "/backups/acceptance.tar.gz", "--offline")
            owned_projects.append(restore_project)
            compose(restore_project, "run", "--rm", "--no-deps", "maintenance", "restore",
                    "--archive", "/backups/acceptance.tar.gz", "--offline")
            compose(restore_project, "up", "-d", "--no-build", "backend")
            _wait_ready(base)
            check_data()
            print(json.dumps({
                "status": "passed", "checks": [
                    "runtime_readiness", "real_pdf_parse", "bib_upload", "container_recreation",
                    "offline_backup", "restore_to_new_volume", "restored_library_and_artifacts",
                ], "paid_ai_calls": 0,
            }, indent=2))
        finally:
            for name in reversed(owned_projects):
                compose(name, "down", "--volumes", "--remove-orphans")
            if owned_projects:
                print("Removed the isolated test containers and test data volumes.")


if __name__ == "__main__":
    main()
