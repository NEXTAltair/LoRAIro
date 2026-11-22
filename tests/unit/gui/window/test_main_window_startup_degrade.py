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
from sqlalchemy.exc import SQLAlchemyError

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
    # self._record_startup_warning(...) で記録する箇所も実体を通す
    window._record_startup_warning = lambda *args, **kwargs: MainWindow._record_startup_warning(
        window, *args, **kwargs
    )
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


# == #1610: 起動経路の except を具体的な例外型へ絞り込む ================================
#
# 各ブロックについて、(1) 想定内の代表例外では継続して起動時の警告に載せ、(2) 想定外の
# 例外は握りつぶさず呼び出し元 (MainWindow.__init__ の初期化失敗経路など) へ伝播する、
# ことを確かめる。


class _UnexpectedStartupError(Exception):
    """絞り込んだ例外型のどれにも当たらない、想定外の例外。"""


_QT_WIRING = (AttributeError, RuntimeError)
_SERVICE_WIRING = (
    AttributeError,
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    SQLAlchemyError,
    ValueError,
)


def _services_window(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """_initialize_services を最後まで通せるよう依存を差し替えた Mock window を作る。"""
    window = _degradable_window()
    for name in ("get_service_container", "ConfigurationService", "WorkerService", "DatasetStateManager"):
        monkeypatch.setattr(f"lorairo.gui.window.main_window.{name}", Mock())
    return window


def _case_file_system_manager(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _services_window(monkeypatch)

    def inject(exc: Exception) -> None:
        window._create_project_file_system_manager.side_effect = exc

    return window, inject, lambda: MainWindow._initialize_services(window)


def _case_dataset_state_manager(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _services_window(monkeypatch)

    def inject(exc: Exception) -> None:
        monkeypatch.setattr("lorairo.gui.window.main_window.DatasetStateManager", Mock(side_effect=exc))

    return window, inject, lambda: MainWindow._initialize_services(window)


def _case_staging_state_manager(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()
    staging_class = Mock()
    monkeypatch.setattr("lorairo.gui.window.main_window.StagingStateManager", staging_class)

    def inject(exc: Exception) -> None:
        staging_class.return_value.staged_images_changed.connect.side_effect = exc

    return window, inject, lambda: MainWindow._initialize_staging_state_manager(window)


def _case_controllers(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        monkeypatch.setattr("lorairo.gui.window.main_window.SelectionStateService", Mock(side_effect=exc))

    return window, inject, lambda: MainWindow._setup_other_custom_widgets(window)


def _patched_component_case(
    monkeypatch: pytest.MonkeyPatch, class_name: str, method: str, **attrs: Any
) -> tuple[Mock, Any, Any]:
    """コンポーネント生成クラスを例外送出に差し替える case を作る。"""
    window = _degradable_window(**attrs)

    def inject(exc: Exception) -> None:
        monkeypatch.setattr(f"lorairo.gui.window.main_window.{class_name}", Mock(side_effect=exc))

    return window, inject, lambda: getattr(MainWindow, method)(window)


def _case_map_tab(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    container = Mock()
    container.layout.return_value.count.return_value = 0
    return _patched_component_case(monkeypatch, "MapTabWidget", "_setup_map_tab", tabMap=container)


def _case_jobs_tab(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    return _patched_component_case(monkeypatch, "JobsTabWidget", "_setup_jobs_tab")


def _case_error_notification(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    return _patched_component_case(monkeypatch, "ErrorNotificationWidget", "_setup_error_notification")


def _case_phase24_services(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    return _patched_component_case(monkeypatch, "ResultHandlerService", "_setup_phase24_services")


def _case_search_tab_signals(_monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        window.search_tab.stage_to_annotation_requested.connect.side_effect = exc

    return window, inject, lambda: MainWindow._connect_search_tab_signals(window)


def _case_edit_menu(_monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        window.actionSelectAll.triggered.connect.side_effect = exc

    return window, inject, lambda: MainWindow._connect_menu_actions(window)


def _case_annotate_tab_signals(_monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        window.annotate_tab.status_message.connect.side_effect = exc

    return window, inject, lambda: MainWindow._connect_batch_tag_signals(window)


def _case_panel_toggle(_monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        window.actionToggleFilterPanel.toggled.connect.side_effect = exc

    return window, inject, lambda: MainWindow._connect_panel_toggle_actions(window)


def _case_connect_events(_monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Any, Any]:
    window = _degradable_window()

    def inject(exc: Exception) -> None:
        window._setup_worker_pipeline_signals.side_effect = exc

    return window, inject, lambda: MainWindow._connect_events(window)


# (case id, builder, 起動時の警告に載る機能名, 継続してよい代表例外)
_NOTIFIED_CASES = [
    pytest.param(
        _case_file_system_manager,
        "画像ファイルの保存先管理",
        (OSError, RuntimeError),
        id="file_system_manager",
    ),
    pytest.param(
        _case_dataset_state_manager, "画像の選択と表示", (RuntimeError,), id="dataset_state_manager"
    ),
    pytest.param(_case_staging_state_manager, "ステージング", _QT_WIRING, id="staging_state_manager"),
    pytest.param(
        _case_controllers, "アノテーション実行・データセット登録・設定", _QT_WIRING, id="controllers"
    ),
    pytest.param(_case_map_tab, "マップタブ", _QT_WIRING, id="map_tab"),
    pytest.param(_case_jobs_tab, "ジョブタブ", _SERVICE_WIRING, id="jobs_tab"),
    pytest.param(
        _case_error_notification, "ステータスバーのエラー件数表示", _QT_WIRING, id="error_notification"
    ),
    pytest.param(
        _case_phase24_services, "検索・処理の進捗表示とキャンセル", _QT_WIRING, id="phase24_services"
    ),
    pytest.param(_case_search_tab_signals, "検索タブの操作ボタン", _QT_WIRING, id="search_tab_signals"),
    pytest.param(_case_edit_menu, "編集メニューの全選択/選択解除", _QT_WIRING, id="edit_menu"),
    pytest.param(
        _case_annotate_tab_signals, "アノテーションタブの実行ボタン", _QT_WIRING, id="annotate_tab_signals"
    ),
    pytest.param(_case_panel_toggle, "表示メニューのパネル表示切替", _QT_WIRING, id="panel_toggle"),
    pytest.param(_case_connect_events, "メニュー操作と処理の進捗表示", _QT_WIRING, id="connect_events"),
]


def _expected_exception_cases() -> list[Any]:
    """(case, feature_name, 例外型) を 1 例外型ごとに展開する。"""
    expanded = []
    for param in _NOTIFIED_CASES:
        builder, feature_name, exception_types = param.values
        for exception_type in exception_types:
            expanded.append(
                pytest.param(
                    builder, feature_name, exception_type, id=f"{param.id}-{exception_type.__name__}"
                )
            )
    return expanded


@pytest.mark.unit
class TestNarrowedStartupExceptions:
    """絞り込んだ except は想定内で継続・通知し、想定外は伝播する (#1610)。"""

    @pytest.mark.parametrize(("builder", "feature_name", "exception_type"), _expected_exception_cases())
    def test_expected_exception_continues_and_notifies(
        self,
        builder: Any,
        feature_name: str,
        exception_type: type[Exception],
        captured_warnings,
        monkeypatch,
    ) -> None:
        window, inject, run = builder(monkeypatch)
        inject(exception_type(_SECRET_ERROR))

        run()

        assert MainWindow.show_startup_notice(window) is True
        _assert_notice(captured_warnings, feature_name, _SECRET_ERROR)

    @pytest.mark.parametrize("builder", [pytest.param(p.values[0], id=p.id) for p in _NOTIFIED_CASES])
    def test_unexpected_exception_propagates(self, builder: Any, monkeypatch) -> None:
        window, inject, run = builder(monkeypatch)
        inject(_UnexpectedStartupError(_SECRET_ERROR))

        with pytest.raises(_UnexpectedStartupError):
            run()

        # 握りつぶされず、起動時の警告にも載っていない
        assert window._startup_warnings == []


_SERVICE_WIRING_PARAMS = [pytest.param(exc, id=exc.__name__) for exc in _SERVICE_WIRING]


@pytest.mark.unit
class TestNarrowedLazyHandlers:
    """起動後の遅延ハンドラ (設定反映・タグ管理ダイアログ) の絞り込み (#1610)。

    これらは ``MainWindow.__init__`` の外で動くため、想定外の例外の伝播先は Qt の
    スロット呼び出し元 (または各メソッドの外側にある既存ハンドラ) になる。
    """

    @pytest.mark.parametrize("exception_type", _SERVICE_WIRING_PARAMS)
    def test_results_review_reload_failure_shows_reason_and_continues(
        self, exception_type: type[Exception], monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "lorairo.services.annotation_review_service.AnnotationReviewService",
            Mock(side_effect=exception_type(_SECRET_ERROR)),
        )
        monkeypatch.setattr("lorairo.gui.window.main_window.get_service_container", Mock())
        window = _degradable_window()

        MainWindow._reload_results_annotation_review_service(window)

        window.results_tab.set_annotation_review_unavailable_reason.assert_called_once()
        window.results_tab.set_annotation_review_services.assert_not_called()

    def test_results_review_reload_unexpected_exception_propagates(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "lorairo.services.annotation_review_service.AnnotationReviewService",
            Mock(side_effect=_UnexpectedStartupError(_SECRET_ERROR)),
        )
        monkeypatch.setattr("lorairo.gui.window.main_window.get_service_container", Mock())
        window = _degradable_window()

        with pytest.raises(_UnexpectedStartupError):
            MainWindow._reload_results_annotation_review_service(window)

        window.results_tab.set_annotation_review_unavailable_reason.assert_not_called()

    @pytest.mark.parametrize("exception_type", _SERVICE_WIRING_PARAMS)
    def test_model_widget_reload_failure_continues(
        self, exception_type: type[Exception], monkeypatch
    ) -> None:
        monkeypatch.setattr("lorairo.gui.window.main_window.get_service_container", Mock())
        window = _degradable_window()
        window.annotate_tab.refresh_model_selection.side_effect = exception_type(_SECRET_ERROR)

        MainWindow._reload_model_widget_after_settings(window)

        window.annotate_tab.refresh_model_selection.assert_called_once_with()

    def test_model_widget_reload_unexpected_exception_propagates(self, monkeypatch) -> None:
        monkeypatch.setattr("lorairo.gui.window.main_window.get_service_container", Mock())
        window = _degradable_window()
        window.annotate_tab.refresh_model_selection.side_effect = _UnexpectedStartupError(_SECRET_ERROR)

        with pytest.raises(_UnexpectedStartupError):
            MainWindow._reload_model_widget_after_settings(window)

    @pytest.mark.parametrize("exception_type", _SERVICE_WIRING_PARAMS)
    def test_settings_apply_failure_is_reported_and_tab_refreshed(
        self, exception_type: type[Exception], monkeypatch
    ) -> None:
        shown: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.show_warning",
            lambda *args, **kwargs: shown.append((args, kwargs)),
        )
        window = Mock()
        window.settings_controller.open_settings_dialog.return_value = True
        window._on_settings_changed.side_effect = exception_type(_SECRET_ERROR)

        MainWindow._on_annotate_configure_key_requested(window, "anthropic")

        assert len(shown) == 1
        assert _SECRET_ERROR in shown[0][1]["detail"]
        window.annotate_tab.refresh.assert_called_once_with()

    def test_settings_apply_unexpected_exception_propagates(self, monkeypatch) -> None:
        shown: list[Any] = []
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.show_warning", lambda *args, **kwargs: shown.append(args)
        )
        window = Mock()
        window.settings_controller.open_settings_dialog.return_value = True
        window._on_settings_changed.side_effect = _UnexpectedStartupError(_SECRET_ERROR)

        with pytest.raises(_UnexpectedStartupError):
            MainWindow._on_annotate_configure_key_requested(window, "anthropic")

        assert shown == []
        window.annotate_tab.refresh.assert_not_called()

    @staticmethod
    def _tag_dialog_window(exc: Exception, monkeypatch) -> tuple[Mock, Mock]:
        """refinement_service の取得が exc で失敗する service_container を持つ window を作る。"""

        class _Container:
            tag_management_service = Mock()

            @property
            def refinement_service(self) -> None:
                raise exc

        dialog_class = Mock()
        monkeypatch.setattr("lorairo.gui.window.main_window.TagManagementDialog", dialog_class)
        window = Mock()
        window.tag_management_dialog = None
        window.service_container = _Container()
        return window, dialog_class

    @pytest.mark.parametrize("exception_type", _SERVICE_WIRING_PARAMS)
    def test_tag_dialog_degrades_without_refinement_service(
        self, exception_type: type[Exception], monkeypatch
    ) -> None:
        window, dialog_class = self._tag_dialog_window(exception_type(_SECRET_ERROR), monkeypatch)

        MainWindow._show_tag_management_dialog(window)

        assert dialog_class.call_args.kwargs["refinement_service"] is None
        dialog_class.return_value.show.assert_called_once_with()

    def test_tag_dialog_unexpected_refinement_error_reaches_outer_handler(self, monkeypatch) -> None:
        """想定外の例外は握らず、外側の「タグ管理の表示に失敗」ハンドラが利用者へ見せる。"""
        shown: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.show_critical", lambda *args, **kwargs: shown.append(args)
        )
        window, dialog_class = self._tag_dialog_window(_UnexpectedStartupError(_SECRET_ERROR), monkeypatch)

        MainWindow._show_tag_management_dialog(window)

        dialog_class.assert_not_called()
        assert len(shown) == 1
        assert _SECRET_ERROR in shown[0][2]
