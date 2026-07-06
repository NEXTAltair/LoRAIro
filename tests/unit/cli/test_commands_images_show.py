"""images show コマンドのユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _annotations_for(image_id: int) -> dict:
    return {
        "tags": [
            {
                "id": 1,
                "tag": f"tag-{image_id}",
                "tag_id": 10,
                "model_id": 3,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
                "rejected_at": None,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        "captions": [],
        "scores": [],
        "score_labels": [],
        "ratings": [],
        "quality_summary": {},
    }


def _metadata_row_for(image_id: int) -> dict:
    return {
        "id": image_id,
        "uuid": f"uuid-{image_id}",
        "phash": f"phash-{image_id}",
        "original_image_path": f"C:\\src\\img_{image_id}.jpg",
        "stored_image_path": f"image_dataset/original_images/img_{image_id}.jpg",
        "width": 850,
        "height": 1249,
        "format": "JPEG",
        "filename": f"img_{image_id}",
        "extension": "jpg",
        "mode": "RGB",
    }


def _make_container(image_ids: list[int]) -> MagicMock:
    container = MagicMock()
    records = [{"id": i} for i in image_ids]
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.image_repo.get_image_annotations_batch.side_effect = (
        lambda image_ids, include_rejected=False: {i: _annotations_for(i) for i in image_ids}
    )
    container.db_manager.image_repo.get_images_metadata_batch.side_effect = (
        lambda image_ids, include_annotations=True: [_metadata_row_for(i) for i in image_ids]
    )
    return container


@pytest.fixture
def mock_show_context(monkeypatch: pytest.MonkeyPatch):
    container = _make_container([42, 57])
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestImagesShow:
    def test_show_single_image_json(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 1
        assert items[0]["image_id"] == 42
        assert items[0]["tags"][0]["tag"] == "tag-42"
        assert result_row["ok"] is True
        assert result_row["target_images"] == 1

    def test_show_item_includes_image_metadata(self, mock_show_context: MagicMock) -> None:
        """item 出力に画像実物突き合わせ用のメタデータが載る (Issue #1215)。"""
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        item = next(r for r in lines if r.get("kind") == "item")
        metadata = item["metadata"]
        assert metadata["stored_image_path"] == "image_dataset/original_images/img_42.jpg"
        # Windows 由来のバックスラッシュはスラッシュ区切りへ正規化される
        assert metadata["original_image_path"] == "C:/src/img_42.jpg"
        assert metadata["width"] == 850
        assert metadata["height"] == 1249
        assert metadata["format"] == "JPEG"
        assert metadata["filename"] == "img_42"
        assert metadata["extension"] == "jpg"
        assert metadata["phash"] == "phash-42"
        assert metadata["uuid"] == "uuid-42"
        # アノテーションは既に別経路で取得済みのため二重フェッチしない
        repo = mock_show_context.db_manager.image_repo
        repo.get_images_metadata_batch.assert_called_once_with([42], include_annotations=False)

    def test_show_metadata_missing_row_is_null(self, mock_show_context: MagicMock) -> None:
        """メタデータ行が取れない画像は metadata=null で縮退する (Issue #1215)。"""
        repo = mock_show_context.db_manager.image_repo
        repo.get_images_metadata_batch.side_effect = lambda image_ids, include_annotations=True: []
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        item = next(r for r in lines if r.get("kind") == "item")
        assert item["metadata"] is None

    def test_show_batch_csv(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42,57"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        assert {row["image_id"] for row in items} == {42, 57}

    def test_show_passes_include_rejected_flag(self, mock_show_context: MagicMock) -> None:
        runner.invoke(
            app,
            [
                "--json",
                "images",
                "show",
                "--project",
                "proj",
                "--image-ids",
                "42",
                "--include-rejected",
            ],
        )
        mock_show_context.db_manager.image_repo.get_image_annotations_batch.assert_any_call(
            [42], include_rejected=True
        )

    def test_show_missing_image_id_errors(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "999"],
        )
        assert result.exit_code != 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        error_row = next(r for r in lines if r.get("kind") == "error")
        assert error_row["code"] == "NOT_FOUND"

    def test_show_over_500_ids_rejected(self, mock_show_context: MagicMock) -> None:
        csv_ids = ",".join(str(i) for i in range(1, 502))
        result = runner.invoke(
            app,
            ["images", "show", "--project", "proj", "--image-ids", csv_ids],
        )
        assert result.exit_code != 0

    def test_show_positional_ids_json(self, mock_show_context: MagicMock) -> None:
        """位置引数でも画像 ID を指定できる (Issue #1175)。"""
        result = runner.invoke(
            app,
            ["--json", "images", "show", "42", "57", "--project", "proj"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [row for row in lines if row.get("kind") == "item"]
        assert [row["image_id"] for row in items] == [42, 57]

    def test_show_positional_csv_mixed(self, mock_show_context: MagicMock) -> None:
        """位置引数のカンマ区切りと --image-ids の併用をマージする (Issue #1175)。"""
        result = runner.invoke(
            app,
            ["--json", "images", "show", "42,57", "--project", "proj"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [row for row in lines if row.get("kind") == "item"]
        assert [row["image_id"] for row in items] == [42, 57]

    def test_show_without_any_ids_errors(self, mock_show_context: MagicMock) -> None:
        """位置引数も --image-ids も無い場合は INVALID_INPUT で exit 2 (Issue #1175)。"""
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj"],
        )
        assert result.exit_code == 2
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        error_row = next(r for r in lines if r.get("kind") == "error")
        assert error_row["code"] == "INVALID_INPUT"
