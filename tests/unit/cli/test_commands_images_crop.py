"""``images crop`` コマンドのユニットテスト (Issue #1344)。

実 SQLite の ImageDatabaseManager と実 FileSystemManager を container 経由で注入し、
CLI から service までの配線を検証する。
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import TagAnnotationData
from lorairo.filesystem import FileSystemManager

runner = CliRunner()

pytestmark = pytest.mark.unit


def _jsonl(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


@pytest.fixture
def crop_cli_context(
    monkeypatch: pytest.MonkeyPatch,
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """親画像を 1 枚登録し、CLI が使う container を実オブジェクトへ差し替える。"""
    source = tmp_path / "cli_parent.png"
    Image.new("RGB", (1200, 900), (200, 40, 90)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id = registered[0]

    tags: list[TagAnnotationData] = [
        {
            "tag": "solo",
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        },
    ]
    test_db_manager.save_tags(parent_id, tags)
    test_db_manager.annotation_repo.update_manual_rating(parent_id, "PG")

    container = MagicMock()
    container.db_manager = test_db_manager
    container.file_system_manager = fs_manager
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return parent_id


class TestImagesCrop:
    def test_creates_child_and_emits_item_and_result(
        self,
        crop_cli_context: int,
        test_db_manager: ImageDatabaseManager,
    ) -> None:
        """JSON モードで item / result を出し、子画像 ID を返す。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "crop",
                str(crop_cli_context),
                "--project",
                "proj",
                "--x",
                "10",
                "--y",
                "20",
                "--width",
                "320",
                "--height",
                "240",
            ],
        )

        assert result.exit_code == 0, result.output
        rows = _jsonl(result.stdout)
        item = next(row for row in rows if row["kind"] == "item")
        terminal = rows[-1]
        assert isinstance(item["child_image_id"], int)
        assert item["parent_image_id"] == crop_cli_context
        assert (item["x"], item["y"], item["width"], item["height"]) == (10, 20, 320, 240)
        assert item["origin"] == "manual"
        # タグ・レーティングは既定で親から継承する。
        assert item["tag_count"] == 1
        assert item["rating"] == "PG"
        assert terminal["kind"] == "result"
        assert terminal["ok"] is True
        assert terminal["child_image_id"] == item["child_image_id"]

        children = test_db_manager.get_crop_children(crop_cli_context)
        assert [relation.child_image_id for relation in children] == [item["child_image_id"]]

    def test_explicit_tag_rating_and_origin_override_inheritance(
        self,
        crop_cli_context: int,
        test_db_manager: ImageDatabaseManager,
    ) -> None:
        """--tag / --rating / --origin は親からの継承を上書きする。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "crop",
                str(crop_cli_context),
                "--project",
                "proj",
                "--x",
                "0",
                "--y",
                "0",
                "--width",
                "128",
                "--height",
                "128",
                "--tag",
                "closeup",
                "--tag",
                "face",
                "--rating",
                "R",
                "--origin",
                "detector-v1",
            ],
        )

        assert result.exit_code == 0, result.output
        item = next(row for row in _jsonl(result.stdout) if row["kind"] == "item")
        assert item["tag_count"] == 2
        assert item["rating"] == "R"
        assert item["origin"] == "detector-v1"

        child_tags = {
            tag["tag"] for tag in test_db_manager.get_image_annotations(item["child_image_id"])["tags"]
        }
        assert child_tags == {"closeup", "face"}

    def test_invalid_rectangle_exits_two_with_error_row(
        self,
        crop_cli_context: int,
        test_db_manager: ImageDatabaseManager,
    ) -> None:
        """範囲外の矩形は INVALID_INPUT で exit 2、DB に子は作られない。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "crop",
                str(crop_cli_context),
                "--project",
                "proj",
                "--x",
                "0",
                "--y",
                "0",
                "--width",
                "5000",
                "--height",
                "5000",
            ],
        )

        assert result.exit_code == 2, result.output
        error = _jsonl(result.stdout)[-1]
        assert error["kind"] == "error"
        assert error["code"] == "INVALID_INPUT"
        assert test_db_manager.get_crop_children(crop_cli_context) == []

    def test_zero_size_rectangle_exits_two(self, crop_cli_context: int) -> None:
        """幅 0 の矩形も INVALID_INPUT で拒否される。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "crop",
                str(crop_cli_context),
                "--project",
                "proj",
                "--x",
                "0",
                "--y",
                "0",
                "--width",
                "0",
                "--height",
                "100",
            ],
        )

        assert result.exit_code == 2, result.output
        assert _jsonl(result.stdout)[-1]["code"] == "INVALID_INPUT"


def test_read_only_rejects_images_crop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--read-only では書き込みコマンドとして拒否される。"""
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(tmp_path / "cli.log"))
    created = runner.invoke(
        app, ["--json", "--workspace", str(workspace), "project", "create", "synthetic"]
    )
    assert created.exit_code == 0, created.output

    result = runner.invoke(
        app,
        [
            "--json",
            "--workspace",
            str(workspace),
            "--read-only",
            "images",
            "crop",
            "1",
            "--project",
            "synthetic",
            "--x",
            "0",
            "--y",
            "0",
            "--width",
            "10",
            "--height",
            "10",
        ],
    )

    assert result.exit_code == 1, result.output
    assert _jsonl(result.stdout)[-1]["code"] == "PRECONDITION_FAILED"
