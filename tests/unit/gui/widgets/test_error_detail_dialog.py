"""ErrorDetailDialog単体テスト

このモジュールはErrorDetailDialogの単体テストを提供します。
"""

import datetime
from unittest.mock import Mock

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
        resolved_at=datetime.datetime(2025, 11, 24, 13, 0, 0),
        created_at=datetime.datetime(2025, 11, 24, 12, 30, 0),
        stack_trace=None,
    )


class TestErrorDetailDialogInitialization:
    """ErrorDetailDialog初期化テスト"""

    def test_dialog_initialization_with_valid_record(self, qtbot, mock_db_manager, sample_error_record):
        """有効なエラーレコードでの初期化テスト"""
        # Mock準備
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

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

    def test_dialog_initialization_with_nonexistent_record(self, qtbot, mock_db_manager, monkeypatch):
        """存在しないエラーレコードでの初期化テスト"""
        # Mock準備（空リスト）
        mock_db_manager.error_record_repo.get_error_records.return_value = []

        # QMessageBox.critical は autouse の auto_mock_qmessagebox で既にモック済み
        # reject() はインスタンス作成後にモック不可（__init__中に呼ばれる）ため、
        # エラーレコード未発見時のフロー検証のみ行う
        mock_critical = Mock()
        monkeypatch.setattr(QMessageBox, "critical", mock_critical)

        dialog = ErrorDetailDialog(mock_db_manager, error_id=999)
        qtbot.addWidget(dialog)

        # QMessageBox.critical が呼ばれたことを確認
        mock_critical.assert_called_once()
        # エラーレコードが見つからなかった場合、error_record は None
        assert dialog.error_record is None


class TestErrorDetailDialogUIUpdate:
    """ErrorDetailDialog UI更新テスト"""

    def test_update_ui_with_unresolved_error(self, qtbot, mock_db_manager, sample_error_record):
        """未解決エラーのUI更新テスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # 基本情報確認
        assert dialog.lineEditOperationType.text() == "annotation"
        assert dialog.lineEditErrorType.text() == "APIError"
        assert dialog.lineEditFilePath.text() == "/path/to/test_image.jpg"
        assert dialog.lineEditModelName.text() == "test-model-v1"
        assert dialog.lineEditResolvedAt.text() == "未解決"

        # 解決マークボタン有効確認
        assert dialog.buttonMarkResolved.isEnabled()

        # スタックトレース確認
        assert "Traceback" in dialog.textEditStackTrace.toPlainText()

    def test_update_ui_with_resolved_error(self, qtbot, mock_db_manager, resolved_error_record):
        """解決済みエラーのUI更新テスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [resolved_error_record]

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

    def test_mark_resolved_button_success(self, qtbot, mock_db_manager, sample_error_record, monkeypatch):
        """解決マークボタン成功テスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # QMessageBox をモック（question → Yes、information → Ok）
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        # accept() はインスタンスレベルでモック
        mock_accept = Mock()
        monkeypatch.setattr(dialog, "accept", mock_accept)

        dialog._on_mark_resolved_clicked()

        # Repository API呼び出し確認
        mock_db_manager.error_record_repo.mark_error_resolved.assert_called_once_with(1)

        # was_resolved フラグ確認
        assert dialog.was_resolved is True

        # Dialog accept() 呼び出し確認
        mock_accept.assert_called_once()

    def test_mark_resolved_button_cancel(self, qtbot, mock_db_manager, sample_error_record, monkeypatch):
        """解決マークボタンキャンセルテスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # QMessageBox.question() で No を返す
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)

        dialog._on_mark_resolved_clicked()

        # Repository API呼び出しなし
        mock_db_manager.error_record_repo.mark_error_resolved.assert_not_called()

        # was_resolved フラグ確認（変更なし）
        assert dialog.was_resolved is False

    def test_mark_resolved_button_error(self, qtbot, mock_db_manager, sample_error_record, monkeypatch):
        """解決マークボタンエラーテスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # Repository API でエラー発生
        mock_db_manager.error_record_repo.mark_error_resolved.side_effect = Exception("Test error")

        # QMessageBox をモック（question → Yes、critical を記録）
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
        mock_critical = Mock()
        monkeypatch.setattr(QMessageBox, "critical", mock_critical)

        dialog._on_mark_resolved_clicked()

        # エラーメッセージ表示確認
        mock_critical.assert_called_once()

        # was_resolved フラグ確認（変更なし）
        assert dialog.was_resolved is False


class TestErrorDetailDialogImagePreview:
    """ErrorDetailDialog画像プレビューテスト"""

    def test_load_image_preview_no_file_path(self, qtbot, mock_db_manager):
        """ファイルパスなしの画像プレビューテスト"""
        record_without_path = ErrorRecord(
            id=3,
            operation_type="test",
            error_type="TestError",
            error_message="No file path",
            file_path=None,
            model_name=None,
            resolved_at=None,
            created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        )

        mock_db_manager.error_record_repo.get_error_records.return_value = [record_without_path]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=3)
        qtbot.addWidget(dialog)

        # 画像プレビューラベルのテキスト確認
        assert "画像パスが設定されていません" in dialog.labelImagePreview.text()

    def test_load_image_preview_file_not_found(self, qtbot, mock_db_manager, sample_error_record):
        """ファイルが見つからない場合の画像プレビューテスト"""
        mock_db_manager.error_record_repo.get_error_records.return_value = [sample_error_record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=1)
        qtbot.addWidget(dialog)

        # 実際のファイルが存在しないため、エラーメッセージが表示される
        assert "画像ファイルが見つかりません" in dialog.labelImagePreview.text()
        # #1105: メッセージ表示時は ImagePreviewWidget を隠す
        assert dialog._image_preview.isVisibleTo(dialog) is False
        assert dialog.labelImagePreview.isVisibleTo(dialog) is True

    def test_load_image_preview_delegates_to_image_preview_widget(
        self, qtbot, mock_db_manager, tmp_path, monkeypatch
    ):
        """#1105: デコード可能な実画像は ImagePreviewWidget に委譲し、テキストラベルは隠す。"""
        from pathlib import Path

        from PIL import Image

        from lorairo.gui.widgets.image_preview import ImagePreviewWidget

        image_path = tmp_path / "err.png"
        Image.new("RGB", (8, 8), color=(10, 20, 30)).save(image_path)  # デコード可能な実 PNG

        # ImagePreviewWidget の実描画 (QGraphicsView + 遅延サイズ調整) は本テストの対象外。
        # dialog の委譲判断のみを検証するため load_image を差し替える。
        load_calls: list[Path] = []
        monkeypatch.setattr(ImagePreviewWidget, "load_image", lambda self, p: load_calls.append(p))

        record = ErrorRecord(
            id=7,
            operation_type="test",
            error_type="TestError",
            error_message="delegate",
            file_path=str(image_path),
            model_name=None,
            resolved_at=None,
            created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        )
        mock_db_manager.error_record_repo.get_error_records.return_value = [record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=7)
        qtbot.addWidget(dialog)

        # 実描画は ImagePreviewWidget へ委譲され (load_image 呼び出し)、label は隠れる
        assert load_calls == [image_path]
        assert dialog._image_preview.isVisibleTo(dialog) is True
        assert dialog.labelImagePreview.isVisibleTo(dialog) is False

    def test_load_image_preview_decode_failure_shows_message(self, qtbot, mock_db_manager, tmp_path):
        """#1105 Codex P2: 存在するがデコード不能なファイルはテキストヒントへフォールバックする。"""
        broken_path = tmp_path / "broken.png"
        broken_path.write_bytes(b"not-a-real-image")  # 存在するが画像としてデコード不能
        record = ErrorRecord(
            id=8,
            operation_type="test",
            error_type="TestError",
            error_message="decode fail",
            file_path=str(broken_path),
            model_name=None,
            resolved_at=None,
            created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        )
        mock_db_manager.error_record_repo.get_error_records.return_value = [record]

        dialog = ErrorDetailDialog(mock_db_manager, error_id=8)
        qtbot.addWidget(dialog)

        # 空白プレビューではなく理由を伝えるテキストヒントを出す
        assert "画像を読み込めません" in dialog.labelImagePreview.text()
        assert dialog.labelImagePreview.isVisibleTo(dialog) is True
        assert dialog._image_preview.isVisibleTo(dialog) is False
