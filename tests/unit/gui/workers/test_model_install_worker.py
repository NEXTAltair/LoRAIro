# tests/unit/gui/workers/test_model_install_worker.py
"""ModelInstallWorker (Issue #754) のユニットテスト"""

from unittest.mock import Mock

import pytest
from image_annotator_lib import ModelInstallCancelledError

from lorairo.gui.workers.base import WorkerStatus
from lorairo.gui.workers.model_install_worker import ModelInstallResult, ModelInstallWorker

pytestmark = pytest.mark.unit


class TestModelInstallWorker:
    def test_execute_installs_all_models_in_order(self):
        """全モデルを順次インストールし、結果に完了モデルを列挙する"""
        adapter = Mock()
        worker = ModelInstallWorker(adapter, ["model_a", "model_b"])

        result = worker.execute()

        assert isinstance(result, ModelInstallResult)
        assert result.installed_models == ["model_a", "model_b"]
        assert [call.args[0] for call in adapter.install_model.call_args_list] == ["model_a", "model_b"]
        # cancel_event が lib 側へ伝播している
        for call in adapter.install_model.call_args_list:
            assert call.kwargs["cancel_event"] is worker._cancel_event

    def test_progress_callback_maps_bytes_to_overall_percentage(self):
        """byte 進捗がモデル数を跨いだ全体 % とメッセージに変換される"""
        adapter = Mock()
        received = []

        def fake_install(model_name, progress_callback=None, cancel_event=None):
            # 2 モデル中の 1 モデルで 50% -> 100% と進む
            progress_callback(50 * 1024 * 1024, 100 * 1024 * 1024)
            progress_callback(100 * 1024 * 1024, 100 * 1024 * 1024)

        adapter.install_model.side_effect = fake_install
        worker = ModelInstallWorker(adapter, ["model_a", "model_b"])
        worker.progress_updated.connect(received.append)

        worker.execute()

        messages = [p.status_message for p in received]
        assert any("model_a をダウンロード中 50% (50.0/100.0 MB)" in m for m in messages)
        # model_a の 50% は全体の 25%
        pct_for_50 = next(
            p.percentage for p in received if "model_a をダウンロード中 50%" in p.status_message
        )
        assert pct_for_50 == 25
        # 完了時は 100%
        assert received[-1].percentage == 100
        assert "モデルインストール完了: 2件" in received[-1].status_message

    def test_progress_callback_skips_unknown_total(self):
        """総量未確定 (total_bytes=0) の進捗は通知しない"""
        adapter = Mock()
        received = []

        def fake_install(model_name, progress_callback=None, cancel_event=None):
            progress_callback(1024, 0)

        adapter.install_model.side_effect = fake_install
        worker = ModelInstallWorker(adapter, ["model_a"])
        worker.progress_updated.connect(received.append)

        worker.execute()

        # byte 進捗 ("... 45% (10.0/20.0 MB)" 形式) は通知されない
        assert all("MB)" not in p.status_message for p in received)

    def test_cancel_sets_cancel_event(self):
        """cancel() はダウンロード中断用の Event をセットする"""
        worker = ModelInstallWorker(Mock(), ["model_a"])

        worker.cancel()

        assert worker._cancel_event.is_set()

    def test_lib_cancellation_maps_to_canceled_terminal(self):
        """DL 中の lib 中断例外 (ModelInstallCancelledError) は canceled 終端に写像される"""
        adapter = Mock()
        adapter.install_model.side_effect = ModelInstallCancelledError("model_a")
        worker = ModelInstallWorker(adapter, ["model_a"])
        canceled_mock = Mock()
        worker.canceled.connect(canceled_mock)

        worker.run()

        canceled_mock.assert_called_once()
        assert worker.status == WorkerStatus.CANCELED

    def test_install_failure_emits_error(self):
        """インストール失敗は error_occurred として終端する"""
        adapter = Mock()
        adapter.install_model.side_effect = RuntimeError("download failed")
        worker = ModelInstallWorker(adapter, ["model_a"])
        error_mock = Mock()
        worker.error_occurred.connect(error_mock)

        worker.run()

        error_mock.assert_called_once()
        assert worker.status == WorkerStatus.FAILED
