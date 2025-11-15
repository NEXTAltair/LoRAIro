"""ResultHandlerServiceの単体テスト

Phase 2.4 Stage 2で作成されたResultHandlerServiceのテスト。
MainWindowの結果ハンドラメソッドから抽出された結果処理ロジックを検証。
"""

from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtCore import Signal

from lorairo.gui.services.result_handler_service import ResultHandlerService


@pytest.fixture
def mock_parent():
    """親ウィジェットのモック"""
    parent = Mock()
    return parent


@pytest.fixture
def mock_status_bar():
    """ステータスバーのモック"""
    status_bar = Mock()
    status_bar.clearMessage = Mock()
    status_bar.showMessage = Mock()
    return status_bar


@pytest.fixture
def service(mock_parent):
    """ResultHandlerServiceインスタンス"""
    return ResultHandlerService(parent=mock_parent)


@pytest.mark.gui
class TestResultHandlerServiceInit:
    """初期化テスト"""

    def test_init_with_parent(self, mock_parent):
        """正常な初期化（parent有り）"""
        service = ResultHandlerService(parent=mock_parent)
        assert service.parent is mock_parent

    def test_init_without_parent(self):
        """parent無しの初期化"""
        service = ResultHandlerService(parent=None)
        assert service.parent is None


@pytest.mark.gui
class TestHandleBatchRegistrationFinished:
    """handle_batch_registration_finished()テスト"""

    def test_handle_registration_success(self, service, mock_status_bar):
        """正常なバッチ登録完了"""
        # Setup - DatabaseRegistrationResult
        result = Mock()
        result.registered_count = 100
        result.skipped_count = 10
        result.error_count = 5
        result.total_processing_time = 12.5

        completion_signal = Mock()
        completion_signal.emit = Mock()

        # Execute
        service.handle_batch_registration_finished(
            result, status_bar=mock_status_bar, completion_signal=completion_signal
        )

        # Assert
        mock_status_bar.clearMessage.assert_called_once()
        mock_status_bar.showMessage.assert_called_once()
        assert "登録=100" in mock_status_bar.showMessage.call_args[0][0]
        assert "スキップ=10" in mock_status_bar.showMessage.call_args[0][0]
        completion_signal.emit.assert_called_once_with(100)

    def test_handle_registration_without_status_bar(self, service):
        """ステータスバー無し"""
        result = Mock()
        result.registered_count = 100
        result.skipped_count = 10
        result.error_count = 5
        result.total_processing_time = 12.5

        # Execute - エラーなく完了すること
        service.handle_batch_registration_finished(result, status_bar=None)

    def test_handle_registration_unexpected_format(self, service, mock_status_bar):
        """予期しない結果フォーマット"""
        # Setup - registered_count属性なし
        result = Mock(spec=[])

        # Execute
        service.handle_batch_registration_finished(result, status_bar=mock_status_bar)

        # Assert - フォールバックメッセージ
        mock_status_bar.showMessage.assert_called_once()
        assert "詳細情報取得不可" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_registration_error(self, service, mock_status_bar):
        """結果処理中のエラー"""
        # Setup - registered_countアクセス時にエラー
        result = Mock()
        result.registered_count = Mock(side_effect=RuntimeError("Test error"))

        # Execute
        service.handle_batch_registration_finished(result, status_bar=mock_status_bar)

        # Assert - エラーメッセージ表示
        mock_status_bar.showMessage.assert_called()


@pytest.mark.gui
class TestHandleBatchAnnotationFinished:
    """handle_batch_annotation_finished()テスト"""

    def test_handle_annotation_all_success(self, mock_status_bar):
        """全画像成功"""
        # Setup - parent=Noneでテスト（QMessageBox表示回避）
        service = ResultHandlerService(parent=None)
        result = Mock()
        result.total_images = 50
        result.successful_annotations = 50
        result.failed_annotations = 0
        result.success_rate = 100.0
        result.summary = "50枚完了"

        # Execute
        service.handle_batch_annotation_finished(result, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "50件成功" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_annotation_partial_failure(self, mock_status_bar):
        """一部失敗"""
        # Setup - parent=Noneでテスト（QMessageBox表示回避）
        service = ResultHandlerService(parent=None)
        result = Mock()
        result.total_images = 50
        result.successful_annotations = 45
        result.failed_annotations = 5
        result.success_rate = 90.0
        result.summary = "45/50完了"

        # Execute
        service.handle_batch_annotation_finished(result, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "45件成功" in mock_status_bar.showMessage.call_args[0][0]
        assert "5件失敗" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_annotation_without_parent(self, mock_status_bar):
        """parent無しの場合（QMessageBox表示しない）"""
        # Setup
        service = ResultHandlerService(parent=None)
        result = Mock()
        result.total_images = 50
        result.successful_annotations = 50
        result.failed_annotations = 0
        result.success_rate = 100.0
        result.summary = "完了"

        # Execute - エラーなく完了すること
        service.handle_batch_annotation_finished(result, status_bar=mock_status_bar)

    def test_handle_annotation_error(self, mock_status_bar):
        """結果処理中のエラー"""
        # Setup - parent=Noneでテスト（QMessageBox表示回避）
        service = ResultHandlerService(parent=None)
        result = Mock()
        result.total_images = Mock(side_effect=RuntimeError("Test error"))

        # Execute - エラーなく完了すること
        service.handle_batch_annotation_finished(result, status_bar=mock_status_bar)


@pytest.mark.gui
class TestHandleAnnotationFinished:
    """handle_annotation_finished()テスト"""

    def test_handle_annotation_finished(self, service, mock_status_bar):
        """正常な単発アノテーション完了"""
        result = {"status": "success"}

        # Execute
        service.handle_annotation_finished(result, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "完了" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_annotation_finished_without_status_bar(self, service):
        """ステータスバー無し"""
        result = {"status": "success"}

        # Execute - エラーなく完了すること
        service.handle_annotation_finished(result, status_bar=None)


@pytest.mark.gui
class TestHandleAnnotationError:
    """handle_annotation_error()テスト"""

    def test_handle_annotation_error(self, mock_status_bar):
        """アノテーションエラー処理"""
        # Setup - parent=Noneでテスト（QMessageBox表示回避）
        service = ResultHandlerService(parent=None)
        error_msg = "API key invalid"

        # Execute
        service.handle_annotation_error(error_msg, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "API key invalid" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_annotation_error_without_parent(self, mock_status_bar):
        """parent無しの場合（QMessageBox表示しない）"""
        service = ResultHandlerService(parent=None)
        error_msg = "Test error"

        # Execute - エラーなく完了すること
        service.handle_annotation_error(error_msg, status_bar=mock_status_bar)


@pytest.mark.gui
class TestHandleModelSyncCompleted:
    """handle_model_sync_completed()テスト"""

    def test_handle_sync_success(self, service, mock_status_bar):
        """モデル同期成功"""
        # Setup
        sync_result = Mock()
        sync_result.success = True
        sync_result.summary = "3モデル同期完了"

        # Execute
        service.handle_model_sync_completed(sync_result, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "3モデル同期完了" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_sync_failure(self, service, mock_status_bar):
        """モデル同期失敗"""
        # Setup
        sync_result = Mock()
        sync_result.success = False
        sync_result.errors = ["Error 1", "Error 2"]

        # Execute
        service.handle_model_sync_completed(sync_result, status_bar=mock_status_bar)

        # Assert
        mock_status_bar.showMessage.assert_called_once()
        assert "Error 1" in mock_status_bar.showMessage.call_args[0][0]

    def test_handle_sync_without_status_bar(self, service):
        """ステータスバー無し"""
        sync_result = Mock()
        sync_result.success = True

        # Execute - エラーなく完了すること
        service.handle_model_sync_completed(sync_result, status_bar=None)
