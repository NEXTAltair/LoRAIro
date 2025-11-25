"""ErrorDetailDialog単体テスト

このモジュールはErrorDetailDialogの単体テストを提供します。
"""

import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from lorairo.database.schema import ErrorRecord
from lorairo.gui.widgets.error_detail_dialog import ErrorDetailDialog


@pytest.fixture
def mock_db_manager():
    """Mock ImageDatabaseManager"""
    db_manager = Mock()
    db_manager.repository = Mock()
    return db_manager


@pytest.fixture
def sample_error_record():
    """Sample ErrorRecord for testing"""
    return ErrorRecord(
        id=1,
        operation_type="annotation",
        error_type="APIError",
        error_message="Test error message for unit testing",
        file_path="/path/to/test_image.jpg",
        model_name="test-model-v1",
        retry_count=2,
        resolved_at=None,
        created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        stack_trace="Traceback (most recent call last):\n  File test.py, line 10\n    raise APIError()",
    )


@pytest.fixture
def resolved_error_record():
    """Resolved ErrorRecord for testing"""
    return ErrorRecord(
        id=2,
        operation_type="processing",
        error_type="FileIOError",
        error_message="File not accessible",
        file_path="/path/to/missing.jpg",
        model_name=None,
        retry_count=0,
        resolved_at=datetime.datetime(2025, 11, 24, 13, 0, 0),
        created_at=datetime.datetime(2025, 11, 24, 12, 30, 0),
        stack_trace=None,
    )


class TestErrorDetailDialogInitialization:
    """ErrorDetailDialog初期化テスト"""

    def test_dialog_initialization_with_valid_record(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """有効なエラーレコードでの初期化テスト"""
        # Mock準備
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        # Dialog作成
        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # 検証
        assert dialog.error_id == 1
        assert dialog.error_record == sample_error_record
        assert dialog.was_resolved is False

        # UI要素確認
        assert dialog.lineEditOperationType.text() == "annotation"
        assert dialog.lineEditErrorType.text() == "APIError"
        assert "Test error message" in dialog.textEditErrorMessage.toPlainText()

    def test_dialog_initialization_with_nonexistent_record(
        self, qtbot, mock_db_manager
    ):
        """存在しないエラーレコードでの初期化テスト"""
        # Mock準備（空リスト）
        mock_db_manager.repository.get_error_records.return_value = []

        # QMessageBox.critical() と reject() をモック
        with (
            patch.object(QMessageBox, "critical") as mock_critical,
            patch.object(ErrorDetailDialog, "reject") as mock_reject,
        ):
            dialog = ErrorDetailDialog(mock_db_manager, error_id=999)
            qtbot.addWidget(dialog)

            # エラーメッセージ表示確認
            mock_critical.assert_called_once()
            mock_reject.assert_called_once()


class TestErrorDetailDialogUIUpdate:
    """ErrorDetailDialog UI更新テスト"""

    def test_update_ui_with_unresolved_error(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """未解決エラーのUI更新テスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # 基本情報確認
        assert dialog.lineEditOperationType.text() == "annotation"
        assert dialog.lineEditErrorType.text() == "APIError"
        assert dialog.lineEditFilePath.text() == "/path/to/test_image.jpg"
        assert dialog.lineEditModelName.text() == "test-model-v1"
        assert dialog.lineEditRetryCount.text() == "2"
        assert dialog.lineEditResolvedAt.text() == "未解決"

        # 解決マークボタン有効確認
        assert dialog.buttonMarkResolved.isEnabled()

        # スタックトレース確認
        assert "Traceback" in dialog.textEditStackTrace.toPlainText()

    def test_update_ui_with_resolved_error(
        self, qtbot, mock_db_manager, resolved_error_record
    ):
        """解決済みエラーのUI更新テスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            resolved_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=2)
        qtbot.addWidget(dialog)

        # 解決日時確認
        assert dialog.lineEditResolvedAt.text() == "2025-11-24 13:00:00"

        # 解決マークボタン無効確認
        assert not dialog.buttonMarkResolved.isEnabled()

        # モデル名がNoneの場合
        assert dialog.lineEditModelName.text() == "N/A"

        # スタックトレースなしの場合
        assert "スタックトレースなし" in dialog.textEditStackTrace.toPlainText()


class TestErrorDetailDialogActions:
    """ErrorDetailDialogアクションテスト"""

    def test_mark_resolved_button_success(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """解決マークボタン成功テスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # QMessageBox.question() と QMessageBox.information() をモック
        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(QMessageBox, "information"),
            patch.object(dialog, "accept") as mock_accept,
        ):
            dialog._on_mark_resolved_clicked()

            # Repository API呼び出し確認
            mock_db_manager.repository.mark_error_resolved.assert_called_once_with(1)

            # was_resolved フラグ確認
            assert dialog.was_resolved is True

            # Dialog accept() 呼び出し確認
            mock_accept.assert_called_once()

    def test_mark_resolved_button_cancel(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """解決マークボタンキャンセルテスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # QMessageBox.question() で No を返す
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ):
            dialog._on_mark_resolved_clicked()

            # Repository API呼び出しなし
            mock_db_manager.repository.mark_error_resolved.assert_not_called()

            # was_resolved フラグ確認（変更なし）
            assert dialog.was_resolved is False

    def test_mark_resolved_button_error(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """解決マークボタンエラーテスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # Repository API でエラー発生
        mock_db_manager.repository.mark_error_resolved.side_effect = Exception(
            "Test error"
        )

        # QMessageBox.question() と QMessageBox.critical() をモック
        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(QMessageBox, "critical") as mock_critical,
        ):
            dialog._on_mark_resolved_clicked()

            # エラーメッセージ表示確認
            mock_critical.assert_called_once()

            # was_resolved フラグ確認（変更なし）
            assert dialog.was_resolved is False


class TestErrorDetailDialogImagePreview:
    """ErrorDetailDialog画像プレビューテスト"""

    def test_load_image_preview_no_file_path(
        self, qtbot, mock_db_manager
    ):
        """ファイルパスなしの画像プレビューテスト"""
        record_without_path = ErrorRecord(
            id=3,
            operation_type="test",
            error_type="TestError",
            error_message="No file path",
            file_path=None,
            model_name=None,
            retry_count=0,
            resolved_at=None,
            created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        )

        mock_db_manager.repository.get_error_records.return_value = [
            record_without_path
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=3)
        qtbot.addWidget(dialog)

        # 画像プレビューラベルのテキスト確認
        assert "画像パスが設定されていません" in dialog.labelImagePreview.text()

    def test_load_image_preview_file_not_found(
        self, qtbot, mock_db_manager, sample_error_record
    ):
        """ファイルが見つからない場合の画像プレビューテスト"""
        mock_db_manager.repository.get_error_records.return_value = [
            sample_error_record
        ]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # 実際のファイルが存在しないため、エラーメッセージが表示される
        assert "画像ファイルが見つかりません" in dialog.labelImagePreview.text()
