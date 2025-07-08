"""AnnotationService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QObject, QThread

from lorairo.services.annotation_service import AnnotationService, run_annotation_task


class TestRunAnnotationTask:
    """run_annotation_task 関数のテスト"""

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_annotation_task_success(self, mock_annotate):
        """正常なアノテーション処理のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        mock_result = {"test_hash": {"test_model": {"tags": ["tag1"], "error": None}}}
        mock_annotate.return_value = mock_result

        # Act
        result = run_annotation_task(images, phash_list, models)

        # Assert
        mock_annotate.assert_called_once_with(images, models, phash_list)
        assert result == mock_result

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_annotation_task_with_callbacks(self, mock_annotate):
        """コールバック付きアノテーション処理のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        mock_result = {"test_hash": {"test_model": {"tags": ["tag1"], "error": None}}}
        mock_annotate.return_value = mock_result
        
        progress_callback = Mock()
        status_callback = Mock()

        # Act
        result = run_annotation_task(
            images, phash_list, models,
            progress_callback=progress_callback,
            status_callback=status_callback
        )

        # Assert
        mock_annotate.assert_called_once_with(images, models, phash_list)
        assert result == mock_result
        
        # コールバックが呼ばれることを確認
        progress_callback.assert_any_call(10)  # 開始時
        progress_callback.assert_any_call(100)  # 完了時
        status_callback.assert_any_call("AIアノテーション処理を開始...")
        status_callback.assert_any_call("アノテーション処理が完了しました。")

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_annotation_task_canceled(self, mock_annotate):
        """キャンセル時のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        
        is_canceled = Mock(return_value=True)

        # Act & Assert
        with pytest.raises(RuntimeError, match="アノテーション処理がキャンセルされました"):
            run_annotation_task(
                images, phash_list, models,
                is_canceled=is_canceled
            )
        
        # annotate が呼ばれないことを確認
        mock_annotate.assert_not_called()

    @patch("lorairo.services.annotation_service.annotate")
    def test_run_annotation_task_exception(self, mock_annotate):
        """アノテーション処理でエラーが発生した場合のテスト"""
        # Arrange
        images = [Mock(spec=Image.Image)]
        phash_list = ["test_hash"]
        models = ["test_model"]
        mock_annotate.side_effect = ValueError("Test error")
        
        status_callback = Mock()

        # Act & Assert
        with pytest.raises(ValueError, match="Test error"):
            run_annotation_task(
                images, phash_list, models,
                status_callback=status_callback
            )
        
        # エラーメッセージがコールバックに送られることを確認
        status_callback.assert_any_call("エラー: Test error")


class TestAnnotationService:
    """AnnotationService のテスト"""

    def test_init(self):
        """初期化テスト"""
        service = AnnotationService()

        assert service._controller is None
        assert service._annotation_result is None
        assert isinstance(service, QObject)

    def test_start_annotation_empty_images(self):
        """空の画像リストでアノテーションを開始した場合のテスト"""
        service = AnnotationService()

        # シグナルをモック
        with patch.object(service, "annotationError") as mock_signal:
            service.start_annotation([], [], ["model1"])

            # エラーメッセージがエミットされることを確認
            mock_signal.emit.assert_called_once_with("入力画像がありません。")

    def test_start_annotation_mismatched_lists(self):
        """画像とpHashリストの数が一致しない場合のテスト"""
        service = AnnotationService()
        images = [Mock(spec=Image.Image), Mock(spec=Image.Image)]
        phash_list = ["hash1"]  # 画像より少ない

        with patch.object(service, "annotationError") as mock_signal:
            service.start_annotation(images, phash_list, ["model1"])

            mock_signal.emit.assert_called_once_with("画像とpHashの数が一致しません。")

    def test_start_annotation_empty_models(self):
        """空のモデルリストでアノテーションを開始した場合のテスト"""
        service = AnnotationService()
        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]

        with patch.object(service, "annotationError") as mock_signal:
            service.start_annotation(images, phash_list, [])

            mock_signal.emit.assert_called_once_with("モデルが選択されていません。")

    def test_start_annotation_already_running(self):
        """既に処理が実行中の場合のテスト"""
        service = AnnotationService()
        service._controller = Mock()  # 既存のコントローラーがある状態

        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]
        models = ["model1"]

        with patch.object(service, "annotationError") as mock_signal:
            service.start_annotation(images, phash_list, models)
            mock_signal.emit.assert_called_once_with("アノテーション処理が既に実行中です。")

    @patch("lorairo.services.annotation_service.Controller")
    def test_start_annotation_success(self, mock_controller_class):
        """正常なアノテーション開始のテスト"""
        # Arrange
        service = AnnotationService()
        images = [Mock(spec=Image.Image)]
        phash_list = ["hash1"]
        models = ["model1"]

        mock_controller = Mock()
        mock_worker = Mock()
        mock_controller.worker = mock_worker
        mock_controller_class.return_value = mock_controller

        # Act
        service.start_annotation(images, phash_list, models)

        # Assert
        mock_controller_class.assert_called_once()
        mock_controller.start_process.assert_called_once()
        # ワーカーのシグナルが接続されることを確認
        mock_worker.finished.connect.assert_called()
        mock_worker.error_occurred.connect.assert_called()

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

    def test_cancel_annotation_no_controller(self):
        """コントローラーがない状態でキャンセルを試行した場合のテスト"""
        service = AnnotationService()

        with patch("lorairo.services.annotation_service.logger") as mock_logger:
            service.cancel_annotation()
            mock_logger.info.assert_called_once_with(
                "AnnotationService: キャンセル対象のアノテーション処理はありません。"
            )

    def test_cancel_annotation_with_controller(self):
        """コントローラーがある状態でキャンセルを試行した場合のテスト"""
        service = AnnotationService()
        mock_controller = Mock()
        mock_worker = Mock()
        mock_controller.worker = mock_worker
        service._controller = mock_controller

        service.cancel_annotation()

        mock_worker.cancel.assert_called_once()

    def test_handle_annotation_finished(self):
        """アノテーション完了時の処理テスト"""
        service = AnnotationService()
        test_result = {"test": "result"}
        service._annotation_result = test_result

        with patch.object(service, "annotationFinished") as mock_signal, \
             patch.object(service, "_reset_controller") as mock_reset:
            service._handle_annotation_finished()
            
            mock_signal.emit.assert_called_once_with(test_result)
            mock_reset.assert_called_once()

    def test_handle_annotation_error(self):
        """アノテーションエラー時の処理テスト"""
        service = AnnotationService()
        error_message = "Test error"

        with patch.object(service, "annotationError") as mock_signal, \
             patch.object(service, "_reset_controller") as mock_reset:
            service._handle_annotation_error(error_message)
            
            mock_signal.emit.assert_called_once_with(error_message)
            mock_reset.assert_called_once()

    def test_reset_controller(self):
        """コントローラーのリセットテスト"""
        service = AnnotationService()
        service._controller = Mock()
        service._annotation_result = {"test": "result"}

        service._reset_controller()

        assert service._controller is None
        assert service._annotation_result is None
