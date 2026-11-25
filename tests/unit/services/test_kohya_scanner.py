"""kohya_scanner のテスト。"""

from pathlib import Path

from PIL import Image

from lorairo.services.kohya_scanner import (
    DEFAULT_DISCOVERY_MAX_DEPTH,
    TRIGGER_CANDIDATE_MIN_RATE,
    discover_kohya_roots,
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


# --- 親フォルダからの探索 (Issue #1648) ---


def _make_version(parent: Path, *parts: str) -> Path:
    """`parent/<parts...>/10_a/x.png` を作り、取り込みのルート (`10_a` の親) を返す。"""
    root = parent.joinpath(*parts)
    _make_image(root / "10_a" / "x.png")
    return root


def test_discover_finds_roots_under_version_folders(tmp_path: Path) -> None:
    v1 = _make_version(tmp_path, "raikou_v01", "lora_train_data", "train_dir")
    v6 = _make_version(tmp_path, "raikou_v06ps", "lora_train_data", "train_dir")
    flat = _make_version(tmp_path, "raikou_v02")

    assert discover_kohya_roots(tmp_path) == [v1, flat, v6]


def test_discover_returns_parent_itself_when_it_is_a_root(tmp_path: Path) -> None:
    _make_version(tmp_path)

    assert discover_kohya_roots(tmp_path) == [tmp_path]


def test_discover_does_not_treat_symlinked_repeat_folder_as_root(tmp_path: Path) -> None:
    """Codex P2 (PR #1652): `10_link` のシンボリックリンクで親を誤ってルートと判定しない。"""
    v1 = _make_version(tmp_path, "raikou_v01", "train_dir")
    v2 = _make_version(tmp_path, "raikou_v02", "train_dir")
    (tmp_path / "10_link").symlink_to(v1 / "10_a", target_is_directory=True)

    assert discover_kohya_roots(tmp_path) == [v1, v2]


def test_discover_does_not_go_below_a_found_root(tmp_path: Path) -> None:
    root = _make_version(tmp_path, "v1")
    _make_version(root, "nested")

    assert discover_kohya_roots(tmp_path) == [root]


def test_discover_depth_limit_is_four(tmp_path: Path) -> None:
    assert DEFAULT_DISCOVERY_MAX_DEPTH == 4
    at_limit = _make_version(tmp_path, "a", "b", "c", "d")
    _make_version(tmp_path, "deep", "b", "c", "d", "e")

    assert discover_kohya_roots(tmp_path) == [at_limit]


def test_discover_does_not_enter_excluded_folders(tmp_path: Path) -> None:
    kept = _make_version(tmp_path, "v1")
    for name in ("sample", "sample_old", "reg", "log", "logs", "wandb", "old__Processed", "終了"):
        _make_version(tmp_path, name)
        _make_version(tmp_path, name, "deeper")

    assert discover_kohya_roots(tmp_path) == [kept]


def test_discover_does_not_treat_excluded_repeat_folder_as_root(tmp_path: Path) -> None:
    """除外パターンに一致する `<数字>_<名前>` しか無いディレクトリは候補にしない。"""
    _make_image(tmp_path / "v1" / "10_a__Processed" / "x.png")

    assert discover_kohya_roots(tmp_path) == []


def test_discover_ignores_archives(tmp_path: Path) -> None:
    kept = _make_version(tmp_path, "v1")
    (tmp_path / "v0.7z").write_bytes(b"7z")
    (tmp_path / "10_v0.zip").write_bytes(b"PK")

    assert discover_kohya_roots(tmp_path) == [kept]


def test_discover_uses_extra_exclude_patterns(tmp_path: Path) -> None:
    kept = _make_version(tmp_path, "v1")
    _make_version(tmp_path, "backup")

    roots = discover_kohya_roots(tmp_path, ("backup",))

    assert roots == [kept]
