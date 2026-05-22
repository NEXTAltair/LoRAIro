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
