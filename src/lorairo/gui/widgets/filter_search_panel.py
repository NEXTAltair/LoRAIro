# src/lorairo/gui/widgets/filter_search_panel.py
"""FilterSearchPanel: 統合検索・フィルタパネル (mediator)。

ADR 0036 に基づき、以下 4 つの sub-component を composition で保持する mediator:

- `PipelineStateMachine` (Qt-free): 6 状態の遷移ロジック
- `TagSuggestionWidget`: タグオートコンプリート + 非同期タスク
- `CountEstimateWidget`: 件数見積もり + 非同期タスク
- `FavoriteFilterPanel`: お気に入りフィルタの保存・読込・削除

`FilterSearchPanel` 本体は以下を担当する:
- 日付・解像度・レーティング・スコアフィルタの UI 構築
- sub-component とのコールバック / signal 連携 (mediator)
- WorkerService と SearchFilterService の依存注入と検索フロー

Signal/Slot 流通ルール (ADR 0036 §3):
- Sub-widget 同士の直接接続禁止
- Sub-widget → Parent はコールバック / シグナル経由
- Parent (mediator) が他 sub-widget や Service を呼ぶ

import 互換性: `PipelineState` Enum は本モジュールから引き続き export する。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLayout,
    QPushButton,
    QScrollArea,
    QWidget,
)

from ...gui.designer.FilterSearchPanel_ui import Ui_FilterSearchPanel
from ...gui.services.operation_events import OperationOutcome, OperationType, WorkerOperationEvent
from ...utils.log import logger
from .. import theme
from .count_estimate import CountEstimateWidget
from .custom_range_slider import CustomRangeSlider
from .favorite_filter import FavoriteFilterPanel
from .pipeline_state import PipelineState, PipelineStateMachine
from .search_facets_sidebar import SearchFacetsSidebar
from .tag_suggestion import TagSuggestionWidget

# 後方互換性: 旧 import path から PipelineState を export する
__all__ = ["FilterSearchPanel", "PipelineState"]

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...services.search_models import SearchConditions
    from ...services.tag_suggestion_service import TagSuggestionService
    from ..services.search_filter_service import SearchFilterService
    from ..services.worker_service import WorkerService


# レーティング chip の選択肢 (filter_value, 表示ラベル)。
# 番兵 UNRATED は手動行で「なし」、AI 行で「未設定」と表示し分ける (Issue #811)。
_MANUAL_RATING_OPTIONS: list[tuple[str, str]] = [
    ("PG", "PG"),
    ("PG-13", "PG-13"),
    ("R", "R"),
    ("X", "X"),
    ("XXX", "XXX"),
    ("UNRATED", "なし"),
]
_AI_RATING_OPTIONS: list[tuple[str, str]] = [
    ("PG", "PG"),
    ("PG-13", "PG-13"),
    ("R", "R"),
    ("X", "X"),
    ("XXX", "XXX"),
    ("UNRATED", "未設定"),
]
_RATING_COMBINE_OPTIONS: list[tuple[str, str]] = [("and", "AND"), ("or", "OR")]


def _rating_chip_qss(active: bool) -> str:
    """レーティング chip トグル 1 個分の QSS を返す (DS chip 文法、borders-not-shadows)。

    active = accent-soft 塗り + accent border + accent-hover 文字。inactive = card 地 +
    line border + ink-soft 文字 (hover で line-strong 強調)。ハードコード hex/px は使わず
    theme token のみを参照する (Issue #782 token / #811)。

    Args:
        active: chip が選択状態か。

    Returns:
        QPushButton 用の QSS 文字列。
    """
    if active:
        return (
            f"QPushButton {{ background-color: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 2px 10px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
    return (
        f"QPushButton {{ background-color: {theme.CARD}; color: {theme.INK_SOFT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; border-radius: {theme.RADIUS_CHIP}px;"
        f" padding: 2px 10px; font-size: {theme.FONT_SIZE_SMALL}px;"
        f" font-weight: {theme.FONT_WEIGHT_MEDIUM}; }}"
        f" QPushButton:hover {{ border-color: {theme.LINE_STRONG}; color: {theme.INK}; }}"
    )


class RatingChipToggleRow(QWidget):
    """レーティング値などを選択する chip トグルボタン行 (Issue #811)。

    checkable な flat ``QPushButton`` を ``QButtonGroup`` で束ねる。``exclusive=False``
    でマルチセレクト (レーティング選択集合 = OR)、``exclusive=True`` で単一選択
    (AND/OR 結合トグル) として使う。選択変更時に :data:`changed` を emit する。
    """

    changed = Signal()

    def __init__(
        self,
        options: list[tuple[str, str]],
        *,
        exclusive: bool,
        default: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """chip 行を構築する。

        Args:
            options: (filter_value, 表示ラベル) のリスト。
            exclusive: 単一選択にするか (True) マルチセレクトにするか (False)。
            default: 初期選択する filter_value (主に exclusive トグル用)。
            parent: 親 widget。
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._group = QButtonGroup(self)
        self._group.setExclusive(exclusive)
        self._buttons: dict[str, QPushButton] = {}
        for value, label in options:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            checked = value == default
            button.setChecked(checked)
            button.setStyleSheet(_rating_chip_qss(checked))
            button.toggled.connect(self._make_toggle_handler(button))
            self._group.addButton(button)
            self._buttons[value] = button
            layout.addWidget(button)

    def _make_toggle_handler(self, button: QPushButton) -> "Callable[[bool], None]":
        """chip の checked 状態に応じて QSS を更新し changed を emit するハンドラを返す。"""

        def handler(checked: bool) -> None:
            button.setStyleSheet(_rating_chip_qss(checked))
            self.changed.emit()

        return handler

    def selected_values(self) -> list[str]:
        """選択中の filter_value を選択順 (定義順) で返す。"""
        return [value for value, button in self._buttons.items() if button.isChecked()]

    def value(self) -> str | None:
        """単一選択トグルの現在値を返す (未選択時 None)。"""
        selected = self.selected_values()
        return selected[0] if selected else None

    def set_value(self, value: str) -> None:
        """指定 value を選択状態にする (排他グループでは他を自動解除)。"""
        button = self._buttons.get(value)
        if button is not None:
            button.setChecked(True)

    def clear(self) -> None:
        """全 chip を未選択にする (非排他グループ用)。"""
        for button in self._buttons.values():
            button.setChecked(False)


class FilterSearchPanel(QScrollArea):
    """統合検索・フィルターパネル (mediator)。

    タグ検索、キャプション検索、解像度フィルター、日付範囲フィルターを統合。
    Sub-component (Tag/Count/Favorite/Pipeline) を composition で保持する。
    """

    # お気に入りフィルター保存スキーマの版数 (#1060)。
    # 旧形式 (version キー無し) は _migrate_legacy_conditions で変換する。
    CONDITIONS_SCHEMA_VERSION = 2

    # シグナル
    filter_applied = Signal(dict)  # filter_conditions
    filter_cleared = Signal()
    search_requested = Signal(dict)  # search_conditions
    search_completed = Signal(dict)  # 検索結果

    # Pipeline State Management
    pipeline_state_changed = Signal(object)  # PipelineState

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # === 依存注入される Service ===
        self.search_filter_service: SearchFilterService | None = None
        self.worker_service: WorkerService | None = None

        # === Sub-component の生成 (ADR 0036 §2) ===
        self._pipeline = PipelineStateMachine()
        self._pipeline.register_listener(self._on_pipeline_state_changed)

        self._tag_suggestion = TagSuggestionWidget(self)
        self._count_estimate = CountEstimateWidget(self)
        self._favorite_filter = FavoriteFilterPanel(self)
        self._search_facets_sidebar = SearchFacetsSidebar(self)
        self._facet_values: dict[str, object] = {}

        # 現在の SearchWorker の ID
        self._current_search_worker_id: str | None = None

        # === UI 設定 ===
        self.ui = Ui_FilterSearchPanel()
        self.ui.setupUi(self)
        self.setup_custom_widgets()
        self._setup_sub_components()
        self.connect_signals()

        logger.debug("FilterSearchPanel initialized")

    # ============================================================
    # ===  UI セットアップ
    # ============================================================

    def setup_custom_widgets(self) -> None:
        """Qt DesignerのUIに日付範囲スライダー、スコア範囲スライダー、進捗表示、QButtonGroupを追加。"""
        from PySide6.QtWidgets import (
            QBoxLayout,
            QButtonGroup,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QProgressBar,
            QVBoxLayout,
        )

        # 日付範囲スライダー
        self.date_range_slider = CustomRangeSlider()
        self.date_range_slider.set_date_range()
        self._replace_placeholder(self.ui.dateRangeSliderPlaceholder, self.date_range_slider)

        # 登録日フィルタの導線 (checkbox) を見落とされないよう強調 (#821)
        self.ui.checkboxDateFilter.setStyleSheet(
            f"QCheckBox {{ font-weight: {theme.FONT_WEIGHT_BOLD}; color: {theme.INK}; }}"
        )

        # スコア範囲スライダー (内部値 0-1000、表示 0.00-10.00)
        self.score_range_slider = CustomRangeSlider(min_value=0, max_value=1000)
        self.score_range_slider.set_score_mode()

        score_group = QGroupBox("スコア範囲")
        score_layout = QVBoxLayout()
        score_layout.addWidget(self.score_range_slider)
        score_group.setLayout(score_layout)

        if hasattr(self.ui, "filterGroup"):
            filter_layout = self.ui.filterGroup.layout()
            if isinstance(filter_layout, QBoxLayout):
                filter_layout.addWidget(score_group)

        # QButtonGroup (論理演算子)
        self.logic_button_group = QButtonGroup(self)
        self.logic_button_group.addButton(self.ui.radioAnd)
        self.logic_button_group.addButton(self.ui.radioOr)
        self.ui.radioAnd.setChecked(True)

        # 進捗表示 UI
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)

        # ステータスラベル
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {theme.ERR}; font-size: 11px;")
        self._status_label.setVisible(False)

        # 進捗表示レイアウト
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_layout.addWidget(self._status_label)

        # 検索グループの最後に件数表示と進捗 UI を追加
        main_layout = self.ui.searchGroup.layout()
        if isinstance(main_layout, QBoxLayout):
            main_layout.addWidget(self._count_estimate)
            main_layout.addLayout(self.progress_layout)

        # レーティング chip トグル群 (Issue #811: dropdown → マルチセレクト chip)
        self._setup_rating_chips()

        # 廃止フラグ (登録時 pHash 重複防止により不要)
        self.ui.checkboxExcludeDuplicates.setChecked(False)
        self.ui.checkboxExcludeDuplicates.setVisible(False)
        # 廃止フラグ (レーティング選択から自動判定)
        self.ui.checkboxIncludeNSFW.setChecked(False)
        self.ui.checkboxIncludeNSFW.setVisible(False)

        # お気に入りフィルター UI をメインレイアウトに追加
        # Phase 4: Search サイドバー（フィルター UI の最後に追加）
        contents_layout = self.ui.scrollAreaWidgetContents.layout()
        if isinstance(contents_layout, QBoxLayout):
            insert_index = contents_layout.count() - 1
            contents_layout.insertWidget(insert_index, self._favorite_filter)
            contents_layout.addWidget(self._search_facets_sidebar)

    def _setup_rating_chips(self) -> None:
        """レーティング dropdown を chip トグル群へ置き換える (Issue #811)。

        手動 / AI それぞれをマルチセレクト chip 行に、両者の組合せ (AND/OR) を
        単一選択トグルに置き換え、Qt Designer の placeholder と差し替える。
        """
        self._rating_chips = RatingChipToggleRow(_MANUAL_RATING_OPTIONS, exclusive=False)
        self._ai_rating_chips = RatingChipToggleRow(_AI_RATING_OPTIONS, exclusive=False)
        self._rating_combine_toggle = RatingChipToggleRow(
            _RATING_COMBINE_OPTIONS, exclusive=True, default="and"
        )

        self._replace_placeholder(self.ui.ratingChipPlaceholder, self._rating_chips)
        self._replace_placeholder(self.ui.aiRatingChipPlaceholder, self._ai_rating_chips)
        self._replace_placeholder(self.ui.ratingCombinePlaceholder, self._rating_combine_toggle)

    @staticmethod
    def _replace_placeholder(placeholder: QWidget, widget: QWidget) -> None:
        """Qt Designer の placeholder widget をレイアウト上で実 widget に差し替える。

        placeholder が parent widget のトップレベルレイアウトではなく
        ネストした子レイアウト (例: QGroupBox の QVBoxLayout 内の QHBoxLayout) に
        属していても、その実レイアウトを再帰探索して同じ位置に差し替える。
        """
        parent_widget = placeholder.parentWidget()
        if parent_widget is None:
            return
        target = FilterSearchPanel._find_box_layout_containing(parent_widget.layout(), placeholder)
        if target is None:
            return
        index = target.indexOf(placeholder)
        target.removeWidget(placeholder)
        placeholder.deleteLater()
        target.insertWidget(index, widget)

    @staticmethod
    def _find_box_layout_containing(layout: QLayout | None, widget: QWidget) -> QBoxLayout | None:
        """widget を直接保持する QBoxLayout を (ネストした子レイアウト含め) 再帰探索する。"""
        if layout is None:
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            if item.widget() is widget:
                return layout if isinstance(layout, QBoxLayout) else None
            found = FilterSearchPanel._find_box_layout_containing(item.layout(), widget)
            if found is not None:
                return found
        return None

    def _setup_sub_components(self) -> None:
        """Sub-component の依存と連携を設定する。"""
        # TagSuggestionWidget: lineEditSearch に attach し、enabled 判定を渡す
        self._tag_suggestion.attach_line_edit(
            self.ui.lineEditSearch,
            is_enabled_provider=lambda: self.ui.checkboxTags.isChecked(),
        )

        # CountEstimateWidget: 条件構築コールバックを渡す
        self._count_estimate.set_conditions_builder(
            lambda: self._build_search_conditions_from_ui(show_status=False),
        )

        # FavoriteFilterPanel: 条件 getter / applier を渡す
        self._favorite_filter.set_conditions_getter(self.get_current_conditions)
        self._favorite_filter.set_conditions_applier(self.apply_conditions)

    def connect_signals(self) -> None:
        """Qt Designer の UI コンポーネントにシグナルを接続する。"""
        # 検索関連
        self.ui.lineEditSearch.returnPressed.connect(self._on_search_requested)
        self.ui.lineEditSearch.textEdited.connect(self._tag_suggestion.on_search_text_edited)
        self.ui.checkboxTags.toggled.connect(self._on_search_type_changed)
        self.ui.checkboxCaption.toggled.connect(self._on_search_type_changed)

        # 解像度フィルター
        self.ui.comboResolution.currentTextChanged.connect(self._on_resolution_changed)

        # 日付フィルター
        self.ui.checkboxDateFilter.toggled.connect(self._on_date_filter_toggled)
        self.date_range_slider.valueChanged.connect(self._on_date_range_changed)

        # Rating フィルター (Issue #811: chip トグル群)
        self._rating_chips.changed.connect(self._on_rating_changed)

        # アクションボタン
        self.ui.buttonApply.clicked.connect(self._on_apply_clicked)
        self.ui.buttonClear.clicked.connect(self._on_clear_clicked)

        # リアルタイム件数更新トリガー
        self.ui.lineEditSearch.textChanged.connect(self._on_filter_value_changed)
        self.ui.radioAnd.toggled.connect(self._on_filter_value_changed)
        self.ui.radioOr.toggled.connect(self._on_filter_value_changed)
        self.ui.comboResolution.currentTextChanged.connect(self._on_filter_value_changed)
        self.ui.comboAspectRatio.currentTextChanged.connect(self._on_filter_value_changed)
        self.ui.checkboxDateFilter.toggled.connect(self._on_filter_value_changed)
        self._rating_chips.changed.connect(self._on_filter_value_changed)
        self._ai_rating_chips.changed.connect(self._on_filter_value_changed)
        self._rating_combine_toggle.changed.connect(self._on_filter_value_changed)
        self.ui.checkboxIncludeUnrated.toggled.connect(self._on_filter_value_changed)
        self.ui.checkboxOnlyUntagged.toggled.connect(self._on_filter_value_changed)
        self.ui.checkboxOnlyUncaptioned.toggled.connect(self._on_filter_value_changed)
        self.date_range_slider.valueChanged.connect(self._on_filter_value_changed)
        self.score_range_slider.valueChanged.connect(self._on_filter_value_changed)

        # Phase 4: facets サイドバー
        self._search_facets_sidebar.facets_changed.connect(self._on_facets_changed)

    # ============================================================
    # ===  依存注入 setter (外部 API)
    # ============================================================

    def set_search_filter_service(self, service: "SearchFilterService") -> None:
        """SearchFilterService を設定する。"""
        if service is None:
            raise ValueError("SearchFilterService cannot be None")

        if not hasattr(service, "create_search_conditions"):
            raise TypeError(f"Invalid SearchFilterService: missing required methods. Got: {type(service)}")

        if self.search_filter_service is not None:
            logger.warning(
                f"SearchFilterService置き換え: "
                f"old={type(self.search_filter_service)} -> new={type(service)}",
            )

        self.search_filter_service = service
        self._count_estimate.set_search_filter_service(service)
        logger.info(f"SearchFilterService set for FilterSearchPanel: {type(service)}")

        # TagSuggestionService を SearchFilterService 経由で初期化
        merged_reader = self._resolve_tag_suggestion_reader(service)
        if merged_reader is not None:
            from ...services.tag_suggestion_service import TagSuggestionService

            self.set_tag_suggestion_service(TagSuggestionService(merged_reader))
        else:
            logger.debug("MergedTagReader not available: tag autocomplete disabled")
            self.set_tag_suggestion_service(None)

        # 基本メソッド存在確認 (DEBUG レベルに圧縮)
        required_methods = ["create_search_conditions", "parse_search_input"]
        missing = [m for m in required_methods if not hasattr(service, m)]
        if missing:
            logger.warning(f"SearchFilterService missing methods: {missing}")
        else:
            logger.debug("SearchFilterService method validation: OK")

        # Phase 4: 初期化時にモデルリストとヒストグラムを更新
        if hasattr(service, "get_recently_used_model_ids"):
            model_ids = service.get_recently_used_model_ids()
            self._search_facets_sidebar.update_models(model_ids)
        if hasattr(service, "get_created_at_histogram"):
            histogram_bins = service.get_created_at_histogram()
            self._search_facets_sidebar.update_histogram(histogram_bins)

    @staticmethod
    def _resolve_tag_suggestion_reader(service: "SearchFilterService") -> Any:
        """SearchFilterService からタグ補完用 MergedTagReader を取得する。

        現行の DB manager は external tag DB を AnnotationRepository が所有する。
        旧テスト/旧経路との互換性のため、最後に repository.merged_reader も参照する。
        """
        db_manager = getattr(service, "db_manager", None)
        if db_manager is None:
            return None

        db_manager_attrs = getattr(db_manager, "__dict__", {})
        annotation_repo = db_manager_attrs.get("annotation_repo")
        get_merged_reader = getattr(annotation_repo, "get_merged_reader", None)
        if callable(get_merged_reader):
            try:
                merged_reader = get_merged_reader()
            except Exception as e:
                logger.warning(f"MergedTagReader 取得に失敗: {e}")
            else:
                if merged_reader is not None:
                    return merged_reader

        repository = db_manager_attrs.get("repository")
        return getattr(repository, "merged_reader", None)

    def set_tag_suggestion_service(self, service: "TagSuggestionService | None") -> None:
        """TagSuggestionService を設定する (旧 API 互換)。"""
        self._tag_suggestion.set_tag_suggestion_service(service)

    def set_worker_service(self, service: "WorkerService") -> None:
        """WorkerService を設定する。"""
        self.worker_service = service

        if self.worker_service:
            self.worker_service.operation_event.connect(self._on_worker_operation_event)
            self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.debug("WorkerService set for FilterSearchPanel")

    def set_favorite_filters_service(self, service: Any) -> None:
        """FavoriteFiltersService を設定する (旧 API 互換)。"""
        self._favorite_filter.set_favorite_filters_service(service)

    # ============================================================
    # ===  旧 API 互換: TagSuggestion 関連メソッド (delegation)
    # ============================================================

    @staticmethod
    def _extract_last_token(text: str) -> str:
        """旧 API 互換: 静的ヘルパーを delegation 経由で提供。"""
        return TagSuggestionWidget._extract_last_token(text)

    def _on_search_text_edited(self, text: str) -> None:
        """旧 API 互換: TagSuggestionWidget へ delegation。"""
        self._tag_suggestion.on_search_text_edited(text)

    def _update_tag_completions(self) -> None:
        """旧 API 互換: TagSuggestionWidget へ delegation。"""
        self._tag_suggestion._update_tag_completions()

    def _clear_tag_suggestions(self) -> None:
        """旧 API 互換: TagSuggestionWidget へ delegation。"""
        self._tag_suggestion._clear_tag_suggestions()

    def _on_tag_completion_activated(self, selected_tag: str) -> None:
        """旧 API 互換: TagSuggestionWidget へ delegation。"""
        self._tag_suggestion._on_tag_completion_activated(selected_tag)

    # ============================================================
    # ===  closeEvent
    # ============================================================

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィジェット破棄時のクリーンアップ。"""
        self._tag_suggestion.cleanup()
        self._count_estimate.cleanup()
        super().closeEvent(event)

    # ============================================================
    # ===  Worker / Pipeline event handlers
    # ============================================================

    def _on_worker_operation_event(self, event: WorkerOperationEvent) -> None:
        """検索 operation event から検索パネル状態を更新する。"""
        if event.operation_type is not OperationType.SEARCH or not event.is_current:
            return

        if event.outcome is OperationOutcome.SUCCEEDED:
            self._on_search_finished(event.result)
        elif event.outcome in {
            OperationOutcome.FAILED,
            OperationOutcome.TERMINATED,
            OperationOutcome.UNRESPONSIVE,
        }:
            self._on_search_error(event.error or f"検索処理が終了しました: {event.outcome.value}")
        elif event.outcome is OperationOutcome.CANCELED:
            self._on_search_canceled(event.worker_id)

    def _on_search_finished(self, result: Any) -> None:
        """検索完了イベント処理。"""
        logger.debug("検索完了イベント受信")

        try:
            if hasattr(result, "total_count") and hasattr(result, "image_metadata"):
                count = result.total_count

                if count > 0:
                    self._pipeline.transition_to(PipelineState.LOADING_THUMBNAILS)
                else:
                    self._pipeline.transition_to(PipelineState.DISPLAYING)

                self.update_search_preview(count)

                self.search_completed.emit(
                    {
                        "results": result.image_metadata,
                        "count": count,
                        "conditions": getattr(result, "filter_conditions", {}),
                    },
                )
                logger.info(f"検索結果: {count}件")
            else:
                logger.error(f"無効な検索結果: {result}")
                self._pipeline.transition_to(PipelineState.ERROR)
        except Exception as e:
            logger.error(f"検索完了処理エラー: {e}", exc_info=True)
            self._pipeline.transition_to(PipelineState.ERROR)
        finally:
            self._current_search_worker_id = None

    def _on_search_error(self, error: str) -> None:
        """検索エラーイベント処理。"""
        logger.error(f"検索エラー: {error}")
        self._current_search_worker_id = None
        self._pipeline.transition_to(PipelineState.ERROR)
        self.search_completed.emit({"results": [], "count": 0, "error": error})

    def _on_search_canceled(self, worker_id: str) -> None:
        """検索キャンセルイベント処理。"""
        logger.info(f"検索キャンセル: {worker_id}")
        self._current_search_worker_id = None
        self._pipeline.transition_to(PipelineState.CANCELED)
        self.search_completed.emit({"results": [], "count": 0, "canceled": True})

    def _on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """ワーカーのバッチ進捗処理 (動的進捗計算)。"""
        try:
            if worker_id == self._current_search_worker_id:
                if total > 0:
                    search_progress = current / total
                    overall_progress = search_progress * 0.3  # 30%まで
                    self.update_pipeline_progress(f"検索中... ({current}/{total})", overall_progress, 0.3)
                    logger.debug(f"Search batch progress: {current}/{total} -> {overall_progress:.1%}")
            elif (
                self.worker_service is not None
                and hasattr(self.worker_service, "current_thumbnail_worker_id")
                and worker_id == self.worker_service.current_thumbnail_worker_id
            ):
                if total > 0:
                    thumbnail_progress = current / total
                    overall_progress = 0.3 + (thumbnail_progress * 0.7)
                    self.update_pipeline_progress(
                        f"サムネイル読み込み中... ({current}/{total}) {filename}",
                        overall_progress,
                        1.0,
                    )
                    logger.debug(f"Thumbnail batch progress: {current}/{total} -> {overall_progress:.1%}")
        except Exception as e:
            logger.error(f"バッチ進捗処理エラー: {e}")

    # ============================================================
    # ===  Pipeline state listener + UI update
    # ============================================================

    def _on_pipeline_state_changed(self, old_state: PipelineState, new_state: PipelineState) -> None:
        """PipelineStateMachine の state 変更通知ハンドラ。"""
        del old_state  # signature 一致のため受け取るが未使用 (logger 出力は machine 側)
        self._update_ui_for_state(new_state)
        self.pipeline_state_changed.emit(new_state)

    def _update_ui_for_state(self, state: PipelineState) -> None:
        """状態に応じた UI 更新。"""
        if state == PipelineState.IDLE:
            self.progress_bar.setVisible(False)
            self._hide_status_message()
        elif state == PipelineState.SEARCHING:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(10)
            self._hide_status_message()
        elif state == PipelineState.LOADING_THUMBNAILS:
            self.progress_bar.setValue(30)
        elif state == PipelineState.DISPLAYING:
            self.progress_bar.setValue(100)
        elif state in (PipelineState.ERROR, PipelineState.CANCELED):
            self.progress_bar.setVisible(False)
            message = self._pipeline.state_messages.get(state, "")
            if message:
                self._show_status_message(message)

    def _show_status_message(self, message: str, auto_hide_ms: int = 0) -> None:
        """ステータスラベルにメッセージを表示する。"""
        from PySide6.QtCore import QTimer

        self._status_label.setText(message)
        self._status_label.setVisible(True)
        if auto_hide_ms > 0:
            QTimer.singleShot(auto_hide_ms, self._hide_status_message)

    def _hide_status_message(self) -> None:
        """ステータスラベルを非表示にする。"""
        self._status_label.setVisible(False)
        self._status_label.clear()

    def hide_progress_after_completion(self) -> None:
        """パイプライン完全完了後にプログレスバーを非表示にする。"""
        logger.debug("Progress hiding (pipeline completion; statusbar 通知に集約済み)")
        if hasattr(self, "progress_bar") and self.progress_bar:
            self.progress_bar.setVisible(False)

    # ============================================================
    # ===  Event handlers (filter UI)
    # ============================================================

    def _on_resolution_changed(self, text: str) -> None:
        """解像度選択変更処理。"""
        del text  # 固定解像度のみのため処理不要

    def _on_rating_changed(self) -> None:
        """手動 Rating chip 選択変更処理。"""
        logger.debug(f"Manual rating chips changed: {self._rating_chips.selected_values()}")

    def _on_date_filter_toggled(self, checked: bool) -> None:
        """日付フィルター有効化切り替え処理。"""
        self.ui.frameDateRange.setVisible(checked)

    def _on_date_range_changed(self, min_timestamp: int, max_timestamp: int) -> None:
        """日付範囲変更処理。"""
        logger.debug(f"日付範囲変更: {min_timestamp} - {max_timestamp}")

    def _on_filter_value_changed(self, *args: Any) -> None:
        """フィルター変更時に件数更新をデバウンス実行する。"""
        del args
        self._count_estimate.schedule_update()

    # ============================================================
    # ===  Helpers: UI 値の取り出し
    # ============================================================

    def get_date_range_from_slider(self) -> tuple[datetime | None, datetime | None]:
        """CustomRangeSlider から日付範囲を取得して datetime に変換。"""
        if not self.ui.checkboxDateFilter.isChecked():
            return None, None

        try:
            min_timestamp, max_timestamp = self.date_range_slider.get_range()

            if min_timestamp < 0 or max_timestamp < 0:
                logger.warning(f"無効なタイムスタンプ: min={min_timestamp}, max={max_timestamp}")
                return None, None

            if min_timestamp > max_timestamp:
                logger.warning(f"開始日付が終了日付より後: start={min_timestamp}, end={max_timestamp}")
                min_timestamp, max_timestamp = max_timestamp, min_timestamp

            start_date = datetime.fromtimestamp(min_timestamp)
            end_date = datetime.fromtimestamp(max_timestamp)

            current_time = datetime.now()
            if start_date > current_time:
                logger.warning(f"開始日付が未来: {start_date}, 現在時刻に調整")
                start_date = current_time
            if end_date > current_time:
                logger.info(f"終了日付が未来: {end_date}, 現在時刻に調整")
                end_date = current_time

            logger.debug(f"日付範囲変換完了: {start_date} - {end_date}")
            return start_date, end_date
        except (ValueError, OSError) as e:
            logger.error(f"日付範囲変換エラー (タイムスタンプ無効): {e}")
            return None, None
        except Exception as e:
            logger.error(f"予期しない日付範囲変換エラー: {e}", exc_info=True)
            return None, None

    def _get_selected_search_types(self) -> list[str]:
        """選択された検索タイプのリストを取得。"""
        types: list[str] = []
        if self.ui.checkboxTags.isChecked():
            types.append("tags")
        if self.ui.checkboxCaption.isChecked():
            types.append("caption")
        return types

    def _get_primary_search_type(self) -> str:
        """主要な検索タイプを取得 (従来 API 互換)。"""
        types = self._get_selected_search_types()
        if "tags" in types:
            return "tags"
        if "caption" in types:
            return "caption"
        return "tags"

    def _get_rating_filter_value(self) -> list[str]:
        """手動 Rating chip から選択された値リストを取得 (Issue #811)。

        マルチセレクト chip の選択集合を返す。未選択時は空リスト (絞り込みなし)。
        複数値はバックエンドで選択集合の OR として扱われる。
        """
        values = self._rating_chips.selected_values()
        logger.debug(f"Manual rating filter values: {values}")
        return values

    def _get_ai_rating_filter_value(self) -> list[str]:
        """AI Rating chip から選択された値リストを取得 (Issue #811)。

        マルチセレクト chip の選択集合を返す。未選択時は空リスト (絞り込みなし)。
        """
        values = self._ai_rating_chips.selected_values()
        logger.debug(f"AI rating filter values: {values}")
        return values

    def _get_score_filter_values(self) -> tuple[float | None, float | None]:
        """スコアスライダーからフィルター値を取得。"""
        score_min_internal, score_max_internal = self.score_range_slider.get_range()
        if score_min_internal == 0 and score_max_internal == 1000:
            return None, None
        return score_min_internal / 100.0, score_max_internal / 100.0

    @staticmethod
    def _normalize_rating_values(rating_filter: str | list[str] | None) -> list[str]:
        """レーティングフィルタ値を非空文字列のリストへ正規化する (単一値/複数値/None 共通)。"""
        if rating_filter is None:
            return []
        values = [rating_filter] if isinstance(rating_filter, str) else list(rating_filter)
        return [v for v in values if v]

    @classmethod
    def _is_nsfw_rating(cls, rating_filter: str | list[str] | None) -> bool:
        """NSFW レーティング値 (R/X/XXX) を含むか判定する (単一値/複数値対応)。"""
        return any(v in {"R", "X", "XXX"} for v in cls._normalize_rating_values(rating_filter))

    def _resolve_include_nsfw(
        self,
        rating_filter: str | list[str] | None,
        ai_rating_filter: str | list[str] | None,
    ) -> bool:
        """レーティング選択から NSFW 含有フラグを決定する。

        選択集合に NSFW レーティング (R/X/XXX) が含まれる、または「レーティング済み」
        (RATED = レーティングがある画像すべて) が含まれる場合は NSFW 画像も含める
        (Issue #561 / #811 マルチセレクト対応)。
        """
        manual_values = self._normalize_rating_values(rating_filter)
        ai_values = self._normalize_rating_values(ai_rating_filter)
        include_nsfw = (
            self._is_nsfw_rating(manual_values)
            or self._is_nsfw_rating(ai_values)
            or "RATED" in manual_values
            or "RATED" in ai_values
        )
        logger.debug(
            f"NSFW include resolved from ratings: manual={manual_values}, "
            f"ai={ai_values}, include_nsfw={include_nsfw}",
        )
        return include_nsfw

    def _on_search_type_changed(self) -> None:
        """検索タイプ変更時の処理 (チェックボックス対応)。"""
        self._update_search_input_state()

        selected_types = self._get_selected_search_types()
        if not selected_types:
            self.ui.lineEditSearch.setPlaceholderText("検索タイプを選択してください...")
        elif len(selected_types) == 1:
            if "tags" in selected_types:
                if self.ui.checkboxOnlyUntagged.isChecked():
                    self.ui.lineEditSearch.setPlaceholderText("未タグ画像検索中(タグ入力無効)")
                else:
                    self.ui.lineEditSearch.setPlaceholderText(
                        "検索キーワードを入力(複数タグの場合はカンマ区切り)...",
                    )
            elif "caption" in selected_types:
                if self.ui.checkboxOnlyUncaptioned.isChecked():
                    self.ui.lineEditSearch.setPlaceholderText(
                        "未キャプション画像検索中(キャプション入力無効)",
                    )
                else:
                    self.ui.lineEditSearch.setPlaceholderText("キャプション検索キーワードを入力...")
        else:
            self.ui.lineEditSearch.setPlaceholderText("タグ・キャプション検索キーワードを入力...")

        if not self.ui.checkboxTags.isChecked():
            self._tag_suggestion._clear_tag_suggestions()

    def _update_search_input_state(self) -> None:
        """検索入力フィールドの有効/無効状態を更新。"""
        disabled = (self.ui.checkboxTags.isChecked() and self.ui.checkboxOnlyUntagged.isChecked()) or (
            self.ui.checkboxCaption.isChecked() and self.ui.checkboxOnlyUncaptioned.isChecked()
        )
        self.ui.lineEditSearch.setEnabled(not disabled)

    # ============================================================
    # ===  検索条件構築 + 検索実行
    # ============================================================

    def _build_search_conditions_from_ui(self, *, show_status: bool = True) -> "SearchConditions | None":
        """UI 入力から SearchConditions を構築する。検証失敗時は None を返す。"""
        if self.search_filter_service is None:
            return None
        search_text = self.ui.lineEditSearch.text().strip()
        keywords, excluded_keywords = (
            self.search_filter_service.parse_search_input(search_text) if search_text else ([], [])
        )

        score_min_internal, score_max_internal = self.score_range_slider.get_range()
        has_score_filter = score_min_internal != 0 or score_max_internal != 1000
        has_facet_filter = any(v is not None for v in self._facet_values.values())

        if not keywords and not any(
            [
                self.ui.checkboxOnlyUntagged.isChecked(),
                self.ui.checkboxOnlyUncaptioned.isChecked(),
                self.ui.checkboxDateFilter.isChecked(),
                self.ui.comboResolution.currentText() != "全て",
                self.ui.comboAspectRatio.currentText() != "全て",
                bool(self._get_rating_filter_value()),
                bool(self._get_ai_rating_filter_value()),
                has_score_filter,
                has_facet_filter,
            ],
        ):
            logger.debug("検索条件が未指定のため検索をスキップ")
            if show_status:
                self._show_status_message("検索条件が未指定です", auto_hide_ms=3000)
            return None

        date_range_start, date_range_end = self.get_date_range_from_slider()
        if self.ui.checkboxDateFilter.isChecked() and (date_range_start is None or date_range_end is None):
            logger.warning("日付範囲フィルターエラー: 有効だが範囲が無効")
            if show_status:
                self._show_status_message("日付範囲が無効です", auto_hide_ms=3000)
            return None

        rating_filter = self._get_rating_filter_value()
        ai_rating_filter = self._get_ai_rating_filter_value()
        include_nsfw = self._resolve_include_nsfw(rating_filter, ai_rating_filter)
        score_min, score_max = self._get_score_filter_values()

        return self.search_filter_service.create_search_conditions(
            search_type=self._get_primary_search_type(),
            keywords=keywords,
            excluded_keywords=excluded_keywords,
            tag_logic="and" if self.ui.radioAnd.isChecked() else "or",
            resolution_filter=self.ui.comboResolution.currentText(),
            aspect_ratio_filter=self.ui.comboAspectRatio.currentText(),
            date_filter_enabled=self.ui.checkboxDateFilter.isChecked(),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            only_untagged=self.ui.checkboxOnlyUntagged.isChecked(),
            only_uncaptioned=self.ui.checkboxOnlyUncaptioned.isChecked(),
            exclude_duplicates=False,
            include_nsfw=include_nsfw,
            rating_filter=rating_filter,
            ai_rating_filter=ai_rating_filter,
            rating_combine=self._rating_combine_toggle.value() or "and",
            include_unrated=self.ui.checkboxIncludeUnrated.isChecked(),
            score_min=score_min,
            score_max=score_max,
            manual_edit_filter=cast(bool | None, self._facet_values.get("manual_edit_filter")),
            reviewed_at_filter=cast(str | None, self._facet_values.get("reviewed_at_filter")),
            error_state_filter=cast(str | None, self._facet_values.get("error_state_filter")),
            model_filter=cast(list[str] | None, self._facet_values.get("model_filter")),
        )

    def _on_facets_changed(self, facets: dict[str, object]) -> None:
        """Phase 4 facet 変化ハンドラ: facet 値を保存して検索を再実行する。"""
        self._facet_values = facets
        self._on_search_requested()

    def _on_search_requested(self) -> None:
        """検索要求処理: WorkerService 経由で非同期実行 (フォールバック: 同期)。"""
        if not self.search_filter_service:
            logger.error("SearchFilterService not set: search aborted")
            return

        if not self.worker_service:
            logger.warning("WorkerService not set, falling back to synchronous search")
            self._execute_synchronous_search()
            return

        # 既存検索の置換は start_search 側が SEARCH_REPLACED で破棄する。
        # ここで cancel_search を呼ぶと USER_REQUESTED 扱いになり誤キャンセルログ +
        # 二重キャンセルの WARNING が出るため、pipeline 状態のリセットのみ行う。
        if self._current_search_worker_id:
            self._pipeline.transition_to(PipelineState.IDLE)

        try:
            conditions = self._build_search_conditions_from_ui()
            if conditions is None:
                return

            self._pipeline.transition_to(PipelineState.SEARCHING)

            worker_id = self.worker_service.start_search(conditions)
            if worker_id:
                self._current_search_worker_id = worker_id
                logger.debug(f"非同期検索開始: {worker_id}")
                self.search_requested.emit({"conditions": conditions, "worker_id": worker_id})
            else:
                logger.error("WorkerService.start_search failed")
                self._pipeline.transition_to(PipelineState.ERROR)

        except AttributeError as e:
            logger.error(f"UI AttributeError: {e}", exc_info=True)
            self._pipeline.transition_to(PipelineState.ERROR)
        except ValueError as e:
            logger.error(f"検索入力値エラー: {e}")
            self._pipeline.transition_to(PipelineState.ERROR)
        except Exception as e:
            logger.error(f"検索実行エラー: {e}", exc_info=True)
            self._pipeline.transition_to(PipelineState.ERROR)

    def _execute_synchronous_search(self) -> None:
        """同期検索実行 (WorkerService が利用できない場合のフォールバック)。"""
        if self.search_filter_service is None:
            logger.error("SearchFilterService not set: synchronous search aborted")
            return
        logger.warning("フォールバック: 同期検索を実行")

        try:
            conditions = self._build_search_conditions_from_ui()
            if conditions is None:
                return

            results, count = self.search_filter_service.criteria_processor.execute_search_with_filters(
                conditions
            )

            self.update_search_preview(count)

            result_data = {"results": results, "count": count, "conditions": conditions}
            self.search_requested.emit(result_data)
            self.search_completed.emit(result_data)
            logger.info(f"同期検索完了: {count}件")
        except Exception as e:
            logger.error(f"同期検索実行エラー: {e}", exc_info=True)
            self.search_completed.emit({"results": [], "count": 0, "error": str(e)})

    def _on_clear_requested(self) -> None:
        """クリア要求処理。"""
        self._clear_all_inputs()
        self.filter_cleared.emit()
        logger.info("フィルター・検索をクリア")

    # ============================================================
    # ===  UI 状態の更新
    # ============================================================

    def _update_ui_from_conditions(self, conditions: dict[str, Any]) -> None:
        """条件辞書から UI の検索条件を復元する (#1060)。

        現行スキーマ (``get_current_conditions`` と対、version キー付き) を全項目
        復元する。version キーの無い旧形式 (search_type/keywords/resolution_filter 系)
        は :meth:`_migrate_legacy_conditions` で best-effort 変換してから適用する。
        """
        if "version" not in conditions:
            conditions = self._migrate_legacy_conditions(conditions)
            if not conditions:
                logger.warning("お気に入り条件が空か旧形式のため復元できませんでした")
                return

        self.ui.lineEditSearch.setText(str(conditions.get("search_text", "")))
        self.ui.checkboxTags.setChecked(bool(conditions.get("search_tags", True)))
        self.ui.checkboxCaption.setChecked(bool(conditions.get("search_caption", False)))
        use_and = conditions.get("tag_logic", "and") != "or"
        self.ui.radioAnd.setChecked(use_and)
        self.ui.radioOr.setChecked(not use_and)

        self._set_combo_text_if_choice(self.ui.comboResolution, conditions.get("resolution"))
        self._set_combo_text_if_choice(self.ui.comboAspectRatio, conditions.get("aspect_ratio"))

        self.ui.checkboxDateFilter.setChecked(bool(conditions.get("date_filter_enabled", False)))
        date_range = conditions.get("date_range")
        if isinstance(date_range, list | tuple) and len(date_range) == 2:
            self.date_range_slider.slider.setValue((int(date_range[0]), int(date_range[1])))

        self.ui.checkboxOnlyUntagged.setChecked(bool(conditions.get("only_untagged", False)))
        self.ui.checkboxOnlyUncaptioned.setChecked(bool(conditions.get("only_uncaptioned", False)))
        self.ui.checkboxExcludeDuplicates.setChecked(bool(conditions.get("exclude_duplicates", False)))

        # レーティング chip (#811) とスコア範囲も復元対象に含める
        self._rating_chips.clear()
        for value in conditions.get("rating_filter") or []:
            self._rating_chips.set_value(str(value))
        self._ai_rating_chips.clear()
        for value in conditions.get("ai_rating_filter") or []:
            self._ai_rating_chips.set_value(str(value))
        self._rating_combine_toggle.set_value(str(conditions.get("rating_combine", "and")))
        # include_unrated の既定は True (UI 既定・SearchConditions 既定と一致)。
        # False に倒すと未評価画像が全件除外される (Codex P2)。
        self.ui.checkboxIncludeUnrated.setChecked(bool(conditions.get("include_unrated", True)))

        score_range = conditions.get("score_range")
        if isinstance(score_range, list | tuple) and len(score_range) == 2:
            self.score_range_slider.slider.setValue((int(score_range[0]), int(score_range[1])))

        # 復元した条件で件数見積もりを更新する
        self._count_estimate.schedule_update()

    @staticmethod
    def _set_combo_text_if_choice(combo: QComboBox, text: Any) -> None:
        """text が combo の既存選択肢に含まれる場合のみ setCurrentText する。"""
        if not text:
            return
        if str(text) in [combo.itemText(i) for i in range(combo.count())]:
            combo.setCurrentText(str(text))

    @staticmethod
    def _migrate_legacy_conditions(conditions: dict[str, Any]) -> dict[str, Any]:
        """version キーの無い旧形式のお気に入り条件を現行スキーマへ写像する (#1060)。

        旧 ``get_current_conditions`` は「最後に実行した検索」の
        search_type/keywords/excluded_keywords/resolution_filter 系キーで保存していた。
        取り込めるキーだけ best-effort で変換し、空なら空辞書を返す。
        """
        if not conditions:
            return {}
        migrated: dict[str, Any] = {"version": FilterSearchPanel.CONDITIONS_SCHEMA_VERSION}
        keywords = [str(k) for k in conditions.get("keywords") or []]
        excluded = [f"-{k}" for k in conditions.get("excluded_keywords") or []]
        if keywords or excluded:
            # 除外キーワードは parse_search_input の "-tag" 構文へ戻す
            migrated["search_text"] = ", ".join(keywords + excluded)
        search_type = conditions.get("search_type")
        if search_type:
            migrated["search_tags"] = search_type == "tags"
            migrated["search_caption"] = search_type == "caption"
        for legacy_key, new_key in (
            ("tag_logic", "tag_logic"),
            ("resolution_filter", "resolution"),
            ("aspect_ratio_filter", "aspect_ratio"),
            ("date_filter_enabled", "date_filter_enabled"),
            ("only_untagged", "only_untagged"),
            ("only_uncaptioned", "only_uncaptioned"),
            ("exclude_duplicates", "exclude_duplicates"),
        ):
            if conditions.get(legacy_key) is not None:
                migrated[new_key] = conditions[legacy_key]
        # 旧形式の日付境界を date_range へ変換する (Codex P2)。変換できない場合は
        # date_range を落とし、有効フラグだけ引き継ぐ (誤った日付での検索を防ぐ)。
        start_ts = FilterSearchPanel._coerce_timestamp(conditions.get("date_range_start"))
        end_ts = FilterSearchPanel._coerce_timestamp(conditions.get("date_range_end"))
        if start_ts is not None and end_ts is not None:
            migrated["date_range"] = [start_ts, end_ts]
        # 旧スキーマは include_unrated を保存しておらず、歴史的既定は True
        # (SearchConditions 既定)。欠落を False 化すると未評価画像が全件除外される
        # ため明示的に True を入れる (Codex P2)。
        migrated["include_unrated"] = True
        return migrated

    @staticmethod
    def _coerce_timestamp(value: Any) -> int | None:
        """旧形式の日付境界値 (epoch 秒 / ISO 文字列 / datetime) を epoch 秒へ変換する。"""
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, str):
            try:
                return int(datetime.fromisoformat(value).timestamp())
            except ValueError:
                return None
        return None

    def _clear_all_inputs(self) -> None:
        """全入力をクリアする。"""
        self._count_estimate.reset()
        self.ui.lineEditSearch.clear()
        self.ui.checkboxTags.setChecked(True)
        self.ui.checkboxCaption.setChecked(False)
        self.ui.radioAnd.setChecked(True)

        self.ui.comboResolution.setCurrentIndex(0)
        self.ui.comboAspectRatio.setCurrentIndex(0)

        self.ui.checkboxDateFilter.setChecked(False)
        self.ui.frameDateRange.setVisible(False)
        self.date_range_slider.slider.setValue((0, 100))

        self.ui.checkboxOnlyUntagged.setChecked(False)
        self.ui.checkboxOnlyUncaptioned.setChecked(False)
        self.ui.checkboxExcludeDuplicates.setChecked(False)

        # レーティング chip を全解除し、組合せトグルを既定 (AND) に戻す (Issue #811)
        self._rating_chips.clear()
        self._ai_rating_chips.clear()
        self._rating_combine_toggle.set_value("and")

    # ============================================================
    # ===  Public API (外部から呼ばれるもの)
    # ============================================================

    def set_search_text(self, text: str, search_type: str = "tags") -> None:
        """検索テキストを設定する。"""
        self.ui.lineEditSearch.setText(text)
        if search_type == "tags":
            self.ui.checkboxTags.setChecked(True)
            self.ui.checkboxCaption.setChecked(False)
        else:
            self.ui.checkboxCaption.setChecked(True)
            self.ui.checkboxTags.setChecked(False)

    def get_current_conditions(self) -> dict[str, Any]:
        """UI の現在状態をお気に入り保存用の辞書に直列化する (#1060)。

        「最後に実行した検索の条件」ではなく UI の今の入力を保存する
        (未検索でも保存でき、検索後に UI を変えた場合も現状が保存される)。
        値は JSON セーフな型のみ (FavoriteFiltersService が JSON 永続化するため)。
        :meth:`_update_ui_from_conditions` と往復一致するスキーマを保つこと。
        """
        date_min, date_max = self.date_range_slider.get_range()
        score_min, score_max = self.score_range_slider.get_range()
        return {
            "version": self.CONDITIONS_SCHEMA_VERSION,
            "search_text": self.ui.lineEditSearch.text(),
            "search_tags": self.ui.checkboxTags.isChecked(),
            "search_caption": self.ui.checkboxCaption.isChecked(),
            "tag_logic": "and" if self.ui.radioAnd.isChecked() else "or",
            "resolution": self.ui.comboResolution.currentText(),
            "aspect_ratio": self.ui.comboAspectRatio.currentText(),
            "date_filter_enabled": self.ui.checkboxDateFilter.isChecked(),
            "date_range": [date_min, date_max],
            "only_untagged": self.ui.checkboxOnlyUntagged.isChecked(),
            "only_uncaptioned": self.ui.checkboxOnlyUncaptioned.isChecked(),
            "exclude_duplicates": self.ui.checkboxExcludeDuplicates.isChecked(),
            "rating_filter": self._get_rating_filter_value(),
            "ai_rating_filter": self._get_ai_rating_filter_value(),
            "rating_combine": self._rating_combine_toggle.value() or "and",
            "include_unrated": self.ui.checkboxIncludeUnrated.isChecked(),
            "score_range": [score_min, score_max],
        }

    def apply_conditions(self, conditions: dict[str, Any]) -> None:
        """条件を適用する。"""
        self._update_ui_from_conditions(conditions)

    def update_search_preview(self, result_count: int, preview_text: str = "") -> None:
        """検索結果プレビューを更新する。"""
        LARGE_RESULT_WARNING_THRESHOLD = 10000

        if result_count > LARGE_RESULT_WARNING_THRESHOLD:
            logger.info(f"Large search result warning displayed: {result_count} items")
        del preview_text  # 現在は使われていないが API 互換のため残す
        logger.debug(f"検索結果プレビュー更新: {result_count}件")

    def clear_search_preview(self) -> None:
        """検索結果プレビューをクリアする。"""
        logger.debug("検索結果プレビューをクリア")

    def _on_apply_clicked(self) -> None:
        """適用ボタンクリック処理。"""
        self._on_search_requested()

    def _on_clear_clicked(self) -> None:
        """クリアボタンクリック処理。"""
        self._on_clear_requested()

    def update_pipeline_progress(self, message: str, current_progress: float, end_progress: float) -> None:
        """Pipeline 進捗表示の更新 (statusbar 通知へ移行済みのため無効化)。"""
        del end_progress
        logger.trace(
            f"Progress update delegated to statusbar: {message} ({current_progress * 100:.1f}%)",
        )

        if hasattr(self, "progress_bar") and self.progress_bar and self.progress_bar.isVisible():
            self.progress_bar.setVisible(False)
            logger.debug("Inline progress bar hidden - statusbar 通知を使用")

    def handle_pipeline_error(self, phase: str, error_info: dict[str, Any]) -> None:
        """Pipeline エラー処理。"""
        try:
            self._pipeline.transition_to(PipelineState.ERROR)
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Pipeline {phase} error: {error_message}")

            if hasattr(self, "search_completed"):
                self.search_completed.emit({"success": False, "phase": phase, "error": error_message})
        except Exception as e:
            logger.error(f"Failed to handle pipeline error: {e}")

    def clear_pipeline_results(self) -> None:
        """Pipeline 結果のクリア (キャンセル・エラー時用)。"""
        try:
            self._pipeline.clear_results()
            self.filter_cleared.emit()
            logger.info("Pipeline results cleared")
        except Exception as e:
            logger.error(f"Failed to clear pipeline results: {e}")

    def notify_thumbnail_loading_started(self) -> None:
        """サムネイル読み込み開始通知 (MainWindow から呼び出し)。"""
        if self._pipeline.notify_thumbnail_loading_started():
            logger.info("Thumbnail loading phase started")

    def notify_thumbnail_loading_completed(self, thumbnail_count: int) -> None:
        """サムネイル読み込み完了通知 (MainWindow から呼び出し)。"""
        if self._pipeline.notify_thumbnail_loading_completed():
            logger.info(f"Thumbnail loading completed: {thumbnail_count} thumbnails")

    def notify_thumbnail_loading_error(self, error: str) -> None:
        """サムネイル読み込みエラー通知 (MainWindow から呼び出し)。"""
        logger.error(f"Thumbnail loading error: {error}")
        self._pipeline.transition_to(PipelineState.ERROR)

    def get_current_pipeline_state(self) -> PipelineState:
        """現在のパイプライン状態を取得する。"""
        return self._pipeline.current_state

    def is_pipeline_active(self) -> bool:
        """パイプラインがアクティブ状態かどうか。"""
        return self._pipeline.is_active()

    def force_pipeline_reset(self) -> None:
        """強制的にパイプライン状態をリセットする (緊急時用)。"""
        self._pipeline.force_reset()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    logconf = {"level": "DEBUG", "file": "FilterSearchPanel.log"}
    initialize_logging(logconf)

    app = QApplication(sys.argv)

    main_window = QMainWindow()
    main_window.setWindowTitle("FilterSearchPanel テスト")
    main_window.resize(350, 700)

    filter_panel = FilterSearchPanel()

    def on_search_requested(data: dict[str, Any]) -> None:
        logger.debug(f"検索要求: {data}")

    def on_filter_cleared() -> None:
        logger.debug("フィルタークリア")

    filter_panel.search_requested.connect(on_search_requested)
    filter_panel.filter_cleared.connect(on_filter_cleared)

    main_window.setCentralWidget(filter_panel)
    main_window.show()

    sys.exit(app.exec())
