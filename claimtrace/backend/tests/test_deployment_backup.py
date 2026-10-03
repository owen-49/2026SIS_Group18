"""Recover actual files and reject corrupt or unsafe archives before writing data."""

import io
import tarfile

import pytest
from backend.deploy.manage_data import backup, restore
from backend.deploy.smoke_deployment import _pdf


def test_backup_restore_roundtrip(tmp_path):
    source = tmp_path / "uploads"
    (source / "parsed/audits").mkdir(parents=True)
    (source / "verify-sources").mkdir()
    (source / "papers.json").write_text('{"papers": []}')
    (source / "parsed/audits/report.json").write_text('{"contract_version": 2}')
    (source / "verify-sources/source.pdf").write_bytes(b"%PDF-test")
    archive = tmp_path / "backup.tar.gz"
    assert backup(source, archive)["files"] == 3
    target = tmp_path / "restored"
    assert restore(archive, target)["files"] == 3
    for path in source.rglob("*"):
        restored = target / path.relative_to(source)
        if path.is_file():
            assert restored.read_bytes() == path.read_bytes()
        else:
            assert restored.is_dir()


def test_existing_data_and_archive_are_preserved(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    valuable = source / "papers.json"
    valuable.write_text("original")
    archive = tmp_path / "backup.tar.gz"
    backup(source, archive)
    with pytest.raises(ValueError, match="new file"):
        backup(source, archive)
    with pytest.raises(ValueError, match="empty"):
        restore(archive, source)
    assert valuable.read_text() == "original"


@pytest.mark.parametrize("name", ["files/../../outside", "/absolute", "files/link"])
def test_unsafe_archive_does_not_touch_destination(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo(name)
        if name == "files/link":
            info.type = tarfile.SYMTYPE
            info.linkname = "../../outside"
            output.addfile(info)
        else:
            info.size = 3
            output.addfile(info, io.BytesIO(b"bad"))
    destination = tmp_path / "restored"
    with pytest.raises((ValueError, KeyError)):
        restore(archive, destination)
    assert not destination.exists()
    assert not (tmp_path / "outside").exists()


def test_bad_checksum_leaves_empty_destination_untouched(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "papers.json").write_text("original")
    good = tmp_path / "good.tar.gz"
    bad = tmp_path / "bad.tar.gz"
    backup(source, good)
    with tarfile.open(good, "r:gz") as original, tarfile.open(bad, "w:gz") as output:
        for member in original.getmembers():
            with original.extractfile(member) as stream:
                content = stream.read()
            if member.name == "files/papers.json":
                content = b"tampered"
            output.addfile(member, io.BytesIO(content))
    destination = tmp_path / "restored"
    destination.mkdir()
    with pytest.raises(ValueError, match="checksum"):
        restore(bad, destination)
    assert list(destination.iterdir()) == []


def test_acceptance_fixture_uses_real_parser_and_persisted_manuscript(client):
    response = client.post(
        "/api/parse", files={"file": ("acceptance.pdf", _pdf(), "application/pdf")},
    )
    assert response.status_code == 200
    parsed = response.json()
    assert parsed["status"] == "completed"
    assert parsed["paragraph_count"] > 0
    manuscript = client.get(f"/api/papers/{parsed['paper_id']}/claims").json()
    assert manuscript["status"] == "completed"
    assert manuscript["manuscript_document"]
    assert manuscript["claims"] == []


def test_hardlinked_data_files_restore_as_regular_files(tmp_path):
    import os

    source = tmp_path / "uploads"
    source.mkdir()
    (source / "original.pdf").write_bytes(b"%PDF-acceptance")
    os.link(source / "original.pdf", source / "copy.pdf")
    archive = tmp_path / "backup.tar.gz"
    backup(source, archive)
    target = tmp_path / "restored"
    restore(archive, target)
    assert (target / "copy.pdf").read_bytes() == (target / "original.pdf").read_bytes()
