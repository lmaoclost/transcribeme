"""Lock in chunked upload service: allowed types, chunk append, finalize, missing upload."""

from __future__ import annotations

import os

import pytest
from types import SimpleNamespace


@pytest.fixture()
def isolated_uploads(tmp_path, monkeypatch):
    import app.services.uploads as uploads

    monkeypatch.setattr(uploads, "settings", SimpleNamespace(downloads_dir=str(tmp_path)))
    return uploads


def test_only_mp4_mp3_allowed(isolated_uploads):
    assert isolated_uploads.is_allowed_file("clip.mp4")
    assert isolated_uploads.is_allowed_file("audio.MP3")
    assert not isolated_uploads.is_allowed_file("movie.mkv")
    assert not isolated_uploads.is_allowed_file("notes.txt")


def test_chunk_roundtrip_reassembles_bytes(isolated_uploads):
    uid = "u1"
    isolated_uploads.append_chunk(uid, b"hello ")
    isolated_uploads.append_chunk(uid, b"world")
    assert isolated_uploads.get_uploaded_size(uid) == 11

    final = isolated_uploads.finalize_upload(uid, "my clip.mp4")
    assert final.read_bytes() == b"hello world"
    assert final.suffix == ".mp4"
    assert not os.path.exists(isolated_uploads.get_upload_path(uid))


def test_finalize_missing_upload_raises(isolated_uploads):
    with pytest.raises(FileNotFoundError):
        isolated_uploads.finalize_upload("nope", "x.mp4")
