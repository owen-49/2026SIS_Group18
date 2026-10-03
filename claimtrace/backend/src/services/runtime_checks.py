"""Local deployment checks. Never contact an LLM or metadata provider."""

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import get_settings


def _java_available() -> bool:
    java = shutil.which("java")
    if java is None:
        return False
    try:
        result = subprocess.run(
            [java, "-version"], capture_output=True, text=True, timeout=5, check=False,
        )
        match = re.search(r'version "(\d+)(?:\.(\d+))?', result.stderr + result.stdout)
        if result.returncode != 0 or match is None:
            return False
        major = int(match[1])
        if major == 1:
            major = int(match[2] or 0)
        return major >= 11
    except (OSError, subprocess.TimeoutExpired):
        return False


def _writable(directory: Path, create: bool) -> bool:
    try:
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"claimtrace-readiness")
            probe.flush()
        return True
    except OSError:
        return False


def runtime_checks(*, create_directories: bool = False) -> dict[str, bool]:
    """Check dependencies and storage, without disclosing paths or credentials.

    Package discovery is intentionally cheap: this does not load Torch or
    download an embedding model. Real PDF/model checks belong to the smoke run.
    """
    settings = get_settings()
    modules = ("parser", "engine", "fitz", "opendataloader_pdf", "faiss", "sentence_transformers")
    checks = {
        f"package_{module}": importlib.util.find_spec(module) is not None for module in modules
    }
    checks["java_11_or_newer"] = _java_available()
    for label, directory in (
        ("uploads_writable", settings.upload_dir),
        ("paper_store_writable", settings.papers_file.parent),
        ("parsed_writable", settings.parsed_dir),
    ):
        checks[label] = _writable(directory, create_directories)
    cache = os.getenv("HF_HOME")
    if cache:
        checks["model_cache_writable"] = _writable(Path(cache), create_directories)
    return checks
