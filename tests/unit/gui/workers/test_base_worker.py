# tests/unit/gui/workers/test_base_worker.py

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, QThread

from lorairo.gui.workers.base import (
    CancellationController,
    LoRAIroWorkerBase,
    ProgressReporter,
    WorkerProgress,
    WorkerStatus,
)


class TestWorkerProgress:
    """WorkerProgress データクラスのテスト"""

    def test_basic_creation(self):
        """基本的な作成テスト"""
        progress = WorkerProgress(50, "テスト中")
        assert progress.percentage == 50
        assert progress.status_message == "テスト中"
        assert progress.current_item == ""
        assert progress.processed_count == 0
        assert progress.total_count == 0

    def test_full_creation(self):
        """全パラメータ指定作成テスト"""
        progress = WorkerProgress(
            percentage=75,
            status_message="処理中",
            current_item="file.jpg",
            processed_count=3,
            total_count=10,
        )
        assert progress.percentage == 75
        assert progress.status_message == "処理中"
        assert progress.current_item == "file.jpg"
        assert progress.processed_count == 3
        assert progress.total_count == 10


class TestWorkerStatus:
    """WorkerStatus 列挙型のテスト"""

    def test_status_values(self):
        """ステータス値テスト"""
        assert WorkerStatus.IDLE.value == "idle"
        assert WorkerStatus.RUNNING.value == "running"
        assert WorkerStatus.CANCELING.value == "canceling"
        assert WorkerStatus.COMPLETED.value == "completed"
        assert WorkerStatus.FAILED.value == "failed"


class TestCancellationController:
    """CancellationController のテスト"""

    def test_initial_state(self):
        """初期状態テスト"""
        controller = CancellationController()
        assert not controller.is_canceled()

    def test_cancel_operation(self):
        """キャンセル操作テスト"""
        controller = CancellationController()
        controller.cancel()
        assert controller.is_canceled()

    def test_reset_operation(self):
        """リセット操作テスト"""
        controller = CancellationController()
        controller.cancel()
        assert controller.is_canceled()

        controller.reset()
        assert not controller.is_canceled()


class TestProgressReporter:
    """ProgressReporter のテスト"""

    def test_signal_emission(self):
        """シグナル発行テスト"""
        reporter = ProgressReporter()

        # シグナル受信用モック
        progress_mock = Mock()
        batch_mock = Mock()

        reporter.progress_updated.connect(progress_mock)
        reporter.batch_progress.connect(batch_mock)

        # 進捗報告
        progress = WorkerProgress(50, "テスト")
        reporter.report(progress)
        progress_mock.assert_called_once_with(progress)

        # バッチ進捗報告
        reporter.report_batch(1, 10, "file.jpg")
        batch_mock.assert_called_once_with(1, 10, "file.jpg")


class ConcreteWorker(LoRAIroWorkerBase[str]):
    """テスト用具象ワーカー"""

    def __init__(self, duration: float = 0.1, should_fail: bool = False):
        super().__init__()
        self.duration = duration
        self.should_fail = should_fail
        self.execute_called = False

    def execute(self) -> str:
        """テスト用実行メソッド"""
        self.execute_called = True

        if self.should_fail:
            raise RuntimeError("テスト例外")

        # 段階的な進捗報告
        for i in range(5):
            if self.cancellation.is_canceled():
                return "canceled"

            progress = int((i + 1) * 20)
            self._report_progress(progress, f"ステップ {i + 1}/5")
            time.sleep(self.duration / 5)

        return "completed"


class TestLoRAIroWorkerBase:
    """LoRAIroWorkerBase のテスト"""

    @pytest.fixture
    def worker(self):
        """テスト用ワーカー"""
        return ConcreteWorker(duration=0.1)

    def test_initialization(self, worker):
        """初期化テスト"""
        assert worker.status == WorkerStatus.IDLE
        assert isinstance(worker.cancellation, CancellationController)
        assert isinstance(worker.progress, ProgressReporter)
        assert not worker.cancellation.is_canceled()

    def test_signal_connectivity(self, worker):
        """シグナル接続テスト"""
        # シグナル受信用モック
        progress_mock = Mock()
        batch_mock = Mock()
        status_mock = Mock()
        finished_mock = Mock()
        error_mock = Mock()

        worker.progress_updated.connect(progress_mock)
        worker.batch_progress.connect(batch_mock)
        worker.status_changed.connect(status_mock)
        worker.finished.connect(finished_mock)
        worker.error_occurred.connect(error_mock)

        # 進捗報告テスト
        worker._report_progress(50, "テスト")
        progress_mock.assert_called()

        # バッチ進捗報告テスト
        worker._report_batch_progress(1, 10, "file.jpg")
        batch_mock.assert_called_once_with(1, 10, "file.jpg")

    def test_successful_execution(self, worker):
        """正常実行テスト"""
        # シグナル受信用モック
        finished_mock = Mock()
        status_mock = Mock()

        worker.finished.connect(finished_mock)
        worker.status_changed.connect(status_mock)

        # 実行
        worker.run()

        # 結果検証
        assert worker.execute_called
        finished_mock.assert_called_once_with("completed")

        # ステータス変化確認
        status_calls = [call[0][0] for call in status_mock.call_args_list]
        assert WorkerStatus.RUNNING in status_calls
        assert WorkerStatus.COMPLETED in status_calls

    def test_execution_with_error(self):
        """エラー実行テスト"""
        worker = ConcreteWorker(should_fail=True)

        # シグナル受信用モック
        error_mock = Mock()
        status_mock = Mock()

        worker.error_occurred.connect(error_mock)
        worker.status_changed.connect(status_mock)

        # 実行
        worker.run()

        # エラー確認
        error_mock.assert_called_once()
        error_message = error_mock.call_args[0][0]
        assert "テスト例外" in error_message

        # ステータス確認
        status_calls = [call[0][0] for call in status_mock.call_args_list]
        assert WorkerStatus.FAILED in status_calls

    def test_cancellation(self, worker):
        """キャンセルテスト"""
        # キャンセルシグナル接続
        status_mock = Mock()
        worker.status_changed.connect(status_mock)

        # キャンセル実行
        worker.cancel()

        # ステータス確認
        assert worker.status == WorkerStatus.CANCELING
        assert worker.cancellation.is_canceled()
        status_mock.assert_called_with(WorkerStatus.CANCELING)

    def test_check_cancellation_helper(self, worker):
        """キャンセルチェックヘルパーテスト"""
        # 通常状態では例外なし
        worker._check_cancellation()

        # キャンセル後は例外発生
        worker.cancel()
        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker._check_cancellation()

    def test_progress_report_helper(self, worker):
        """進捗報告ヘルパーテスト"""
        progress_mock = Mock()
        worker.progress_updated.connect(progress_mock)

        # 進捗報告実行
        worker._report_progress(
            percentage=75,
            status_message="テスト進捗",
            current_item="file.jpg",
            processed_count=3,
            total_count=4,
        )

        # 呼び出し確認
        progress_mock.assert_called_once()
        progress = progress_mock.call_args[0][0]
        assert progress.percentage == 75
        assert progress.status_message == "テスト進捗"
        assert progress.current_item == "file.jpg"
        assert progress.processed_count == 3
        assert progress.total_count == 4

    def test_batch_progress_report_helper(self, worker):
        """バッチ進捗報告ヘルパーテスト"""
        batch_mock = Mock()
        worker.batch_progress.connect(batch_mock)

        # バッチ進捗報告実行
        worker._report_batch_progress(5, 20, "test_file.jpg")

        # 呼び出し確認
        batch_mock.assert_called_once_with(5, 20, "test_file.jpg")

    def test_status_change_prevention(self, worker):
        """ステータス変更防止テスト"""
        status_mock = Mock()
        worker.status_changed.connect(status_mock)

        # 同じステータスに設定
        worker._set_status(WorkerStatus.IDLE)  # 初期値と同じ
        status_mock.assert_not_called()

        # 異なるステータスに設定
        worker._set_status(WorkerStatus.RUNNING)
        status_mock.assert_called_once_with(WorkerStatus.RUNNING)


class TestLoRAIroWorkerBaseAlias:
    """LoRAIroWorkerBase エイリアステスト"""

    def test_alias_functionality(self):
        """エイリアス機能テスト"""
        # LoRAIroWorkerBase と LoRAIroWorkerBase が同じクラスであることを確認
        assert LoRAIroWorkerBase is LoRAIroWorkerBase

        # エイリアスでも正常に継承できることを確認
        worker = ConcreteWorker()
        assert isinstance(worker, LoRAIroWorkerBase)
        assert isinstance(worker, LoRAIroWorkerBase)
