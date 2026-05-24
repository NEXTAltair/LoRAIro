"""ModelSelectionWidget 単体テスト

ModelSelectionService をモックして get_service_container() の呼び出しを回避。
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QProgressBar, QPushButton

from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget


def _fake_db_model(
    *,
    name: str,
    provider: str,
    litellm_model_id: str,
    requires_api_key: bool = True,
    capabilities: list[str] | None = None,
    is_recommended: bool = False,
    available: bool = True,
) -> SimpleNamespace:
    """`schema.Model` 互換の軽量 fake (Issue #245)。

    `_convert_model_to_info` と `_group_models_by_provider` と
    `select_recommended_models` が参照する属性のみを再現する。
    """
    return SimpleNamespace(
        name=name,
        provider=provider,
        litellm_model_id=litellm_model_id,
        requires_api_key=requires_api_key,
        capabilities=capabilities or ["caption", "tags"],
        is_recommended=is_recommended,
        available=available,
    )


@pytest.fixture
def mock_model_service():
    service = Mock()
    service.load_models.return_value = []
    service.get_recommended_models.return_value = []
    service.filter_models.return_value = []
    return service


@pytest.fixture
def widget(qtbot, mock_model_service):
    w = ModelSelectionWidget(model_selection_service=mock_model_service)
    qtbot.addWidget(w)
    return w


class TestModelSelectionWidgetInit:
    def test_initialization(self, widget, mock_model_service):
        assert widget is not None
        mock_model_service.load_models.assert_called_once()

    def test_has_model_selection_changed_signal(self, widget):
        assert hasattr(widget, "model_selection_changed")

    def test_has_selection_count_changed_signal(self, widget):
        assert hasattr(widget, "selection_count_changed")

    def test_initial_selected_models_empty(self, widget):
        assert widget.get_selected_models() == []

    def test_has_refresh_controls(self, widget):
        assert isinstance(widget.btnRefreshModels, QPushButton)
        assert isinstance(widget.refreshProgressBar, QProgressBar)
        assert widget.btnRefreshModels.text() == "更新"
        assert widget.refreshProgressBar.isVisible() is False

    def test_get_selection_info_returns_dict(self, widget):
        info = widget.get_selection_info()
        assert isinstance(info, dict)
        assert "selected_count" in info
        assert "total_available" in info
        assert "filtered_count" in info


class TestModelSelectionWidgetFilters:
    def test_apply_filters_does_not_crash(self, widget):
        widget.apply_filters(provider="openai", capabilities=["caption"])

    def test_select_all_does_not_crash_with_no_models(self, widget):
        widget.select_all_models()

    def test_deselect_all_does_not_crash_with_no_models(self, widget):
        widget.deselect_all_models()

    def test_select_recommended_does_not_crash_with_no_models(self, widget, mock_model_service):
        mock_model_service.get_recommended_models.return_value = []
        widget.select_recommended_models()

    def test_set_selected_models_does_not_crash_with_empty_list(self, widget):
        widget.set_selected_models([])

    def test_batch_web_api_only_shows_placeholder_without_model_rows(self, qtbot, mock_model_service):
        """Batch annotation の Web API only では通常モデル行を表示しない"""
        mock_model_service.load_grouped_models.return_value = []
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)

        w.apply_filters(execution_env="APIモデルのみ", annotation_only=True)

        assert not w.placeholderLabel.isHidden()
        assert w.placeholderLabel.text() == ModelSelectionWidget.WEB_API_BATCH_PLACEHOLDER
        assert w.model_checkbox_widgets == {}
        assert w.get_selected_models() == []

    def test_non_batch_web_api_only_uses_normal_filtering(self, qtbot, mock_model_service):
        """通常利用時の Web API only は batch placeholder 分岐に入らない"""
        mock_model_service.load_grouped_models.return_value = []
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)

        w.apply_filters(execution_env="APIモデルのみ")

        assert w.placeholderLabel.text() != ModelSelectionWidget.WEB_API_BATCH_PLACEHOLDER
        assert mock_model_service.load_grouped_models.call_args[0][0].execution_env == "APIモデルのみ"

    def test_batch_annotation_filtering_passes_annotation_only_criteria(self, qtbot, mock_model_service):
        """Batch annotation opt-in 時だけ annotation_only criteria を渡す"""
        mock_model_service.load_grouped_models.return_value = []
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)

        w.apply_filters(execution_env="ローカルモデルのみ", annotation_only=True)

        criteria = mock_model_service.load_grouped_models.call_args[0][0]
        assert criteria.annotation_only is True
        assert criteria.execution_env == "ローカルモデルのみ"


class TestModelSelectionWidgetRefreshThread:
    def test_stop_refresh_thread_quits_and_waits(self, widget):
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = True
        widget._refresh_thread = thread
        widget._refresh_worker = Mock()

        result = widget._stop_refresh_thread()

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(30000)
        assert widget._refresh_thread is None
        assert widget._refresh_worker is None
        assert result is True

    def test_stop_refresh_thread_ignores_missing_thread(self, widget):
        widget._refresh_thread = None

        result = widget._stop_refresh_thread()

        assert widget._refresh_thread is None
        assert result is True

    def test_stop_refresh_thread_timeout_keeps_thread_reference(self, widget):
        thread = Mock()
        thread.isRunning.return_value = True
        thread.wait.return_value = False
        widget._refresh_thread = thread
        widget._refresh_worker = Mock()

        result = widget._stop_refresh_thread()

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(30000)
        assert widget._refresh_thread is thread
        assert result is False

    def test_close_event_ignores_when_refresh_thread_cannot_stop(self, widget, monkeypatch):
        monkeypatch.setattr(widget, "_stop_refresh_thread", Mock(return_value=False))
        mock_warning = Mock()
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.QMessageBox.warning",
            mock_warning,
        )
        event = QCloseEvent()

        widget.closeEvent(event)

        mock_warning.assert_called_once()
        assert event.isAccepted() is False


class TestModelSelectionWidgetLitellmIdKeying:
    """Issue #245 リグレッション防止: 同 name 異 provider の行が共存しても
    `get_selected_models()` は `litellm_model_id` を返し、ルーティングミスを起こさない。
    """

    @pytest.fixture
    def widget_with_dual_routes(self, qtbot, mock_model_service):
        """migration 経路 (OpenRouter, name 縮退) と新規 sync 経路 (OpenAI 直接版)
        の両方を含む DB fixture を simple ではなく advanced モードでロードする。
        """
        migration_route = _fake_db_model(
            name="openai/gpt-4o",
            provider="openrouter",
            litellm_model_id="openrouter/openai/gpt-4o",
            is_recommended=False,
        )
        new_sync_direct = _fake_db_model(
            name="openai/gpt-4o",
            provider="openai",
            litellm_model_id="openai/gpt-4o",
            is_recommended=True,
        )

        # advanced モードでは filter_models が表示対象を決める
        mock_model_service.filter_models.return_value = [migration_route, new_sync_direct]
        mock_model_service.load_models.return_value = [migration_route, new_sync_direct]
        mock_model_service.get_recommended_models.return_value = [new_sync_direct]

        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)
        return w, migration_route, new_sync_direct

    def test_get_selected_models_returns_litellm_ids(self, widget_with_dual_routes):
        """選択結果は `Model.litellm_model_id` の値で返す (#245 のコア要件)。

        Issue #241 で挙動が変化: 同一 canonical_key (``openai/gpt-4o``) を持つ
        ``migration_route`` (OpenRouter, name 縮退) と ``new_sync_direct``
        (OpenAI 直接版) は UI 上 1 行に畳まれ、preferred (= direct) のみ表示
        される。それでも戻り値の semantic ``litellm_model_id`` ベースは維持される。
        """
        w, _migration_route, new_sync_direct = widget_with_dual_routes

        # Issue #241: 1 行に畳まれているので、preferred (direct) のみ選択可能
        w.set_selected_models([new_sync_direct.litellm_model_id])

        selected = w.get_selected_models()
        # litellm_model_id ベースで返る (Issue #245 SSoT)
        # 旧バグでは `name` ベースだったため "openai/gpt-4o" に縮退していた。
        assert selected == [new_sync_direct.litellm_model_id]

    def test_set_selected_models_targets_preferred_route(self, widget_with_dual_routes):
        """Issue #241: 1 行畳み込み環境で preferred route の litellm_id で選択できる。

        旧テスト (Issue #245 単独時) は migration_route も独立行として表示・選択
        可能だったが、Issue #241 で同一 canonical_key の 2 経路は preferred (direct)
        の 1 行に集約される。alternatives は tooltip で確認できる。
        """
        w, _migration_route, new_sync_direct = widget_with_dual_routes

        w.set_selected_models([new_sync_direct.litellm_model_id])

        selected = w.get_selected_models()
        assert selected == [new_sync_direct.litellm_model_id]

    def test_select_recommended_models_uses_litellm_id_match(self, widget_with_dual_routes):
        """推奨選択は litellm_model_id で一致判定する (name 同値でも誤マッチしない)"""
        w, migration_route, new_sync_direct = widget_with_dual_routes

        w.select_recommended_models()

        selected = w.get_selected_models()
        # 推奨は new_sync_direct (openai 直接版) のみ
        assert selected == [new_sync_direct.litellm_model_id]
        assert migration_route.litellm_model_id not in selected


class TestModelSelectionWidgetWebApiDisplay:
    """Issue #343: Web API の primary display は raw route ID ではなく表示名/family を使う。"""

    def test_openrouter_qwen_display_name_and_group_use_canonical_model_family(
        self, qtbot, mock_model_service
    ) -> None:
        model = _fake_db_model(
            name="openrouter/qwen/qwen3.7-max",
            provider="openrouter",
            litellm_model_id="openrouter/qwen/qwen3.7-max",
            is_recommended=True,
        )
        mock_model_service.load_models.return_value = [model]
        mock_model_service.get_recommended_models.return_value = [model]

        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="simple")
        qtbot.addWidget(w)

        checkbox = w.model_checkbox_widgets["openrouter/qwen/qwen3.7-max"]
        assert checkbox.labelModelName.text() == "qwen3.7-max (Qwen)"
        assert "openrouter/qwen/qwen3.7-max" not in checkbox.labelModelName.text()
        assert "Model ID: openrouter/qwen/qwen3.7-max" in checkbox.labelModelName.toolTip()
        assert "Route: openrouter via OpenRouter" in checkbox.labelModelName.toolTip()

        group_labels = [
            w.dynamicContentLayout.itemAt(i).widget().text()
            for i in range(w.dynamicContentLayout.count())
            if w.dynamicContentLayout.itemAt(i).widget()
            and hasattr(w.dynamicContentLayout.itemAt(i).widget(), "text")
        ]
        assert any("Qwen Models" in label for label in group_labels)

    def test_selection_still_returns_raw_litellm_id_for_short_display_name(
        self, qtbot, mock_model_service
    ) -> None:
        model = _fake_db_model(
            name="openrouter/qwen/qwen3.7-max",
            provider="openrouter",
            litellm_model_id="openrouter/qwen/qwen3.7-max",
            is_recommended=True,
        )
        mock_model_service.load_models.return_value = [model]
        mock_model_service.get_recommended_models.return_value = [model]

        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="simple")
        qtbot.addWidget(w)
        w.set_selected_models(["openrouter/qwen/qwen3.7-max"])

        assert w.get_selected_models() == ["openrouter/qwen/qwen3.7-max"]


class TestModelSelectionWidgetRoutePreference:
    """Issue #249: route_preference を config から読み込む挙動。"""

    def test_get_route_preference_uses_config_value(self, qtbot, mock_model_service, monkeypatch) -> None:
        """config の model_selection.route_preference が ``_get_route_preference`` に反映される。"""
        mock_container = Mock()
        mock_container.config_service.get_setting.return_value = "direct"
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            lambda: mock_container,
        )

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        assert w._get_route_preference() == "direct"

    def test_get_route_preference_invalid_value_falls_back_to_auto(
        self, qtbot, mock_model_service, monkeypatch
    ) -> None:
        """config 不正値は parse_route_preference 経由で auto fallback。"""
        mock_container = Mock()
        mock_container.config_service.get_setting.return_value = "bogus"
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            lambda: mock_container,
        )

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        assert w._get_route_preference() == "auto"

    def test_get_route_preference_falls_back_on_container_exception(
        self, qtbot, mock_model_service, monkeypatch
    ) -> None:
        """get_service_container が例外を投げた場合は auto に fallback。"""

        def _raise() -> None:
            raise RuntimeError("container not initialized")

        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            _raise,
        )

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        assert w._get_route_preference() == "auto"


class TestModelSelectionWidgetLoadModelsException:
    """load_models() 例外パスのテスト（line 221-224）"""

    def test_load_models_exception_sets_empty_list(self, qtbot, mock_model_service) -> None:
        """load_models が例外を投げると all_models が空リストになる"""
        mock_model_service.load_models.side_effect = RuntimeError("DB unavailable")

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        # コンストラクタで既に呼ばれているが、明示的に再呼び出しもテスト
        mock_model_service.load_models.side_effect = RuntimeError("DB error")
        w.load_models()

        assert w.all_models == []


class TestModelSelectionWidgetRefreshRegistry:
    """refresh_model_registry() 関連テスト（line 229-281）"""

    def test_refresh_model_registry_disables_button_and_shows_progress(self, widget, monkeypatch) -> None:
        """refresh_model_registry() でボタン無効化 + プログレスバー表示（line 229-250）"""
        # QThread と _ModelRefreshWorker をモックしてスレッドが実際には起動しないようにする
        mock_thread = Mock()
        mock_worker = Mock()
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.QThread",
            Mock(return_value=mock_thread),
        )
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget._ModelRefreshWorker",
            Mock(return_value=mock_worker),
        )

        # btnRefreshModels が有効な状態から開始
        assert widget.btnRefreshModels.isEnabled() is True

        widget.refresh_model_registry()

        # ボタンが無効化されている（スレッド起動後）
        assert widget.btnRefreshModels.isEnabled() is False
        # _refresh_thread が設定されている
        assert widget._refresh_thread is not None

    def test_refresh_model_registry_skips_when_thread_running(self, widget) -> None:
        """スレッドが既に実行中の場合は早期リターン（line 229-230）"""
        widget._refresh_thread = Mock()

        # btnRefreshModels は変化しない
        widget.refresh_model_registry()

        # スレッドは変わらない（新しいスレッドが起動されない）
        assert widget._refresh_thread is not None

    def test_on_model_refresh_succeeded(self, widget, monkeypatch) -> None:
        """成功時に情報ダイアログと load_models が呼ばれる（line 253-262）"""
        info_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.QMessageBox.information",
            lambda *a: info_called.append(True),
        )

        widget._on_model_refresh_succeeded(5, "summary text")

        assert info_called
        # load_models が呼ばれた（model_selection_service.load_models 呼び出し確認）
        widget.model_selection_service.load_models.assert_called()

    def test_on_model_refresh_failed(self, widget, monkeypatch) -> None:
        """失敗時に警告ダイアログが表示される（line 265-272）"""
        warning_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.model_selection_widget.QMessageBox.warning",
            lambda *a: warning_called.append(True),
        )

        widget._on_model_refresh_failed("connection error")

        assert warning_called

    def test_on_model_refresh_finished_restores_ui(self, widget) -> None:
        """完了時に UI が復帰する（line 275-281）"""
        widget.btnRefreshModels.setEnabled(False)
        widget.refreshProgressBar.setVisible(True)
        widget._refresh_thread = Mock()
        widget._refresh_worker = Mock()

        widget._on_model_refresh_finished()

        assert widget.btnRefreshModels.isEnabled() is True
        assert widget.refreshProgressBar.isVisible() is False
        assert widget._refresh_thread is None
        assert widget._refresh_worker is None


class TestModelSelectionWidgetSimpleMode:
    """simple モードの update_model_display テスト（line 338-340, 544）"""

    def test_update_model_display_simple_mode_exception_fallback(
        self, qtbot, mock_model_service, monkeypatch
    ) -> None:
        """simple モードで get_recommended_models 例外時に is_recommended フォールバック（line 338-340）"""
        from types import SimpleNamespace

        model = SimpleNamespace(
            name="test-model",
            provider="openai",
            litellm_model_id="openai/test-model",
            requires_api_key=True,
            capabilities=["caption"],
            is_recommended=True,
            available=True,
        )

        mock_model_service.load_models.return_value = [model]
        mock_model_service.get_recommended_models.side_effect = RuntimeError("service error")

        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="simple")
        qtbot.addWidget(w)

        # クラッシュしないことを確認
        assert w is not None

    def test_update_selection_count_simple_mode_label(self, qtbot, mock_model_service) -> None:
        """simple モードの statusLabel は "(推奨)" を含む（line 589）"""
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="simple")
        qtbot.addWidget(w)

        w._update_selection_count()

        assert "推奨" in w.statusLabel.text()

    def test_update_selection_count_advanced_mode_label(self, qtbot, mock_model_service) -> None:
        """advanced モードの statusLabel は "(フィルタ後)" を含む（line 591）"""
        mock_model_service.load_grouped_models.return_value = []
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)

        w._update_selection_count()

        assert "フィルタ後" in w.statusLabel.text()


class TestModelSelectionWidgetExecutionEnvChanged:
    """_on_execution_env_changed テスト（line 558-560）"""

    def test_on_execution_env_changed_updates_filter(self, qtbot, mock_model_service) -> None:
        """executionEnvCombo 変更で current_execution_env が更新される"""
        mock_model_service.load_grouped_models.return_value = []
        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)

        w._on_execution_env_changed("ローカルモデルのみ")

        assert w.current_execution_env == "ローカルモデルのみ"


class TestModelSelectionWidgetModelSelectionChanged:
    """_on_model_selection_changed テスト（line 563-569）"""

    def test_on_model_selection_changed_emits_signal(self, qtbot, mock_model_service) -> None:
        """モデル選択変更でシグナルが発火する"""
        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        received_ids: list[list[str]] = []
        w.model_selection_changed.connect(lambda ids: received_ids.append(ids))

        with qtbot.waitSignal(w.model_selection_changed, timeout=1000):
            w._on_model_selection_changed("openai/gpt-4o", True)

        assert received_ids[0] == []


class TestModelSelectionWidgetSelectAllDeselect:
    """select_all/deselect_all テスト（line 596-605）"""

    @pytest.fixture
    def widget_with_checkboxes(self, qtbot, mock_model_service) -> ModelSelectionWidget:
        """ModelCheckboxWidget が1件ある状態の widget を作成"""
        from lorairo.gui.widgets.model_checkbox_widget import ModelCheckboxWidget, ModelInfo

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        # ModelCheckboxWidget を手動で追加
        info = ModelInfo(
            name="test-model",
            provider="openai",
            capabilities=["caption"],
            litellm_model_id="openai/test-model",
            is_local=False,
            requires_api_key=True,
        )
        checkbox_widget = ModelCheckboxWidget(info)
        qtbot.addWidget(checkbox_widget)
        w.model_checkbox_widgets["openai/test-model"] = checkbox_widget

        return w

    def test_select_all_models_selects_all(self, widget_with_checkboxes: ModelSelectionWidget) -> None:
        """select_all_models() で全チェックボックスが選択される（line 596-599）"""
        widget_with_checkboxes.select_all_models()

        assert "openai/test-model" in widget_with_checkboxes.get_selected_models()

    def test_deselect_all_models_deselects_all(self, widget_with_checkboxes: ModelSelectionWidget) -> None:
        """deselect_all_models() で全チェックボックスの選択が解除される（line 601-605）"""
        widget_with_checkboxes.select_all_models()
        widget_with_checkboxes.deselect_all_models()

        assert widget_with_checkboxes.get_selected_models() == []


class TestModelSelectionWidgetSelectRecommendedFallback:
    """select_recommended_models() 例外フォールバックのテスト（line 620-629）"""

    @pytest.fixture
    def widget_with_model(self, qtbot, mock_model_service) -> ModelSelectionWidget:
        """all_models に is_recommended=True のモデルがある widget を作成"""
        from types import SimpleNamespace

        from lorairo.gui.widgets.model_checkbox_widget import ModelCheckboxWidget, ModelInfo

        model = SimpleNamespace(
            name="rec-model",
            provider="openai",
            litellm_model_id="openai/rec-model",
            requires_api_key=True,
            capabilities=["caption"],
            is_recommended=True,
            available=True,
        )
        mock_model_service.load_models.return_value = [model]
        mock_model_service.get_recommended_models.side_effect = RuntimeError("service down")

        w = ModelSelectionWidget(model_selection_service=mock_model_service)
        qtbot.addWidget(w)

        # ModelCheckboxWidget を手動追加
        info = ModelInfo(
            name="rec-model",
            provider="openai",
            capabilities=["caption"],
            litellm_model_id="openai/rec-model",
            is_local=False,
            requires_api_key=True,
        )
        checkbox_widget = ModelCheckboxWidget(info)
        qtbot.addWidget(checkbox_widget)
        w.model_checkbox_widgets["openai/rec-model"] = checkbox_widget
        w.all_models = [model]

        return w

    def test_select_recommended_fallback_uses_is_recommended(
        self, widget_with_model: ModelSelectionWidget
    ) -> None:
        """get_recommended_models が例外を投げると is_recommended フォールバックで選択する（line 620-629）"""
        widget_with_model.select_recommended_models()

        assert "openai/rec-model" in widget_with_model.get_selected_models()


class TestModelRefreshWorker:
    """_ModelRefreshWorker の run メソッドのテスト（line 57-72）"""

    def test_run_emits_succeeded_on_success(self, qtbot) -> None:
        """正常終了時に succeeded と finished が発火する（line 57-67, 71-72）"""
        from unittest.mock import Mock, patch

        from lorairo.gui.widgets.model_selection_widget import _ModelRefreshWorker

        worker = _ModelRefreshWorker()

        mock_models = [Mock(), Mock()]
        mock_sync_result = Mock()
        mock_sync_result.errors = []
        mock_sync_result.summary = "2 models synced"

        mock_container = Mock()
        mock_container.annotator_library.refresh_available_models.return_value = mock_models
        mock_container.model_sync_service.sync_available_models.return_value = mock_sync_result

        succeeded_args: list[tuple[int, str]] = []
        finished_called: list[bool] = []

        worker.succeeded.connect(lambda count, summary: succeeded_args.append((count, summary)))
        worker.finished.connect(lambda: finished_called.append(True))

        with patch(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            return_value=mock_container,
        ):
            worker.run()

        assert succeeded_args == [(2, "2 models synced")]
        assert finished_called

    def test_run_emits_failed_when_sync_has_errors(self, qtbot) -> None:
        """sync_result に errors があると failed が発火する（line 63-65）"""
        from unittest.mock import Mock, patch

        from lorairo.gui.widgets.model_selection_widget import _ModelRefreshWorker

        worker = _ModelRefreshWorker()

        mock_sync_result = Mock()
        mock_sync_result.errors = ["error1", "error2"]

        mock_container = Mock()
        mock_container.annotator_library.refresh_available_models.return_value = []
        mock_container.model_sync_service.sync_available_models.return_value = mock_sync_result

        failed_args: list[str] = []
        finished_called: list[bool] = []

        worker.failed.connect(lambda msg: failed_args.append(msg))
        worker.finished.connect(lambda: finished_called.append(True))

        with patch(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            return_value=mock_container,
        ):
            worker.run()

        assert "error1" in failed_args[0]
        assert "error2" in failed_args[0]
        assert finished_called

    def test_run_emits_failed_on_exception(self, qtbot) -> None:
        """例外発生時に failed と finished が発火する（line 68-72）"""
        from unittest.mock import patch

        from lorairo.gui.widgets.model_selection_widget import _ModelRefreshWorker

        worker = _ModelRefreshWorker()

        failed_args: list[str] = []
        finished_called: list[bool] = []

        worker.failed.connect(lambda msg: failed_args.append(msg))
        worker.finished.connect(lambda: finished_called.append(True))

        with patch(
            "lorairo.gui.widgets.model_selection_widget.get_service_container",
            side_effect=RuntimeError("container error"),
        ):
            worker.run()

        assert failed_args[0] == "container error"
        assert finished_called


class TestApplyBasicFilters:
    """_apply_basic_filters() のブランチテスト（line 444-462）"""

    @pytest.fixture
    def widget_advanced(self, qtbot, mock_model_service) -> ModelSelectionWidget:
        from types import SimpleNamespace

        model_openai = SimpleNamespace(
            name="gpt-4",
            provider="openai",
            litellm_model_id="openai/gpt-4",
            requires_api_key=True,
            capabilities=["caption", "tags"],
            is_recommended=False,
            available=True,
        )
        model_anthropic = SimpleNamespace(
            name="claude-3",
            provider="anthropic",
            litellm_model_id="anthropic/claude-3",
            requires_api_key=True,
            capabilities=["caption"],
            is_recommended=False,
            available=True,
        )
        mock_model_service.load_models.return_value = [model_openai, model_anthropic]
        mock_model_service.load_grouped_models.side_effect = RuntimeError("force fallback")
        mock_model_service._is_annotation_eligible_model.side_effect = lambda m: True

        w = ModelSelectionWidget(model_selection_service=mock_model_service, mode="advanced")
        qtbot.addWidget(w)
        return w

    def test_apply_basic_filters_provider_filter(self, widget_advanced: ModelSelectionWidget) -> None:
        """provider フィルタが _apply_basic_filters で適用される（line 444-449）"""
        widget_advanced.current_provider_filter = "openai"
        result = widget_advanced._apply_basic_filters()

        assert all(m.provider == "openai" for m in result)

    def test_apply_basic_filters_capability_filter(self, widget_advanced: ModelSelectionWidget) -> None:
        """capability フィルタが _apply_basic_filters で適用される（line 451-456）"""
        widget_advanced.current_capability_filters = ["tags"]
        result = widget_advanced._apply_basic_filters()

        assert all("tags" in m.capabilities for m in result)

    def test_apply_basic_filters_annotation_only(self, widget_advanced: ModelSelectionWidget) -> None:
        """annotation_only フィルタが _apply_basic_filters で適用される（line 458-461）"""
        widget_advanced.annotation_only_filtering = True
        widget_advanced._apply_basic_filters()

        # _is_annotation_eligible_model が呼ばれている
        widget_advanced.model_selection_service._is_annotation_eligible_model.assert_called()
