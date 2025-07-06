"""ImageAnalyzer のユニットテスト"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.annotations.caption_tags import ImageAnalyzer


class TestImageAnalyzer:
    """ImageAnalyzer のテスト"""

    def test_init(self):
        """初期化テスト"""
        analyzer = ImageAnalyzer()

        # TagCleaner が適切に初期化されることを確認
        assert analyzer.tag_cleaner is not None
        assert analyzer.format_name == "unknown"

    def test_initialize(self):
        """initialize メソッドのテスト"""
        analyzer = ImageAnalyzer()
        vision_models = {"1": {"name": "model1"}}
        score_models = {"1": {"name": "score1"}}
        models_config = (vision_models, score_models)

        analyzer.initialize(models_config)

        assert analyzer.vision_models == vision_models
        assert analyzer.score_models == score_models

    def test_get_batch_analysis_with_content(self):
        """バッチ分析結果の取得テスト（コンテンツあり）"""
        analyzer = ImageAnalyzer()
        batch_results = {"test_image": "dummy content"}
        processed_path = Path("test_image.jpg")

        with patch("lorairo.annotations.caption_tags.logger") as mock_logger:
            result = analyzer.get_batch_analysis(batch_results, processed_path)

            # 削除されたメソッドを使用するため警告が出ることを確認
            mock_logger.warning.assert_called_once_with(
                "get_batch_analysis は削除されたメソッドを使用しているため動作しません"
            )
            assert result is None

    def test_get_batch_analysis_without_content(self):
        """バッチ分析結果の取得テスト（コンテンツなし）"""
        analyzer = ImageAnalyzer()
        batch_results = {}  # 空の結果
        processed_path = Path("test_image.jpg")

        result = analyzer.get_batch_analysis(batch_results, processed_path)

        # custom_id が見つからないため何も返されない
        assert result is None

    def test_format_name_persistence(self):
        """format_name の永続性テスト"""
        analyzer = ImageAnalyzer()

        # 初期値の確認
        assert analyzer.format_name == "unknown"

        # 値の変更
        analyzer.format_name = "e621"
        assert analyzer.format_name == "e621"

    @patch("lorairo.annotations.caption_tags.TagCleaner")
    def test_tag_cleaner_initialization(self, mock_tag_cleaner_class):
        """TagCleaner の初期化テスト"""
        mock_tag_cleaner = Mock()
        mock_tag_cleaner_class.return_value = mock_tag_cleaner

        analyzer = ImageAnalyzer()

        # genai-tag-db-tools の TagCleaner が使用されることを確認
        mock_tag_cleaner_class.assert_called_once()
        assert analyzer.tag_cleaner == mock_tag_cleaner


class TestDeletedMethodsReferences:
    """削除されたメソッドに関する参照のテスト"""

    def test_analyze_image_method_removed(self):
        """analyze_image メソッドが削除されていることのテスト"""
        analyzer = ImageAnalyzer()

        # analyze_image メソッドが存在しないことを確認
        assert not hasattr(analyzer, "analyze_image")

    def test_get_existing_annotations_method_removed(self):
        """get_existing_annotations メソッドが削除されていることのテスト"""
        analyzer = ImageAnalyzer()

        # get_existing_annotations メソッドが存在しないことを確認
        assert not hasattr(analyzer, "get_existing_annotations")

    def test_read_annotations_method_removed(self):
        """_read_annotations メソッドが削除されていることのテスト"""
        analyzer = ImageAnalyzer()

        # _read_annotations メソッドが存在しないことを確認
        assert not hasattr(analyzer, "_read_annotations")

    def test_process_response_method_removed(self):
        """_process_response メソッドが削除されていることのテスト"""
        analyzer = ImageAnalyzer()

        # _process_response メソッドが存在しないことを確認
        assert not hasattr(analyzer, "_process_response")

    def test_extract_tags_and_caption_method_removed(self):
        """_extract_tags_and_caption メソッドが削除されていることのテスト"""
        analyzer = ImageAnalyzer()

        # _extract_tags_and_caption メソッドが存在しないことを確認
        assert not hasattr(analyzer, "_extract_tags_and_caption")


class TestImageAnalyzerIntegration:
    """ImageAnalyzer の統合テスト"""

    def test_workflow_without_deleted_methods(self):
        """削除されたメソッドなしでのワークフローテスト"""
        analyzer = ImageAnalyzer()

        # 基本的な初期化とプロパティアクセス
        vision_models = {"1": {"name": "test_model"}}
        score_models = {"1": {"name": "test_score"}}
        analyzer.initialize((vision_models, score_models))

        # 設定が正しく保存されていることを確認
        assert analyzer.vision_models == vision_models
        assert analyzer.score_models == score_models
        assert analyzer.tag_cleaner is not None

    def test_models_access_after_initialization(self):
        """初期化後のモデルアクセステスト"""
        analyzer = ImageAnalyzer()

        vision_models = {"1": {"name": "gpt-4o"}, "2": {"name": "claude-3"}}
        score_models = {"1": {"name": "aesthetic_score"}, "2": {"name": "quality_score"}}

        analyzer.initialize((vision_models, score_models))

        # vision_models から名前を取得できることを確認
        model_name = analyzer.vision_models.get("1", {}).get("name")
        assert model_name == "gpt-4o"

        # score_models からも取得できることを確認
        score_name = analyzer.score_models.get("2", {}).get("name")
        assert score_name == "quality_score"
