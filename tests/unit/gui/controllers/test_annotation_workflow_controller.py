"""AnnotationWorkflowControllerの単体テスト

Phase 2.3で作成されたAnnotationWorkflowControllerのテスト。
DatasetControllerパターンに従ったアノテーションワークフロー制御を検証。
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from lorairo.gui.controllers.annotation_workflow_controller import (
    AnnotationWorkflowController,
)


@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.start_enhanced_batch_annotation = Mock(return_value="test_worker_id")
    return service


@pytest.fixture
def mock_selection_state_service():
    """SelectionStateServiceのモック"""
    service = Mock()
    service.get_selected_image_paths.return_value = [
        "/path/to/image1.jpg",
        "/path/to/image2.jpg",
    ]
    return service


@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
    }
    service.get_available_annotation_models.return_value = [
        "gpt-4o-mini",
        "gpt-4o",
        "claude-3-haiku-20240307",
        "claude-3-sonnet-20240229",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    return service


@pytest.fixture
def mock_parent():
    """親ウィジェットのモック"""
    parent = Mock()
    return parent


@pytest.fixture
def controller(
    mock_worker_service,
    mock_selection_state_service,
    mock_config_service,
    mock_parent,
):
    """AnnotationWorkflowControllerインスタンス"""
    return AnnotationWorkflowController(
        worker_service=mock_worker_service,
        selection_state_service=mock_selection_state_service,
        config_service=mock_config_service,
        parent=mock_parent,
    )


class TestAnnotationWorkflowControllerInit:
    """初期化テスト"""

    def test_init(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
        mock_parent,
    ):
        """正常な初期化"""
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=mock_parent,
        )

        assert controller.worker_service is mock_worker_service
        assert controller.selection_state_service is mock_selection_state_service
        assert controller.config_service is mock_config_service
        assert controller._parent_widget is mock_parent

    def test_init_without_parent(
        self, mock_worker_service, mock_selection_state_service, mock_config_service
    ):
        """親なしの初期化"""
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )

        assert controller._parent_widget is None


class TestStartAnnotationWorkflow:
    """start_annotation_workflow()テスト"""

    def test_start_annotation_workflow_success(
        self,
        controller,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """正常なアノテーション開始"""

        # Setup - モデル選択callback
        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - SelectionStateService呼び出し確認
        mock_selection_state_service.get_selected_image_paths.assert_called_once()

        # Assert - WorkerService呼び出し確認
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()
        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["image_paths"] == [
            "/path/to/image1.jpg",
            "/path/to/image2.jpg",
        ]
        assert call_args[1]["litellm_model_ids"] == ["gpt-4o-mini"]

    def test_start_annotation_workflow_no_images_selected(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """画像未選択エラー"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )
        mock_selection_state_service.get_selected_image_paths.side_effect = ValueError(
            "画像が選択されていません"
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert
        # ValueError should be caught and handled gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - WorkerServiceは呼ばれない
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_model_selection_cancelled(self, controller, mock_worker_service):
        """モデル選択キャンセル"""

        # Setup - callback returns None (cancelled)
        def model_selection_callback(available_models: list[str]) -> str | None:
            return None

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - WorkerServiceは呼ばれない
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_no_api_keys(
        self, controller, mock_config_service, mock_worker_service
    ):
        """APIキー未設定の場合でもデフォルトモデルで実行"""
        # Setup
        mock_config_service.get_api_keys.return_value = {}

        def model_selection_callback(available_models: list[str]) -> str:
            # デフォルトモデルリストが渡される
            assert "gpt-4o-mini" in available_models
            return "gpt-4o-mini"

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - デフォルトモデルで実行される
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()

    def test_start_annotation_workflow_worker_service_failure(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """WorkerService実行失敗"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )
        mock_worker_service.start_enhanced_batch_annotation.side_effect = RuntimeError("Annotation failed")

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute - Should handle exception gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - Exception was caught
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()

    def test_start_annotation_workflow_no_worker_service(
        self, mock_selection_state_service, mock_config_service
    ):
        """WorkerServiceがNoneの場合"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=None,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert - Should handle gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

    def test_start_annotation_workflow_no_selection_service(self, mock_worker_service, mock_config_service):
        """SelectionStateServiceがNoneの場合"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=None,
            config_service=mock_config_service,
            parent=None,
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert - Should handle gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_no_config_service(
        self, mock_worker_service, mock_selection_state_service
    ):
        """ConfigurationServiceがNoneの場合（空のモデルリスト）"""
        # Setup - parent=None for consistency
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=None,
            parent=None,
        )

        callback_called = False

        def model_selection_callback(available_models: list[str]) -> str | None:
            nonlocal callback_called
            callback_called = True
            # ConfigurationServiceがNoneの場合、空リストが渡される
            assert available_models == []
            # 空リストの場合、Noneを返す（キャンセル扱い）
            return None

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - callbackは呼ばれるが、start_enhanced_batch_annotationは呼ばれない
        assert callback_called
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_with_available_providers(self, controller, mock_config_service):
        """利用可能なプロバイダーに基づくモデル選択"""
        # Setup
        mock_config_service.get_api_keys.return_value = {
            "openai_key": "test-key",
            "claude_key": "test-key",
            "google_key": "test-key",
        }

        available_models_captured = []

        def model_selection_callback(available_models: list[str]) -> str:
            available_models_captured.extend(available_models)
            return available_models[0]

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - 全プロバイダーのモデルが利用可能
        assert len(available_models_captured) >= 3  # OpenAI, Anthropic, Google models

    def test_start_annotation_workflow_with_selected_models(
        self,
        controller,
        mock_worker_service,
        mock_selection_state_service,
    ):
        """selected_modelsパラメータでモデルを直接指定"""
        # Setup - チェックボックスから選択されたモデルを想定
        selected_models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # Execute - model_selection_callbackなしで実行
        controller.start_annotation_workflow(selected_litellm_model_ids=selected_models)

        # Assert - WorkerServiceが選択されたモデルで呼ばれる
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()
        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["litellm_model_ids"] == selected_models

    def test_start_annotation_workflow_with_selected_models_priority(
        self,
        controller,
        mock_worker_service,
    ):
        """selected_modelsがある場合、model_selection_callbackは呼ばれない"""
        # Setup
        selected_models = ["gpt-4o-mini"]
        callback_called = False

        def model_selection_callback(available_models: list[str]) -> str:
            nonlocal callback_called
            callback_called = True
            return "claude-3-haiku-20240307"

        # Execute - selected_modelsを優先
        controller.start_annotation_workflow(
            selected_litellm_model_ids=selected_models,
            model_selection_callback=model_selection_callback,
        )

        # Assert - callbackは呼ばれず、selected_modelsが使用される
        assert not callback_called
        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["litellm_model_ids"] == selected_models

    @patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox.warning")
    @patch("lorairo.gui.controllers.annotation_workflow_controller.get_service_container")
    def test_start_annotation_workflow_warns_but_allows_deprecated_models(
        self,
        mock_get_container,
        mock_warning,
        controller,
        mock_worker_service,
    ):
        """廃止モデル選択時は警告し、OKなら実行は継続する。"""
        from PySide6.QtWidgets import QMessageBox

        mock_container = Mock()
        mock_container.annotator_library.is_model_deprecated.side_effect = lambda model_name: (
            model_name == "openai/old-model"
        )
        mock_get_container.return_value = mock_container
        mock_warning.return_value = QMessageBox.StandardButton.Ok

        controller.start_annotation_workflow(selected_litellm_model_ids=["openai/old-model"])

        mock_warning.assert_called_once()
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()

    @patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox.warning")
    @patch("lorairo.gui.controllers.annotation_workflow_controller.get_service_container")
    def test_start_annotation_workflow_cancel_deprecated_warning_blocks_start(
        self,
        mock_get_container,
        mock_warning,
        controller,
        mock_worker_service,
    ):
        """廃止モデル警告でCancelした場合は開始しない。"""
        from PySide6.QtWidgets import QMessageBox

        mock_container = Mock()
        mock_container.annotator_library.is_model_deprecated.return_value = True
        mock_get_container.return_value = mock_container
        mock_warning.return_value = QMessageBox.StandardButton.Cancel

        controller.start_annotation_workflow(selected_litellm_model_ids=["openai/old-model"])

        mock_warning.assert_called_once()
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_no_models_no_callback(
        self,
        controller,
        mock_worker_service,
        monkeypatch,
    ):
        """selected_modelsなし、callbackなしの場合は警告表示"""
        # Setup - QMessageBoxをモック
        mock_warning = Mock()
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", mock_warning)

        # Execute - 両方なし
        controller.start_annotation_workflow()

        # Assert - 警告が表示される
        mock_warning.assert_called_once()

        # Assert - アノテーションは開始されない
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()


class _StubModel:
    """provider_batch_capability helper が読む属性だけ持つ stub。"""

    def __init__(self, *, id: int, provider: str, litellm_model_id: str) -> None:
        self.id = id
        self.provider = provider
        self.litellm_model_id = litellm_model_id
        self.model_types: tuple[object, ...] = ()


class TestConfigureAsyncDispatch:
    """async batch dispatch の DI 足場テスト (#896 PR4b, Task 4.2)。"""

    def test_controller_is_qobject_for_queued_slots(self, controller):
        """worker→slot を queued 接続にするため QObject であること (#896 PR4b)。

        非 QObject だと cross-thread の direct 接続になり worker スレッドから
        GUI/state を触りクラッシュする。
        """
        from PySide6.QtCore import QObject

        assert isinstance(controller, QObject)

    def test_async_dispatch_state_initialized(self, controller):
        """async dispatch state が安全な初期値で構築される。"""
        assert controller._async_dispatch_in_progress is False
        assert controller._async_dispatch_thread is None
        assert controller._async_dispatch_worker is None
        assert controller._async_dispatch_image_ids == []
        assert controller._service_container is None
        assert controller._db_manager is None
        assert controller._staging_state_manager is None
        assert controller._annotate_tab is None
        # 未注入時の callback は no-op (呼んでも例外を出さない)
        controller._jobs_refresh()
        controller._status_callback("msg", 100)

    def test_configure_async_dispatch_injects_collaborators(self, controller):
        """configure_async_dispatch が協調オブジェクトを注入する。"""
        sc, db, staging, tab = Mock(), Mock(), Mock(), Mock()
        jobs_refresh, status_cb = Mock(), Mock()

        controller.configure_async_dispatch(
            service_container=sc,
            db_manager=db,
            staging_state_manager=staging,
            annotate_tab=tab,
            jobs_refresh=jobs_refresh,
            status_callback=status_cb,
        )

        assert controller._service_container is sc
        assert controller._db_manager is db
        assert controller._staging_state_manager is staging
        assert controller._annotate_tab is tab
        assert controller._jobs_refresh is jobs_refresh
        assert controller._status_callback is status_cb


class TestDispatchAsyncBatch:
    """dispatch_async_batch の射影 + fail-closed gate テスト (ADR 0076 §2)。

    #896 PR4b で MainWindow から移送 (移送元: test_main_window_coverage.py)。
    unbound メソッドを Mock controller (self) で呼び、射影分岐と gate を検証する。
    """

    @staticmethod
    def _build_controller(
        *,
        ratings: dict[int, str | None],
        selected: list[str],
        discovery: list[str],
        model: object | None,
        in_progress: bool = False,
    ) -> object:
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        ctrl._async_dispatch_in_progress = in_progress
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")
        ctrl._annotate_tab.selected_litellm_model_ids.return_value = selected
        ctrl._annotate_tab.get_staged_items.return_value = {10: ("img10", "stored/10.webp")}
        # processed パス解決 (ADR 0064) は別メソッド。既定で解決成功を返す。
        ctrl._resolve_processed_paths_for_batch.return_value = {10: "/data/processed/10.webp"}

        workflow_service = Mock()
        workflow_service.list_batch_capable_models.return_value = discovery
        ctrl._service_container.provider_batch_workflow_service = workflow_service
        ctrl._service_container.annotator_library = Mock()
        ctrl._db_manager.image_repo.get_latest_normalized_ratings_by_image_ids.return_value = ratings
        ctrl._db_manager.model_repo.get_model_by_litellm_id.return_value = model
        return ctrl

    def test_all_sendable_batch_capable_starts_worker(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()
            mock_qmb.critical.assert_not_called()

        ctrl._start_async_dispatch_worker.assert_called_once()
        assert ctrl._async_dispatch_in_progress is True

    def test_run_settings_prompt_profile_and_description_forwarded(self) -> None:
        # #902: run settings の prompt_profile / description を射影へ配線する。ADR 0076 §1。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        ctrl._annotate_tab.run_options.return_value = RunOptions(
            dispatch_mode="batch_api",
            prompt_profile="photoreal-v2",
            description="monthly audit run",
        )

        with (
            patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox"),
            patch(
                "lorairo.gui.controllers.annotation_workflow_controller.project_async_batch_dispatch"
            ) as mock_project,
        ):
            AnnotationWorkflowController.dispatch_async_batch(ctrl)

        mock_project.assert_called_once()
        kwargs = mock_project.call_args.kwargs
        assert kwargs["prompt_profile"] == "photoreal-v2"
        assert kwargs["description"] == "monthly audit run"

    def test_unrated_images_rejected(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={},  # 未判定 (unrated)
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_called_once()

        ctrl._start_async_dispatch_worker.assert_not_called()

    def test_non_batch_capable_model_rejected(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],  # local は discovery に無い
            model=model,
        )

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_called_once()

        ctrl._start_async_dispatch_worker.assert_not_called()

    def test_no_staged_images_shows_info(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = self._build_controller(
            ratings={},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=None,
        )
        ctrl._annotate_tab.get_staged_items.return_value = {}

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.information.assert_called_once()

        ctrl._start_async_dispatch_worker.assert_not_called()

    def test_reentry_guard_blocks_second_dispatch(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
            in_progress=True,
        )

        AnnotationWorkflowController.dispatch_async_batch(ctrl)

        ctrl._start_async_dispatch_worker.assert_not_called()

    def test_dry_run_skips_submission(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api", dry_run=True)

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.information.assert_called_once()

        ctrl._start_async_dispatch_worker.assert_not_called()

    def test_missing_processed_paths_rejected(self) -> None:
        # ADR 0064: processed 版が無い画像があれば dispatch しない。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )
        ctrl._resolve_processed_paths_for_batch.return_value = None  # 解決失敗

        AnnotationWorkflowController.dispatch_async_batch(ctrl)

        ctrl._start_async_dispatch_worker.assert_not_called()


class TestFinalizeSubmittedJobs:
    """_finalize_submitted_jobs / _on_async_dispatch_* の二重送信防止テスト。

    #896 PR4b で MainWindow から移送 (#900 Codex P2 の杭)。jobs 反映は callback、
    status は callback 経由。
    """

    def test_finalize_clears_staging_and_refreshes_jobs(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()
        ctrl._staging_state_manager = Mock()
        ctrl._async_dispatch_image_ids = [10, 11]

        AnnotationWorkflowController._finalize_submitted_jobs(ctrl, [101])

        ctrl._staging_state_manager.remove_image_ids.assert_called_once_with([10, 11])
        ctrl._jobs_refresh.assert_called_once()

    def test_finalize_noop_when_no_jobs(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()
        ctrl._staging_state_manager = Mock()
        ctrl._async_dispatch_image_ids = [10]

        AnnotationWorkflowController._finalize_submitted_jobs(ctrl, [])

        ctrl._staging_state_manager.remove_image_ids.assert_not_called()
        ctrl._jobs_refresh.assert_not_called()

    def test_succeeded_finalizes_and_reports_status(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()

        AnnotationWorkflowController._on_async_dispatch_succeeded(ctrl, [101, 102])

        ctrl._finalize_submitted_jobs.assert_called_once_with([101, 102])
        ctrl._status_callback.assert_called_once()

    def test_failed_with_partial_finalizes(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController._on_async_dispatch_failed(ctrl, ValueError("boom"), [101])
            mock_qmb.critical.assert_called_once()

        ctrl._finalize_submitted_jobs.assert_called_once_with([101])

    def test_failed_total_does_not_finalize(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController._on_async_dispatch_failed(ctrl, ValueError("boom"), [])
            mock_qmb.critical.assert_called_once()

        ctrl._finalize_submitted_jobs.assert_not_called()
