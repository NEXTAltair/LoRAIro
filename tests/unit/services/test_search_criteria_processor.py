# tests/unit/services/test_search_criteria_processor.py

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.services.search_criteria_processor import SearchCriteriaProcessor
from lorairo.services.search_models import SearchConditions


class TestSearchCriteriaProcessor:
    """SearchCriteriaProcessor のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock_db = Mock()
        mock_db.get_images_by_filter.return_value = ([], 0)
        mock_db.check_image_has_annotation.return_value = False
        # #1106: 重複除外の phash 補完はデフォルト「補完なし」(空 dict) で決定論的にする
        mock_db.image_repo.get_phash_classification_by_ids.return_value = {}
        return mock_db

    @pytest.fixture
    def processor(self, mock_db_manager):
        """テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_initialization(self, processor, mock_db_manager):
        """初期化テスト"""
        assert processor.db_manager == mock_db_manager

    def test_execute_search_with_filters_basic(self, processor, mock_db_manager):
        """基本的な検索実行テスト（直接呼び出し方式）"""
        # モック設定
        mock_images = [{"id": 1, "width": 1024, "height": 768}, {"id": 2, "width": 512, "height": 512}]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)

        # 検索条件作成
        conditions = SearchConditions(search_type="tags", keywords=["test", "tag"], tag_logic="and")

        # 検索実行
        results, count = processor.execute_search_with_filters(conditions)

        # 結果検証
        assert len(results) == 2
        assert count == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

        # DB呼び出しの引数を検証（ImageFilterCriteria使用）
        mock_db_manager.get_images_by_filter.assert_called_once()
        call_kwargs = mock_db_manager.get_images_by_filter.call_args.kwargs
        criteria = call_kwargs.get("criteria")
        assert criteria is not None
        # #1093/#1094: タグ検索は per-keyword の keyword_groups に組まれる
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [["test"], ["tag"]]
        assert criteria.use_and is True

    def test_search_conditions_to_filter_criteria(self, processor):
        """SearchConditions.to_filter_criteria() のテスト"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["tag1", "tag2"],
            tag_logic="and",
            resolution_filter="1024x1024",
            only_untagged=False,
        )

        criteria = conditions.to_filter_criteria()

        # criteria 属性の確認 (#1093/#1094: タグ検索は keyword_groups に組まれる)
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [["tag1"], ["tag2"]]
        assert all(g.caption_terms == [] for g in criteria.keyword_groups)
        assert criteria.caption is None
        assert criteria.resolution == 1024  # max(1024, 1024)
        assert criteria.use_and is True
        assert criteria.include_untagged is False
        assert criteria.start_date is None
        assert criteria.end_date is None

    def test_process_date_filter_with_dates(self, processor):
        """日付フィルター処理テスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)

        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            date_filter_enabled=True,
            date_range_start=start_date,
            date_range_end=end_date,
        )

        result = processor.process_date_filter(conditions)

        assert "start_date" in result
        assert "end_date" in result
        assert result["start_date"] == start_date
        assert result["end_date"] == end_date

    def test_process_date_filter_no_dates(self, processor):
        """日付なしフィルター処理テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = processor.process_date_filter(conditions)

        # 日付が設定されていない場合は空の辞書
        assert result == {}

    def test_apply_untagged_filter_untagged_only(self, processor):
        """未タグ付きのみフィルター適用テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", only_untagged=True
        )

        result = processor.apply_untagged_filter(conditions)

        assert result.get("has_tags") is False

    def test_apply_untagged_filter_tagged_only(self, processor):
        """タグ付きのみフィルター適用テスト"""
        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", only_untagged=False
        )
        # 擬似的にtagged_onlyを設定
        conditions.tagged_only = True

        result = processor.apply_untagged_filter(conditions)

        assert result.get("has_tags") is True

    def test_apply_tagged_filter_logic_with_tags(self, processor):
        """タグ付きフィルターロジック適用テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["tag1", "tag2"], tag_logic="or")

        result = processor.apply_tagged_filter_logic(conditions)

        assert result["tags"] == ["tag1", "tag2"]
        assert result["tag_operator"] == "or"

    def test_apply_tagged_filter_logic_no_tags(self, processor):
        """タグなしフィルターロジック適用テスト"""
        conditions = SearchConditions(search_type="tags", keywords=[], tag_logic="and")

        result = processor.apply_tagged_filter_logic(conditions)

        # keywordsが空の場合は空の辞書
        assert "tags" not in result or not result.get("tags")

    def test_apply_simple_frontend_filters_aspect_ratio(self, processor):
        """シンプルフロントエンドフィルター適用テスト（アスペクト比）"""
        images = [
            {"width": 1000, "height": 1000},  # 1:1
            {"width": 1920, "height": 1080},  # 16:9
            {"width": 800, "height": 800},  # 1:1
        ]

        conditions = SearchConditions(
            search_type="tags", keywords=["test"], tag_logic="and", aspect_ratio_filter="正方形 (1:1)"
        )

        result = processor._apply_simple_frontend_filters(images, conditions)

        # 正方形(1:1)画像のみ残る
        assert len(result) == 2
        assert result[0]["width"] == 1000
        assert result[1]["width"] == 800

    def test_apply_simple_frontend_filters_basic(self, processor):
        """シンプルフロントエンドフィルター基本テスト"""
        images = [
            {"width": 1000, "height": 1000},
            {"width": 1920, "height": 1080},
        ]

        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = processor._apply_simple_frontend_filters(images, conditions)

        # フィルター条件がない場合は全画像が残る
        assert len(result) == 2

    def test_apply_simple_frontend_filters_with_duplicate_exclusion(self, processor):
        """重複除外フィルター統合テスト（Issue #6）"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
        ]

        conditions = SearchConditions(
            search_type="tags",
            keywords=[],
            tag_logic="and",
            exclude_duplicates=True,
        )

        result = processor._apply_simple_frontend_filters(images, conditions)

        # 検証: 重複が除外され、最初の画像のみ保持
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_filter_by_aspect_ratio_square(self, processor):
        """正方形アスペクト比フィルタリングテスト"""
        images = [
            {"width": 1024, "height": 1024},  # 正方形
            {"width": 1920, "height": 1080},  # 横長
            {"width": 512, "height": 512},  # 正方形
        ]

        result = processor._filter_by_aspect_ratio(images, "正方形 (1:1)")

        assert len(result) == 2
        assert all(img["width"] == img["height"] for img in result)

    def test_filter_by_aspect_ratio_landscape_16_9(self, processor):
        """16:9フィルターで16:9画像のみ残ることを確認"""
        images = [
            {"id": 1, "width": 1920, "height": 1080},  # 16:9
            {"id": 2, "width": 1600, "height": 1200},  # 4:3
            {"id": 3, "width": 1080, "height": 1920},  # 9:16
        ]

        result = processor._filter_by_aspect_ratio(images, "風景 (16:9)")

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_aspect_ratio_landscape_4_3(self, processor):
        """4:3フィルターで16:9を混在させないことを確認"""
        images = [
            {"id": 1, "width": 1920, "height": 1080},  # 16:9
            {"id": 2, "width": 1600, "height": 1200},  # 4:3
            {"id": 3, "width": 1080, "height": 1920},  # 9:16
        ]

        result = processor._filter_by_aspect_ratio(images, "風景 (4:3)")

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_by_aspect_ratio_no_filter(self, processor):
        """アスペクト比フィルターなしテスト"""
        images = [{"width": 1024, "height": 1024}, {"width": 1920, "height": 1080}]

        result = processor._filter_by_aspect_ratio(images, "全て")

        # フィルターなしの場合は全画像が残る
        assert len(result) == 2

    def test_filter_by_date_range_with_range(self, processor):
        """日付範囲フィルタリングテスト"""
        images = [
            {"created_at": "2023-06-15T00:00:00Z"},  # 範囲内
            {"created_at": "2022-12-01T00:00:00Z"},  # 範囲外
            {"modified_at": "2023-03-15T00:00:00Z"},  # modified_atで範囲内
        ]

        date_filter = {"start_date": datetime(2023, 1, 1), "end_date": datetime(2023, 12, 31)}

        result = processor._filter_by_date_range(images, date_filter)

        assert len(result) == 2

    def test_filter_by_date_range_no_filter(self, processor):
        """日付範囲フィルターなしテスト"""
        images = [{"created_at": "2023-06-15T00:00:00Z"}, {"created_at": "2022-12-01T00:00:00Z"}]

        result = processor._filter_by_date_range(images, None)

        # フィルターなしの場合は全画像が残る
        assert len(result) == 2

    def test_filter_images_by_annotation_status_annotated(self, processor, mock_db_manager):
        """アノテーション済み画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        # id=1,3はアノテーション済み、id=2は未アノテーション
        mock_db_manager.get_annotated_image_ids.return_value = {1, 3}

        result = processor.filter_images_by_annotation_status(images, "annotated")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3
        # バッチメソッドが1回だけ呼ばれること
        mock_db_manager.get_annotated_image_ids.assert_called_once_with([1, 2, 3])

    def test_filter_images_by_annotation_status_not_annotated(self, processor, mock_db_manager):
        """未アノテーション画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        # id=1,3はアノテーション済み → id=2のみ未アノテーション
        mock_db_manager.get_annotated_image_ids.return_value = {1, 3}

        result = processor.filter_images_by_annotation_status(images, "not_annotated")

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_images_by_annotation_status_all(self, processor, mock_db_manager):
        """全画像フィルタリングテスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]

        result = processor.filter_images_by_annotation_status(images, "all")

        assert len(result) == 3
        # get_annotated_image_idsは呼ばれない
        mock_db_manager.get_annotated_image_ids.assert_not_called()

    def test_parse_resolution_value_valid(self, processor):
        """有効な解像度文字列解析テスト"""
        assert processor._parse_resolution_value("1920x1080") == (1920, 1080)
        assert processor._parse_resolution_value("512x512") == (512, 512)
        assert processor._parse_resolution_value("2048x1024") == (2048, 1024)

    def test_parse_resolution_value_invalid(self, processor):
        """無効な解像度文字列解析テスト"""
        assert processor._parse_resolution_value("invalid") == (None, None)
        assert processor._parse_resolution_value("1920x") == (None, None)
        assert processor._parse_resolution_value("x1080") == (None, None)
        assert processor._parse_resolution_value("") == (None, None)
        assert processor._parse_resolution_value(None) == (None, None)

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_execute_search_with_filters_error_handling(self, mock_logger, processor, mock_db_manager):
        """検索実行エラーハンドリングテスト"""
        # データベースエラーを発生させる
        mock_db_manager.get_images_by_filter.side_effect = Exception("Database error")

        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # エラーが再発生することを確認
        with pytest.raises(Exception, match="Database error"):
            processor.execute_search_with_filters(conditions)

        # エラーログが出力されることを確認
        mock_logger.error.assert_called_once()


class TestSearchCriteriaProcessorIntegration:
    """SearchCriteriaProcessor の統合テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """統合テスト用モックデータベースマネージャー"""
        mock_db = Mock()
        return mock_db

    @pytest.fixture
    def processor(self, mock_db_manager):
        """統合テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_end_to_end_search_execution(self, processor, mock_db_manager):
        """エンドツーエンド検索実行テスト（直接呼び出し方式）"""
        # モック画像データ
        mock_images = [
            {"id": 1, "width": 1024, "height": 1024, "created_at": "2023-06-15T00:00:00Z"},
            {"id": 2, "width": 1920, "height": 1080, "created_at": "2023-07-20T00:00:00Z"},
        ]
        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)

        # 直接呼び出し用検索条件
        conditions = SearchConditions(
            search_type="tags",
            keywords=["anime", "girl"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
        )

        # 検索実行
        results, count = processor.execute_search_with_filters(conditions)

        # DB呼び出しの引数を検証（ImageFilterCriteria使用）
        mock_db_manager.get_images_by_filter.assert_called_once()
        call_kwargs = mock_db_manager.get_images_by_filter.call_args.kwargs
        criteria = call_kwargs.get("criteria")
        assert criteria is not None
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [["anime"], ["girl"]]
        assert criteria.use_and is True
        assert criteria.resolution == 1024

        # フロントエンドフィルター適用後の結果確認
        assert count == 1  # 正方形のみ
        assert len(results) == 1
        assert results[0]["id"] == 1


@pytest.mark.unit
class TestSearchCriteriaProcessorErrorPaths:
    """SearchCriteriaProcessor の例外パスカバレッジテスト。"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return Mock()

    @pytest.fixture
    def processor(self, mock_db_manager):
        """テスト用 SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_process_date_filter_exception_returns_empty_dict(self, mock_logger, processor) -> None:
        """process_date_filter で例外が起きた場合、空辞書を返してエラーログを出す。"""

        class _BrokenConditions:
            @property
            def date_filter_enabled(self) -> bool:
                raise RuntimeError("boom")

        result = processor.process_date_filter(_BrokenConditions())

        assert result == {}
        mock_logger.error.assert_called_once()

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_apply_untagged_filter_exception_returns_empty_dict(self, mock_logger, processor) -> None:
        """apply_untagged_filter で例外が起きた場合、空辞書を返してエラーログを出す。"""

        class _BrokenConditions:
            @property
            def only_untagged(self) -> bool:
                raise RuntimeError("fail")

        result = processor.apply_untagged_filter(_BrokenConditions())

        assert result == {}
        mock_logger.error.assert_called_once()

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_apply_tagged_filter_logic_exception_returns_empty_dict(self, mock_logger, processor) -> None:
        """apply_tagged_filter_logic で例外が起きた場合、空辞書を返してエラーログを出す。"""

        class _BrokenConditions:
            @property
            def keywords(self) -> list:
                raise RuntimeError("fail")

        result = processor.apply_tagged_filter_logic(_BrokenConditions())

        assert result == {}
        mock_logger.error.assert_called_once()

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_apply_simple_frontend_filters_exception_returns_original_images(
        self, mock_logger, processor
    ) -> None:
        """_apply_simple_frontend_filters で例外が起きた場合、元リストを返してエラーログを出す。"""
        images = [{"id": 1}, {"id": 2}]

        class _BrokenConditions:
            @property
            def aspect_ratio_filter(self) -> str:
                raise RuntimeError("crash")

        result = processor._apply_simple_frontend_filters(images, _BrokenConditions())

        assert result == images
        mock_logger.error.assert_called_once()

    def test_resolve_target_aspect_ratio_denominator_zero(self, processor) -> None:
        """分母がゼロのアスペクト比指定はフォールバックとして 1.0 を返す。"""
        # "0:0" のように分母が 0 となるケース
        result = processor._resolve_target_aspect_ratio("0:0")
        # denominator == 0 のため ratio_match はマッチするが除算スキップ → 後続ブランチへ
        # "0:0" に "正方形"/"風景"/"縦長" は含まれないのでデフォルト 1.0
        assert result == 1.0

    def test_resolve_target_aspect_ratio_縦長(self, processor) -> None:
        """'縦長' を含む文字列は 9/16 を返す。"""
        result = processor._resolve_target_aspect_ratio("縦長ポートレート")
        assert result == pytest.approx(9 / 16)

    def test_image_matches_aspect_ratio_zero_width_returns_false(self, processor) -> None:
        """幅が 0 の画像は False を返す。"""
        image = {"width": 0, "height": 100}
        assert processor._image_matches_aspect_ratio(image, 1.0, 0.1) is False

    def test_image_matches_aspect_ratio_zero_height_returns_false(self, processor) -> None:
        """高さが 0 の画像は False を返す。"""
        image = {"width": 100, "height": 0}
        assert processor._image_matches_aspect_ratio(image, 1.0, 0.1) is False

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_filter_by_aspect_ratio_exception_returns_original_images(self, mock_logger, processor) -> None:
        """_filter_by_aspect_ratio で例外が起きた場合、元リストを返してエラーログを出す。"""
        images = [{"id": 1}]
        # _resolve_target_aspect_ratio が例外を投げるようにする
        with patch.object(processor, "_resolve_target_aspect_ratio", side_effect=RuntimeError("bad")):
            result = processor._filter_by_aspect_ratio(images, "some_filter")

        assert result == images
        mock_logger.error.assert_called_once()

    def test_filter_by_date_range_with_timezone_aware_start_date(self, processor) -> None:
        """タイムゾーン付き start_date を naive に変換してフィルタリングする。"""

        images = [{"created_at": "2023-06-15T00:00:00Z"}]
        # start_date がタイムゾーン付き
        start_date_aware = datetime(2023, 1, 1, tzinfo=UTC)
        date_filter = {"start_date": start_date_aware, "end_date": None}

        result = processor._filter_by_date_range(images, date_filter)

        # 日付は範囲内なので含まれる
        assert len(result) == 1

    def test_filter_by_date_range_with_timezone_aware_end_date(self, processor) -> None:
        """タイムゾーン付き end_date を naive に変換してフィルタリングする。"""

        images = [{"created_at": "2024-06-15T00:00:00Z"}]
        # end_date がタイムゾーン付きで画像の日付より前
        end_date_aware = datetime(2023, 12, 31, tzinfo=UTC)
        date_filter = {"start_date": None, "end_date": end_date_aware}

        result = processor._filter_by_date_range(images, date_filter)

        # 2024年の画像は 2023年末より後なのでフィルターされる
        assert len(result) == 0

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_filter_by_date_range_exception_returns_original_images(self, mock_logger, processor) -> None:
        """_filter_by_date_range で例外が起きた場合、元リストを返してエラーログを出す。"""
        images = [{"id": 1, "created_at": "2023-06-15T00:00:00Z"}]
        # start_date が tzinfo 属性アクセス時に例外を起こすオブジェクト
        bad_start_date = Mock()
        bad_start_date.tzinfo = True  # truthy → replace(tzinfo=None) が呼ばれる
        bad_start_date.replace.side_effect = RuntimeError("replace error")
        bad_date_filter = {"start_date": bad_start_date, "end_date": None}

        result = processor._filter_by_date_range(images, bad_date_filter)

        # エラー時は元リストが返る
        assert result == images
        mock_logger.error.assert_called_once()

    def test_filter_by_duplicate_exclusion_with_no_phash_image(self, processor) -> None:
        """phash キーがない画像は重複チェックなしで保持される。"""
        images = [
            {"id": 1},  # phash なし
            {"id": 2, "phash": "abc123"},
        ]
        result = processor._filter_by_duplicate_exclusion(images)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_filter_by_duplicate_exclusion_with_empty_phash(self, processor) -> None:
        """phash が空文字列の画像は重複チェックなしで保持される。"""
        images = [
            {"id": 1, "phash": ""},  # 空のphash
            {"id": 2, "phash": "abc123"},
        ]
        result = processor._filter_by_duplicate_exclusion(images)

        assert len(result) == 2

    def test_filter_by_duplicate_exclusion_keeps_variants(self, processor) -> None:
        """#633: 同一 pHash でも属性差のある別版は重複除外せず残す。"""
        images = [
            {
                "id": 1,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
            # 別版: 解像度違い → 残る
            {
                "id": 2,
                "phash": "p",
                "width": 128,
                "height": 128,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
            # 別版: グレースケール相当 → 残る
            {
                "id": 3,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": True,
            },
        ]
        result = processor._filter_by_duplicate_exclusion(images)

        assert [img["id"] for img in result] == [1, 2, 3]

    def test_filter_by_duplicate_exclusion_removes_true_duplicates(self, processor) -> None:
        """#633: pHash も属性も完全一致する真の重複は除外する。"""
        images = [
            {
                "id": 1,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
            # 属性まで完全一致 → 除外
            {
                "id": 2,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
        ]
        result = processor._filter_by_duplicate_exclusion(images)

        assert [img["id"] for img in result] == [1]

    def test_filter_by_duplicate_exclusion_null_is_wildcard(self, processor) -> None:
        """#633 (codex P2): 遅延 backfill 未済の NULL 属性は登録分類と同じく一致扱い。

        旧 DB の NULL 属性行と、同一 pHash・同一可視属性だが is_grayscale_like=False の
        新行は、登録側 classify_phash_candidate では DUPLICATE。除外フィルタも NULL を
        wildcard として一致させ、真の重複として 1 件に畳む (pHash-only 時代から退行しない)。
        """
        images = [
            # 遅延 backfill 未済 (has_alpha / is_grayscale_like = None)
            {
                "id": 1,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": None,
                "is_grayscale_like": None,
            },
            # backfill 済みの真の重複 (None は wildcard で一致)
            {
                "id": 2,
                "phash": "p",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
        ]
        result = processor._filter_by_duplicate_exclusion(images)

        assert [img["id"] for img in result] == [1]

    def test_filter_by_duplicate_exclusion_backfills_phash_for_resolution_search(
        self, processor, mock_db_manager
    ) -> None:
        """解像度検索で phash を欠く processed メタでも、オリジナル画像から補完して重複除外する (#1106 Codex P2)。"""
        # processed メタは phash / オリジナル分類属性を持たない (resized 幅高のみ)
        images = [
            {"id": 1, "width": 512, "height": 512},
            {"id": 2, "width": 512, "height": 512},
        ]
        # Image テーブル由来の重複判定フィールド: 両者は同一 pHash・同一属性の真の重複
        original = {
            "phash": "dup",
            "width": 1024,
            "height": 1024,
            "has_alpha": False,
            "is_grayscale_like": False,
        }
        mock_db_manager.image_repo.get_phash_classification_by_ids.return_value = {
            1: dict(original),
            2: dict(original),
        }

        result = processor._filter_by_duplicate_exclusion(images)

        # 補完した phash + オリジナル属性で真の重複と判定し 1 件に畳む
        assert [img["id"] for img in result] == [1]
        mock_db_manager.image_repo.get_phash_classification_by_ids.assert_called_once_with([1, 2])

    def test_filter_by_duplicate_exclusion_no_backfill_when_phash_present(
        self, processor, mock_db_manager
    ) -> None:
        """メタに phash があれば (resolution=0 検索) 補完 fetch は発生しない (#1106)。"""
        images = [
            {
                "id": 1,
                "phash": "a",
                "width": 64,
                "height": 64,
                "has_alpha": False,
                "is_grayscale_like": False,
            },
        ]
        processor._filter_by_duplicate_exclusion(images)
        mock_db_manager.image_repo.get_phash_classification_by_ids.assert_not_called()

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_filter_by_duplicate_exclusion_exception_returns_original_images(
        self, mock_logger, processor
    ) -> None:
        """_filter_by_duplicate_exclusion で例外が起きた場合、元リストを返してエラーログを出す。"""

        # list の iteration で例外を発生させる
        class BrokenList(list):
            def __iter__(self):
                raise RuntimeError("iteration failed")

        images_input = [{"id": 1, "phash": "abc"}]
        broken = BrokenList(images_input)

        result = processor._filter_by_duplicate_exclusion(broken)

        assert result is broken
        mock_logger.error.assert_called_once()

    @patch("lorairo.services.search_criteria_processor.logger")
    def test_parse_resolution_value_exception_returns_none_tuple(self, mock_logger, processor) -> None:
        """_parse_resolution_value で例外が起きた場合、(None, None) を返してエラーログを出す。"""
        # re.match が例外を投げるようにする
        with patch("lorairo.services.search_criteria_processor.re") as mock_re:
            mock_re.match.side_effect = RuntimeError("re error")
            result = processor._parse_resolution_value("1920x1080")

        assert result == (None, None)
        mock_logger.error.assert_called_once()


class TestDuplicateExclusionFilter:
    """重複除外フィルターのユニットテスト（Issue #6）"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return Mock()

    @pytest.fixture
    def processor(self, mock_db_manager):
        """テスト用SearchCriteriaProcessor"""
        return SearchCriteriaProcessor(mock_db_manager)

    def test_filter_by_duplicate_exclusion_basic(self, processor):
        """基本的な重複除外テスト"""
        # テストデータ: 重複あり（同じphash）
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 重複は除外され、最初の画像のみ保持
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_filter_by_duplicate_exclusion_empty_list(self, processor):
        """空リスト処理テスト"""
        images = []

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 空リストはそのまま返却
        assert len(result) == 0
        assert result == []

    def test_filter_by_duplicate_exclusion_no_duplicates(self, processor):
        """重複なしケーステスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "def456", "width": 512, "height": 512},
            {"id": 3, "phash": "ghi789", "width": 800, "height": 600},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 全画像保持
        assert len(result) == 3
        assert result == images

    def test_filter_by_duplicate_exclusion_all_duplicates(self, processor):
        """全て重複ケーステスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 3, "phash": "abc123", "width": 1024, "height": 768},
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 1枚のみ保持
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_duplicate_exclusion_single_image(self, processor):
        """単一画像テスト"""
        images = [{"id": 1, "phash": "abc123", "width": 1024, "height": 768}]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: そのまま保持
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filter_by_duplicate_exclusion_partial_duplicates(self, processor):
        """部分重複テスト"""
        images = [
            {"id": 1, "phash": "abc123", "width": 1024, "height": 768},
            {"id": 2, "phash": "abc123", "width": 1024, "height": 768},  # 重複グループ1
            {"id": 3, "phash": "def456", "width": 512, "height": 512},
            {"id": 4, "phash": "def456", "width": 512, "height": 512},  # 重複グループ2
            {"id": 5, "phash": "ghi789", "width": 800, "height": 600},  # ユニーク
        ]

        result = processor._filter_by_duplicate_exclusion(images)

        # 検証: 各グループから1枚ずつ保持
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3
        assert result[2]["id"] == 5

    def test_filter_by_duplicate_exclusion_performance(self, processor):
        """性能テスト（10,000画像で < 500ms）"""
        import time

        # テストデータ生成: 10,000画像（50%重複）
        test_images = []
        for i in range(5000):
            # 重複ペア
            phash = f"phash_{i:06d}"
            test_images.append({"id": i * 2, "phash": phash, "width": 1024, "height": 1024})
            test_images.append({"id": i * 2 + 1, "phash": phash, "width": 1024, "height": 1024})

        start = time.perf_counter()
        result = processor._filter_by_duplicate_exclusion(test_images)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        # 検証: 期待される結果数
        assert len(result) == 5000, f"Expected 5000, got {len(result)}"

        # 性能要件検証
        assert elapsed < 500, f"Performance requirement failed: {elapsed:.2f}ms > 500ms"


class TestSearchTargetRedesign:
    """タグ / キャプション独立検索対象と翻訳解決の再設計テスト (#1093 / #1094)。"""

    def test_dual_target_group_has_tag_and_caption_terms(self):
        """タグ + キャプション同時 ON で各 keyword_group が両ターゲット語を持つ (#1093)。"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["alpha", "beta"],
            tag_logic="or",
            search_tags=True,
            search_caption=True,
        )
        criteria = conditions.to_filter_criteria()
        assert criteria.tags is None and criteria.caption is None
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [["alpha"], ["beta"]]
        assert [g.caption_terms for g in criteria.keyword_groups] == [["alpha"], ["beta"]]

    def test_caption_only_group_has_no_tag_terms(self):
        """キャプションのみ ON で keyword_group のタグ語は空、全キーワードが caption 語になる (#1093)。"""
        conditions = SearchConditions(
            search_type="tags",  # 旧主タイプは tags だが flag が優先される
            keywords=["cat", "dog"],
            tag_logic="and",
            search_tags=False,
            search_caption=True,
        )
        criteria = conditions.to_filter_criteria()
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [[], []]
        assert [g.caption_terms for g in criteria.keyword_groups] == [["cat"], ["dog"]]

    def test_backward_compat_search_type_caption(self):
        """flag 未指定時は search_type から導出し、caption 検索で全キーワードを使う。"""
        conditions = SearchConditions(search_type="caption", keywords=["k1", "k2"], tag_logic="and")
        criteria = conditions.to_filter_criteria()
        assert criteria.keyword_groups is not None
        assert [g.tag_terms for g in criteria.keyword_groups] == [[], []]
        assert [g.caption_terms for g in criteria.keyword_groups] == [["k1"], ["k2"]]

    def test_flag_precedence_over_search_type(self):
        """search_tags/search_caption が指定されていれば search_type より優先される。"""
        conditions = SearchConditions(
            search_type="caption",
            keywords=["x"],
            tag_logic="and",
            search_tags=True,
            search_caption=False,
        )
        assert conditions.is_tag_search_enabled() is True
        assert conditions.is_caption_search_enabled() is False

    def test_tag_resolver_expands_translations_within_keyword(self):
        """tag_resolver がキーワード内のタグエイリアス群として翻訳解決を展開する (#1094)。"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["犬"],
            tag_logic="or",
            search_tags=True,
        )
        criteria = conditions.to_filter_criteria(tag_resolver=lambda kws: [*kws, "dog"])
        assert criteria.keyword_groups is not None
        # 1 キーワードのエイリアス群として ["犬", "dog"] が入る (キーワード内 OR)
        assert criteria.keyword_groups[0].tag_terms == ["犬", "dog"]

    def test_tag_resolver_not_applied_to_caption(self):
        """tag_resolver はキャプション検索対象には適用されない (#1094)。"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["犬"],
            tag_logic="or",
            search_tags=False,
            search_caption=True,
        )
        criteria = conditions.to_filter_criteria(tag_resolver=lambda kws: [*kws, "dog"])
        assert criteria.keyword_groups is not None
        assert criteria.keyword_groups[0].tag_terms == []
        assert criteria.keyword_groups[0].caption_terms == ["犬"]


class TestResolveTagSearchTargets:
    """resolve_tag_search_targets の翻訳解決ユニットテスト (#1094)。"""

    def test_none_reader_returns_keywords_unchanged(self):
        """merged_reader が None のとき元キーワードをそのまま返す (グレースフルデグラデーション)。"""
        from lorairo.services.search_criteria_processor import resolve_tag_search_targets

        assert resolve_tag_search_targets(None, ["犬", "cat"]) == ["犬", "cat"]

    def test_adds_canonical_tags_from_search(self):
        """search_tags のヒット正規タグ名を元キーワードに重複排除して追加する。"""
        from types import SimpleNamespace

        from lorairo.services import search_criteria_processor

        reader = Mock()
        result = SimpleNamespace(items=[SimpleNamespace(tag="dog"), SimpleNamespace(tag="dog")])
        with patch("genai_tag_db_tools.search_tags", return_value=result):
            resolved = search_criteria_processor.resolve_tag_search_targets(reader, ["犬"])
        # 元キーワード維持 + 翻訳ヒット追加 + 重複排除
        assert resolved == ["犬", "dog"]

    def test_search_failure_degrades_to_keywords(self):
        """search_tags が例外を投げても元キーワードで検索継続する。"""
        from lorairo.services import search_criteria_processor

        reader = Mock()
        with patch("genai_tag_db_tools.search_tags", side_effect=RuntimeError("boom")):
            resolved = search_criteria_processor.resolve_tag_search_targets(reader, ["犬"])
        assert resolved == ["犬"]


class TestBuildTagResolverLazyReader:
    """build_tag_resolver は MergedTagReader を遅延取得する (#1122 Codex P2)。"""

    def test_reader_not_fetched_until_tag_keywords_resolved(self):
        """構築時・空キーワード解決では reader を取得せず、実際のタグ語解決で初回取得しキャッシュする。"""
        from lorairo.services.search_criteria_processor import build_tag_resolver

        db = Mock()
        db.annotation_repo.get_merged_reader.return_value = None  # reader 不在で縮退

        resolver = build_tag_resolver(db)
        # 構築時点では get_merged_reader は呼ばれない (caption-only 等では resolver 自体が未使用)
        db.annotation_repo.get_merged_reader.assert_not_called()

        # 空キーワード解決でも取得しない
        assert resolver([]) == []
        db.annotation_repo.get_merged_reader.assert_not_called()

        # 実際のタグ語解決で初めて reader を取得する
        assert resolver(["犬"]) == ["犬"]  # reader None のため縮退
        db.annotation_repo.get_merged_reader.assert_called_once()

        # 2 回目以降はキャッシュし再取得しない
        resolver(["cat"])
        db.annotation_repo.get_merged_reader.assert_called_once()
