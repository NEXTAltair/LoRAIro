"""AnnotationService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QObject, QThread

from lorairo.services.annotation_service import AnnotationService, AnnotationWorker


class TestAnnotationWorker:
    """AnnotationWorker のテスト"""

    def test_init(self):
        """初期化テスト"""
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]

        worker = AnnotationWorker(images, phash_list, models)

        assert worker._images == images
        assert worker._phash_list == phash_list
        assert worker._models == models

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_task_success(self, mock_annotate):
        """正常なアノテーション処理のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        mock_result = {"test_hash": {"test_model": {"tags": ["tag1"], "error": None}}}
        mock_annotate.return_value = mock_result

        worker = AnnotationWorker(images, phash_list, models)

        # Act
        result = worker.run_task()

        # Assert
        mock_annotate.assert_called_once_with(images, models, phash_list)
        assert result == mock_result

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_task_exception(self, mock_annotate):
        """アノテーション処理でエラーが発生した場合のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        mock_annotate.side_effect = ValueError("Test error")

        worker = AnnotationWorker(images, phash_list, models)

        # Act & Assert
        with pytest.raises(ValueError, match="Test error"):
            worker.run_task()


class TestAnnotationService:
    """AnnotationService のテスト"""

    def test_init(self):
        """初期化テスト"""
        service = AnnotationService()

        assert service._thread is None
        assert service._worker is None
        assert isinstance(service, QObject)

    def test_start_annotation_empty_images(self):
        """空の画像リストでアノテーションを開始した場合のテスト"""
        service = AnnotationService()

        # シグナルをモック
        with patch.object(service, "annotationFinished") as mock_signal:
            service.start_annotation([], [], ["model1"])

            # ValueError がエミットされることを確認
            mock_signal.emit.assert_called_once()
            args = mock_signal.emit.call_args[0]
            assert isinstance(args[0], ValueError)
            assert "入力画像がありません" in str(args[0])

    def test_start_annotation_mismatched_lists(self):
        """画像とpHashリストの数が一致しない場合のテスト"""
        service = AnnotationService()
        images = [Mock(spec=Image.Image), Mock(spec=Image.Image)]
        phash_list = ["hash1"]  # 画像より少ない

        with patch.object(service, "annotationFinished") as mock_signal:
            service.start_annotation(images, phash_list, ["model1"])

            mock_signal.emit.assert_called_once()
            args = mock_signal.emit.call_args[0]
            assert isinstance(args[0], ValueError)
            assert "画像とpHashの数が一致しません" in str(args[0])

    def test_start_annotation_empty_models(self):
        """空のモデルリストでアノテーションを開始した場合のテスト"""
        service = AnnotationService()
        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]

        with patch.object(service, "annotationFinished") as mock_signal:
            service.start_annotation(images, phash_list, [])

            mock_signal.emit.assert_called_once()
            args = mock_signal.emit.call_args[0]
            assert isinstance(args[0], ValueError)
            assert "モデルが選択されていません" in str(args[0])

    def test_start_annotation_already_running(self):
        """既に処理が実行中の場合のテスト"""
        service = AnnotationService()
        service._thread = Mock(spec=QThread)
        service._thread.isRunning.return_value = True

        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]
        models = ["model1"]

        # ログが警告を出力することを確認（実際にはシグナルを出さない）
        with patch("lorairo.services.annotation_service.logger") as mock_logger:
            service.start_annotation(images, phash_list, models)
            mock_logger.warning.assert_called_once()

    @patch("lorairo.services.annotation_service.QThread")
    @patch("lorairo.services.annotation_service.AnnotationWorker")
    def test_start_annotation_success(self, mock_worker_class, mock_thread_class):
        """正常なアノテーション開始のテスト"""
        # Arrange
        service = AnnotationService()
        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]
        models = ["model1"]

        mock_thread = Mock(spec=QThread)
        mock_worker = Mock(spec=AnnotationWorker)
        mock_thread_class.return_value = mock_thread
        mock_worker_class.return_value = mock_worker

        # Act
        service.start_annotation(images, phash_list, models)

        # Assert
        mock_worker_class.assert_called_once_with(images, phash_list, models)
        mock_worker.moveToThread.assert_called_once_with(mock_thread)
        mock_thread.start.assert_called_once()

    @patch("lorairo.services.annotation_service.list_available_annotators")
    def test_fetch_available_annotators_success(self, mock_list_annotators):
        """利用可能なアノテーター取得成功のテスト"""
        service = AnnotationService()
        mock_models = ["model1", "model2"]
        mock_list_annotators.return_value = mock_models

        with patch.object(service, "availableAnnotatorsFetched") as mock_signal:
            service.fetch_available_annotators()

            mock_list_annotators.assert_called_once()
            mock_signal.emit.assert_called_once_with(mock_models)

    @patch("lorairo.services.annotation_service.list_available_annotators")
    def test_fetch_available_annotators_exception(self, mock_list_annotators):
        """利用可能なアノテーター取得でエラーが発生した場合のテスト"""
        service = AnnotationService()
        mock_list_annotators.side_effect = Exception("Test error")

        with patch.object(service, "availableAnnotatorsFetched") as mock_signal:
            service.fetch_available_annotators()

            mock_signal.emit.assert_called_once_with([])

    def test_cancel_annotation_no_worker(self):
        """ワーカーがない状態でキャンセルを試行した場合のテスト"""
        service = AnnotationService()

        with patch("lorairo.services.annotation_service.logger") as mock_logger:
            service.cancel_annotation()
            mock_logger.info.assert_called_once_with(
                "AnnotationService: キャンセル対象のアノテーション処理はありません。"
            )

    def test_cancel_annotation_with_worker(self):
        """ワーカーがある状態でキャンセルを試行した場合のテスト"""
        service = AnnotationService()
        service._worker = Mock(spec=AnnotationWorker)
        service._thread = Mock(spec=QThread)
        service._thread.isRunning.return_value = True

        service.cancel_annotation()

        service._worker.cancel.assert_called_once()

    def test_handle_finished(self):
        """ワーカー完了時の処理テスト"""
        service = AnnotationService()
        test_result = {"test": "result"}

        with patch.object(service, "annotationFinished") as mock_signal:
            service._handle_finished(test_result)
            mock_signal.emit.assert_called_once_with(test_result)

    def test_reset_thread_worker(self):
        """スレッドとワーカーのリセットテスト"""
        service = AnnotationService()
        service._thread = Mock(spec=QThread)
        service._worker = Mock(spec=AnnotationWorker)

        service._reset_thread_worker()

        assert service._thread is None
        assert service._worker is None
