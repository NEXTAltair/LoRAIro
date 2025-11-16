"""AnnotationWorkerユニットテスト

Phase 7で再設計された3層アーキテクチャに対応:
- AnnotationLogic依存注入
- image_paths/modelsインターフェース
- 進捗報告・キャンセル処理
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_worker import AnnotationWorker


@pytest.fixture
def mock_annotation_logic():
    """AnnotationLogicのモック"""
    logic = Mock()
    logic.execute_annotation.return_value = {
        "test_phash": {
            "gpt-4o-mini": {
                "tags": ["cat", "animal"],
                "formatted_output": {"captions": ["A cat"]},
                "error": None,
            }
        }
    }
    return logic


class TestAnnotationWorkerInitialization:
    """AnnotationWorker初期化テスト"""

    def test_initialization_with_annotation_logic(self, mock_annotation_logic):
        """正常な初期化テスト"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
        )

        assert worker.annotation_logic is mock_annotation_logic
        assert worker.image_paths == image_paths
        assert worker.models == models


class TestAnnotationWorkerExecute:
    """AnnotationWorker execute()テスト"""

    def test_execute_success_single_model(self, mock_annotation_logic):
        """単一モデルでの正常実行"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
        )

        result = worker.execute()

        # AnnotationLogic.execute_annotation()が呼ばれたことを確認
        mock_annotation_logic.execute_annotation.assert_called_once_with(
            image_paths=image_paths,
            model_names=["gpt-4o-mini"],
        )

        # 結果が正しく返されることを確認
        assert "test_phash" in result
        assert "gpt-4o-mini" in result["test_phash"]

    def test_execute_success_multiple_models(self, mock_annotation_logic):
        """複数モデルでの正常実行（結果マージ確認）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # モデルごとの戻り値
        mock_annotation_logic.execute_annotation.side_effect = [
            {
                "phash1": {
                    "gpt-4o-mini": {
                        "tags": ["cat"],
                        "formatted_output": {},
                        "error": None,
                    }
                }
            },
            {
                "phash1": {
                    "claude-3-haiku-20240307": {
                        "tags": ["feline"],
                        "formatted_output": {},
                        "error": None,
                    }
                }
            },
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
        )

        result = worker.execute()

        # execute_annotation()が2回（モデル数）呼ばれたことを確認
        assert mock_annotation_logic.execute_annotation.call_count == 2

        # 結果がマージされていることを確認
        assert "phash1" in result
        assert "gpt-4o-mini" in result["phash1"]
        assert "claude-3-haiku-20240307" in result["phash1"]

    def test_execute_model_error_partial_success(self, mock_annotation_logic):
        """モデルエラー時の部分的成功"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307", "gemini-1.5-flash-latest"]

        # 2番目のモデルでエラー
        mock_annotation_logic.execute_annotation.side_effect = [
            {"phash1": {"gpt-4o-mini": {"tags": ["cat"], "formatted_output": {}, "error": None}}},
            RuntimeError("API Error"),  # 2番目はエラー
            {
                "phash1": {
                    "gemini-1.5-flash-latest": {"tags": ["animal"], "formatted_output": {}, "error": None}
                }
            },
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
        )

        # エラーでも処理継続（部分的成功を許容）
        result = worker.execute()

        # 3回呼ばれたことを確認
        assert mock_annotation_logic.execute_annotation.call_count == 3

        # 成功したモデルの結果のみ含まれる
        assert "phash1" in result
        assert "gpt-4o-mini" in result["phash1"]
        assert "claude-3-haiku-20240307" not in result["phash1"]  # エラーで除外
        assert "gemini-1.5-flash-latest" in result["phash1"]

    def test_execute_all_models_fail(self, mock_annotation_logic):
        """全モデルエラー時（空結果）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # 全てエラー
        mock_annotation_logic.execute_annotation.side_effect = [
            RuntimeError("API Error 1"),
            RuntimeError("API Error 2"),
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
        )

        # エラーでも例外は発生しない（空結果を返す）
        result = worker.execute()

        # 空の結果が返される
        assert result == {}
