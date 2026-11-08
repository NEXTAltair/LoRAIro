"""``images crop-batch`` コマンドのユニットテスト (Issue #1340 / ADR 0103)。

実 SQLite の ImageDatabaseManager と実 FileSystemManager を container 経由で注入し、
JSONL → provider → 一括作成 → JSONL 出力 / 終了コードの配線を検証する。
"""

import json
import random
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.filesystem import FileSystemManager

runner = CliRunner()

pytestmark = pytest.mark.unit


def _jsonl(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


@pytest.fixture
def parent_id(
    monkeypatch: pytest.MonkeyPatch,
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """ノイズ画像 (400x300) を親として登録し、CLI の container を実オブジェクトへ差し替える。"""
    source = tmp_path / "noise_parent.png"
    Image.frombytes("RGB", (400, 300), random.Random(7).randbytes(400 * 300 * 3)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None

    container = MagicMock()
    container.db_manager = test_db_manager
    container.file_system_manager = fs_manager
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return registered[0]


def _rects(tmp_path: Path, *rows: str) -> str:
    path = tmp_path / "rects.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def _row(image_id: int, x: int, y: int, w: int, h: int, **extra: Any) -> str:
    return json.dumps({"image_id": image_id, "x": x, "y": y, "width": w, "height": h, **extra})


def _invoke(rects: str, *extra: str, json_mode: bool = True) -> Any:
    args = ["--json"] if json_mode else ["--no-json"]
    return runner.invoke(
        app, [*args, "images", "crop-batch", "--project", "proj", "--rects", rects, *extra]
    )


def test_all_rows_created_exit_zero(
    parent_id: int, tmp_path: Path, test_db_manager: ImageDatabaseManager
) -> None:
    rects = _rects(
        tmp_path,
        _row(parent_id, 0, 0, 100, 100, score=0.9),
        _row(parent_id, 200, 100, 150, 150, origin="yolo"),
    )

    result = _invoke(rects)

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    items = [row for row in rows if row["kind"] == "item"]
    assert [(i["line"], i["status"], i["origin"]) for i in items] == [
        (1, "created", "manual"),
        (2, "created", "yolo"),
    ]
    assert items[0]["score"] == 0.9
    terminal = rows[-1]
    assert terminal["kind"] == "result"
    assert (terminal["ok"], terminal["status"], terminal["created"], terminal["failed"]) == (
        True,
        "success",
        2,
        0,
    )
    assert terminal["created_ids"] == [i["child_image_id"] for i in items]
    assert len(test_db_manager.get_crop_children(parent_id)) == 2


def test_partial_success_reports_line_numbers_and_exits_3(
    parent_id: int, tmp_path: Path, test_db_manager: ImageDatabaseManager
) -> None:
    rects = _rects(
        tmp_path,
        _row(parent_id, 0, 0, 100, 100),
        "{broken",
        _row(parent_id, 350, 0, 100, 100),
        _row(424242, 0, 0, 10, 10),
    )

    result = _invoke(rects)

    assert result.exit_code == 3, result.output
    rows = _jsonl(result.stdout)
    by_line = {row["line"]: row for row in rows if row["kind"] == "item"}
    assert by_line[1]["status"] == "created"
    assert (by_line[2]["status"], by_line[2]["reason"]) == ("failed", "invalid_row")
    assert (by_line[3]["status"], by_line[3]["reason"]) == ("failed", "invalid_rect")
    assert (by_line[4]["status"], by_line[4]["reason"]) == ("failed", "parent_not_found")
    terminal = rows[-1]
    assert (terminal["ok"], terminal["status"], terminal["failed_lines"]) == (
        False,
        "partial_success",
        [2, 3, 4],
    )


def test_all_failed_exits_1_and_human_mode_lists_lines(parent_id: int, tmp_path: Path) -> None:
    rects = _rects(tmp_path, _row(parent_id, 0, 0, 999, 10))

    result = _invoke(rects, json_mode=False)

    assert result.exit_code == 1, result.output
    assert "line=1" in result.stdout
    assert "invalid_rect" in result.stdout


def test_rerun_is_idempotent(parent_id: int, tmp_path: Path, test_db_manager: ImageDatabaseManager) -> None:
    rects = _rects(tmp_path, _row(parent_id, 0, 0, 100, 100))
    assert _invoke(rects).exit_code == 0

    result = _invoke(rects)

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    assert rows[0]["status"] == "skipped"
    assert rows[0]["reason"] == "already_exists"
    assert (rows[-1]["skipped"], rows[-1]["created"]) == (1, 0)
    assert len(test_db_manager.get_crop_children(parent_id)) == 1


def test_dry_run_writes_nothing(
    parent_id: int, tmp_path: Path, test_db_manager: ImageDatabaseManager
) -> None:
    rects = _rects(tmp_path, _row(parent_id, 0, 0, 100, 100))

    result = _invoke(rects, "--dry-run", "--origin", "external")

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    assert (rows[0]["status"], rows[0]["origin"]) == ("would_create", "external")
    assert (rows[-1]["dry_run"], rows[-1]["would_create"], rows[-1]["created_ids"]) == (True, 1, [])
    assert test_db_manager.get_crop_children(parent_id) == []


def test_more_than_500_rows_is_rejected_before_writing(
    parent_id: int, tmp_path: Path, test_db_manager: ImageDatabaseManager
) -> None:
    rects = _rects(tmp_path, *[_row(parent_id, 0, 0, 10 + i, 10) for i in range(501)])

    result = _invoke(rects)

    assert result.exit_code == 2, result.output
    error = _jsonl(result.stdout)[-1]
    assert error["kind"] == "error"
    assert error["code"] == "RESULT_SET_TOO_LARGE"
    assert error["details"] == {"limit": 500, "matched": 501}
    assert test_db_manager.get_crop_children(parent_id) == []


def test_missing_rects_file_is_input_error(parent_id: int, tmp_path: Path) -> None:
    result = _invoke(str(tmp_path / "missing.jsonl"))

    assert result.exit_code == 2, result.output
    assert _jsonl(result.stdout)[-1]["code"] == "INVALID_INPUT"
