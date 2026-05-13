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
