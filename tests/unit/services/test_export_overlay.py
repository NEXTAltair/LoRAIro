"""ExportTagOverlay / ExportOverlayPlan / apply_overlay のユニットテスト。

ADR 0080 §1-§4 に基づく受け入れ条件:
- overlay 未指定で既存 export と同一出力
- exclude / replace / trigger / scope 各単体
- 漢字 trigger が convert されない
- 順序（convert 後 prepend）と dedup（先頭優先）
- 「exclude タグは出力に出ない」（replace 産含む）
- effective_for 積み上げ合成（add 連結 / exclude 和 / replace 後勝ち）
"""

import pytest

from lorairo.services.export_overlay import (
    ExportOverlayPlan,
    ExportTagOverlay,
    ScopedOverlayRule,
    apply_overlay,
)

# ─────────────────────────────────────────────────────────────────────────────
# テスト用 MergedTagReader スタブ
# ─────────────────────────────────────────────────────────────────────────────


class FakeReader:
    """apply_overlay の convert 経路を実経路で動かす最小スタブ。"""

    def __init__(self, mapping: dict[str, str], *, types: dict[str, str] | None = None) -> None:
        self._mapping = mapping
        self._types = types or {}

    def get_format_id(self, format_name: str) -> int:
        return 1

    def search_tags_bulk(
        self, tags: list[str], format_name: str | None = None, resolve_preferred: bool = True
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for tag in tags:
            key = tag.lower()
            if key in self._mapping:
                result[tag] = {
                    "tag": self._mapping[key],
                    "type_name": self._types.get(key),
                }
        return result


# ─────────────────────────────────────────────────────────────────────────────
# ExportTagOverlay データクラス
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExportTagOverlay:
    def test_default_values_are_empty(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        assert overlay.add == []
        assert overlay.exclude == set()
        assert overlay.replace == {}

    def test_fields_are_preserved(self) -> None:
        overlay = ExportTagOverlay(
            add=["trigger_word"],
            exclude={"bad_tag"},
            replace={"old": "new"},
        )
        assert overlay.add == ["trigger_word"]
        assert overlay.exclude == {"bad_tag"}
        assert overlay.replace == {"old": "new"}

    def test_is_noop_true_when_all_empty(self) -> None:
        """add/exclude/replace がすべて空のとき is_noop=True。"""
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        assert overlay.is_noop is True

    def test_is_noop_false_when_add_nonempty(self) -> None:
        overlay = ExportTagOverlay(add=["trigger"], exclude=set(), replace={})
        assert overlay.is_noop is False

    def test_is_noop_false_when_exclude_nonempty(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude={"bad"}, replace={})
        assert overlay.is_noop is False

    def test_is_noop_false_when_replace_nonempty(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={"a": "b"})
        assert overlay.is_noop is False


# ─────────────────────────────────────────────────────────────────────────────
# ScopedOverlayRule
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestScopedOverlayRule:
    def test_none_image_ids_means_global(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        rule = ScopedOverlayRule(image_ids=None, overlay=overlay)
        assert rule.image_ids is None

    def test_specific_image_ids(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        rule = ScopedOverlayRule(image_ids={1, 2, 3}, overlay=overlay)
        assert rule.image_ids == {1, 2, 3}


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - overlay 未指定時リグレッションなし
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayNoOverlay:
    def test_empty_overlay_with_reader_returns_converted_tags(self) -> None:
        """add/exclude/replace 全空 + reader あり → convert のみ適用。"""
        reader = FakeReader({"girl": "1girl"})
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay(["anime", "girl"], overlay, reader, "danbooru")
        assert result == ["anime", "1girl"]

    def test_empty_overlay_without_reader_returns_original_tags(self) -> None:
        """add/exclude/replace 全空 + reader=None → タグをそのまま返す。"""
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay(["anime", "girl"], overlay, None, "danbooru")
        assert result == ["anime", "girl"]

    def test_empty_overlay_empty_tags_returns_empty(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay([], overlay, None, "danbooru")
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - exclude
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayExclude:
    def test_exclude_removes_tag(self) -> None:
        """exclude は convert 前（step 2）に除去される。"""
        overlay = ExportTagOverlay(add=[], exclude={"bad_tag"}, replace={})
        result = apply_overlay(["good", "bad_tag", "another"], overlay, None, "danbooru")
        assert "bad_tag" not in result
        assert "good" in result
        assert "another" in result

    def test_exclude_all_tags_returns_empty(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude={"a", "b"}, replace={})
        result = apply_overlay(["a", "b"], overlay, None, "danbooru")
        assert result == []

    def test_exclude_nonexistent_tag_has_no_effect(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude={"ghost"}, replace={})
        result = apply_overlay(["anime", "girl"], overlay, None, "danbooru")
        assert result == ["anime", "girl"]

    def test_exclude_replace_product(self) -> None:
        """replace 産 Y も exclude 指定なら消える。"""
        overlay = ExportTagOverlay(add=[], exclude={"nsfw"}, replace={"bad": "nsfw"})
        result = apply_overlay(["anime", "bad"], overlay, None, "danbooru")
        assert "nsfw" not in result
        assert "bad" not in result
        assert "anime" in result

    def test_exclude_applied_before_convert(self) -> None:
        """exclude は convert 前のタグ名に対して効く。"""
        reader = FakeReader({"girl": "1girl"})
        overlay = ExportTagOverlay(add=[], exclude={"girl"}, replace={})
        result = apply_overlay(["anime", "girl"], overlay, reader, "danbooru")
        assert "girl" not in result
        assert "1girl" not in result
        assert "anime" in result


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - replace
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayReplace:
    def test_replace_substitutes_tag(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={"old_tag": "new_tag"})
        result = apply_overlay(["anime", "old_tag"], overlay, None, "danbooru")
        assert "old_tag" not in result
        assert "new_tag" in result

    def test_replace_then_convert(self) -> None:
        """replace 後のタグは convert に掛かる。

        注意: TagCleaner はアンダースコアをスペースに変換する。
        FakeReader のキーは convert_tags に渡される正規化済み形式（スペース区切り）で指定する。
        例: "girlalias" (アンダースコアなし) → convert で "1girl" に解決。
        """
        # アンダースコアを含まないエイリアス名を使用（TagCleaner 正規化を回避）
        reader = FakeReader({"girlalias": "1girl"})
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={"rawgirl": "girlalias"})
        result = apply_overlay(["anime", "rawgirl"], overlay, reader, "danbooru")
        assert "rawgirl" not in result
        assert "girlalias" not in result
        assert "1girl" in result

    def test_replace_wins_over_exclude_on_original_key(self) -> None:
        """矛盾入力: X を exclude かつ X→Y の replace → replace が先に効くため Y が残る。"""
        overlay = ExportTagOverlay(add=[], exclude={"old_tag"}, replace={"old_tag": "new_tag"})
        result = apply_overlay(["anime", "old_tag"], overlay, None, "danbooru")
        assert "old_tag" not in result
        assert "new_tag" in result

    def test_replace_unknown_tag_has_no_effect(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={"ghost": "something"})
        result = apply_overlay(["anime", "girl"], overlay, None, "danbooru")
        assert result == ["anime", "girl"]


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - add（trigger word）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayAdd:
    def test_add_prepended_to_front(self) -> None:
        overlay = ExportTagOverlay(add=["trigger"], exclude=set(), replace={})
        result = apply_overlay(["anime", "girl"], overlay, None, "danbooru")
        assert result[0] == "trigger"
        assert result == ["trigger", "anime", "girl"]

    def test_add_multiple_in_order(self) -> None:
        overlay = ExportTagOverlay(add=["trigger_a", "trigger_b"], exclude=set(), replace={})
        result = apply_overlay(["anime"], overlay, None, "danbooru")
        assert result[0] == "trigger_a"
        assert result[1] == "trigger_b"
        assert result[2] == "anime"

    def test_add_kanji_trigger_not_converted(self) -> None:
        """漢字 trigger は convert されずリテラルで出力される。"""
        reader = FakeReader({"ご注文はうさぎですか": "gochiusa"})
        overlay = ExportTagOverlay(add=["ご注文はうさぎですか"], exclude=set(), replace={})
        result = apply_overlay(["anime"], overlay, reader, "danbooru")
        assert result[0] == "ご注文はうさぎですか"
        assert "gochiusa" not in result

    def test_add_after_convert_order(self) -> None:
        """add の prepend は convert の後（step 4）に行われる。"""
        reader = FakeReader({"girl": "1girl"})
        overlay = ExportTagOverlay(add=["trigger"], exclude=set(), replace={})
        result = apply_overlay(["girl"], overlay, reader, "danbooru")
        assert result == ["trigger", "1girl"]

    def test_add_empty_does_not_prepend(self) -> None:
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay(["anime"], overlay, None, "danbooru")
        assert result == ["anime"]


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - dedup（先頭優先）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayDedup:
    def test_dedup_trigger_wins_over_body_tag(self) -> None:
        """trigger と本文タグが重複したら trigger（先頭）を残す。"""
        overlay = ExportTagOverlay(add=["anime"], exclude=set(), replace={})
        result = apply_overlay(["anime", "girl"], overlay, None, "danbooru")
        assert result.count("anime") == 1
        assert result[0] == "anime"

    def test_dedup_preserves_order_of_first_occurrence(self) -> None:
        overlay = ExportTagOverlay(add=["a", "b"], exclude=set(), replace={})
        result = apply_overlay(["b", "c"], overlay, None, "danbooru")
        assert result == ["a", "b", "c"]

    def test_dedup_replace_product_duplicate(self) -> None:
        """replace 産と既存タグの重複 → 先頭（初出）を残す。"""
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={"old_tag": "new_tag"})
        result = apply_overlay(["old_tag", "new_tag"], overlay, None, "danbooru")
        assert result.count("new_tag") == 1
        assert "old_tag" not in result


# ─────────────────────────────────────────────────────────────────────────────
# apply_overlay - meta タグ除外（convert 経由）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestApplyOverlayMetaExclusion:
    def test_meta_tag_excluded_by_convert(self) -> None:
        """type=meta タグは convert で除外される。"""
        reader = FakeReader(
            {"highres": "highres", "anime": "anime"},
            types={"highres": "meta"},
        )
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay(["anime", "highres"], overlay, reader, "danbooru")
        assert "highres" not in result
        assert "anime" in result

    def test_reader_none_does_not_exclude_meta(self) -> None:
        """reader=None → convert スキップ → meta タグもそのまま残る。"""
        overlay = ExportTagOverlay(add=[], exclude=set(), replace={})
        result = apply_overlay(["anime", "highres"], overlay, None, "danbooru")
        assert "highres" in result


# ─────────────────────────────────────────────────────────────────────────────
# ExportOverlayPlan.effective_for
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEffectiveFor:
    def test_no_rules_returns_empty_overlay(self) -> None:
        plan = ExportOverlayPlan(rules=[])
        overlay = plan.effective_for(1)
        assert overlay.add == []
        assert overlay.exclude == set()
        assert overlay.replace == {}

    def test_global_rule_applies_to_all(self) -> None:
        global_rule = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["global_trigger"], exclude={"bad"}, replace={}),
        )
        plan = ExportOverlayPlan(rules=[global_rule])
        overlay = plan.effective_for(42)
        assert "global_trigger" in overlay.add
        assert "bad" in overlay.exclude

    def test_scoped_rule_applies_only_to_specified_ids(self) -> None:
        scoped_rule = ScopedOverlayRule(
            image_ids={1, 2},
            overlay=ExportTagOverlay(add=["scoped_trigger"], exclude=set(), replace={}),
        )
        plan = ExportOverlayPlan(rules=[scoped_rule])
        overlay_1 = plan.effective_for(1)
        assert "scoped_trigger" in overlay_1.add
        overlay_99 = plan.effective_for(99)
        assert "scoped_trigger" not in overlay_99.add

    def test_add_concatenated_in_rule_order(self) -> None:
        """add はルール定義順に連結される。"""
        global_rule = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["global_a", "global_b"], exclude=set(), replace={}),
        )
        scoped_rule = ScopedOverlayRule(
            image_ids={1},
            overlay=ExportTagOverlay(add=["scoped_c"], exclude=set(), replace={}),
        )
        plan = ExportOverlayPlan(rules=[global_rule, scoped_rule])
        overlay = plan.effective_for(1)
        assert overlay.add == ["global_a", "global_b", "scoped_c"]

    def test_exclude_is_union_of_all_applicable_rules(self) -> None:
        """exclude は全該当ルールの和集合。"""
        global_rule = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=[], exclude={"bad_a"}, replace={}),
        )
        scoped_rule = ScopedOverlayRule(
            image_ids={1},
            overlay=ExportTagOverlay(add=[], exclude={"bad_b"}, replace={}),
        )
        plan = ExportOverlayPlan(rules=[global_rule, scoped_rule])
        overlay = plan.effective_for(1)
        assert overlay.exclude == {"bad_a", "bad_b"}

    def test_replace_later_key_wins(self) -> None:
        """replace のキー衝突は後定義（後勝ち）。"""
        global_rule = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=[], exclude=set(), replace={"x": "global_y"}),
        )
        scoped_rule = ScopedOverlayRule(
            image_ids={1},
            overlay=ExportTagOverlay(add=[], exclude=set(), replace={"x": "scoped_y"}),
        )
        plan = ExportOverlayPlan(rules=[global_rule, scoped_rule])
        overlay = plan.effective_for(1)
        assert overlay.replace["x"] == "scoped_y"

    def test_inapplicable_scoped_rule_not_merged(self) -> None:
        global_rule = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["from_global"], exclude=set(), replace={}),
        )
        scoped_rule = ScopedOverlayRule(
            image_ids={99},
            overlay=ExportTagOverlay(add=["from_scoped"], exclude={"bad"}, replace={"x": "y"}),
        )
        plan = ExportOverlayPlan(rules=[global_rule, scoped_rule])
        overlay = plan.effective_for(1)
        assert overlay.add == ["from_global"]
        assert overlay.exclude == set()
        assert overlay.replace == {}

    def test_multiple_global_rules_all_merged(self) -> None:
        rule1 = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["t1"], exclude={"e1"}, replace={"a": "b"}),
        )
        rule2 = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["t2"], exclude={"e2"}, replace={"c": "d"}),
        )
        plan = ExportOverlayPlan(rules=[rule1, rule2])
        overlay = plan.effective_for(5)
        assert overlay.add == ["t1", "t2"]
        assert overlay.exclude == {"e1", "e2"}
        assert overlay.replace == {"a": "b", "c": "d"}

    def test_add_deduped_in_effective_overlay(self) -> None:
        """同じ add トークンが複数ルールで重複しても dedup される。"""
        rule1 = ScopedOverlayRule(
            image_ids=None,
            overlay=ExportTagOverlay(add=["trigger"], exclude=set(), replace={}),
        )
        rule2 = ScopedOverlayRule(
            image_ids={1},
            overlay=ExportTagOverlay(add=["trigger"], exclude=set(), replace={}),
        )
        plan = ExportOverlayPlan(rules=[rule1, rule2])
        overlay = plan.effective_for(1)
        assert overlay.add.count("trigger") == 1


# ─────────────────────────────────────────────────────────────────────────────
# DatasetExportService との統合（overlay フック）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDatasetExportServiceOverlayHook:
    """DatasetExportService に overlay_plan を渡すと出力タグに反映される。"""

    def _make_service(self) -> object:
        from unittest.mock import Mock

        from lorairo.services.dataset_export_service import DatasetExportService

        db_manager = Mock()
        db_manager.annotation_repo.get_merged_reader.return_value = None
        return DatasetExportService(
            config_service=Mock(),
            file_system_manager=Mock(),
            db_manager=db_manager,
            search_processor=Mock(),
        )

    def test_txt_export_with_overlay_adds_trigger(self, tmp_path: object) -> None:
        """TXT export に ExportOverlayPlan を渡すと trigger が先頭に付く。"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "girl"}],
            "captions": [],
        }

        plan = ExportOverlayPlan(
            rules=[
                ScopedOverlayRule(
                    image_ids=None,
                    overlay=ExportTagOverlay(add=["my_trigger"], exclude=set(), replace={}),
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format(
                    image_ids=[1],
                    output_path=output_path,
                    overlay_plan=plan,
                )

            content = (output_path / "test_project_00001.txt").read_text(encoding="utf-8")
            tags = [t.strip() for t in content.split(",")]
            assert tags[0] == "my_trigger"
            assert "anime" in tags
            assert "girl" in tags

    def test_txt_export_without_overlay_is_unchanged(self, tmp_path: object) -> None:
        """overlay_plan=None の場合は従来の出力と同一（リグレッションなし）。"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "girl"}],
            "captions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format(
                    image_ids=[1],
                    output_path=output_path,
                    overlay_plan=None,
                )

            content = (output_path / "test_project_00001.txt").read_text(encoding="utf-8")
            assert content == "anime, girl"

    def test_txt_export_with_overlay_excludes_tag(self, tmp_path: object) -> None:
        """overlay で exclude されたタグは出力に出ない。"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "nsfw"}, {"tag": "girl"}],
            "captions": [],
        }

        plan = ExportOverlayPlan(
            rules=[
                ScopedOverlayRule(
                    image_ids=None,
                    overlay=ExportTagOverlay(add=[], exclude={"nsfw"}, replace={}),
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format(
                    image_ids=[1],
                    output_path=output_path,
                    overlay_plan=plan,
                )

            content = (output_path / "test_project_00001.txt").read_text(encoding="utf-8")
            assert "nsfw" not in content

    def test_json_export_with_overlay_applies_replace(self, tmp_path: object) -> None:
        """JSON export にも overlay の replace が適用される。"""
        import json as json_module
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "old_tag"}, {"tag": "anime"}],
            "captions": [],
            "score_labels": [],
            "quality_summary": {},
        }

        plan = ExportOverlayPlan(
            rules=[
                ScopedOverlayRule(
                    image_ids=None,
                    overlay=ExportTagOverlay(add=[], exclude=set(), replace={"old_tag": "new_tag"}),
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_json_format(
                    image_ids=[1],
                    output_path=output_path,
                    overlay_plan=plan,
                )

            metadata = json_module.loads((output_path / "metadata.json").read_text(encoding="utf-8"))
            entry = metadata[str(output_path / "test_project_00001.webp")]
            tags_str = entry["tags"]
            assert "old_tag" not in tags_str
            assert "new_tag" in tags_str

    def test_scoped_overlay_applies_only_to_matching_image(self, tmp_path: object) -> None:
        """スコープ付き overlay は image_ids に含まれる画像にのみ適用される。"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        def make_image_data(img_id: int) -> dict:
            return {
                "metadata": {"id": img_id},
                "tags": [{"tag": "anime"}],
                "captions": [],
            }

        plan = ExportOverlayPlan(
            rules=[
                ScopedOverlayRule(
                    image_ids={1},
                    overlay=ExportTagOverlay(add=["scoped_trigger"], exclude=set(), replace={}),
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    side_effect=lambda img_id, res: Path(f"/mock/processed/img_{img_id:05d}.webp"),
                ),
                patch.object(
                    service,
                    "_get_image_export_data",
                    side_effect=make_image_data,
                ),
            ):
                service.export_dataset_txt_format(
                    image_ids=[1, 2],
                    output_path=output_path,
                    overlay_plan=plan,
                )

            content_1 = (output_path / "img_00001.txt").read_text(encoding="utf-8")
            assert "scoped_trigger" in content_1

            content_2 = (output_path / "img_00002.txt").read_text(encoding="utf-8")
            assert "scoped_trigger" not in content_2

    def test_scoped_overlay_out_of_scope_image_matches_no_overlay_output(self, tmp_path: object) -> None:
        """スコープ外画像は overlay_plan=None と同一出力になる（P2 リグレッション防止）。

        空 effective overlay で apply_overlay の dedup が走り convert 産重複タグが
        消えてしまうケースを防ぐ。is_noop=True のときレガシーパスへフォールバックする。
        """
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from lorairo.services.dataset_export_service import DatasetExportService

        service = self._make_service()
        assert isinstance(service, DatasetExportService)

        # スコープは image_id=1 のみ。image_id=2 はスコープ外 → 空 effective overlay
        plan = ExportOverlayPlan(
            rules=[
                ScopedOverlayRule(
                    image_ids={1},
                    overlay=ExportTagOverlay(add=["trigger"], exclude=set(), replace={}),
                )
            ]
        )

        def make_image_data(img_id: int) -> dict:
            return {
                "metadata": {"id": img_id},
                "tags": [{"tag": "anime"}, {"tag": "girl"}],
                "captions": [],
            }

        with (
            tempfile.TemporaryDirectory() as temp_dir_overlay,
            tempfile.TemporaryDirectory() as temp_dir_no_overlay,
        ):
            out_overlay = Path(temp_dir_overlay) / "export"
            out_overlay.mkdir()
            out_no_overlay = Path(temp_dir_no_overlay) / "export"
            out_no_overlay.mkdir()

            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    side_effect=lambda img_id, res: Path(f"/mock/processed/img_{img_id:05d}.webp"),
                ),
                patch.object(
                    service,
                    "_get_image_export_data",
                    side_effect=make_image_data,
                ),
            ):
                service.export_dataset_txt_format(
                    image_ids=[2],
                    output_path=out_overlay,
                    overlay_plan=plan,
                )
                service.export_dataset_txt_format(
                    image_ids=[2],
                    output_path=out_no_overlay,
                    overlay_plan=None,
                )

            content_overlay = (out_overlay / "img_00002.txt").read_text(encoding="utf-8")
            content_no_overlay = (out_no_overlay / "img_00002.txt").read_text(encoding="utf-8")
            # スコープ外画像はレガシーパスと同一出力でなければならない
            assert content_overlay == content_no_overlay
