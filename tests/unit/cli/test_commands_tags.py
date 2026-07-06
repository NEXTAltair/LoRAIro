"""tags コマンド群のユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.repository.annotation_record import ManualTagClassification

runner = CliRunner()


def _exact_classification(tag: str) -> ManualTagClassification:
    return ManualTagClassification(tag, tag, "exact", tag, 10, [])


def _make_container(*, image_exists: bool = True) -> MagicMock:
    container = MagicMock()
    mock_records = [{"id": 1}, {"id": 2}] if image_exists else []
    container.db_manager.image_repo.get_images_by_filter.return_value = (mock_records, len(mock_records))
    # classify は実 dataclass を返す (分類結果が JSON 出力に載るため MagicMock 不可、Issue #1174)
    container.db_manager.annotation_repo.classify_manual_tag.side_effect = _exact_classification
    container.db_manager.annotation_repo.register_user_tag.return_value = 111
    container.db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 2)
    container.db_manager.annotation_repo.remove_tag_from_images_batch.return_value = (
        True,
        [(1, "changed"), (2, "changed")],
    )
    container.db_manager.annotation_repo.replace_tag_for_images_batch.return_value = (
        True,
        [(1, "changed"), (2, "skipped")],
    )
    # dry-run 見積り用の読み取り専用 preview (Issue #1217)
    container.db_manager.annotation_repo.preview_add_tag_to_images_batch.return_value = 2
    container.db_manager.annotation_repo.preview_remove_tag_from_images_batch.return_value = [
        (1, "changed"),
        (2, "skipped"),
    ]
    return container


@pytest.fixture
def mock_project_and_container(monkeypatch):
    container = _make_container()
    monkeypatch.setattr("lorairo.cli.commands.tags.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.tags.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestTagsAdd:
    def test_add_dry_run_default_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_not_called()

    def test_add_apply_writes_to_db(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_called()

    def test_add_dry_run_result_has_would_add(self, mock_project_and_container):
        """dry-run 出力に追加見込み件数 (既存重複スキップ込み) が載る (Issue #1217)。"""
        repo = mock_project_and_container.db_manager.annotation_repo
        result = runner.invoke(
            app,
            ["--json", "tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat"],
        )
        assert result.exit_code == 0
        row = _json_result_row(result.stdout)
        assert row["dry_run"] is True
        assert row["would_add"] == 2
        repo.preview_add_tag_to_images_batch.assert_called_once_with([1, 2], "cat")
        repo.add_tag_to_images_batch.assert_not_called()

    def test_add_apply_result_has_no_would_add(self, mock_project_and_container):
        """would_add は dry-run 専用フィールド (Issue #1217)。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "cat",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        row = _json_result_row(result.stdout)
        assert row["dry_run"] is False
        assert "would_add" not in row
        assert row["added"] == 2

    def test_add_json_output_has_result_row(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "cat",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False


def _json_result_row(output: str) -> dict:
    lines = [json.loads(line) for line in output.strip().splitlines() if line.strip().startswith("{")]
    return next(r for r in lines if r.get("kind") == "result")


@pytest.mark.unit
class TestTagsAddClassification:
    """tags add の refinement 分類 surface (Issue #1174)。"""

    def test_dry_run_emits_tag_resolutions_without_registration(self, mock_project_and_container):
        repo = mock_project_and_container.db_manager.annotation_repo
        result = runner.invoke(
            app,
            ["--json", "tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat"],
        )
        assert result.exit_code == 0
        row = _json_result_row(result.stdout)
        assert row["tag_resolutions"] == [
            {
                "tag": "cat",
                "classification": "exact",
                "canonical_tag": "cat",
                "tag_id": 10,
                "candidates": [],
            }
        ]
        repo.register_user_tag.assert_not_called()
        repo.add_tag_to_images_batch.assert_not_called()

    def test_apply_registers_unregistered_tag_to_user_db(self, mock_project_and_container):
        repo = mock_project_and_container.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda tag: ManualTagClassification(
            tag, tag, "unregistered", tag, None, []
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "brand_new_tag",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        repo.register_user_tag.assert_called_once_with("brand_new_tag")
        repo.add_tag_to_images_batch.assert_called_once_with(
            [1, 2], "brand_new_tag", None, resolved=("brand_new_tag", 111)
        )
        row = _json_result_row(result.stdout)
        assert row["tag_resolutions"][0]["tag_id"] == 111
        assert row["unresolved_tag_count"] == 0

    def test_apply_surfaces_typo_candidates_without_auto_alias(self, mock_project_and_container):
        repo = mock_project_and_container.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda tag: ManualTagClassification(
            tag, tag, "typo_candidate", tag, None, ["european architecture"]
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "europian architecture",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        # typo 候補は user DB 登録しない (自動 alias 化しない)
        repo.register_user_tag.assert_not_called()
        repo.add_tag_to_images_batch.assert_called_once_with(
            [1, 2], "europian architecture", None, resolved=("europian architecture", None)
        )
        row = _json_result_row(result.stdout)
        resolution = row["tag_resolutions"][0]
        assert resolution["classification"] == "typo_candidate"
        assert resolution["candidates"] == ["european architecture"]
        assert resolution["tag_id"] is None
        assert row["unresolved_tag_count"] == 1

    def test_alias_resolved_uses_canonical_for_storage(self, mock_project_and_container):
        repo = mock_project_and_container.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda tag: ManualTagClassification(
            tag, tag, "alias_resolved", "preferred_tag", 42, []
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "old_alias",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        repo.register_user_tag.assert_not_called()
        repo.add_tag_to_images_batch.assert_called_once_with(
            [1, 2], "old_alias", None, resolved=("preferred_tag", 42)
        )

    def test_all_invalid_tags_rejected_as_input_error(self, mock_project_and_container):
        repo = mock_project_and_container.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda tag: ManualTagClassification(
            tag, "", "invalid", tag, None, []
        )
        result = runner.invoke(
            app,
            ["--json", "tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "###"],
        )
        assert result.exit_code == 2


@pytest.mark.unit
class TestTagsRemove:
    def test_remove_dry_run_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_not_called()

    def test_remove_apply_writes(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_called()

    def test_remove_dry_run_result_has_would_remove_and_mode(self, mock_project_and_container):
        """dry-run 出力に予定件数と soft-reject である旨が載る (Issue #1217)。"""
        result = runner.invoke(
            app,
            ["--json", "tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag"],
        )
        assert result.exit_code == 0
        row = _json_result_row(result.stdout)
        assert row["dry_run"] is True
        assert row["would_remove"] == 1  # preview で changed=1 (image 2 は skipped)
        assert row["mode"] == "soft_reject"
        assert row["removed"] == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_not_called()

    def test_remove_apply_result_has_mode_without_would_remove(self, mock_project_and_container):
        """apply 出力にも mode は載るが、would_remove は dry-run 専用 (Issue #1217)。"""
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "remove",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "bad_tag",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        row = _json_result_row(result.stdout)
        assert row["dry_run"] is False
        assert row["mode"] == "soft_reject"
        assert row["removed"] == 2
        assert "would_remove" not in row


@pytest.mark.unit
class TestTagsReplace:
    def test_replace_dry_run_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
            ],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_not_called()

    def test_replace_apply_writes(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_called()

    def test_replace_json_item_rows(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 2
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False
