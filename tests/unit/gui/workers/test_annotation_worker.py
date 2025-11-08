"""AnnotationWorkerユニットテスト

Phase 4-4: AnnotationWorker実装のテスト
AnnotationService統合とWorker進捗レポートを検証
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.gui.workers.annotation_worker import AnnotationWorker, ModelSyncWorker


@pytest.fixture
def mock_annotation_service() -> MagicMock:
    """AnnotationServiceのモックフィクスチャ"""
    service = MagicMock()

    # start_single_annotationモック（同期的に結果を設定）
    def mock_start_single(images: Any, phash_list: Any, models: Any) -> None:
        service._last_result = {
            "test_phash": {
                "gpt-4o": {
                    "tags": ["cat", "animal"],
                    "formatted_output": {"captions": ["A cat sitting"]},
                    "error": None,
                }
            }
        }

    service.start_single_annotation.side_effect = mock_start_single
    service.get_last_annotation_result.return_value = {
        "test_phash": {
            "gpt-4o": {
                "tags": ["cat", "animal"],
                "formatted_output": {"captions": ["A cat sitting"]},
                "error": None,
            }
        }
    }

    # start_batch_annotationモック
    mock_batch_result = MagicMock()
    mock_batch_result.summary = "Processed 10 images"
    mock_batch_result.processed_images = 10
    mock_batch_result.total_images = 10

    def mock_start_batch(image_paths: Any, models: Any, batch_size: Any) -> None:
        service._last_batch_result = mock_batch_result

    service.start_batch_annotation.side_effect = mock_start_batch
    service.get_last_batch_result.return_value = mock_batch_result

    # sync_available_modelsモック
    service.sync_available_models.return_value = None

    return service


class TestAnnotationWorker:
    """AnnotationWorkerユニットテスト"""

    def test_initialization_single_mode(self) -> None:
        """初期化テスト（単発モード）"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o"]

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = AnnotationWorker(
                images=images, phash_list=phash_list, models=models, operation_mode="single"
            )

            assert worker.operation_mode == "single"
            assert len(worker.images) == 1
            assert len(worker.phash_list) == 1
            assert len(worker.models) == 1

    def test_initialization_batch_mode(self):
        """初期化テスト（バッチモード）"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o"]

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = AnnotationWorker(
                image_paths=image_paths, models=models, batch_size=50, operation_mode="batch"
            )

            assert worker.operation_mode == "batch"
            assert len(worker.image_paths) == 2
            assert worker.batch_size == 50
            assert len(worker.models) == 1

    def test_execute_single_annotation_success(self, mock_annotation_service):
        """単発アノテーション実行成功テスト"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o"]

        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(
                images=images, phash_list=phash_list, models=models, operation_mode="single"
            )

            # 実行
            result = worker.execute()

            # 検証
            mock_annotation_service.start_single_annotation.assert_called_once_with(
                images=images, models=models, phash_list=phash_list
            )
            assert "test_phash" in result
            assert result["test_phash"]["gpt-4o"]["tags"] == ["cat", "animal"]

    def test_execute_single_annotation_no_images(self, mock_annotation_service):
        """画像なしエラーテスト"""
        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(images=[], models=["gpt-4o"], operation_mode="single")

            with pytest.raises(ValueError, match="単発モードで画像が指定されていません"):
                worker.execute()

    def test_execute_single_annotation_no_models(self, mock_annotation_service):
        """モデルなしエラーテスト"""
        test_image = Image.new("RGB", (100, 100))

        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(images=[test_image], models=[], operation_mode="single")

            with pytest.raises(ValueError, match="モデルが選択されていません"):
                worker.execute()

    def test_execute_single_annotation_no_result(self, mock_annotation_service):
        """結果取得失敗エラーテスト"""
        mock_annotation_service.get_last_annotation_result.return_value = None

        test_image = Image.new("RGB", (100, 100))

        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(
                images=[test_image], phash_list=["test"], models=["gpt-4o"], operation_mode="single"
            )

            with pytest.raises(RuntimeError, match="アノテーション結果が取得できませんでした"):
                worker.execute()

    def test_execute_batch_annotation_success(self, mock_annotation_service):
        """バッチアノテーション実行成功テスト"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o"]

        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(image_paths=image_paths, models=models, operation_mode="batch")

            # 実行
            result = worker.execute()

            # 検証
            mock_annotation_service.start_batch_annotation.assert_called_once()
            assert result.processed_images == 10
            assert result.total_images == 10

    def test_execute_batch_annotation_no_paths(self, mock_annotation_service):
        """画像パスなしエラーテスト"""
        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(image_paths=[], models=["gpt-4o"], operation_mode="batch")

            with pytest.raises(ValueError, match="バッチモードで画像パスが指定されていません"):
                worker.execute()

    def test_execute_batch_annotation_no_result(self, mock_annotation_service):
        """バッチ結果取得失敗エラーテスト"""
        mock_annotation_service.get_last_batch_result.return_value = None

        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(image_paths=["/test.jpg"], models=["gpt-4o"], operation_mode="batch")

            with pytest.raises(RuntimeError, match="バッチアノテーション結果が取得できませんでした"):
                worker.execute()

    def test_execute_invalid_mode(self, mock_annotation_service):
        """不正な動作モードエラーテスト"""
        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(images=[Image.new("RGB", (100, 100))], models=["gpt-4o"])
            worker.operation_mode = "invalid"

            with pytest.raises(ValueError, match="不正な動作モード"):
                worker.execute()

    def test_get_worker_info(self, mock_annotation_service):
        """ワーカー情報取得テスト"""
        with patch(
            "lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_annotation_service
        ):
            worker = AnnotationWorker(
                images=[Image.new("RGB", (100, 100))], models=["gpt-4o"], operation_mode="single"
            )

            info = worker.get_worker_info()

            assert info["worker_type"] == "AnnotationWorker"
            assert info["operation_mode"] == "single"
            assert info["model_count"] == 1
            assert info["models"] == ["gpt-4o"]


class TestModelSyncWorker:
    """ModelSyncWorkerユニットテスト"""

    def test_initialization(self):
        """初期化テスト"""
        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = ModelSyncWorker()
            assert worker is not None

    def test_execute_success(self):
        """モデル同期実行成功テスト"""
        mock_service = MagicMock()
        mock_service.sync_available_models.return_value = None

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService", return_value=mock_service):
            worker = ModelSyncWorker()
            result = worker.execute()

            mock_service.sync_available_models.assert_called_once()
            assert result is not None

    def test_get_worker_info(self):
        """ワーカー情報取得テスト"""
        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = ModelSyncWorker()
            info = worker.get_worker_info()

            assert info["worker_type"] == "ModelSyncWorker"
            assert info["operation"] == "model_sync"
