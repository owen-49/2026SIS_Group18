"""Offline backup/restore of the uploads tree, including all JSON artifacts.

Stop the backend before either command. Restore refuses non-empty destinations.
Archives contain relative paths and SHA-256 checksums, never deployment secrets.
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def _relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name or len(name) > 4096 or path.is_absolute()
        or ".." in path.parts or "\\" in name or ":" in name
        or str(path) != name or name == "."
    ):
        raise ValueError("Archive contains an unsafe relative path.")
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup(data_dir: Path, archive: Path) -> dict:
    if data_dir.is_symlink() or not data_dir.is_dir():
        raise ValueError("Backup source must be a real data directory.")
    root = data_dir.resolve()
    archive = archive.resolve()
    if archive.is_relative_to(root) or archive.exists():
        raise ValueError("Archive must be a new file outside the data directory.")
    files = {}
    directories = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Data symlinks are not supported in backups.")
        relative = path.relative_to(root).as_posix()
        _relative(relative)
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = {"size": path.stat().st_size, "sha256": _digest(path)}
        else:
            raise ValueError("Only regular data files and directories can be backed up.")
    manifest = {"version": 1, "directories": directories, "files": files}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="claimtrace-backup-", dir=archive.parent) as temp:
        staged = Path(temp) / "backup.tar.gz"
        with tarfile.open(staged, "w:gz", dereference=True) as output:
            encoded = json.dumps(manifest, sort_keys=True).encode()
            header = tarfile.TarInfo("manifest.json")
            header.size = len(encoded)
            header.mode = 0o600
            output.addfile(header, io.BytesIO(encoded))
            for relative, expected in files.items():
                path = root / relative
                output.add(path, arcname=f"files/{relative}", recursive=False)
                if path.stat().st_size != expected["size"] or _digest(path) != expected["sha256"]:
                    raise ValueError("Data changed during backup; stop the backend and retry.")
        staged.chmod(0o600)
        # Publish without overwriting a backup created by another operator.
        os.link(staged, archive)
    return {"files": len(files), "archive": str(archive)}


def restore(archive: Path, data_dir: Path) -> dict:
    if data_dir.is_symlink():
        raise ValueError("Restore destination cannot be a symlink.")
    target = data_dir.resolve()
    if target == Path(target.anchor) or target.exists() and (
        not target.is_dir() or any(target.iterdir())
    ):
        raise ValueError("Restore requires a new or empty data directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        if len({member.name for member in members}) != len(members):
            raise ValueError("Archive contains duplicate members.")
        if any(not member.isfile() for member in members):
            raise ValueError("Archive contains a link or non-regular member.")
        header = source.getmember("manifest.json")
        if header.size > 10 * 1024 * 1024:
            raise ValueError("Archive manifest is too large.")
        with source.extractfile(header) as stream:
            manifest = json.load(stream)
        if manifest.get("version") != 1:
            raise ValueError("Unsupported backup format.")
        files = manifest["files"]
        directories = manifest["directories"]
        for name in [*files, *directories]:
            _relative(name)
        expected_names = {"manifest.json", *(f"files/{name}" for name in files)}
        if {member.name for member in members} != expected_names:
            raise ValueError("Archive contents do not match its manifest.")
        with tempfile.TemporaryDirectory(prefix="claimtrace-restore-", dir=target.parent) as temp:
            staged = Path(temp) / "uploads"
            staged.mkdir(mode=0o700)
            for name in directories:
                (staged / name).mkdir(parents=True, exist_ok=True)
            for name, expected in files.items():
                member = source.getmember(f"files/{name}")
                if member.size != expected["size"]:
                    raise ValueError("Backup file size does not match its checksum manifest.")
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream, destination.open("xb") as output:
                    shutil.copyfileobj(stream, output)
                if _digest(destination) != expected["sha256"]:
                    raise ValueError("Backup checksum validation failed.")
            if target.exists():
                # Never delete existing records, even if another process wrote meanwhile.
                target.rmdir()
            staged.rename(target)
    return {"files": len(files), "restored_to": str(target)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--data-dir", type=Path, default=Path("/data/uploads"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--offline", action="store_true", required=True,
        help="Confirm that the backend using this data is stopped.",
    )
    args = parser.parse_args()
    try:
        result = (
            backup(args.data_dir, args.archive) if args.operation == "backup"
            else restore(args.archive, args.data_dir)
        )
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        parser.exit(1, f"Data operation failed: {exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
