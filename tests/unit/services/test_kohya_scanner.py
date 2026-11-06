"""kohya_scanner のテスト。"""

from pathlib import Path

from PIL import Image

from lorairo.services.kohya_scanner import (
    TRIGGER_CANDIDATE_MIN_RATE,
    parse_folder_name,
    scan_kohya_directory,
)


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(path)


def test_parse_folder_name_extracts_repeats_and_name() -> None:
    assert parse_folder_name("10_abe no seimei") == (10, "abe no seimei")
    assert parse_folder_name("sample001") is None


def test_scan_reads_only_direct_children_of_folders(tmp_path: Path) -> None:
    _make_image(tmp_path / "10_a" / "x.png")
    _make_image(tmp_path / "10_a" / "sub" / "y.png")
    folders = scan_kohya_directory(tmp_path)
    assert [i.file_stem for i in folders[0].images] == ["x"]


def test_scan_skips_excluded_and_non_repeat_folders(tmp_path: Path) -> None:
    for name in ("sample001", "終了", "10_a__Processed", "log", "plain", "10_ok"):
        _make_image(tmp_path / name / "x.png")
    folders = scan_kohya_directory(tmp_path)
    assert [f.dir_name for f in folders] == ["10_ok"]


def test_scan_reads_txt_and_caption_raw_text(tmp_path: Path) -> None:
    _make_image(tmp_path / "5_a" / "x.png")
    (tmp_path / "5_a" / "x.txt").write_bytes(b"Kariginu, (tag:1.2)\r\nline2")
    (tmp_path / "5_a" / "x.caption").write_bytes(b"cap, b")
    texts = scan_kohya_directory(tmp_path)[0].images[0].texts
    by_ext = {t.extension: t for t in texts}
    assert by_ext[".txt"].raw_text == "Kariginu, (tag:1.2)\r\nline2"
    assert by_ext[".caption"].raw_text == "cap, b"
    assert by_ext[".caption"].elements == ["cap", "b"]


def test_scan_image_without_text_has_empty_texts(tmp_path: Path) -> None:
    _make_image(tmp_path / "5_a" / "x.png")
    assert scan_kohya_directory(tmp_path)[0].images[0].texts == []


def test_scan_ignores_text_without_image(tmp_path: Path) -> None:
    _make_image(tmp_path / "5_a" / "x.png")
    (tmp_path / "5_a" / "orphan.txt").write_text("a, b")
    assert [i.file_stem for i in scan_kohya_directory(tmp_path)[0].images] == ["x"]


def test_trigger_candidate_uses_most_common_first_element(tmp_path: Path) -> None:
    for i in range(5):
        _make_image(tmp_path / "5_a" / f"{i}.png")
        (tmp_path / "5_a" / f"{i}.txt").write_text("kariginu, x")
    folder = scan_kohya_directory(tmp_path)[0]
    assert (folder.trigger_candidate, folder.trigger_match_rate) == ("kariginu", 1.0)


def test_trigger_candidate_none_below_threshold(tmp_path: Path) -> None:
    for i in range(5):
        _make_image(tmp_path / "5_b" / f"{i}.png")
        (tmp_path / "5_b" / f"{i}.txt").write_text("common, x" if i == 0 else f"other{i}, x")
    folder = scan_kohya_directory(tmp_path)[0]
    assert TRIGGER_CANDIDATE_MIN_RATE == 0.5
    assert folder.trigger_candidate is None
    assert folder.trigger_match_rate == 0.2
