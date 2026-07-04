"""AnnotationWorkflowControllerの単体テスト

Phase 2.3で作成されたAnnotationWorkflowControllerのテスト。
DatasetControllerパターンに従ったアノテーションワークフロー制御を検証。
"""

from unittest.mock import Mock, patch

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

    def test_start_annotation_workflow_passes_run_options(
        self,
        controller,
        mock_worker_service,
    ):
        """Issue #803: run_options が worker_service へ伝搬される。"""
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        run_options = RunOptions(dry_run=True, rating_gate=False)

        controller.start_annotation_workflow(
            selected_litellm_model_ids=["gpt-4o-mini"],
            run_options=run_options,
        )

        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["run_options"] is run_options

    def test_start_annotation_workflow_run_options_default_none(
        self,
        controller,
        mock_worker_service,
    ):
        """run_options 省略時は None が伝搬され従来挙動を維持する。"""
        controller.start_annotation_workflow(selected_litellm_model_ids=["gpt-4o-mini"])

        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["run_options"] is None

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


def _stub_projection(litellm_id: str, model_id: int, task_type: str, ineligible: tuple = ()):
    """project_async_batch_dispatch のパッチ差し替え用に実 DispatchProjection を作る。"""
    from lorairo.services.dispatch_projection_service import DispatchEntry, DispatchProjection

    entry = DispatchEntry(
        provider="openai",
        endpoint="/v1/x",
        litellm_model_id=litellm_id,
        model_id=model_id,
        prompt_profile="default",
        description=None,
        task_type=task_type,
        image_ids=(10,),
        image_paths=None,
    )
    return DispatchProjection(entries=(entry,), ineligible_litellm_model_ids=ineligible)


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
        # 未注入時はアノテーションタブ非アクティブ扱い (#896 PR4c)
        assert controller._is_annotate_tab_active() is False

    def test_configure_async_dispatch_injects_collaborators(self, controller):
        """configure_async_dispatch が協調オブジェクトを注入する。"""
        sc, db, staging, tab = Mock(), Mock(), Mock(), Mock()
        jobs_refresh, status_cb, is_active = Mock(), Mock(), Mock()

        controller.configure_async_dispatch(
            service_container=sc,
            db_manager=db,
            staging_state_manager=staging,
            annotate_tab=tab,
            jobs_refresh=jobs_refresh,
            status_callback=status_cb,
            is_annotate_tab_active=is_active,
        )

        assert controller._service_container is sc
        assert controller._db_manager is db
        assert controller._staging_state_manager is staging
        assert controller._annotate_tab is tab
        assert controller._jobs_refresh is jobs_refresh
        assert controller._status_callback is status_cb
        assert controller._is_annotate_tab_active is is_active


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
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()
            mock_qmb.critical.assert_not_called()

        ctrl._start_async_dispatch_worker.assert_called_once()
        assert ctrl._async_dispatch_in_progress is True
        # #1102: 送信を開始できたら True を返す (遷移判定に使う)
        assert started is True

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
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_called_once()

        ctrl._start_async_dispatch_worker.assert_not_called()
        # #1102: 開始前に拒否したら False を返す (遷移しない)
        assert started is False

    def test_non_batch_capable_model_routed_to_sync(self) -> None:
        # #1133: batch 非対応モデルは拒否せず同期ワークフローへ振り分ける。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],  # local は discovery に無い
            model=model,
        )
        ctrl.start_annotation_workflow.return_value = True

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()

        # batch worker は起動せず、同期ワークフローへ振り分ける
        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_called_once()
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "local/wd-tagger"
        ]
        assert started is True

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

    def test_moderation_only_uses_rating_preflight_and_skips_gate(self) -> None:
        # #1098: moderation 専用モデルのみ選択 → task_type=rating_preflight。
        # 未判定 rating があっても fail-closed gate は適用せず送信できる。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=5, provider="openai", litellm_model_id="openai/omni-moderation-latest")
        ctrl = self._build_controller(
            ratings={},  # 未判定 (通常は gate がブロックする状態)
            selected=["openai/omni-moderation-latest"],
            discovery=["openai/omni-moderation-latest"],
            model=model,
        )

        with (
            patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb,
            patch(
                "lorairo.gui.controllers.annotation_workflow_controller.project_async_batch_dispatch"
            ) as mock_project,
        ):
            mock_project.return_value = _stub_projection(
                "openai/omni-moderation-latest", 5, "rating_preflight"
            )
            AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()

        # gate (rating 取得) は呼ばれない = moderation gate をスキップした
        ctrl._db_manager.image_repo.get_latest_normalized_ratings_by_image_ids.assert_not_called()
        assert mock_project.call_args.kwargs["task_type"] == "rating_preflight"
        ctrl._start_async_dispatch_worker.assert_called_once()

    def test_normal_model_keeps_annotation_task_type(self) -> None:
        # #1098: 通常モデルのみなら task_type=annotation のまま (回帰防止)。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        model = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o"],
            discovery=["openai/gpt-4o"],
            model=model,
        )

        with (
            patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox"),
            patch(
                "lorairo.gui.controllers.annotation_workflow_controller.project_async_batch_dispatch"
            ) as mock_project,
        ):
            mock_project.return_value = _stub_projection("openai/gpt-4o", 1, "annotation")
            AnnotationWorkflowController.dispatch_async_batch(ctrl)

        # 通常モデルは gate 対象 (rating 取得が走る)
        ctrl._db_manager.image_repo.get_latest_normalized_ratings_by_image_ids.assert_called_once()
        assert mock_project.call_args.kwargs["task_type"] == "annotation"

    def test_mixed_moderation_and_normal_auto_split(self) -> None:
        # #1133: moderation + 通常モデル混在は拒否せず自動振り分け。
        # moderation → rating_preflight で batch、通常モデル → 同期へ。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        mod = _StubModel(id=5, provider="openai", litellm_model_id="openai/omni-moderation-latest")
        normal = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/omni-moderation-latest", "openai/gpt-4o"],
            discovery=["openai/omni-moderation-latest", "openai/gpt-4o"],
            model=None,
        )
        resolved = {"openai/omni-moderation-latest": mod, "openai/gpt-4o": normal}
        ctrl._db_manager.model_repo.get_model_by_litellm_id.side_effect = resolved.get
        ctrl.start_annotation_workflow.return_value = True

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()

        # moderation は Batch API worker へ、通常モデルは同期ワークフローへ
        ctrl._start_async_dispatch_worker.assert_called_once()
        ctrl.start_annotation_workflow.assert_called_once()
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "openai/gpt-4o"
        ]
        assert started is True

    def test_mixed_batch_and_sync_only_split(self) -> None:
        # #1133: batch 対応 (openai) + 同期専用 (local) 混在 → openai=batch、local=sync。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        gpt = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o", "local/wd-tagger"],
            discovery=["openai/gpt-4o"],  # local は discovery に無い = batch 非対応
            model=None,
        )
        resolved = {"openai/gpt-4o": gpt, "local/wd-tagger": local}
        ctrl._db_manager.model_repo.get_model_by_litellm_id.side_effect = resolved.get
        ctrl.start_annotation_workflow.return_value = True

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.warning.assert_not_called()

        ctrl._start_async_dispatch_worker.assert_called_once()  # openai → batch
        ctrl.start_annotation_workflow.assert_called_once()  # local → sync
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "local/wd-tagger"
        ]
        # 振り分け結果をステータスへ明示 (黙って振り分けない)
        assert ctrl._status_callback.called
        assert started is True

    def test_all_sync_only_notifies_and_no_batch(self) -> None:
        # #1133: 全て同期専用 + Batch API実行 → 全て同期、案内メッセージを出す。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=local,
        )
        ctrl.start_annotation_workflow.return_value = True

        AnnotationWorkflowController.dispatch_async_batch(ctrl)

        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_called_once()
        message = ctrl._status_callback.call_args.args[0]
        assert "1 モデルを同期で実行します" in message

    def test_no_batch_service_runs_sync_only(self) -> None:
        # #1136 Codex P2 #2: Batch サービス不在でも同期対象は同期で起動する。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=local,
        )
        ctrl._service_container.provider_batch_workflow_service = None  # Batch サービス不在
        ctrl.start_annotation_workflow.return_value = True

        started = AnnotationWorkflowController.dispatch_async_batch(ctrl)

        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_called_once()
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "local/wd-tagger"
        ]
        assert started is True

    def test_batch_path_failure_still_runs_sync(self) -> None:
        # #1136 Codex P2 #1: batch の processed パス解決が失敗しても同期対象は独立起動する。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        gpt = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o", "local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=None,
        )
        resolved = {"openai/gpt-4o": gpt, "local/wd-tagger": local}
        ctrl._db_manager.model_repo.get_model_by_litellm_id.side_effect = resolved.get
        ctrl._resolve_processed_paths_for_batch.return_value = None  # batch のパス解決失敗
        ctrl.start_annotation_workflow.return_value = True

        started = AnnotationWorkflowController.dispatch_async_batch(ctrl)

        # batch (openai) はパス失敗で起動せず、同期 (local) は独立して起動する
        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_called_once()
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "local/wd-tagger"
        ]
        assert started is True

    def test_moderation_not_in_discovery_is_unsupported_not_synced(self) -> None:
        # #1136 Codex P2 #4: batch に乗れない moderation は同期へ流さず実行対象外で明示。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        mod = _StubModel(id=5, provider="openai", litellm_model_id="openai/omni-moderation-latest")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/omni-moderation-latest"],
            discovery=[],  # moderation が discovery に無い = batch に乗れない
            model=mod,
        )

        started = AnnotationWorkflowController.dispatch_async_batch(ctrl)

        # 同期にも batch にも流さない (moderation は同期実行不可)
        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_not_called()
        message = ctrl._status_callback.call_args.args[0]
        assert "Batch API のみ対応" in message
        assert started is False

    def test_no_batch_service_blocks_api_models_syncs_local(self) -> None:
        # #1136 2巡目 P2 #3: Batch サービス不在時、API モデルは同期へ流さず、local のみ同期。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        gpt = _StubModel(id=1, provider="openai", litellm_model_id="openai/gpt-4o")
        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["openai/gpt-4o", "local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=None,
        )
        ctrl._service_container.provider_batch_workflow_service = None  # Batch サービス不在
        resolved = {"openai/gpt-4o": gpt, "local/wd-tagger": local}
        ctrl._db_manager.model_repo.get_model_by_litellm_id.side_effect = resolved.get
        ctrl.start_annotation_workflow.return_value = True

        started = AnnotationWorkflowController.dispatch_async_batch(ctrl)

        # local のみ同期、API モデル (gpt-4o) は黙って同期実行しない
        ctrl.start_annotation_workflow.assert_called_once()
        assert ctrl.start_annotation_workflow.call_args.kwargs["selected_litellm_model_ids"] == [
            "local/wd-tagger"
        ]
        message = ctrl._status_callback.call_args.args[0]
        assert "API モデル 1 件は実行されません" in message
        assert started is True

    def test_discovery_failure_runs_sync_fallback(self) -> None:
        # #1136 2巡目 P2 #1: discovery 失敗でも同期専用モデルは同期起動する。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.services.provider_batch_service import ProviderBatchError

        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=local,
        )
        ctrl._service_container.provider_batch_workflow_service.list_batch_capable_models.side_effect = (
            ProviderBatchError("discovery down")
        )
        ctrl.start_annotation_workflow.return_value = True

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox"):
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)

        # discovery 失敗でも local は同期起動する
        ctrl._start_async_dispatch_worker.assert_not_called()
        ctrl.start_annotation_workflow.assert_called_once()
        assert started is True

    def test_empty_staged_paths_guards_sync(self) -> None:
        # #1136 2巡目 P2 #2: staged パスが全滅なら空パス同期を起動せず明示エラー。
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        local = _StubModel(id=9, provider="local", litellm_model_id="local/wd-tagger")
        ctrl = self._build_controller(
            ratings={10: "PG"},
            selected=["local/wd-tagger"],
            discovery=["openai/gpt-4o"],
            model=local,
        )
        ctrl._service_container.provider_batch_workflow_service = None  # 同期経路へ
        ctrl._annotate_tab.staged_image_paths.return_value = []  # パス全滅

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            started = AnnotationWorkflowController.dispatch_async_batch(ctrl)
            mock_qmb.information.assert_called()

        # 空パスでは同期を起動しない (SelectionStateService への誤フォールバック防止)
        ctrl.start_annotation_workflow.assert_not_called()
        assert started is False


class TestNotifyDispatchSplit:
    """#1133: 振り分け結果メッセージの生成。"""

    def _ctrl(self):
        ctrl = Mock()
        return ctrl

    def test_mixed_message(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import _notify_dispatch_split

        ctrl = self._ctrl()
        _notify_dispatch_split(ctrl, 2, 3)
        msg = ctrl._status_callback.call_args.args[0]
        assert "2 モデルを Batch API へ" in msg
        assert "3 モデルを同期で" in msg

    def test_batch_only_message(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import _notify_dispatch_split

        ctrl = self._ctrl()
        _notify_dispatch_split(ctrl, 2, 0)
        msg = ctrl._status_callback.call_args.args[0]
        assert "Batch API" in msg and "同期" not in msg

    def test_sync_only_message(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import _notify_dispatch_split

        ctrl = self._ctrl()
        _notify_dispatch_split(ctrl, 0, 3)
        msg = ctrl._status_callback.call_args.args[0]
        assert "3 モデルを同期で実行します" in msg

    def test_unsupported_moderation_note(self) -> None:
        # #1136: moderation を同期へ流さず実行対象外として明示する
        from lorairo.gui.controllers.annotation_workflow_controller import _notify_dispatch_split

        ctrl = self._ctrl()
        _notify_dispatch_split(ctrl, 1, 0, unsupported_count=2)
        msg = ctrl._status_callback.call_args.args[0]
        assert "moderation 2 件" in msg and "Batch API のみ対応" in msg

    def test_all_unsupported_message(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import _notify_dispatch_split

        ctrl = self._ctrl()
        _notify_dispatch_split(ctrl, 0, 0, unsupported_count=1)
        msg = ctrl._status_callback.call_args.args[0]
        assert "実行できるモデルがありません" in msg


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

    def test_thread_finished_reenables_execute_buttons(self) -> None:
        """#1156: Batch dispatch thread 終了で実行ボタンロックを解除する。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()
        ctrl._annotate_tab = Mock()

        AnnotationWorkflowController._on_async_dispatch_thread_finished(ctrl)

        assert ctrl._async_dispatch_in_progress is False
        ctrl._annotate_tab.set_execution_running.assert_called_once_with(False)

    def test_thread_finished_noop_when_no_annotate_tab(self) -> None:
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController

        ctrl = Mock()
        ctrl._annotate_tab = None

        # annotate_tab 未注入でも例外を出さない
        AnnotationWorkflowController._on_async_dispatch_thread_finished(ctrl)
        assert ctrl._async_dispatch_in_progress is False

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


class TestStartAnnotationEntry:
    """start_annotation の dispatch mode 分岐テスト (ADR 0076 §1)。

    #896 PR4c で MainWindow から移送 (移送元: test_main_window_coverage.py の
    TestStartAnnotationDispatchMode)。run bar 実行ボタンのエントリ分岐を検証する。
    """

    def test_batch_api_mode_delegates_to_async_dispatch(self) -> None:
        """dispatch_mode=batch_api は async dispatch へ委譲し同期 workflow を起動しない。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")

        AnnotationWorkflowController.start_annotation(ctrl)

        ctrl.dispatch_async_batch.assert_called_once()
        ctrl.start_annotation_workflow.assert_not_called()

    def test_sync_mode_runs_workflow(self) -> None:
        """dispatch_mode=sync は従来どおり同期 workflow を起動する。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="sync")
        ctrl._annotate_tab.selected_litellm_model_ids.return_value = ["openai/gpt-4o"]
        # アノテーションタブ非アクティブ → ステージング override 経路を避ける
        ctrl._is_annotate_tab_active.return_value = False

        AnnotationWorkflowController.start_annotation(ctrl)

        ctrl.start_annotation_workflow.assert_called_once()
        ctrl.dispatch_async_batch.assert_not_called()

    def test_explicit_batch_mode_arg_overrides_run_options(self) -> None:
        """#1099: 実行ボタンが渡す dispatch_mode 引数が RunOptions より優先される。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        # RunOptions は sync だが、ボタン引数 batch_api が優先されるべき
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="sync")

        AnnotationWorkflowController.start_annotation(ctrl, "batch_api")

        ctrl.dispatch_async_batch.assert_called_once()
        ctrl.start_annotation_workflow.assert_not_called()

    def test_explicit_sync_mode_arg_overrides_run_options(self) -> None:
        """#1099: dispatch_mode="sync" 引数は async dispatch へ行かず同期 workflow を起動する。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")
        ctrl._annotate_tab.selected_litellm_model_ids.return_value = ["openai/gpt-4o"]
        ctrl._is_annotate_tab_active.return_value = False

        AnnotationWorkflowController.start_annotation(ctrl, "sync")

        ctrl.start_annotation_workflow.assert_called_once()
        ctrl.dispatch_async_batch.assert_not_called()

    def test_annotate_tab_active_with_empty_staging_aborts(self) -> None:
        """アノテーションタブがアクティブでステージング空なら info 表示し中止する (#896 PR4c)。"""
        from lorairo.gui.controllers.annotation_workflow_controller import AnnotationWorkflowController
        from lorairo.gui.widgets.run_settings_dialog import RunOptions

        ctrl = Mock()
        ctrl._annotate_tab.run_options.return_value = RunOptions(dispatch_mode="sync")
        ctrl._annotate_tab.selected_litellm_model_ids.return_value = ["openai/gpt-4o"]
        ctrl._is_annotate_tab_active.return_value = True
        ctrl._annotate_tab.staged_image_paths.return_value = []  # ステージング空

        with patch("lorairo.gui.controllers.annotation_workflow_controller.QMessageBox") as mock_qmb:
            AnnotationWorkflowController.start_annotation(ctrl)
            mock_qmb.information.assert_called_once()

        ctrl.start_annotation_workflow.assert_not_called()
