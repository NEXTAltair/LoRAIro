# tests/unit/gui/workers/test_progress_manager.py

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QProgressDialog, QWidget

from lorairo.gui.workers.base import SimpleWorkerBase, WorkerProgress
from lorairo.gui.workers.progress_manager import ProgressManager


class MockWorker(SimpleWorkerBase[str]):
    """テスト用モックワーカー"""

    def __init__(self, duration: float = 0.05, result: str = "test_result"):
        super().__init__()
        self.duration = duration
        self.result = result
        self.execute_called = False

    def execute(self) -> str:
        """テスト用実行メソッド"""
        self.execute_called = True

        # 短い進捗報告
        for i in range(3):
            if self.cancellation.is_canceled():
                return "canceled"

            progress = int((i + 1) * 33.33)
            self._report_progress(progress, f"ステップ {i + 1}")
            time.sleep(self.duration / 3)

        return self.result


class TestProgressManager:
    """ProgressManager のユニットテスト"""

    @pytest.fixture
    def parent_widget(self):
        """テスト用親ウィジェット"""
        widget = QWidget()
        yield widget
        widget.close()

    @pytest.fixture
    def progress_manager(self, parent_widget):
        """テスト用ProgressManager"""
        return ProgressManager(parent_widget)

    @pytest.fixture
    def mock_worker(self):
        """テスト用モックワーカー"""
        return MockWorker()

    def test_initialization(self, progress_manager, parent_widget):
        """初期化テスト"""
        assert progress_manager.parent == parent_widget
        assert progress_manager.progress_dialog is None
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_initialization_without_parent(self):
        """親なし初期化テスト"""
        manager = ProgressManager()
        assert manager.parent is None
        assert manager.progress_dialog is None
        assert manager.current_worker is None
        assert manager.current_thread is None

    @patch("lorairo.gui.workers.progress_manager.QProgressDialog")
    @patch("lorairo.gui.workers.progress_manager.QThread")
    def test_start_worker_setup(self, mock_thread_class, mock_dialog_class, progress_manager, mock_worker):
        """ワーカー開始セットアップテスト"""
        # モックインスタンス設定
        mock_dialog = Mock()
        mock_thread = Mock()
        mock_dialog_class.return_value = mock_dialog
        mock_thread_class.return_value = mock_thread

        # moveToThread メソッドをモック化
        mock_worker.moveToThread = Mock()

        # ワーカー開始
        progress_manager.start_worker_with_progress(mock_worker, "テストタスク", 100)

        # プログレスダイアログ作成確認
        mock_dialog_class.assert_called_once_with(
            "テストタスク", "キャンセル", 0, 100, progress_manager.parent
        )
        mock_dialog.setWindowModality.assert_called_once()
        mock_dialog.setAutoClose.assert_called_once_with(True)
        mock_dialog.setAutoReset.assert_called_once_with(True)

        # スレッド作成・設定確認
        mock_thread_class.assert_called_once()
        mock_worker.moveToThread.assert_called_once_with(mock_thread)

        # シグナル接続確認（接続されているかどうかをテスト）
        # Note: Mock objects don't track signal connections, so we check if methods are callable
        assert hasattr(mock_worker, "progress_updated")
        assert hasattr(mock_worker, "finished")
        assert hasattr(mock_worker, "error_occurred")

        # スレッド開始確認
        mock_thread.start.assert_called_once()

        # 状態設定確認
        assert progress_manager.current_worker == mock_worker
        assert progress_manager.current_thread == mock_thread
        assert progress_manager.progress_dialog == mock_dialog

    def test_update_progress_basic(self, progress_manager):
        """基本進捗更新テスト"""
        # モックダイアログ設定
        mock_dialog = Mock()
        progress_manager.progress_dialog = mock_dialog

        # 進捗情報作成
        progress = WorkerProgress(
            percentage=50,
            status_message="処理中",
        )

        # 進捗更新
        progress_manager._update_progress(progress)

        # ダイアログ更新確認
        mock_dialog.setValue.assert_called_once_with(50)
        mock_dialog.setLabelText.assert_called_with("処理中")

    def test_update_progress_with_details(self, progress_manager):
        """詳細付き進捗更新テスト"""
        # モックダイアログ設定
        mock_dialog = Mock()
        progress_manager.progress_dialog = mock_dialog

        # 詳細情報付き進捗情報作成
        progress = WorkerProgress(
            percentage=75,
            status_message="ファイル処理中",
            current_item="test_image.jpg",
            processed_count=3,
            total_count=4,
        )

        # 進捗更新
        progress_manager._update_progress(progress)

        # ダイアログ更新確認
        mock_dialog.setValue.assert_called_once_with(75)

        # 詳細メッセージの確認
        call_args = mock_dialog.setLabelText.call_args_list
        assert len(call_args) == 2  # 基本メッセージと詳細メッセージ

        # 最後の呼び出しで詳細情報が含まれているか確認
        final_message = call_args[-1][0][0]
        assert "ファイル処理中" in final_message
        assert "test_image.jpg" in final_message
        assert "3/4" in final_message

    def test_update_progress_no_dialog(self, progress_manager):
        """ダイアログなし進捗更新テスト"""
        # ダイアログがない状態
        progress_manager.progress_dialog = None

        # 進捗情報作成
        progress = WorkerProgress(50, "処理中")

        # 例外が発生しないことを確認
        progress_manager._update_progress(progress)  # No exception should occur

    def test_on_finished(self, progress_manager):
        """完了処理テスト"""
        # モックダイアログ・スレッド設定
        mock_dialog = Mock()
        mock_thread = Mock()
        mock_worker = Mock()

        progress_manager.progress_dialog = mock_dialog
        progress_manager.current_thread = mock_thread
        progress_manager.current_worker = mock_worker

        # 完了処理実行
        progress_manager._on_finished("test_result")

        # ダイアログクローズ確認
        mock_dialog.close.assert_called_once()
        assert progress_manager.progress_dialog is None

        # スレッドクリーンアップ確認
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_on_error(self, progress_manager):
        """エラー処理テスト"""
        # モックダイアログ・スレッド設定
        mock_dialog = Mock()
        mock_thread = Mock()
        mock_worker = Mock()

        progress_manager.progress_dialog = mock_dialog
        progress_manager.current_thread = mock_thread
        progress_manager.current_worker = mock_worker

        # エラー処理実行
        progress_manager._on_error("テストエラー")

        # ダイアログクローズ確認
        mock_dialog.close.assert_called_once()
        assert progress_manager.progress_dialog is None

        # スレッドクリーンアップ確認
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_cleanup_thread_running(self, progress_manager):
        """実行中スレッドクリーンアップテスト"""
        # モック実行中スレッド設定
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        mock_worker = Mock()

        progress_manager.current_thread = mock_thread
        progress_manager.current_worker = mock_worker

        # クリーンアップ実行
        progress_manager._cleanup_thread()

        # スレッド終了処理確認
        mock_thread.quit.assert_called_once()
        mock_thread.wait.assert_called_once()

        # 状態クリア確認
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_cleanup_thread_not_running(self, progress_manager):
        """停止中スレッドクリーンアップテスト"""
        # モック停止中スレッド設定
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        mock_worker = Mock()

        progress_manager.current_thread = mock_thread
        progress_manager.current_worker = mock_worker

        # クリーンアップ実行
        progress_manager._cleanup_thread()

        # quit/waitが呼ばれないことを確認
        mock_thread.quit.assert_not_called()
        mock_thread.wait.assert_not_called()

        # 状態クリア確認
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_cleanup_thread_no_thread(self, progress_manager):
        """スレッドなしクリーンアップテスト"""
        # スレッドなし状態
        mock_worker = Mock()
        progress_manager.current_worker = mock_worker
        progress_manager.current_thread = None

        # クリーンアップ実行（例外が発生しないことを確認）
        progress_manager._cleanup_thread()

        # ワーカーのみクリア確認
        assert progress_manager.current_worker is None
        assert progress_manager.current_thread is None

    def test_is_active_true(self, progress_manager):
        """アクティブ状態確認テスト（True）"""
        # アクティブ状態設定
        progress_manager.progress_dialog = Mock()
        progress_manager.current_worker = Mock()

        assert progress_manager.is_active() is True

    def test_is_active_false_no_dialog(self, progress_manager):
        """アクティブ状態確認テスト（False - ダイアログなし）"""
        # ダイアログなし状態
        progress_manager.progress_dialog = None
        progress_manager.current_worker = Mock()

        assert progress_manager.is_active() is False

    def test_is_active_false_no_worker(self, progress_manager):
        """アクティブ状態確認テスト（False - ワーカーなし）"""
        # ワーカーなし状態
        progress_manager.progress_dialog = Mock()
        progress_manager.current_worker = None

        assert progress_manager.is_active() is False

    def test_is_active_false_both_none(self, progress_manager):
        """アクティブ状態確認テスト（False - 両方なし）"""
        # 両方なし状態
        progress_manager.progress_dialog = None
        progress_manager.current_worker = None

        assert progress_manager.is_active() is False

    def test_cancel_current_worker(self, progress_manager):
        """現在ワーカーキャンセルテスト"""
        # モックワーカー設定
        mock_worker = Mock()
        progress_manager.current_worker = mock_worker

        # キャンセル実行
        progress_manager.cancel_current_worker()

        # ワーカーキャンセル確認
        mock_worker.cancel.assert_called_once()

    def test_cancel_current_worker_no_worker(self, progress_manager):
        """ワーカーなしキャンセルテスト"""
        # ワーカーなし状態
        progress_manager.current_worker = None

        # キャンセル実行（例外が発生しないことを確認）
        progress_manager.cancel_current_worker()  # No exception should occur
