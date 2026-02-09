"""ErrorLogViewerWidget単体テスト

このモジュールはErrorLogViewerWidgetの単体テストを提供します。
"""

import datetime
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from lorairo.database.schema import ErrorRecord
from lorairo.gui.widgets.error_log_viewer_widget import ErrorLogViewerWidget


@pytest.fixture
def mock_db_manager():
    """Mock ImageDatabaseManager"""
    db_manager = Mock()
    db_manager.repository = Mock()
    return db_manager


@pytest.fixture
def error_log_viewer_widget(qtbot, mock_db_manager):
    """ErrorLogViewerWidget fixture"""
    widget = ErrorLogViewerWidget()
    widget.set_db_manager(mock_db_manager)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def sample_error_record():
    """Sample ErrorRecord for testing"""
    return ErrorRecord(
        id=1,
        operation_type="annotation",
        error_type="APIError",
        error_message="Test error message",
        file_path="/path/to/image.jpg",
        model_name="test-model",
        retry_count=0,
        resolved_at=None,
        created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
    )


class TestErrorLogViewerWidgetInitialization:
    """ErrorLogViewerWidget初期化テスト"""

    def test_widget_initialization(self, error_log_viewer_widget):
        """Widget初期化テスト"""
        assert error_log_viewer_widget.db_manager is not None
        assert error_log_viewer_widget.current_page == 1
        assert error_log_viewer_widget.page_size == 100
        assert error_log_viewer_widget.total_pages == 0
        assert error_log_viewer_widget.current_error_records == []

    def test_set_db_manager(self, qtbot, mock_db_manager):
        """set_db_manager()テスト"""
        widget = ErrorLogViewerWidget()
        qtbot.addWidget(widget)

        assert widget.db_manager is None

        widget.set_db_manager(mock_db_manager)

        assert widget.db_manager == mock_db_manager

    def test_table_properties_setup(self, error_log_viewer_widget):
        """テーブルプロパティ設定テスト"""
        # IDカラムが非表示であることを確認
        assert error_log_viewer_widget.tableWidgetErrors.isColumnHidden(0)

        # カラム数確認
        assert error_log_viewer_widget.tableWidgetErrors.columnCount() == 8


class TestErrorLogViewerWidgetDataLoading:
    """ErrorLogViewerWidgetデータ読み込みテスト"""

    def test_load_error_records_success(
        self, error_log_viewer_widget, mock_db_manager, sample_error_record
    ):
        """エラーレコード読み込み成功テスト"""
        # Mock データ準備
        mock_records = [sample_error_record]
        mock_db_manager.repository.get_error_records.return_value = mock_records
        mock_db_manager.repository.get_error_count_unresolved.return_value = 1

        # 実行
        error_log_viewer_widget.load_error_records()

        # 検証
        assert error_log_viewer_widget.tableWidgetErrors.rowCount() == 1
        assert error_log_viewer_widget.current_error_records == mock_records
        assert error_log_viewer_widget.total_pages == 1

        # Repository API呼び出し確認
        mock_db_manager.repository.get_error_records.assert_called_once()
        mock_db_manager.repository.get_error_count_unresolved.assert_called_once()

    def test_load_error_records_no_db_manager(self, qtbot):
        """db_manager未設定時のエラーレコード読み込みテスト"""
        widget = ErrorLogViewerWidget()
        qtbot.addWidget(widget)

        # db_manager未設定
        assert widget.db_manager is None

        # QMessageBox.warning() をモック
        with patch.object(QMessageBox, "warning") as mock_warning:
            widget.load_error_records()
            mock_warning.assert_called_once()

    def test_load_error_records_with_operation_type_filter(
        self, error_log_viewer_widget, mock_db_manager, sample_error_record
    ):
        """操作種別フィルタ付きエラーレコード読み込みテスト"""
        # 操作種別選択
        error_log_viewer_widget.comboOperationType.setCurrentText("annotation")

        mock_db_manager.repository.get_error_records.return_value = [sample_error_record]
        mock_db_manager.repository.get_error_count_unresolved.return_value = 1

        # 実行
        error_log_viewer_widget.load_error_records()

        # Repository API呼び出し確認（operation_type="annotation"）
        call_args = mock_db_manager.repository.get_error_records.call_args
        assert call_args.kwargs["operation_type"] == "annotation"

    def test_load_error_records_with_show_resolved(
        self, error_log_viewer_widget, mock_db_manager, sample_error_record
    ):
        """解決済み表示付きエラーレコード読み込みテスト"""
        # 解決済み表示チェック
        error_log_viewer_widget.checkBoxShowResolved.setChecked(True)

        mock_db_manager.repository.get_error_records.return_value = [sample_error_record]

        # 実行
        error_log_viewer_widget.load_error_records()

        # Repository API呼び出し確認（resolved=None）
        call_args = mock_db_manager.repository.get_error_records.call_args
        assert call_args.kwargs["resolved"] is None


class TestErrorLogViewerWidgetPagination:
    """ErrorLogViewerWidgetページネーションテスト"""

    def test_pagination_next_page(self, error_log_viewer_widget, mock_db_manager, sample_error_record):
        """次ページボタンテスト"""
        # 初期状態：1ページ目
        assert error_log_viewer_widget.current_page == 1

        # total_pages設定
        error_log_viewer_widget.total_pages = 3
        error_log_viewer_widget._update_page_info()

        # Mock準備
        mock_db_manager.repository.get_error_records.return_value = [sample_error_record]
        mock_db_manager.repository.get_error_count_unresolved.return_value = 250

        # 次ページクリック
        error_log_viewer_widget.buttonNextPage.click()

        # 2ページ目に移動
        assert error_log_viewer_widget.current_page == 2

    def test_pagination_previous_page(self, error_log_viewer_widget, mock_db_manager, sample_error_record):
        """前ページボタンテスト"""
        # 2ページ目に設定
        error_log_viewer_widget.current_page = 2
        error_log_viewer_widget.total_pages = 3
        error_log_viewer_widget._update_page_info()

        # Mock準備
        mock_db_manager.repository.get_error_records.return_value = [sample_error_record]
        mock_db_manager.repository.get_error_count_unresolved.return_value = 250

        # 前ページクリック
        error_log_viewer_widget.buttonPreviousPage.click()

        # 1ページ目に移動
        assert error_log_viewer_widget.current_page == 1

    def test_page_size_change(self, error_log_viewer_widget, mock_db_manager, sample_error_record):
        """ページサイズ変更テスト"""
        # 初期page_size
        assert error_log_viewer_widget.page_size == 100

        # Mock準備
        mock_db_manager.repository.get_error_records.return_value = [sample_error_record]
        mock_db_manager.repository.get_error_count_unresolved.return_value = 50

        # ページサイズ変更
        error_log_viewer_widget.spinBoxPageSize.setValue(50)

        # page_sizeが更新され、1ページ目に戻ることを確認
        assert error_log_viewer_widget.page_size == 50
        assert error_log_viewer_widget.current_page == 1


class TestErrorLogViewerWidgetActions:
    """ErrorLogViewerWidgetアクションテスト"""

    def test_mark_resolved_button_no_selection(self, error_log_viewer_widget):
        """選択なしで解決マークボタンクリックテスト"""
        # 選択なし
        assert error_log_viewer_widget.tableWidgetErrors.currentRow() == -1

        # QMessageBox.warning() をモック
        with patch.object(QMessageBox, "warning") as mock_warning:
            error_log_viewer_widget._on_mark_resolved_clicked()
            mock_warning.assert_called_once()

    def test_view_details_button_no_selection(self, error_log_viewer_widget):
        """選択なしで詳細表示ボタンクリックテスト"""
        # 選択なし
        assert error_log_viewer_widget.tableWidgetErrors.currentRow() == -1

        # QMessageBox.warning() をモック
        with patch.object(QMessageBox, "warning") as mock_warning:
            error_log_viewer_widget._on_view_details_clicked()
            mock_warning.assert_called_once()

    def test_export_log_empty_records_shows_warning(self, error_log_viewer_widget):
        """エクスポート: レコードなしで警告表示"""
        error_log_viewer_widget.current_error_records = []
        with patch.object(QMessageBox, "warning") as mock_warning:
            error_log_viewer_widget._on_export_log_clicked()
            mock_warning.assert_called_once()

    def test_export_log_success(self, error_log_viewer_widget, sample_error_record, tmp_path):
        """エクスポート: CSV保存成功"""
        error_log_viewer_widget.current_error_records = [sample_error_record]
        export_path = str(tmp_path / "export.csv")

        with (
            patch.object(QFileDialog, "getSaveFileName", return_value=(export_path, "")),
            patch.object(QMessageBox, "information") as mock_info,
        ):
            error_log_viewer_widget._on_export_log_clicked()
            mock_info.assert_called_once()

        # CSV ファイルが作成されたことを確認
        assert (tmp_path / "export.csv").exists()

    def test_export_log_cancel(self, error_log_viewer_widget, sample_error_record):
        """エクスポート: ファイルダイアログキャンセル"""
        error_log_viewer_widget.current_error_records = [sample_error_record]

        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            # キャンセル時はQMessageBoxが呼ばれない
            error_log_viewer_widget._on_export_log_clicked()


class TestErrorLogViewerWidgetTableDisplay:
    """ErrorLogViewerWidgetテーブル表示テスト"""

    def test_update_table_display(self, error_log_viewer_widget, sample_error_record):
        """テーブル表示更新テスト"""
        # 複数レコード
        records = [sample_error_record]

        # テーブル表示更新
        error_log_viewer_widget._update_table_display(records)

        # 行数確認
        assert error_log_viewer_widget.tableWidgetErrors.rowCount() == 1

        # データ確認（1行目）
        assert error_log_viewer_widget.tableWidgetErrors.item(0, 1).text() == "2025-11-24 12:00:00"
        assert error_log_viewer_widget.tableWidgetErrors.item(0, 2).text() == "annotation"
        assert error_log_viewer_widget.tableWidgetErrors.item(0, 3).text() == "APIError"
        assert error_log_viewer_widget.tableWidgetErrors.item(0, 4).text() == "Test error message"

    def test_update_table_display_with_resolved_error(self, error_log_viewer_widget):
        """解決済みエラーのテーブル表示テスト"""
        resolved_record = ErrorRecord(
            id=2,
            operation_type="registration",
            error_type="FileIOError",
            error_message="File not found",
            file_path="/path/to/missing.jpg",
            model_name=None,
            retry_count=1,
            resolved_at=datetime.datetime(2025, 11, 24, 13, 0, 0),
            created_at=datetime.datetime(2025, 11, 24, 12, 0, 0),
        )

        # テーブル表示更新
        error_log_viewer_widget._update_table_display([resolved_record])

        # 状態カラム確認（解決済み）
        assert error_log_viewer_widget.tableWidgetErrors.item(0, 7).text() == "解決済み"
