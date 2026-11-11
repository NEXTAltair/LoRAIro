"""起動時の縮退 (degrade) を起動時の警告ダイアログへ載せる配線のテスト (#1599)。

各箇所に失敗を注入し、実際の ``MainWindow.show_startup_notice`` がダイアログへ渡す
本文 / 詳細に、利用者向けの機能名と例外の詳細が出ることを確かめる。本文には内部
クラス名や例外文字列を入れない (詳細側にだけ出す) ことも合わせて検証する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lorairo.gui.window.main_window import MainWindow
from lorairo.gui.workers.tag_db_warmup_worker import TagDbWarmupResult

_SECRET_ERROR = "internal-boom-1599"


def _degradable_window(**attrs: Any) -> Mock:
    """show_startup_notice が読む状態を初期値で持つ Mock window を作る。"""
    window = Mock()
    window._startup_warnings = []
    window._startup_warning_details = {}
    window._startup_notice_shown = False
    window._startup_notified_count = 0
    window._initialization_failed = False
    window._initialization_error = None
    window._closing = False
    for name, value in attrs.items():
        setattr(window, name, value)
    # 後から通知する経路 (warmup) は self.show_startup_notice() を呼ぶため実体を割り当てる
    window.show_startup_notice = lambda: MainWindow.show_startup_notice(window)
    return window


@pytest.fixture
def captured_warnings(monkeypatch: pytest.MonkeyPatch) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """main_window.show_warning に渡った引数を記録する。"""
    shown: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.show_warning",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )
    return shown


def _assert_notice(
    shown: list[tuple[tuple[Any, ...], dict[str, Any]]], feature_name: str, error_text: str
) -> None:
    """1 回だけ通知され、機能名と例外が詳細側にだけ出ていることを確認する。"""
    assert len(shown) == 1
    args, kwargs = shown[0]
    body = args[2]
    detail = kwargs["detail"]
    assert feature_name in detail
    assert error_text in detail
    # 本文に例外文字列・内部クラス名を出さない
    assert error_text not in body
    assert "Widget" not in body
    assert "Error" not in body


@pytest.mark.unit
class TestSignalConnectionFailuresAreNotified:
    """シグナル接続の except ブロックが起動時の警告に載る。"""

    def test_search_tab_signal_failure(self, captured_warnings) -> None:
        window = _degradable_window()
        window.search_tab.stage_to_annotation_requested.connect.side_effect = RuntimeError(_SECRET_ERROR)

        MainWindow._connect_search_tab_signals(window)

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, "検索タブの操作ボタン", _SECRET_ERROR)

    def test_edit_menu_failure(self, captured_warnings) -> None:
        window = _degradable_window()
        window.actionSelectAll.triggered.connect.side_effect = RuntimeError(_SECRET_ERROR)

        MainWindow._connect_menu_actions(window)

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, "編集メニューの全選択/選択解除", _SECRET_ERROR)

    def test_annotate_tab_signal_failure(self, captured_warnings) -> None:
        window = _degradable_window()
        window.annotate_tab.status_message.connect.side_effect = RuntimeError(_SECRET_ERROR)

        MainWindow._connect_batch_tag_signals(window)

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, "アノテーションタブの実行ボタン", _SECRET_ERROR)

    def test_panel_toggle_failure(self, captured_warnings) -> None:
        window = _degradable_window()
        window.actionToggleFilterPanel.toggled.connect.side_effect = RuntimeError(_SECRET_ERROR)

        MainWindow._connect_panel_toggle_actions(window)

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, "表示メニューのパネル表示切替", _SECRET_ERROR)

    def test_connect_events_outer_failure(self, captured_warnings) -> None:
        window = _degradable_window()
        window._setup_worker_pipeline_signals.side_effect = RuntimeError(_SECRET_ERROR)

        MainWindow._connect_events(window)

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, "メニュー操作と処理の進捗表示", _SECRET_ERROR)


@pytest.mark.unit
class TestTagDbWarmupFailureIsNotifiedLater:
    """起動直後通知より後に終わるタグ DB 準備の失敗を後から通知する。"""

    def test_worker_error_is_notified(self, captured_warnings) -> None:
        window = _degradable_window()

        MainWindow._on_tag_db_warmup_done(window, _SECRET_ERROR)

        _assert_notice(captured_warnings, "タグの翻訳表示とタグ補完", _SECRET_ERROR)
        # 通知より先にタブへ反映している
        window.search_tab.on_tag_db_ready.assert_called_once_with()

    def test_reader_unavailable_is_notified(self, captured_warnings) -> None:
        window = _degradable_window()

        MainWindow._on_tag_db_warmup_done(
            window, TagDbWarmupResult(reader_ready=False, tag_management_ready=True)
        )

        assert len(captured_warnings) == 1
        assert "タグの翻訳表示とタグ補完" in captured_warnings[0][1]["detail"]

    def test_tag_management_unavailable_is_notified(self, captured_warnings) -> None:
        window = _degradable_window()

        MainWindow._on_tag_db_warmup_done(
            window, TagDbWarmupResult(reader_ready=True, tag_management_ready=False)
        )

        assert len(captured_warnings) == 1
        detail = captured_warnings[0][1]["detail"]
        assert "未分類タグの整理" in detail
        assert "タグの翻訳表示とタグ補完" not in detail

    def test_success_and_cancel_are_not_notified(self, captured_warnings) -> None:
        window = _degradable_window()

        MainWindow._on_tag_db_warmup_done(window, TagDbWarmupResult(True, True))
        MainWindow._on_tag_db_warmup_done(window, None)

        assert captured_warnings == []
        assert window._startup_warnings == []

    def test_late_failure_after_startup_notice_shows_only_new_items(self, captured_warnings) -> None:
        window = _degradable_window()
        MainWindow._record_startup_warning(window, "マップタブ", "MapTabWidget: x")
        assert MainWindow.show_startup_notice(window) is True

        MainWindow._on_tag_db_warmup_done(window, _SECRET_ERROR)

        assert len(captured_warnings) == 2
        late_args, late_kwargs = captured_warnings[1]
        assert "起動後の準備処理" in late_args[2]
        assert "タグの翻訳表示とタグ補完" in late_kwargs["detail"]
        assert "マップタブ" not in late_kwargs["detail"]
        # 通知済みの内容しか無ければ何もしない
        assert MainWindow.show_startup_notice(window) is False


@pytest.mark.unit
def test_existing_component_failure_uses_feature_name(captured_warnings, monkeypatch) -> None:
    """既存の記録箇所も利用者向けの機能名で載り、クラス名は詳細側に残る。"""

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(_SECRET_ERROR)

    monkeypatch.setattr("lorairo.gui.window.main_window.JobsTabWidget", _raise)
    window = _degradable_window()

    MainWindow._setup_jobs_tab(window)

    assert window.jobs_tab is None
    assert MainWindow.show_startup_notice(window) is True
    _assert_notice(captured_warnings, "ジョブタブ", _SECRET_ERROR)
    assert "JobsTabWidget" in captured_warnings[0][1]["detail"]


@pytest.mark.gui
def test_annotate_tab_load_failures_reach_startup_notice(qtbot, monkeypatch, captured_warnings) -> None:
    """実 AnnotateTabWidget の読み込み失敗 (壊れたプリセット / API キー設定) が通知に出る。"""
    from lorairo.gui.state.dataset_state import DatasetStateManager
    from lorairo.gui.state.staging_state import StagingStateManager
    from lorairo.gui.tab.annotate_tab import AnnotateTabWidget

    class _BrokenPresetSettings:
        def value(self, *_args: Any, **_kwargs: Any) -> str:
            return "{not valid json"

        def setValue(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def sync(self) -> None:
            return None

    monkeypatch.setattr(AnnotateTabWidget, "_preset_settings", lambda self: _BrokenPresetSettings())

    service_container = Mock()
    service_container.db_manager.model_repo.get_model_objects.return_value = []
    service_container.annotator_library = None
    service_container.config_service.get_setting.side_effect = TypeError(_SECRET_ERROR)
    db_manager = Mock()
    db_manager.image_repo.get_latest_normalized_ratings_by_image_ids.return_value = {}

    container = QWidget()
    QVBoxLayout(container)
    qtbot.addWidget(container)
    window = _degradable_window(
        tabBatchTag=container,
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=StagingStateManager(),
        dataset_state_manager=DatasetStateManager(),
        model_selection_state_manager=None,
    )

    MainWindow._setup_annotate_tab(window)
    tab = window.annotate_tab
    assert isinstance(tab, AnnotateTabWidget)

    try:
        assert MainWindow.show_startup_notice(window) is True
        args, kwargs = captured_warnings[0]
        detail = kwargs["detail"]
        assert "保存済みのカスタムプリセット" in detail
        assert "JSONDecodeError" in detail
        assert "WebAPI モデルの API キー判定" in detail
        assert _SECRET_ERROR in detail
        assert _SECRET_ERROR not in args[2]
        assert "JSONDecodeError" not in args[2]
    finally:
        tab.shutdown()


@pytest.mark.unit
def test_settings_apply_failure_after_key_dialog_is_reported(monkeypatch) -> None:
    """API キー設定後の反映失敗を黙って握らず、利用者へ知らせる (#1599)。"""
    shown: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        "lorairo.gui.window.main_window.show_warning",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )
    window = Mock()
    window.settings_controller.open_settings_dialog.return_value = True
    window._on_settings_changed.side_effect = RuntimeError(_SECRET_ERROR)

    MainWindow._on_annotate_configure_key_requested(window, "anthropic")

    assert len(shown) == 1
    args, kwargs = shown[0]
    assert _SECRET_ERROR in kwargs["detail"]
    assert _SECRET_ERROR not in args[2]
    window.annotate_tab.refresh.assert_called_once_with()
