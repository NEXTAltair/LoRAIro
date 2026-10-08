"""付属テキストの種別・サイズ・open 競合と既存解釈の回帰テスト (#1374)。"""

import os
import socket
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from lorairo.annotation.sidecar_reader import SIDECAR_MAX_BYTES, SidecarAnnotationReader
from lorairo.utils.log import logger
from lorairo.utils.tools import read_text_with_fallback

pytestmark = pytest.mark.unit


@pytest.fixture
def sidecar_logs():
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(sink)


@pytest.mark.parametrize("suffix,key", [(".txt", "tags"), (".caption", "captions")])
@pytest.mark.parametrize("size", [0, SIDECAR_MAX_BYTES - 1, SIDECAR_MAX_BYTES, SIDECAR_MAX_BYTES + 1])
def test_sidecar_byte_boundaries(tmp_path, suffix, key, size, sidecar_logs):
    image = tmp_path / "boundary.png"
    sidecar = image.with_suffix(suffix)
    sidecar.write_bytes(b"edge".ljust(size, b" ") if size else b"")
    result = SidecarAnnotationReader().get_existing_annotations(image)
    assert result is not None
    assert result[key] == (["edge"] if 0 < size <= SIDECAR_MAX_BYTES else [])
    if size > SIDECAR_MAX_BYTES:
        assert any(sidecar.name in line and "1 MiB" in line for line in sidecar_logs)


@pytest.mark.parametrize(
    "encoding,text",
    [
        ("utf-8", "1girl, 黒髪, 制服"),
        ("shift_jis", "1girl, 黒髪, 制服"),
        ("euc-jp", "1girl, 東京タワー"),
        ("latin-1", "café résumé"),
    ],
)
def test_sidecar_preserves_encoding_fallback(tmp_path, encoding, text):
    image = tmp_path / "encoded.png"
    image.with_suffix(".txt").write_bytes(text.encode(encoding))
    image.with_suffix(".caption").write_bytes(text.encode(encoding))
    result = SidecarAnnotationReader().get_existing_annotations(image)
    assert result["tags"] == [part.strip() for part in text.split(",")]
    assert result["captions"] == [text]


def test_parsing_and_universal_newlines_match_existing_reader(tmp_path):
    image = tmp_path / "parsed.png"
    image.with_suffix(".txt").write_bytes(b"  tag_one,,tag_two,\r\n tag_three,  ")
    image.with_suffix(".caption").write_bytes(b" First_line\r\nSecond_line\rThird_line ")
    result = SidecarAnnotationReader().get_existing_annotations(image)
    assert result["tags"] == ["tag one", "tag two", "tag three"]
    assert result["captions"] == ["First line, Second line, Third line"]


@pytest.mark.parametrize("kind", ["link", "dangling_link", "directory", "fifo", "socket"])
@pytest.mark.timeout(3)
def test_non_regular_sidecars_are_never_opened(tmp_path, monkeypatch, kind, sidecar_logs):
    image = tmp_path / "unsafe.png"
    sidecar = image.with_suffix(".txt")
    target = tmp_path / "private.txt"
    target.write_text("SECRET_SIDE_TEXT")
    sock = None
    if kind == "link":
        sidecar.symlink_to(target)
    elif kind == "dangling_link":
        sidecar.symlink_to(tmp_path / "missing.txt")
    elif kind == "directory":
        sidecar.mkdir()
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO")
        os.mkfifo(sidecar)
    else:
        if not hasattr(socket, "AF_UNIX"):
            pytest.skip("Unix socket")
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(sidecar))
    opens = []
    real_open = os.open

    def track_open(path, flags):
        opens.append(path)
        return real_open(path, flags)

    monkeypatch.setattr(os, "open", track_open)
    try:
        result = SidecarAnnotationReader().get_existing_annotations(image)
    finally:
        if sock is not None:
            sock.close()
    assert result["tags"] == []
    assert opens == []
    assert any(sidecar.name in line for line in sidecar_logs)
    assert all("SECRET_SIDE_TEXT" not in line for line in sidecar_logs)


@pytest.mark.parametrize("mode", [stat.S_IFCHR, stat.S_IFBLK])
def test_device_sidecars_are_rejected_before_open(tmp_path, monkeypatch, mode):
    image = tmp_path / "device.png"
    real_lstat = Path.lstat

    def lstat(path):
        if path == image.with_suffix(".txt"):
            return SimpleNamespace(st_mode=mode, st_size=0)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(os, "open", lambda *_: pytest.fail("device was opened"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


def test_pre_stat_oversize_never_opens_sidecar(tmp_path, monkeypatch):
    image = tmp_path / "large.png"
    image.with_suffix(".txt").write_bytes(b"x" * (SIDECAR_MAX_BYTES + 1))
    monkeypatch.setattr(os, "open", lambda *_: pytest.fail("oversized sidecar was opened"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


@pytest.mark.parametrize("replacement", ["link", "fifo", "regular", "directory"])
@pytest.mark.timeout(3)
def test_lstat_open_replacement_is_rejected_without_reading(
    tmp_path, monkeypatch, replacement, sidecar_logs
):
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "mkfifo"):
        pytest.skip("POSIX open protections")
    image = tmp_path / "race.png"
    sidecar = image.with_suffix(".txt")
    sidecar.write_text("normal tag")
    target = tmp_path / "private.txt"
    target.write_text("SECRET_RACE_BODY")
    real_open = os.open

    def replace_before_open(path, flags):
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_NONBLOCK
        sidecar.rename(tmp_path / "original.txt")
        if replacement == "link":
            sidecar.symlink_to(target)
        elif replacement == "fifo":
            os.mkfifo(sidecar)
        elif replacement == "directory":
            sidecar.mkdir()
        else:
            sidecar.write_text("SECRET_RACE_BODY")
        return real_open(path, flags)

    monkeypatch.setattr(os, "open", replace_before_open)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("replacement was read"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []
    assert all("SECRET_RACE_BODY" not in line for line in sidecar_logs)


def test_fallback_rechecks_link_even_if_it_points_to_original_inode(tmp_path, monkeypatch):
    image = tmp_path / "fallback.png"
    sidecar = image.with_suffix(".txt")
    sidecar.write_text("private tag")
    real_open = os.open
    monkeypatch.setattr(os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(os, "O_NONBLOCK", 0, raising=False)

    def replace_before_open(path, flags):
        original = tmp_path / "original.txt"
        sidecar.rename(original)
        sidecar.symlink_to(original)
        return real_open(path, flags)

    monkeypatch.setattr(os, "open", replace_before_open)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("fallback followed a link"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


def test_reparse_points_are_rejected_before_open(tmp_path, monkeypatch):
    image = tmp_path / "reparse.png"
    real_lstat = Path.lstat

    def lstat(path):
        if path == image.with_suffix(".txt"):
            return SimpleNamespace(
                st_mode=stat.S_IFREG, st_size=0, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
            )
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(os, "open", lambda *_: pytest.fail("reparse point was opened"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


def test_growth_after_open_is_bounded_and_discards_all_content(tmp_path, monkeypatch, sidecar_logs):
    image = tmp_path / "growing.png"
    sidecar = image.with_suffix(".txt")
    sidecar.write_bytes(b"partial tag")
    real_read = os.read
    requested = []

    def grow_before_read(descriptor, size):
        if not requested:
            sidecar.write_bytes(b"partial tag," + b"x" * SIDECAR_MAX_BYTES)
        requested.append(size)
        return real_read(descriptor, size)

    monkeypatch.setattr(os, "read", grow_before_read)
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []
    assert sum(requested) == SIDECAR_MAX_BYTES + 1
    assert max(requested) <= 64 * 1024
    assert any("during reading" in line for line in sidecar_logs)
    assert all("partial tag" not in line for line in sidecar_logs)


def test_growth_between_lstat_and_fstat_is_rejected_without_reading(tmp_path, monkeypatch):
    image = tmp_path / "open_growth.png"
    sidecar = image.with_suffix(".txt")
    sidecar.write_bytes(b"partial tag")
    real_open = os.open

    def grow_before_open(path, flags):
        sidecar.write_bytes(b"x" * (SIDECAR_MAX_BYTES + 1))
        return real_open(path, flags)

    monkeypatch.setattr(os, "open", grow_before_open)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("oversized opened sidecar was read"))
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


def test_growth_at_eof_is_rejected_by_final_stat(tmp_path, monkeypatch):
    image = tmp_path / "late_growth.png"
    sidecar = image.with_suffix(".txt")
    sidecar.write_text("partial tag")
    real_read = os.read

    def grow_at_eof(descriptor, size):
        data = real_read(descriptor, size)
        if not data:
            sidecar.write_bytes(b"x" * (SIDECAR_MAX_BYTES + 1))
        return data

    monkeypatch.setattr(os, "read", grow_at_eof)
    assert SidecarAnnotationReader().get_existing_annotations(image)["tags"] == []


def test_shared_text_reader_keeps_its_unrestricted_contract(tmp_path):
    text = "x" * (SIDECAR_MAX_BYTES + 1)
    target = tmp_path / "general.txt"
    target.write_text(text)
    assert read_text_with_fallback(target) == text
