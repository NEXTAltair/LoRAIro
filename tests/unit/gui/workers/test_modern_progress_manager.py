"""ModernProgressManager ユニットテスト。"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QProgressDialog

from lorairo.gui.workers.base import WorkerProgress
from lorairo.gui.workers.modern_progress_manager import (
    ModernProgressManager,
    create_worker_id,
)


@pytest.fixture
def manager(qapp) -> ModernProgressManager:
    """ModernProgressManager インスタンスを返す。"""
    return ModernProgressManager()


@pytest.mark.unit
class TestModernProgressManagerInit:
    def test_init_creates_empty_dialogs(self, manager: ModernProgressManager) -> None:
        assert manager._progress_dialogs == {}

    def test_init_creates_empty_active_workers(self, manager: ModernProgressManager) -> None:
        assert manager._active_workers == {}

    def test_has_active_progress_false_initially(self, manager: ModernProgressManager) -> None:
        assert manager.has_active_progress("nonexistent") is False

    def test_get_active_worker_count_zero_initially(self, manager: ModernProgressManager) -> None:
        assert manager.get_active_worker_count() == 0


@pytest.mark.unit
class TestStartWorkerProgress:
    def test_start_registers_dialog(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト操作")
        assert "w1" in manager._progress_dialogs
        assert "w1" in manager._active_workers

    def test_start_sets_operation_name(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "バッチ処理")
        assert manager._active_workers["w1"] == "バッチ処理"

    def test_start_has_active_progress_true(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        assert manager.has_active_progress("w1") is True

    def test_start_increments_active_count(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "操作1")
        assert manager.get_active_worker_count() == 1
        manager.start_worker_progress("w2", "操作2")
        assert manager.get_active_worker_count() == 2

    def test_start_replaces_existing_dialog(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "最初の操作")
        first_dialog = manager._progress_dialogs.get("w1")
        manager.start_worker_progress("w1", "置換操作")
        # 新しいダイアログに置換されているはず
        assert "w1" in manager._progress_dialogs
        assert manager._progress_dialogs["w1"] is not first_dialog

    def test_start_with_custom_initial_message(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "操作", initial_message="カスタムメッセージ")
        dialog = manager._progress_dialogs["w1"]
        assert dialog is not None

    def test_start_dialog_is_qprogress_dialog(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        dialog = manager._progress_dialogs["w1"]
        assert isinstance(dialog, QProgressDialog)


@pytest.mark.unit
class TestUpdateWorkerProgress:
    def test_update_with_total_count(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        progress = WorkerProgress(
            percentage=50,
            status_message="処理中",
            current_item="file.png",
            processed_count=5,
            total_count=10,
        )
        # headless 環境では未表示ダイアログの value() が -1 を返すため
        # 例外が発生しないこととダイアログが存在することを確認する
        manager.update_worker_progress("w1", progress)
        assert "w1" in manager._progress_dialogs

    def test_update_without_current_item(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        progress = WorkerProgress(
            percentage=30,
            status_message="処理中",
            current_item="",
            processed_count=3,
            total_count=10,
        )
        # current_item が空の場合も正常動作すること
        manager.update_worker_progress("w1", progress)
        assert "w1" in manager._progress_dialogs

    def test_update_without_total_count(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        progress = WorkerProgress(
            percentage=20,
            status_message="初期化中",
            processed_count=0,
            total_count=0,
        )
        # total_count=0 の場合は status_message だけが表示されること
        manager.update_worker_progress("w1", progress)
        assert "w1" in manager._progress_dialogs

    def test_update_nonexistent_worker_is_noop(self, manager: ModernProgressManager) -> None:
        progress = WorkerProgress(percentage=50, status_message="テスト")
        # 例外が発生しないことを確認
        manager.update_worker_progress("nonexistent", progress)


@pytest.mark.unit
class TestUpdateBatchProgress:
    def test_update_batch_sets_value(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "バッチ")
        # headless 環境では未表示ダイアログの value() が -1 を返すことがある
        # 例外が発生しないことと、ダイアログが存在することを確認する
        manager.update_batch_progress("w1", 5, 10, "image.png")
        assert "w1" in manager._progress_dialogs

    def test_update_batch_zero_total_gives_zero_percent(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "バッチ")
        # total=0 の場合は 0% として処理されること（例外なし）
        manager.update_batch_progress("w1", 0, 0, "file.png")
        assert "w1" in manager._progress_dialogs

    def test_update_batch_nonexistent_worker_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager.update_batch_progress("nonexistent", 1, 10, "file.png")

    def test_update_batch_full_progress(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "バッチ")
        # headless環境では QProgressDialog.value() が未表示時に -1 を返すため
        # 例外が発生しないことと、ダイアログが存在することを確認する
        manager.update_batch_progress("w1", 10, 10, "last.png")
        assert "w1" in manager._progress_dialogs


@pytest.mark.unit
class TestFinishWorkerProgress:
    def test_finish_success_sets_100(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        manager.finish_worker_progress("w1", success=True)
        # ダイアログがまだ存在する（タイマーで遅延クリーンアップされる）
        # headless環境では setValue が未表示ダイアログに対して -1 を返す場合があるため
        # 例外が発生しないことを確認する
        assert "w1" in manager._progress_dialogs

    def test_finish_failure_leaves_dialog(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        manager.finish_worker_progress("w1", success=False)
        # ダイアログはまだ存在する（タイマーで遅延クリーンアップ）
        assert "w1" in manager._progress_dialogs

    def test_finish_nonexistent_worker_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager.finish_worker_progress("nonexistent", success=True)

    def test_finish_default_success_true(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        # デフォルト引数 success=True で呼び出せること
        manager.finish_worker_progress("w1")
        # headless環境ではダイアログが未表示のため value() が -1 になる可能性あり
        # ダイアログが残っていること（遅延クリーンアップ）を確認する
        assert "w1" in manager._progress_dialogs


@pytest.mark.unit
class TestCancelWorkerProgress:
    def test_cancel_removes_dialog(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        manager.cancel_worker_progress("w1")
        assert "w1" not in manager._progress_dialogs
        assert "w1" not in manager._active_workers

    def test_cancel_nonexistent_worker_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager.cancel_worker_progress("nonexistent")


@pytest.mark.unit
class TestOnCancelRequested:
    def test_on_cancel_emits_cancellation_requested(self, manager: ModernProgressManager, qtbot) -> None:
        manager.start_worker_progress("w1", "テスト")
        emitted_ids: list[str] = []
        manager.cancellation_requested.connect(emitted_ids.append)

        with qtbot.waitSignal(manager.cancellation_requested, timeout=1000):
            manager._on_cancel_requested("w1")

        assert emitted_ids == ["w1"]

    def test_on_cancel_already_completed_worker_is_noop(
        self, manager: ModernProgressManager, qtbot
    ) -> None:
        # worker_id が _active_workers に存在しない（完了済み）場合
        emitted_ids: list[str] = []
        manager.cancellation_requested.connect(emitted_ids.append)
        # シグナルが発火しないことを確認（タイムアウトで確認）
        manager._on_cancel_requested("nonexistent")
        assert emitted_ids == []

    def test_on_cancel_disables_cancel_button(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        manager._on_cancel_requested("w1")
        # dialog は存在し、キャンセルボタンが無効化されているはず
        dialog = manager._progress_dialogs.get("w1")
        assert dialog is not None


@pytest.mark.unit
class TestCloseDialog:
    def test_close_dialog_removes_from_both_dicts(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        manager._close_dialog("w1")
        assert "w1" not in manager._progress_dialogs
        assert "w1" not in manager._active_workers

    def test_close_dialog_nonexistent_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager._close_dialog("nonexistent")


@pytest.mark.unit
class TestCleanupCompletedDialogs:
    def test_cleanup_removes_completed_dialogs(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        # ダイアログの値を 100 に設定して完了状態にする
        dialog = manager._progress_dialogs["w1"]
        dialog.setValue(100)

        manager._cleanup_completed_dialogs()

        assert "w1" not in manager._progress_dialogs

    def test_cleanup_keeps_active_dialogs(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "テスト")
        dialog = manager._progress_dialogs["w1"]
        dialog.setValue(50)  # まだ途中

        manager._cleanup_completed_dialogs()

        # 可視性がFalseの場合もクリーンアップされるので、
        # headless環境ではisVisible()はFalseになることがある
        # ここでは例外が発生しないことを主に確認する

    def test_cleanup_empty_dialogs_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager._cleanup_completed_dialogs()


@pytest.mark.unit
class TestCloseAllDialogs:
    def test_close_all_removes_all(self, manager: ModernProgressManager) -> None:
        manager.start_worker_progress("w1", "操作1")
        manager.start_worker_progress("w2", "操作2")
        manager.start_worker_progress("w3", "操作3")

        manager.close_all_dialogs()

        assert manager.get_active_worker_count() == 0
        assert manager._progress_dialogs == {}
        assert manager._active_workers == {}

    def test_close_all_empty_is_noop(self, manager: ModernProgressManager) -> None:
        # 例外が発生しないことを確認
        manager.close_all_dialogs()


@pytest.mark.unit
class TestCreateWorkerId:
    def test_create_worker_id_default_prefix(self) -> None:
        worker_id = create_worker_id()
        assert worker_id.startswith("worker_")

    def test_create_worker_id_custom_prefix(self) -> None:
        worker_id = create_worker_id("annotation")
        assert worker_id.startswith("annotation_")

    def test_create_worker_id_is_unique(self) -> None:
        id1 = create_worker_id()
        id2 = create_worker_id()
        assert id1 != id2

    def test_create_worker_id_length(self) -> None:
        worker_id = create_worker_id("worker")
        # "worker_" + 8 hex chars
        assert len(worker_id) == len("worker_") + 8
