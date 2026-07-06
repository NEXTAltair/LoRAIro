"""tags translations show/add + tags alias のユニットテスト (Issue #1173 / ADR 0085)。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.repository.annotation_record import ManualTagClassification
from lorairo.services.tag_management_service import TranslationStatus

runner = CliRunner()


def _cls(
    tag: str,
    classification: str = "exact",
    canonical: str | None = None,
    tag_id: int | None = 10,
    candidates: list[str] | None = None,
) -> ManualTagClassification:
    return ManualTagClassification(tag, tag, classification, canonical or tag, tag_id, candidates or [])


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    container = MagicMock()
    container.db_manager.image_repo.get_images_by_filter.return_value = ([{"id": 1}], 1)
    container.db_manager.annotation_repo.classify_manual_tag.side_effect = lambda t: _cls(t)
    container.db_manager.annotation_repo.register_user_tag.return_value = 555
    container.db_manager.annotation_repo.register_user_alias.return_value = 777
    service = container.tag_management_service
    service.resolve_tag_id.return_value = 10
    service.list_translation_candidates.side_effect = lambda tag, lang: (
        (["猫"], "猫") if lang == "ja" else ([], None)
    )
    # translations show は batch API を使う (#1203)。tag ごとに ja のみ翻訳ありの状態を返す。
    service.translation_status_batch.side_effect = lambda tags, languages=("ja", "en"): {
        tag: TranslationStatus(tag_id=10, by_language={"ja": (["猫"], "猫"), "en": ([], None)})
        for tag in tags
    }
    monkeypatch.setattr("lorairo.cli.commands.tags.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.tags.get_service_container", MagicMock(return_value=container)
    )
    return container


def _rows(output: str) -> list[dict]:
    return [json.loads(line) for line in output.strip().splitlines() if line.strip().startswith("{")]


@pytest.mark.unit
class TestTranslationsShow:
    def test_show_by_tags_reports_missing_languages(self, mock_env: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "tags", "translations", "show", "-p", "proj", "--tags", "cat"],
        )
        assert result.exit_code == 0
        rows = _rows(result.stdout)
        item = next(r for r in rows if r.get("kind") == "item")
        assert item["tag"] == "cat"
        assert item["tag_id"] == 10
        assert item["translations"]["ja"]["preferred"] == "猫"
        assert item["missing"] == ["en"]

    def test_show_by_image_ids_groups_tags_per_image(self, mock_env: MagicMock) -> None:
        mock_env.db_manager.image_repo.get_image_annotations_batch.return_value = {
            1: {"tags": [{"tag": "cat"}, {"tag": "cat"}, {"tag": "dog"}]}
        }
        result = runner.invoke(
            app,
            ["--json", "tags", "translations", "show", "-p", "proj", "--image-ids", "1"],
        )
        assert result.exit_code == 0
        rows = _rows(result.stdout)
        item = next(r for r in rows if r.get("kind") == "item")
        assert item["image_id"] == 1
        # 重複タグは初出優先で畳まれる
        assert [t["tag"] for t in item["tags"]] == ["cat", "dog"]

    def test_show_requires_exactly_one_selector(self, mock_env: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "tags", "translations", "show", "-p", "proj"],
        )
        assert result.exit_code == 2

    def test_show_unresolved_tag_marks_all_missing(self, mock_env: MagicMock) -> None:
        mock_env.tag_management_service.translation_status_batch.side_effect = (
            lambda tags, languages=("ja", "en"): {
                tag: TranslationStatus(tag_id=None, by_language={}) for tag in tags
            }
        )
        result = runner.invoke(
            app,
            ["--json", "tags", "translations", "show", "-p", "proj", "--tags", "unknown_tag"],
        )
        assert result.exit_code == 0
        item = next(r for r in _rows(result.stdout) if r.get("kind") == "item")
        assert item["tag_id"] is None
        assert item["missing"] == ["ja", "en"]


@pytest.mark.unit
class TestTranslationsAdd:
    def test_dry_run_does_not_write(self, mock_env: MagicMock) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "cat",
                "--lang",
                "ja",
                "--text",
                "猫",
            ],
        )
        assert result.exit_code == 0
        mock_env.tag_management_service.add_translation.assert_not_called()
        mock_env.db_manager.annotation_repo.register_user_tag.assert_not_called()
        row = next(r for r in _rows(result.stdout) if r.get("kind") == "result")
        assert row["dry_run"] is True

    def test_apply_with_preferred_uses_add_translation(self, mock_env: MagicMock) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "cat",
                "--lang",
                "ja",
                "--text",
                "猫",
                "--preferred",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        mock_env.tag_management_service.add_translation.assert_called_once_with(10, "ja", "猫")

    def test_apply_registers_unregistered_tag_first(self, mock_env: MagicMock) -> None:
        mock_env.db_manager.annotation_repo.classify_manual_tag.side_effect = lambda t: _cls(
            t, "unregistered", tag_id=None
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "new tag",
                "--lang",
                "ja",
                "--text",
                "新規",
                "--preferred",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        mock_env.db_manager.annotation_repo.register_user_tag.assert_called_once_with("new tag")
        mock_env.tag_management_service.add_translation.assert_called_once_with(555, "ja", "新規")
        item = next(r for r in _rows(result.stdout) if r.get("kind") == "item")
        assert item["registered_new_tag"] is True

    def test_typo_candidate_is_rejected_with_candidates(self, mock_env: MagicMock) -> None:
        mock_env.db_manager.annotation_repo.classify_manual_tag.side_effect = lambda t: _cls(
            t, "typo_candidate", tag_id=None, candidates=["european architecture"]
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "europian architecture",
                "--lang",
                "ja",
                "--text",
                "ヨーロッパ建築",
                "--apply",
            ],
        )
        assert result.exit_code == 2
        mock_env.db_manager.annotation_repo.register_user_tag.assert_not_called()

    def test_registration_failure_surfaces_db_error(self, mock_env: MagicMock) -> None:
        mock_env.db_manager.annotation_repo.classify_manual_tag.side_effect = lambda t: _cls(
            t, "unregistered", tag_id=None
        )
        mock_env.db_manager.annotation_repo.register_user_tag.return_value = None
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "edge tag",
                "--lang",
                "ja",
                "--text",
                "訳",
                "--apply",
            ],
        )
        assert result.exit_code == 1
        error_row = next(r for r in _rows(result.stdout) if r.get("kind") == "error")
        assert error_row["code"] == "DB_ERROR"

    def test_invalid_lang_rejected(self, mock_env: MagicMock) -> None:
        result = runner.invoke(
            app,
            [
                "tags",
                "translations",
                "add",
                "-p",
                "proj",
                "--tag",
                "cat",
                "--lang",
                "fr",
                "--text",
                "chat",
            ],
        )
        assert result.exit_code == 2


@pytest.mark.unit
class TestTagsAlias:
    def test_dry_run_does_not_register(self, mock_env: MagicMock) -> None:
        repo = mock_env.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda t: (
            _cls(t, "exact", tag_id=10)
            if t == "european architecture"
            else _cls(t, "typo_candidate", tag_id=None, candidates=["european architecture"])
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "alias",
                "-p",
                "proj",
                "--from",
                "europian architecture",
                "--to",
                "european architecture",
            ],
        )
        assert result.exit_code == 0
        repo.register_user_alias.assert_not_called()
        row = next(r for r in _rows(result.stdout) if r.get("kind") == "result")
        assert row["dry_run"] is True

    def test_apply_registers_alias_to_preferred(self, mock_env: MagicMock) -> None:
        repo = mock_env.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda t: (
            _cls(t, "exact", tag_id=10)
            if t == "european architecture"
            else _cls(t, "unregistered", tag_id=None)
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "alias",
                "-p",
                "proj",
                "--from",
                "europian architecture",
                "--to",
                "european architecture",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        repo.register_user_alias.assert_called_once_with("europian architecture", "european architecture")

    def test_alias_to_missing_target_rejected(self, mock_env: MagicMock) -> None:
        repo = mock_env.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda t: _cls(t, "unregistered", tag_id=None)
        result = runner.invoke(
            app,
            ["tags", "alias", "-p", "proj", "--from", "a", "--to", "missing", "--apply"],
        )
        assert result.exit_code == 2
        repo.register_user_alias.assert_not_called()

    def test_alias_from_existing_tag_rejected(self, mock_env: MagicMock) -> None:
        repo = mock_env.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda t: (
            _cls(t, "exact", tag_id=99, canonical="other tag")
            if t == "other tag"
            else _cls(t, "exact", tag_id=10, canonical="preferred tag")
        )
        result = runner.invoke(
            app,
            ["tags", "alias", "-p", "proj", "--from", "other tag", "--to", "preferred tag", "--apply"],
        )
        assert result.exit_code == 2
        repo.register_user_alias.assert_not_called()

    def test_alias_already_resolving_is_noop(self, mock_env: MagicMock) -> None:
        repo = mock_env.db_manager.annotation_repo
        repo.classify_manual_tag.side_effect = lambda t: _cls(
            t, "alias_resolved", canonical="preferred tag", tag_id=10
        )
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "alias",
                "-p",
                "proj",
                "--from",
                "old alias",
                "--to",
                "preferred tag",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        repo.register_user_alias.assert_not_called()
        row = next(r for r in _rows(result.stdout) if r.get("kind") == "result")
        assert row["status"] == "noop"
