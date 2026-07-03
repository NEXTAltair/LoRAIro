# tests/unit/gui/workers/test_tag_metadata_worker.py
"""TagMetadataWorker の解決ロジックテスト (#1046)。

翻訳/使用頻度/type の batch 解決は従来 SelectedImageDetailsWidget が GUI スレッドで
同期実行していたものを worker へ移設した。クエリロジックの検証もここへ移設する。
"""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.gui.workers.tag_metadata_worker import TagMetadataWorker, resolve_tag_types

pytestmark = pytest.mark.unit


def _make_reader(**overrides) -> Mock:
    reader = Mock()
    reader.get_translations_batch.return_value = {}
    reader.get_preferred_translations_batch.return_value = {}
    reader.get_usage_counts_batch.return_value = {}
    reader.get_format_map.return_value = {}
    reader.search_tags_bulk_all.return_value = {}
    for key, value in overrides.items():
        getattr(reader, key).return_value = value
    return reader


def _row(tag: str, *, source_tag=None, type_name="", format_statuses=None, tag_id=1) -> dict:
    return {
        "tag": tag,
        "source_tag": source_tag,
        "tag_id": tag_id,
        "usage_count": 0,
        "alias": False,
        "deprecated": False,
        "type_id": None,
        "type_name": type_name,
        "translations": {},
        "format_statuses": format_statuses or {},
    }


class TestExecute:
    def test_translations_aggregated_by_language(self):
        tr = Mock()
        tr.language = "japanese"
        tr.translation = "1人の女の子"
        reader = _make_reader(get_translations_batch={42: [tr]})

        result = TagMetadataWorker(reader, image_id=1, tags_list=[{"tag": "1girl", "tag_id": 42}]).execute()

        assert result.translations == {42: {"japanese": "1人の女の子"}}
        assert result.image_id == 1

    def test_usage_counts_resolved_to_format_names(self):
        """format_id を format 名へ解決し、未知 format_id は除外する (#990)。"""
        reader = _make_reader(
            get_format_map={1: "danbooru", 2: "e621"},
            get_usage_counts_batch={42: {1: 1234, 2: 42, 99: 7}},
        )

        result = TagMetadataWorker(reader, image_id=1, tags_list=[{"tag": "1girl", "tag_id": 42}]).execute()

        assert result.usage_counts == {42: {"danbooru": 1234, "e621": 42}}

    def test_tag_without_tag_id_skips_id_based_batches(self):
        """tag_id=None のみのタグ集合では翻訳/使用頻度の batch を呼ばない。"""
        reader = _make_reader()

        TagMetadataWorker(reader, image_id=1, tags_list=[{"tag": "1girl", "tag_id": None}]).execute()

        reader.get_translations_batch.assert_not_called()
        reader.get_usage_counts_batch.assert_not_called()

    def test_translations_batch_called_once_for_many_tags(self):
        """N 個のタグでも get_translations_batch は 1 回 (N+1 禁止 #998)。"""
        reader = _make_reader()
        tags = [{"tag": f"tag{i}", "tag_id": i} for i in range(1, 21)]

        TagMetadataWorker(reader, image_id=1, tags_list=tags).execute()

        assert reader.get_translations_batch.call_count == 1
        assert reader.get_usage_counts_batch.call_count == 1

    def test_preferred_translation_overrides_all_alias_keys(self):
        """主訳は当該言語の全エイリアスキー ("ja"/"japanese") を上書きする (#1084)。"""
        tr = Mock()
        tr.language = "japanese"
        tr.translation = "青目"  # DB 行順の後勝ちで決まる従来訳
        reader = _make_reader(
            get_translations_batch={42: [tr]},
            get_preferred_translations_batch={42: {"ja": "青い目"}},
        )

        result = TagMetadataWorker(
            reader, image_id=1, tags_list=[{"tag": "blue_eyes", "tag_id": 42}]
        ).execute()

        # 主訳 "青い目" が japanese / ja の両キーへ書き込まれ、表示側がどのエイリアス順でも拾える。
        assert result.translations == {42: {"japanese": "青い目", "ja": "青い目"}}

    def test_preferred_translation_added_when_no_base_translation(self):
        """base 訳が無い tag_id でも主訳だけで翻訳が入る (#1084)。"""
        reader = _make_reader(get_preferred_translations_batch={42: {"en": "girl"}})

        result = TagMetadataWorker(reader, image_id=1, tags_list=[{"tag": "1girl", "tag_id": 42}]).execute()

        assert result.translations == {42: {"en": "girl", "english": "girl"}}

    def test_preferred_translation_fetch_failure_is_advisory(self):
        """主訳取得が失敗しても従来訳で続行する (advisory、#1084)。"""
        tr = Mock()
        tr.language = "ja"
        tr.translation = "少女"
        reader = _make_reader(get_translations_batch={42: [tr]})
        reader.get_preferred_translations_batch.side_effect = SQLAlchemyError("db down")

        result = TagMetadataWorker(reader, image_id=1, tags_list=[{"tag": "1girl", "tag_id": 42}]).execute()

        assert result.translations == {42: {"ja": "少女"}}


class TestResolveTagTypes:
    """type 解決の実挙動 (#1056 から移設: format_statuses 経由・完全一致限定・非破壊)。"""

    def test_resolves_type_from_format_statuses(self):
        reader = _make_reader(
            search_tags_bulk_all={
                "hatsune miku": [
                    _row("hatsune miku", format_statuses={"danbooru": {"type_name": "character"}})
                ]
            }
        )

        assert resolve_tag_types(reader, ["hatsune miku"]) == {"hatsune miku": "character"}

    def test_non_exact_match_stays_unknown(self):
        reader = _make_reader(
            search_tags_bulk_all={
                "unregistered_tag": [
                    _row("different_tag", format_statuses={"danbooru": {"type_name": "general"}})
                ]
            }
        )

        assert resolve_tag_types(reader, ["unregistered_tag"]) == {}

    def test_source_tag_match_resolves_type(self):
        reader = _make_reader(
            search_tags_bulk_all={
                "Verbatim_Tag": [
                    _row(
                        "normalized form",
                        source_tag="Verbatim_Tag",
                        format_statuses={"danbooru": {"type_name": "meta"}},
                    )
                ]
            }
        )

        assert resolve_tag_types(reader, ["Verbatim_Tag"]) == {"Verbatim_Tag": "meta"}

    def test_user_format_type_override_wins_over_danbooru(self):
        reader = _make_reader(
            search_tags_bulk_all={
                "some tag": [
                    _row(
                        "some tag",
                        format_statuses={
                            "danbooru": {"type_name": "general"},
                            "Lorairo": {"type_name": "character"},
                        },
                    )
                ]
            }
        )

        assert resolve_tag_types(reader, ["some tag"]) == {"some tag": "character"}

    def test_unknown_type_initial_value_is_skipped(self):
        reader = _make_reader(
            search_tags_bulk_all={
                "some tag": [
                    _row(
                        "some tag",
                        format_statuses={
                            "Lorairo": {"type_name": "unknown"},
                            "danbooru": {"type_name": "meta"},
                        },
                    )
                ]
            }
        )

        assert resolve_tag_types(reader, ["some tag"]) == {"some tag": "meta"}

    def test_lookup_failure_is_non_blocking(self):
        reader = Mock()
        reader.search_tags_bulk_all.side_effect = SQLAlchemyError("db down")

        assert resolve_tag_types(reader, ["1girl"]) == {}
