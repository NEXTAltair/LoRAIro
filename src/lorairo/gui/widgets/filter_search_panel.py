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
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QScrollArea, QWidget

from ...gui.designer.FilterSearchPanel_ui import Ui_FilterSearchPanel
from ...gui.services.operation_events import OperationOutcome, OperationType, WorkerOperationEvent
from ...utils.log import logger
from .custom_range_slider import CustomRangeSlider
from .filter_search import (
    CountEstimateWidget,
    FavoriteFilterPanel,
    PipelineState,
    PipelineStateMachine,
    TagSuggestionWidget,
)

# 後方互換性: 旧 import path から PipelineState を export する
__all__ = ["FilterSearchPanel", "PipelineState"]

if TYPE_CHECKING:
    from ...services.search_models import SearchConditions
    from ...services.tag_suggestion_service import TagSuggestionService
    from ..services.search_filter_service import SearchFilterService
    from ..services.worker_service import WorkerService


class FilterSearchPanel(QScrollArea):
    """統合検索・フィルターパネル (mediator)。

    タグ検索、キャプション検索、解像度フィルター、日付範囲フィルターを統合。
    Sub-component (Tag/Count/Favorite/Pipeline) を composition で保持する。
    """

    # シグナル
    filter_applied = Signal(dict)  # filter_conditions
    filter_cleared = Signal()
    search_requested = Signal(dict)  # search_conditions
    search_progress_started = Signal()  # 検索開始
    search_progress_updated = Signal(int, str)  # 進捗値, メッセージ
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
    # ===  後方互換 properties (旧 instance 変数アクセスへの委譲)
    # ============================================================

    @property
    def tag_suggestion_service(self) -> "TagSuggestionService | None":
        """旧 API 互換: TagSuggestionWidget の保持する service。"""
        return self._tag_suggestion.tag_suggestion_service

    @tag_suggestion_service.setter
    def tag_suggestion_service(self, value: "TagSuggestionService | None") -> None:
        self._tag_suggestion.tag_suggestion_service = value

    @property
    def favorite_filters_service(self) -> Any:
        """旧 API 互換: FavoriteFilterPanel の保持する service。"""
        return self._favorite_filter.favorite_filters_service

    @property
    def _tag_completer_model(self) -> Any:
        """旧 API 互換: TagSuggestionWidget の completer model。"""
        return self._tag_suggestion._tag_completer_model

    @property
    def _tag_suggestion_timer(self) -> Any:
        """旧 API 互換: TagSuggestionWidget のデバウンスタイマー。"""
        return self._tag_suggestion._tag_suggestion_timer

    @property
    def _tag_lookup_in_flight(self) -> bool:
        """旧 API 互換: TagSuggestionWidget の非同期検索進行中フラグ。"""
        return self._tag_suggestion._tag_lookup_in_flight

    @_tag_lookup_in_flight.setter
    def _tag_lookup_in_flight(self, value: bool) -> None:
        self._tag_suggestion._tag_lookup_in_flight = value

    @property
    def _pending_tag_token(self) -> str | None:
        """旧 API 互換: TagSuggestionWidget の保留中トークン。"""
        return self._tag_suggestion._pending_tag_token

    @_pending_tag_token.setter
    def _pending_tag_token(self, value: str | None) -> None:
        self._tag_suggestion._pending_tag_token = value

    @property
    def favorite_filters_list(self) -> Any:
        """旧 API 互換: FavoriteFilterPanel の QListWidget。"""
        return self._favorite_filter.favorite_filters_list

    @property
    def favorite_filters_group(self) -> FavoriteFilterPanel:
        """旧 API 互換: FavoriteFilterPanel の QGroupBox 自体。"""
        return self._favorite_filter

    @property
    def _estimated_count_label(self) -> Any:
        """旧 API 互換: CountEstimateWidget の label。"""
        return self._count_estimate.label

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

        placeholder = self.ui.dateRangeSliderPlaceholder
        parent_widget = placeholder.parentWidget()
        if parent_widget:
            layout = parent_widget.layout()
            if isinstance(layout, QBoxLayout):
                index = layout.indexOf(placeholder)
                layout.removeWidget(placeholder)
                placeholder.deleteLater()
                layout.insertWidget(index, self.date_range_slider)

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
        self._status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
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

        # 廃止フラグ (登録時 pHash 重複防止により不要)
        self.ui.checkboxExcludeDuplicates.setChecked(False)
        self.ui.checkboxExcludeDuplicates.setVisible(False)
        # 廃止フラグ (レーティング選択から自動判定)
        self.ui.checkboxIncludeNSFW.setChecked(False)
        self.ui.checkboxIncludeNSFW.setVisible(False)

        # お気に入りフィルター UI をメインレイアウトに追加
        contents_layout = self.ui.scrollAreaWidgetContents.layout()
        if isinstance(contents_layout, QBoxLayout):
            insert_index = contents_layout.count() - 1
            contents_layout.insertWidget(insert_index, self._favorite_filter)

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

        # Rating フィルター
        self.ui.comboRating.currentTextChanged.connect(self._on_rating_changed)

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
        self.ui.comboRating.currentTextChanged.connect(self._on_filter_value_changed)
        self.ui.comboAIRating.currentTextChanged.connect(self._on_filter_value_changed)
        self.ui.checkboxIncludeUnrated.toggled.connect(self._on_filter_value_changed)
        self.ui.checkboxOnlyUntagged.toggled.connect(self._on_filter_value_changed)
        self.ui.checkboxOnlyUncaptioned.toggled.connect(self._on_filter_value_changed)
        self.date_range_slider.valueChanged.connect(self._on_filter_value_changed)
        self.score_range_slider.valueChanged.connect(self._on_filter_value_changed)

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
        merged_reader = getattr(
            getattr(getattr(service, "db_manager", None), "repository", None),
            "merged_reader",
            None,
        )
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
        logger.debug("Progress hiding delegated to ModernProgressManager (pipeline completion)")
        if hasattr(self, "progress_bar") and self.progress_bar:
            self.progress_bar.setVisible(False)

    # ============================================================
    # ===  Event handlers (filter UI)
    # ============================================================

    def _on_resolution_changed(self, text: str) -> None:
        """解像度選択変更処理。"""
        del text  # 固定解像度のみのため処理不要

    def _on_rating_changed(self, text: str) -> None:
        """Rating 選択変更処理。"""
        logger.debug(f"Rating changed: {text}")

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

    def _get_rating_filter_value(self) -> str | None:
        """Rating コンボボックスから選択された値を取得。"""
        text = self.ui.comboRating.currentText()
        if text == "----":
            return None
        if text == "レーティング済み":
            return "RATED"
        if text == "未設定のみ":
            return "UNRATED"
        rating_value = text.split()[0] if text else None
        logger.debug(f"Rating filter value: {rating_value}")
        return rating_value

    def _get_ai_rating_filter_value(self) -> str | None:
        """AI レーティングコンボボックスから選択された値を取得。"""
        text = self.ui.comboAIRating.currentText()
        if text == "----":
            return None
        if text == "レーティング済み":
            return "RATED"
        if text == "未設定のみ":
            return "UNRATED"
        ai_rating_value = text.split()[0] if text else None
        logger.debug(f"AI rating filter value: {ai_rating_value}")
        return ai_rating_value

    def _get_score_filter_values(self) -> tuple[float | None, float | None]:
        """スコアスライダーからフィルター値を取得。"""
        score_min_internal, score_max_internal = self.score_range_slider.get_range()
        if score_min_internal == 0 and score_max_internal == 1000:
            return None, None
        return score_min_internal / 100.0, score_max_internal / 100.0

    @staticmethod
    def _is_nsfw_rating(rating_value: str | None) -> bool:
        """NSFW レーティング値かどうか判定する。"""
        return rating_value in {"R", "X", "XXX"}

    def _resolve_include_nsfw(self, rating_filter: str | None, ai_rating_filter: str | None) -> bool:
        """レーティング選択から NSFW 含有フラグを決定する。

        「レーティング済み」(RATED) は「レーティングがある画像すべて」を意味するため、
        NSFW レーティング画像も含める (Issue #561)。
        """
        include_nsfw = (
            self._is_nsfw_rating(rating_filter)
            or self._is_nsfw_rating(ai_rating_filter)
            or rating_filter == "RATED"
            or ai_rating_filter == "RATED"
        )
        logger.debug(
            f"NSFW include resolved from ratings: manual={rating_filter}, "
            f"ai={ai_rating_filter}, include_nsfw={include_nsfw}",
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

        if not keywords and not any(
            [
                self.ui.checkboxOnlyUntagged.isChecked(),
                self.ui.checkboxOnlyUncaptioned.isChecked(),
                self.ui.checkboxDateFilter.isChecked(),
                self.ui.comboResolution.currentText() != "全て",
                self.ui.comboAspectRatio.currentText() != "全て",
                self.ui.comboRating.currentText() != "----",
                self.ui.comboAIRating.currentText() != "----",
                has_score_filter,
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
            include_unrated=self.ui.checkboxIncludeUnrated.isChecked(),
            score_min=score_min,
            score_max=score_max,
        )

    def _on_search_requested(self) -> None:
        """検索要求処理: WorkerService 経由で非同期実行 (フォールバック: 同期)。"""
        if not self.search_filter_service:
            logger.error("SearchFilterService not set: search aborted")
            return

        if not self.worker_service:
            logger.warning("WorkerService not set, falling back to synchronous search")
            self._execute_synchronous_search()
            return

        # 既存の検索をキャンセル
        if self._current_search_worker_id:
            logger.info(f"既存の検索をキャンセル: {self._current_search_worker_id}")
            self.worker_service.cancel_search(self._current_search_worker_id)
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
        """条件から UI を更新する。"""
        if conditions.get("tags"):
            self.ui.checkboxTags.setChecked(True)
            self.ui.lineEditSearch.setText(", ".join(conditions["tags"]))
            self.ui.radioAnd.setChecked(conditions.get("use_and", True))
            self.ui.radioOr.setChecked(not conditions.get("use_and", True))
        elif conditions.get("caption"):
            self.ui.checkboxCaption.setChecked(True)
            self.ui.lineEditSearch.setText(conditions["caption"])

        if "resolution" in conditions:
            resolution = conditions["resolution"]
            if resolution in [
                self.ui.comboResolution.itemText(i) for i in range(self.ui.comboResolution.count())
            ]:
                self.ui.comboResolution.setCurrentText(resolution)

        if "date_range" in conditions:
            self.ui.checkboxDateFilter.setChecked(True)

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
        """現在の条件を取得する。"""
        if not self.search_filter_service:
            return {}

        current = self.search_filter_service.get_current_conditions()
        if current:
            return {
                "search_type": current.search_type,
                "keywords": current.keywords,
                "excluded_keywords": current.excluded_keywords or [],
                "tag_logic": current.tag_logic,
                "resolution_filter": current.resolution_filter,
                "aspect_ratio_filter": current.aspect_ratio_filter,
                "date_filter_enabled": current.date_filter_enabled,
                "date_range_start": current.date_range_start,
                "date_range_end": current.date_range_end,
                "only_untagged": current.only_untagged,
                "only_uncaptioned": current.only_uncaptioned,
                "exclude_duplicates": current.exclude_duplicates,
            }
        return {}

    def apply_conditions(self, conditions: dict[str, Any]) -> None:
        """条件を適用する。"""
        self._update_ui_from_conditions(conditions)

    def update_search_preview(self, result_count: int, preview_text: str = "") -> None:
        """検索結果プレビューを更新する。"""
        LARGE_RESULT_WARNING_THRESHOLD = 10000

        if result_count > LARGE_RESULT_WARNING_THRESHOLD:
            logger.warning(f"Large search result warning displayed: {result_count} items")
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
        """Pipeline 進捗表示の更新 (ModernProgressManager に移行済みのため無効化)。"""
        del end_progress
        logger.debug(
            f"Progress update delegated to ModernProgressManager: {message} ({current_progress * 100:.1f}%)",
        )

        if hasattr(self, "progress_bar") and self.progress_bar and self.progress_bar.isVisible():
            self.progress_bar.setVisible(False)
            logger.debug("Inline progress bar hidden - using popup progress display")

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
