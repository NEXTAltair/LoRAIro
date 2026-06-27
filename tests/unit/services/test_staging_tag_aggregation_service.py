"""StagingTagAggregationService のユニットテスト（Issue #945）。

TDD: テストを先に書き、RED → GREEN → REFACTOR サイクルで実装する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.services.staging_tag_aggregation import (
    StagingTagAggregationService,
    TagCount,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# テスト補助
# ---------------------------------------------------------------------------


def _make_service(
    tag_rows: list[tuple[int, str, bool | None]],
) -> StagingTagAggregationService:
    """StagingTagAggregationService をモック DB でインスタンス化する。

    Args:
        tag_rows: ``_load_tags_for_images`` が返す (image_id, tag, is_edited_manually) のリスト。
                  soft-reject 済み行は呼び出し元で除外済み（このメソッドは有効タグのみ返す）。

    Returns:
        モック DB を持つ StagingTagAggregationService。
    """
    db_manager = MagicMock()
    svc = StagingTagAggregationService(db_manager)
    svc._load_tags_for_images = MagicMock(return_value=tag_rows)  # type: ignore[method-assign]
    return svc


# ---------------------------------------------------------------------------
# TagCount データクラス
# ---------------------------------------------------------------------------


class TestTagCount:
    def test_fields_accessible(self) -> None:
        tc = TagCount(tag="smile", count=5, manual=False)
        assert tc.tag == "smile"
        assert tc.count == 5
        assert tc.manual is False

    def test_manual_flag_true(self) -> None:
        tc = TagCount(tag="custom_tag", count=1, manual=True)
        assert tc.manual is True


# ---------------------------------------------------------------------------
# aggregate - 件数降順・タグ名昇順ソート
# ---------------------------------------------------------------------------


class TestAggregateSorting:
    def test_sorted_by_count_descending(self) -> None:
        """件数降順で返すこと。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "rare_tag", False),
            (1, "common_tag", False),
            (2, "common_tag", False),
            (3, "common_tag", False),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2, 3])

        assert result[0].tag == "common_tag"
        assert result[0].count == 3
        assert result[1].tag == "rare_tag"
        assert result[1].count == 1

    def test_same_count_sorted_by_tag_name_ascending(self) -> None:
        """同数タグはタグ名昇順（安定ソート）で返すこと。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "zebra", False),
            (2, "apple", False),
            (3, "mango", False),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2, 3])

        assert [tc.tag for tc in result] == ["apple", "mango", "zebra"]

    def test_mixed_count_and_name_sort(self) -> None:
        """件数 2 のタグが 1 件のタグより先に来ること。同数はタグ名昇順。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "beta", False),
            (1, "alpha", False),
            (2, "alpha", False),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2])

        assert result[0].tag == "alpha"
        assert result[0].count == 2
        assert result[1].tag == "beta"
        assert result[1].count == 1


# ---------------------------------------------------------------------------
# aggregate - manual フラグ集約
# ---------------------------------------------------------------------------


class TestAggregateManualFlag:
    def test_manual_true_if_any_image_has_manual(self) -> None:
        """1 画像でも is_edited_manually=True ならば manual=True になること。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", True),  # 画像 1 は手動
            (2, "smile", False),  # 画像 2 は非手動
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2])

        assert len(result) == 1
        assert result[0].tag == "smile"
        assert result[0].manual is True

    def test_manual_false_if_no_image_is_manual(self) -> None:
        """全画像が is_edited_manually=False / None なら manual=False になること。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", False),
            (2, "smile", None),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2])

        assert result[0].tag == "smile"
        assert result[0].manual is False

    def test_manual_none_treated_as_false(self) -> None:
        """is_edited_manually=None は False 扱いになること。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "tag_a", None),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1])

        assert result[0].manual is False


# ---------------------------------------------------------------------------
# aggregate - 基本的な集計
# ---------------------------------------------------------------------------


class TestAggregateBasic:
    def test_empty_image_ids_returns_empty(self) -> None:
        """image_ids が空リストなら空リストを返すこと。"""
        svc = _make_service([])
        result = svc.aggregate([])
        assert result == []

    def test_single_image_single_tag(self) -> None:
        rows: list[tuple[int, str, bool | None]] = [(1, "smile", False)]
        svc = _make_service(rows)
        result = svc.aggregate([1])

        assert len(result) == 1
        assert result[0].tag == "smile"
        assert result[0].count == 1

    def test_multiple_images_count_per_tag(self) -> None:
        """タグの出現画像数を正しく集計すること。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", False),
            (2, "smile", False),
            (3, "smile", False),
            (1, "hair", False),
            (2, "hair", False),
        ]
        svc = _make_service(rows)
        result = svc.aggregate([1, 2, 3])

        tag_map = {tc.tag: tc.count for tc in result}
        assert tag_map["smile"] == 3
        assert tag_map["hair"] == 2

    def test_returns_list_of_tagcount(self) -> None:
        rows: list[tuple[int, str, bool | None]] = [(1, "smile", False)]
        svc = _make_service(rows)
        result = svc.aggregate([1])
        assert all(isinstance(tc, TagCount) for tc in result)


# ---------------------------------------------------------------------------
# aggregate - N+1 回避（バルク呼び出し確認）
# ---------------------------------------------------------------------------


class TestAggregateNoPlusOneQuery:
    def test_bulk_load_called_once_regardless_of_image_count(self) -> None:
        """多数の画像があっても _load_tags_for_images は1回だけ呼ばれること（N+1 禁止）。"""
        db_manager = MagicMock()
        svc = StagingTagAggregationService(db_manager)
        many_rows: list[tuple[int, str, bool | None]] = [(i, "tag", False) for i in range(100)]
        svc._load_tags_for_images = MagicMock(return_value=many_rows)  # type: ignore[method-assign]

        image_ids = list(range(100))
        svc.aggregate(image_ids)

        # DB アクセスが1回だけであること
        assert svc._load_tags_for_images.call_count == 1
        # 正しい image_ids を渡していること
        svc._load_tags_for_images.assert_called_once_with(image_ids)

    def test_bulk_load_called_once_for_images_with_tag(self) -> None:
        """images_with_tag も _load_tags_for_images は1回だけ呼ばれること。"""
        db_manager = MagicMock()
        svc = StagingTagAggregationService(db_manager)
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", False),
            (2, "smile", False),
            (3, "hair", False),
        ]
        svc._load_tags_for_images = MagicMock(return_value=rows)  # type: ignore[method-assign]

        image_ids = [1, 2, 3]
        svc.images_with_tag(image_ids, "smile")

        assert svc._load_tags_for_images.call_count == 1
        svc._load_tags_for_images.assert_called_once_with(image_ids)


# ---------------------------------------------------------------------------
# images_with_tag
# ---------------------------------------------------------------------------


class TestImagesWithTag:
    def test_returns_image_ids_with_tag(self) -> None:
        """指定タグを非 reject で持つ画像 ID のみ返すこと。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", False),
            (2, "smile", False),
            (3, "hair", False),
        ]
        svc = _make_service(rows)
        result = svc.images_with_tag([1, 2, 3], "smile")

        assert sorted(result) == [1, 2]

    def test_tag_not_found_returns_empty(self) -> None:
        rows: list[tuple[int, str, bool | None]] = [
            (1, "hair", False),
        ]
        svc = _make_service(rows)
        result = svc.images_with_tag([1], "smile")
        assert result == []

    def test_empty_image_ids_returns_empty(self) -> None:
        svc = _make_service([])
        result = svc.images_with_tag([], "smile")
        assert result == []

    def test_no_duplicate_image_ids(self) -> None:
        """同一画像にタグが複数行あっても重複しないこと。"""
        rows: list[tuple[int, str, bool | None]] = [
            (1, "smile", False),
            (1, "smile", True),  # 同じ画像・同じタグで2行
        ]
        svc = _make_service(rows)
        result = svc.images_with_tag([1], "smile")

        # image_id の重複がないこと
        assert result.count(1) == 1
