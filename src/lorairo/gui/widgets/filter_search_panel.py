# src/lorairo/gui/widgets/filter_search_panel.py

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea

from ...gui.designer.FilterSearchPanel_ui import Ui_FilterSearchPanel
from ...utils.log import logger
from .custom_range_slider import CustomRangeSlider

if TYPE_CHECKING:
    from ..services.search_filter_service import SearchFilterService
    from ..services.worker_service import WorkerService


class PipelineState(Enum):
    """Pipeline state machine for search-thumbnail integration (Phase 3)"""

    IDLE = "idle"  # 初期状態/操作待ち
    SEARCHING = "searching"  # 検索実行中
    LOADING_THUMBNAILS = "loading_thumbnails"  # サムネイル読み込み中
    DISPLAYING = "displaying"  # 結果表示中
    ERROR = "error"  # エラー状態
    CANCELED = "canceled"  # キャンセル状態


class FilterSearchPanel(QScrollArea):
    """
    統合検索・フィルターパネル。
    タグ検索、キャプション検索、解像度フィルター、日付範囲フィルターを統合。
    """

    # シグナル
    filter_applied = Signal(dict)  # filter_conditions
    filter_cleared = Signal()
    search_requested = Signal(dict)  # search_conditions
    search_progress_started = Signal()  # 検索開始
    search_progress_updated = Signal(int, str)  # 進捗値, メッセージ
    search_completed = Signal(dict)  # 検索結果

    # Phase 3: Pipeline State Management
    pipeline_state_changed = Signal(object)  # PipelineState

    def __init__(self, parent=None):
        super().__init__(parent)

        # SearchFilterService（依存注入）
        self.search_filter_service: SearchFilterService | None = None

        # WorkerService（依存注入）
        self.worker_service: WorkerService | None = None

        # FavoriteFiltersService（依存注入） - Phase 4
        self.favorite_filters_service: Any = None  # type: ignore[assignment]

        # 現在のSearchWorkerのID
        self._current_search_worker_id: str | None = None

        # Phase 3: Pipeline State Management
        self._current_state: PipelineState = PipelineState.IDLE
        self._state_messages: dict[PipelineState, str] = {
            PipelineState.IDLE: "操作待ち",
            PipelineState.SEARCHING: "検索中...",
            PipelineState.LOADING_THUMBNAILS: "サムネイル読み込み中...",
            PipelineState.DISPLAYING: "表示中",
            PipelineState.ERROR: "エラーが発生しました",
            PipelineState.CANCELED: "キャンセルされました",
        }

        # UI設定
        self.ui = Ui_FilterSearchPanel()
        self.ui.setupUi(self)
        self.setup_custom_widgets()
        self.setup_favorite_filters_ui()  # Phase 4
        self.connect_signals()

        logger.debug("FilterSearchPanel initialized")

    def setup_custom_widgets(self) -> None:
        """Qt DesignerのUIに日付範囲スライダー、進捗表示、QButtonGroupを追加"""
        from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QProgressBar, QPushButton

        # 日付範囲スライダーを作成してプレースホルダーと置き換え
        self.date_range_slider = CustomRangeSlider()
        self.date_range_slider.set_date_range()

        # プレースホルダーを実際のスライダーで置き換え
        placeholder = self.ui.dateRangeSliderPlaceholder
        layout = placeholder.parent().layout()
        if layout:
            # プレースホルダーの位置を取得して置き換え
            index = layout.indexOf(placeholder)
            layout.removeWidget(placeholder)
            placeholder.deleteLater()
            layout.insertWidget(index, self.date_range_slider)

        # QButtonGroup実装（論理演算子の独立化）
        self.logic_button_group = QButtonGroup(self)
        self.logic_button_group.addButton(self.ui.radioAnd)
        self.logic_button_group.addButton(self.ui.radioOr)
        # デフォルト設定
        self.ui.radioAnd.setChecked(True)

        # 進捗表示UI作成（キャンセルボタン削除）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)

        # 進捗表示レイアウト作成（キャンセルボタンなし）
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.progress_bar)

        # 検索グループの最後に進捗UIを追加
        # プレビューエリア削除後は、lineEditSearchの下に追加
        main_layout = self.ui.searchGroup.layout()
        if main_layout:
            main_layout.addLayout(self.progress_layout)

        # 重複除外トグルは廃止: 登録時のpHash重複防止により検索UI上では不要
        self.ui.checkboxExcludeDuplicates.setChecked(False)
        self.ui.checkboxExcludeDuplicates.setVisible(False)

        # NSFWトグルは廃止: レーティング選択から自動判定する
        self.ui.checkboxIncludeNSFW.setChecked(False)
        self.ui.checkboxIncludeNSFW.setVisible(False)

    def setup_favorite_filters_ui(self) -> None:
        """お気に入りフィルターUIを作成してメインレイアウトに追加 (Phase 4)"""
        from PySide6.QtWidgets import (
            QGroupBox,
            QHBoxLayout,
            QListWidget,
            QPushButton,
            QVBoxLayout,
        )

        # グループボックス作成
        self.favorite_filters_group = QGroupBox("お気に入りフィルター")
        self.favorite_filters_group.setCheckable(True)
        self.favorite_filters_group.setChecked(False)  # 初期状態は折りたたみ

        # リストウィジェット作成
        self.favorite_filters_list = QListWidget()
        self.favorite_filters_list.setMaximumHeight(150)

        # ボタン作成
        self.button_save_filter = QPushButton("保存")
        self.button_load_filter = QPushButton("読込")
        self.button_delete_filter = QPushButton("削除")

        # ボタンレイアウト
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.button_save_filter)
        button_layout.addWidget(self.button_load_filter)
        button_layout.addWidget(self.button_delete_filter)

        # グループボックスレイアウト
        group_layout = QVBoxLayout()
        group_layout.addWidget(self.favorite_filters_list)
        group_layout.addLayout(button_layout)
        self.favorite_filters_group.setLayout(group_layout)

        # メインレイアウトに追加（buttonApply/buttonClearの前に追加）
        main_layout = self.ui.scrollAreaWidgetContents.layout()
        if main_layout:
            # 最後から2番目に挿入（Apply/Clearボタンの前）
            insert_index = main_layout.count() - 1
            main_layout.insertWidget(insert_index, self.favorite_filters_group)

        # シグナル接続
        self.button_save_filter.clicked.connect(self._on_save_filter_clicked)
        self.button_load_filter.clicked.connect(self._on_load_filter_clicked)
        self.button_delete_filter.clicked.connect(self._on_delete_filter_clicked)
        self.favorite_filters_list.itemDoubleClicked.connect(self._on_filter_double_clicked)

        logger.debug("Favorite filters UI initialized")

    def set_favorite_filters_service(self, service: Any) -> None:  # type: ignore[misc]
        """FavoriteFiltersServiceを設定 (Phase 4)

        Args:
            service: FavoriteFiltersServiceインスタンス
        """
        if service is None:
            raise ValueError("FavoriteFiltersService cannot be None")

        self.favorite_filters_service = service
        self._refresh_favorite_filters_list()
        logger.info("FavoriteFiltersService set successfully")

    def _refresh_favorite_filters_list(self) -> None:
        """お気に入りフィルター一覧を更新 (Phase 4)"""
        if not self.favorite_filters_service:
            return

        self.favorite_filters_list.clear()

        try:
            filter_names = self.favorite_filters_service.list_filters()
            for name in filter_names:
                self.favorite_filters_list.addItem(name)

            logger.debug("Refreshed favorite filters list: {} items", len(filter_names))
        except Exception as e:
            logger.error("Failed to refresh favorite filters list: {}", e, exc_info=True)

    def _on_save_filter_clicked(self) -> None:
        """保存ボタンクリックハンドラ (Phase 4)"""
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        # 現在の条件を取得
        conditions = self.get_current_conditions()
        if not conditions:
            QMessageBox.warning(self, "保存失敗", "保存する条件がありません。")
            return

        # フィルター名を入力
        filter_name, ok = QInputDialog.getText(
            self,
            "フィルター保存",
            "フィルター名を入力してください:",
        )

        if not ok or not filter_name.strip():
            return

        filter_name = filter_name.strip()

        # 重複チェック
        if self.favorite_filters_service.filter_exists(filter_name):
            reply = QMessageBox.question(
                self,
                "上書き確認",
                f"フィルター '{filter_name}' は既に存在します。上書きしますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 保存実行
        try:
            success = self.favorite_filters_service.save_filter(filter_name, conditions)
            if success:
                QMessageBox.information(self, "保存完了", f"フィルター '{filter_name}' を保存しました。")
                self._refresh_favorite_filters_list()
            else:
                QMessageBox.warning(self, "保存失敗", "フィルターの保存に失敗しました。")
        except Exception as e:
            logger.error("Failed to save filter: {}", e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの保存中にエラーが発生しました:\n{e}")

    def _on_load_filter_clicked(self) -> None:
        """読込ボタンクリックハンドラ (Phase 4)"""
        from PySide6.QtWidgets import QMessageBox

        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        # 選択されたアイテムを取得
        selected_items = self.favorite_filters_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "読込失敗", "読み込むフィルターを選択してください。")
            return

        filter_name = selected_items[0].text()
        self._load_filter_by_name(filter_name)

    def _on_filter_double_clicked(self, item: Any) -> None:  # type: ignore[misc]
        """フィルターダブルクリックハンドラ (Phase 4)

        Args:
            item: クリックされたQListWidgetItem
        """
        filter_name = item.text()
        self._load_filter_by_name(filter_name)

    def _load_filter_by_name(self, filter_name: str) -> None:
        """フィルター名からフィルターを読み込んで適用 (Phase 4)

        Args:
            filter_name: フィルター名
        """
        from PySide6.QtWidgets import QMessageBox

        if not self.favorite_filters_service:
            return

        try:
            conditions = self.favorite_filters_service.load_filter(filter_name)
            if conditions:
                self.apply_conditions(conditions)
                QMessageBox.information(self, "読込完了", f"フィルター '{filter_name}' を適用しました。")
                logger.info("Loaded and applied favorite filter: {}", filter_name)
            else:
                QMessageBox.warning(
                    self, "読込失敗", f"フィルター '{filter_name}' の読み込みに失敗しました。"
                )
        except Exception as e:
            logger.error("Failed to load filter '{}': {}", filter_name, e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの読み込み中にエラーが発生しました:\n{e}")

    def _on_delete_filter_clicked(self) -> None:
        """削除ボタンクリックハンドラ (Phase 4)"""
        from PySide6.QtWidgets import QMessageBox

        if not self.favorite_filters_service:
            QMessageBox.warning(self, "エラー", "お気に入りフィルターサービスが利用できません。")
            return

        # 選択されたアイテムを取得
        selected_items = self.favorite_filters_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "削除失敗", "削除するフィルターを選択してください。")
            return

        filter_name = selected_items[0].text()

        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "削除確認",
            f"フィルター '{filter_name}' を削除しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 削除実行
        try:
            success = self.favorite_filters_service.delete_filter(filter_name)
            if success:
                QMessageBox.information(self, "削除完了", f"フィルター '{filter_name}' を削除しました。")
                self._refresh_favorite_filters_list()
            else:
                QMessageBox.warning(self, "削除失敗", "フィルターの削除に失敗しました。")
        except Exception as e:
            logger.error("Failed to delete filter '{}': {}", filter_name, e, exc_info=True)
            QMessageBox.critical(self, "エラー", f"フィルターの削除中にエラーが発生しました:\n{e}")

    def connect_signals(self) -> None:
        """Qt DesignerのUIコンポーネントにシグナルを接続"""
        # 検索関連（チェックボックスに更新）
        self.ui.lineEditSearch.returnPressed.connect(self._on_search_requested)
        self.ui.checkboxTags.toggled.connect(self._on_search_type_changed)
        self.ui.checkboxCaption.toggled.connect(self._on_search_type_changed)

        # 解像度フィルター
        self.ui.comboResolution.currentTextChanged.connect(self._on_resolution_changed)

        # 日付フィルター
        self.ui.checkboxDateFilter.toggled.connect(self._on_date_filter_toggled)
        self.date_range_slider.valueChanged.connect(self._on_date_range_changed)

        # Ratingフィルター
        self.ui.comboRating.currentTextChanged.connect(self._on_rating_changed)

        # アクションボタン
        self.ui.buttonApply.clicked.connect(self._on_apply_clicked)
        self.ui.buttonClear.clicked.connect(self._on_clear_clicked)

    def set_search_filter_service(self, service: "SearchFilterService") -> None:
        """SearchFilterServiceを設定（拡張版：バリデーションとログ強化）"""
        if service is None:
            raise ValueError("SearchFilterService cannot be None")

        if not hasattr(service, "create_search_conditions"):
            raise TypeError(f"Invalid SearchFilterService: missing required methods. Got: {type(service)}")

        # 既存サービスの置き換え警告
        if self.search_filter_service is not None:
            logger.warning(
                f"SearchFilterService置き換え: "
                f"old={type(self.search_filter_service)} -> new={type(service)}"
            )

        self.search_filter_service = service
        logger.info(f"SearchFilterService set for FilterSearchPanel: {type(service)}")

        # サービス機能確認（デバッグ用）
        try:
            # 基本メソッド存在確認
            required_methods = ["create_search_conditions", "parse_search_input"]
            missing_methods = []
            for method in required_methods:
                if not hasattr(service, method):
                    missing_methods.append(method)

            if missing_methods:
                logger.warning(f"SearchFilterService missing methods: {missing_methods}")
            else:
                logger.debug("SearchFilterService method validation: OK")

        except Exception as e:
            logger.error(f"SearchFilterService validation error: {e}", exc_info=True)

    def set_worker_service(self, service: "WorkerService") -> None:
        """WorkerServiceを設定"""
        self.worker_service = service

        # WorkerServiceのシグナル接続（検索専用）
        if self.worker_service:
            self.worker_service.search_finished.connect(self._on_search_finished)
            self.worker_service.search_error.connect(self._on_search_error)

            # Option B: バッチ進捗シグナル接続を追加
            self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.debug("WorkerService set for FilterSearchPanel")

    def _on_search_finished(self, result: Any) -> None:
        """検索完了イベント処理（SearchResult/dataclass想定）"""
        logger.info("検索完了イベント受信")

        try:
            # SearchWorkerの標準結果（SearchResult dataclass）
            if hasattr(result, "total_count") and hasattr(result, "image_metadata"):
                count = result.total_count

                # Phase 3: State transition based on result
                if count > 0:
                    # サムネイル読み込み段階に移行
                    self._transition_to_state(PipelineState.LOADING_THUMBNAILS)
                else:
                    # 結果0件の場合は表示状態に直接移行
                    self._transition_to_state(PipelineState.DISPLAYING)

                # プレビュー更新
                self.update_search_preview(count)

                # 後方互換: dict形式でも通知
                self.search_completed.emit(
                    {
                        "results": result.image_metadata,
                        "count": count,
                        "conditions": getattr(result, "filter_conditions", {}),
                    }
                )
                logger.info(f"検索結果: {count}件")
            else:
                logger.error(f"無効な検索結果: {result}")
                # Phase 3: State transition to ERROR
                self._transition_to_state(PipelineState.ERROR)
        except Exception as e:
            logger.error(f"検索完了処理エラー: {e}", exc_info=True)
            # Phase 3: State transition to ERROR
            self._transition_to_state(PipelineState.ERROR)
        finally:
            # 状態リセット
            self._current_search_worker_id = None

    def _on_search_error(self, error: str) -> None:
        """検索エラーイベント処理"""
        logger.error(f"検索エラー: {error}")
        self._current_search_worker_id = None

        # Phase 3: State transition to ERROR
        self._transition_to_state(PipelineState.ERROR)

        self.search_completed.emit({"results": [], "count": 0, "error": error})

    def _on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """ワーカーのバッチ進捗処理（Option B: 動的進捗計算）"""
        try:
            # 現在の検索・サムネイルワーカーかチェック
            if worker_id == self._current_search_worker_id:
                # 検索フェーズ: 0-30%
                if total > 0:
                    search_progress = current / total
                    overall_progress = search_progress * 0.3  # 30%まで
                    self.update_pipeline_progress(f"検索中... ({current}/{total})", overall_progress, 0.3)
                    logger.debug(f"Search batch progress: {current}/{total} -> {overall_progress:.1%}")

            elif (
                hasattr(self.worker_service, "current_thumbnail_worker_id")
                and worker_id == self.worker_service.current_thumbnail_worker_id
            ):
                # サムネイル読み込みフェーズ: 30-100%
                if total > 0:
                    thumbnail_progress = current / total
                    overall_progress = 0.3 + (thumbnail_progress * 0.7)  # 30% + 70%
                    self.update_pipeline_progress(
                        f"サムネイル読み込み中... ({current}/{total}) {filename}", overall_progress, 1.0
                    )
                    logger.debug(f"Thumbnail batch progress: {current}/{total} -> {overall_progress:.1%}")

        except Exception as e:
            logger.error(f"バッチ進捗処理エラー: {e}")

    def _reset_search_ui(self) -> None:
        """検索UI状態をリセット"""
        # Phase 3: State transition to IDLE
        self._transition_to_state(PipelineState.IDLE)

    def _show_search_progress(self) -> None:
        """検索進捗UI表示 - ModernProgressManagerに移行済みため無効化"""
        logger.debug("Search progress display delegated to ModernProgressManager popup")

    def _transition_to_state(self, new_state: PipelineState) -> None:
        """パイプライン状態遷移管理 (Phase 3)"""
        if self._current_state == new_state:
            return  # 同じ状態への遷移は無視

        old_state = self._current_state
        self._current_state = new_state

        # 状態遷移ログ
        logger.info(f"Pipeline state transition: {old_state.value} → {new_state.value}")

        # 状態別UI更新
        self._update_ui_for_state(new_state)

        # 状態変更シグナル発火
        self.pipeline_state_changed.emit(new_state)

    def _update_ui_for_state(self, state: PipelineState) -> None:
        """状態に応じたUI更新 (Phase 3)"""
        if state == PipelineState.IDLE:
            self.progress_bar.setVisible(False)
            pass

        elif state == PipelineState.SEARCHING:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(10)  # 開始時の進捗

        elif state == PipelineState.LOADING_THUMBNAILS:
            # 検索完了、サムネイル読み込み開始
            self.progress_bar.setValue(30)  # 0.3 * 100 = 30%

        elif state == PipelineState.DISPLAYING:
            # プログレスバーは表示継続（サムネイル読み込み中の可能性があるため）
            self.progress_bar.setValue(100)  # 完了表示
            # 結果表示はmessageで行う（検索結果テキスト）

        elif state in (PipelineState.ERROR, PipelineState.CANCELED):
            self.progress_bar.setVisible(False)

    def hide_progress_after_completion(self) -> None:
        """パイプライン完全完了後にプログレスバーを非表示にする - ModernProgressManagerに移行済み"""
        # Phase 3: ポップアップ式プログレス表示への完全移行
        # ModernProgressManagerが自動的にプログレス完了処理を行うため、無効化
        logger.debug("Progress hiding delegated to ModernProgressManager (pipeline completion)")

        # プログレスバーのみ非表示（キャンセルボタン削除により簡素化）
        if hasattr(self, "progress_bar") and self.progress_bar:
            self.progress_bar.setVisible(False)

    # === Event Handlers ===

    def _on_resolution_changed(self, text: str) -> None:
        """解像度選択変更処理"""
        # 固定解像度選択肢のみのため処理不要

    def _on_rating_changed(self, text: str) -> None:
        """Rating選択変更処理"""
        # Rating選択肢変更時の処理（必要に応じて実装）
        logger.debug(f"Rating changed: {text}")

    def _on_date_filter_toggled(self, checked: bool) -> None:
        """日付フィルター有効化切り替え処理"""
        self.ui.frameDateRange.setVisible(checked)

    def _on_date_range_changed(self, min_timestamp: int, max_timestamp: int) -> None:
        """日付範囲変更処理"""
        logger.debug(f"日付範囲変更: {min_timestamp} - {max_timestamp}")
        # 自動検索は行わず、ユーザーが検索ボタンを押すまで待つ

    def get_date_range_from_slider(self) -> tuple[datetime | None, datetime | None]:
        """
        CustomRangeSliderから日付範囲を取得してdatetimeオブジェクトに変換
        # NOTE: CustomRangeSliderがdatetimeオブジェクトを返すようにしたほうがいいかも

        Returns:
            tuple: (start_datetime, end_datetime) または (None, None) if not enabled
        """
        if not self.ui.checkboxDateFilter.isChecked():
            return None, None

        try:
            min_timestamp, max_timestamp = self.date_range_slider.get_range()

            # タイムスタンプの妥当性検証
            if min_timestamp < 0 or max_timestamp < 0:
                logger.warning(f"無効なタイムスタンプ: min={min_timestamp}, max={max_timestamp}")
                return None, None

            if min_timestamp > max_timestamp:
                logger.warning(f"開始日付が終了日付より後: start={min_timestamp}, end={max_timestamp}")
                # 自動修正: 値を交換
                min_timestamp, max_timestamp = max_timestamp, min_timestamp

            # タイムスタンプをdatetimeオブジェクトに変換
            start_date = datetime.fromtimestamp(min_timestamp)
            end_date = datetime.fromtimestamp(max_timestamp)

            # 日付範囲の妥当性確認（未来の日付チェック）
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

    def _on_only_untagged_toggled(self, checked: bool) -> None:
        """未タグ画像のみ検索トグル処理"""
        self._update_search_input_state()
        self._on_search_type_changed()

    def _on_only_uncaptioned_toggled(self, checked: bool) -> None:
        """未キャプション画像のみ検索トグル処理"""
        self._update_search_input_state()
        self._on_search_type_changed()

    def _get_selected_search_types(self) -> list[str]:
        """選択された検索タイプのリストを取得"""
        types = []
        if self.ui.checkboxTags.isChecked():
            types.append("tags")
        if self.ui.checkboxCaption.isChecked():
            types.append("caption")
        return types

    def _get_primary_search_type(self) -> str:
        """主要な検索タイプを取得（従来のAPI互換性のため）"""
        types = self._get_selected_search_types()
        if "tags" in types:
            return "tags"
        elif "caption" in types:
            return "caption"
        else:
            return "tags"  # デフォルト

    def _get_rating_filter_value(self) -> str | None:
        """
        Ratingコンボボックスから選択された値を取得

        Returns:
            str | None: Rating値（'PG', 'PG-13', 'R', 'X', 'XXX', 'UNRATED'）または None（全て選択時）
        """
        text = self.ui.comboRating.currentText()
        if text == "全て":
            return None
        if text == "未設定のみ":
            return "UNRATED"

        # "PG (全年齢)" -> "PG" に変換
        rating_value = text.split()[0] if text else None
        logger.debug(f"Rating filter value: {rating_value}")
        return rating_value

    def _get_ai_rating_filter_value(self) -> str | None:
        """
        AIレーティングコンボボックスから選択された値を取得

        Returns:
            str | None: AI Rating値（'PG', 'PG-13', 'R', 'X', 'XXX', 'UNRATED'）または None（全て選択時）
        """
        text = self.ui.comboAIRating.currentText()
        if text == "全て":
            return None
        if text == "未設定のみ":
            return "UNRATED"

        # "PG (全年齢)" -> "PG" に変換
        ai_rating_value = text.split()[0] if text else None
        logger.debug(f"AI rating filter value: {ai_rating_value}")
        return ai_rating_value

    @staticmethod
    def _is_nsfw_rating(rating_value: str | None) -> bool:
        """NSFWレーティング値かどうか判定する。"""
        return rating_value in {"R", "X", "XXX"}

    def _resolve_include_nsfw(
        self, rating_filter: str | None, ai_rating_filter: str | None
    ) -> bool:
        """レーティング選択からNSFW含有フラグを決定する。"""
        include_nsfw = self._is_nsfw_rating(rating_filter) or self._is_nsfw_rating(ai_rating_filter)
        logger.debug(
            f"NSFW include resolved from ratings: manual={rating_filter}, "
            f"ai={ai_rating_filter}, include_nsfw={include_nsfw}"
        )
        return include_nsfw

    def _on_search_type_changed(self) -> None:
        """検索タイプ変更時の処理（チェックボックス対応）"""
        # 入力フィールドの有効/無効を更新
        self._update_search_input_state()

        # プレースホルダーテキストを更新
        selected_types = self._get_selected_search_types()

        if not selected_types:
            # 何も選択されていない場合
            self.ui.lineEditSearch.setPlaceholderText("検索タイプを選択してください...")
        elif len(selected_types) == 1:
            # 単一タイプ選択時
            if "tags" in selected_types:
                if self.ui.checkboxOnlyUntagged.isChecked():
                    self.ui.lineEditSearch.setPlaceholderText("未タグ画像検索中（タグ入力無効）")
                else:
                    self.ui.lineEditSearch.setPlaceholderText(
                        "検索キーワードを入力（複数タグの場合はカンマ区切り）..."
                    )
            elif "caption" in selected_types:
                if self.ui.checkboxOnlyUncaptioned.isChecked():
                    self.ui.lineEditSearch.setPlaceholderText(
                        "未キャプション画像検索中（キャプション入力無効）"
                    )
                else:
                    self.ui.lineEditSearch.setPlaceholderText("キャプション検索キーワードを入力...")
        else:
            # 複数タイプ選択時
            self.ui.lineEditSearch.setPlaceholderText("タグ・キャプション検索キーワードを入力...")

    def _update_search_input_state(self) -> None:
        """検索入力フィールドの有効/無効状態を更新（チェックボックス対応）"""
        # タグ検索で未タグ検索が有効、またはキャプション検索で未キャプション検索が有効の場合は無効化
        disabled = (self.ui.checkboxTags.isChecked() and self.ui.checkboxOnlyUntagged.isChecked()) or (
            self.ui.checkboxCaption.isChecked() and self.ui.checkboxOnlyUncaptioned.isChecked()
        )
        self.ui.lineEditSearch.setEnabled(not disabled)

    def _on_search_requested(self) -> None:
        """検索要求処理 - WorkerService経由で非同期実行（Qt Designer Phase 2レスポンシブレイアウト対応強化版）"""
        if not self.search_filter_service:
            # 詳細診断情報を追加（Qt Designer Phase 2対応強化版）
            error_details = [
                "SearchFilterService not set - 詳細診断:",
                f"  - FilterSearchPanel instance: {id(self)}",
                f"  - search_filter_service: {self.search_filter_service}",
                f"  - hasattr(search_filter_service): {hasattr(self, 'search_filter_service')}",
            ]

            # MainWindow統合状況の確認（Qt Designer Phase 2診断強化版）
            try:
                parent_window = self.window()
                if hasattr(parent_window, "filter_search_panel"):
                    parent_instance = parent_window.filter_search_panel
                    is_same_instance = parent_instance is self
                    parent_service = (
                        getattr(parent_instance, "search_filter_service", None) if parent_instance else None
                    )

                    error_details.extend(
                        [
                            f"  - MainWindow.filter_search_panel: {id(parent_instance) if parent_instance else None}",
                            f"    (same instance: {is_same_instance})",
                            f"  - Parent instance service: {parent_service}",
                            f"    (parent service type: {type(parent_service) if parent_service else 'None'})",
                        ]
                    )

                    # Qt Designer生成インスタンス確認
                    if hasattr(parent_window, "filterSearchPanel"):
                        qt_designer_instance = parent_window.filterSearchPanel
                        qt_same_as_parent = qt_designer_instance is parent_instance
                        qt_same_as_self = qt_designer_instance is self

                        error_details.extend(
                            [
                                f"  - Qt Designer filterSearchPanel: {id(qt_designer_instance) if qt_designer_instance else None}",
                                f"    (same as parent: {qt_same_as_parent}, same as self: {qt_same_as_self})",
                            ]
                        )

                        # Qt Designer Phase 2の影響を確認
                        if qt_designer_instance and hasattr(qt_designer_instance, "search_filter_service"):
                            qt_service = getattr(qt_designer_instance, "search_filter_service", None)
                            error_details.append(f"    (Qt Designer instance service: {qt_service})")

                    # Phase 3.5統合状況の推測
                    if parent_instance and parent_service and not is_same_instance:
                        error_details.append(
                            "  - 疑われる問題: Qt Designer Phase 2変更によるインスタンス不整合"
                        )
                    elif parent_instance and not parent_service:
                        error_details.append(
                            "  - 疑われる問題: MainWindow._setup_search_filter_integration()未実行または失敗"
                        )
                    elif not parent_instance:
                        error_details.append(
                            "  - 疑われる問題: MainWindow.setup_custom_widgets()未実行または失敗"
                        )

                else:
                    error_details.append("  - MainWindow.filter_search_panel attribute not found")

            except Exception as diagnostic_error:
                error_details.append(f"  - Diagnostic error: {diagnostic_error}")

            # 詳細エラーログ出力
            logger.error("\n".join(error_details))
            return

        if not self.worker_service:
            logger.warning("WorkerService not set, falling back to synchronous search")
            self._execute_synchronous_search()
            return

        # 既存の検索をキャンセル
        if self._current_search_worker_id:
            logger.info(f"既存の検索をキャンセル: {self._current_search_worker_id}")
            self.worker_service.cancel_search(self._current_search_worker_id)
            self._reset_search_ui()

        try:
            # 検索テキストをキーワードリストに変換
            search_text = self.ui.lineEditSearch.text().strip()
            keywords = self.search_filter_service.parse_search_input(search_text) if search_text else []

            # 基本的な入力検証
            if not keywords and not any(
                [
                    self.ui.checkboxOnlyUntagged.isChecked(),
                    self.ui.checkboxOnlyUncaptioned.isChecked(),
                    self.ui.checkboxDateFilter.isChecked(),
                    self.ui.comboResolution.currentText() != "全て",
                    self.ui.comboAspectRatio.currentText() != "全て",
                    self.ui.comboRating.currentText() != "全て",
                    self.ui.comboAIRating.currentText() != "全て",
                ]
            ):
                logger.info("検索条件が未指定のため検索をスキップ")
                return

            # 日付範囲を取得
            date_range_start, date_range_end = self.get_date_range_from_slider()

            # 日付フィルターが有効だが範囲が取得できない場合の処理
            if self.ui.checkboxDateFilter.isChecked() and (
                date_range_start is None or date_range_end is None
            ):
                logger.warning("日付範囲フィルターエラー: 有効だが範囲が無効")
                return

            rating_filter = self._get_rating_filter_value()
            ai_rating_filter = self._get_ai_rating_filter_value()
            include_nsfw = self._resolve_include_nsfw(rating_filter, ai_rating_filter)

            # SearchFilterServiceを使用して検索条件を作成
            conditions = self.search_filter_service.create_search_conditions(
                search_type=self._get_primary_search_type(),
                keywords=keywords,
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
            )

            # Phase 3: State transition to SEARCHING
            self._transition_to_state(PipelineState.SEARCHING)

            # WorkerServiceで非同期検索開始
            worker_id = self.worker_service.start_search(conditions)
            if worker_id:
                self._current_search_worker_id = worker_id
                logger.info(f"非同期検索開始: {worker_id}")

                # 旧形式のシグナルも発行（後方互換性）
                self.search_requested.emit({"conditions": conditions, "worker_id": worker_id})
            else:
                logger.error("WorkerService.start_search failed")
                # Phase 3: State transition to ERROR
                self._transition_to_state(PipelineState.ERROR)

        except AttributeError as e:
            logger.error(f"UI AttributeError: {e}", exc_info=True)
            # Phase 3: State transition to ERROR
            self._transition_to_state(PipelineState.ERROR)
        except ValueError as e:
            logger.error(f"検索入力値エラー: {e}")
            # Phase 3: State transition to ERROR
            self._transition_to_state(PipelineState.ERROR)
        except Exception as e:
            logger.error(f"検索実行エラー: {e}", exc_info=True)
            # Phase 3: State transition to ERROR
            self._transition_to_state(PipelineState.ERROR)

    def _execute_synchronous_search(self) -> None:
        """同期検索実行（WorkerServiceが利用できない場合のフォールバック）"""
        logger.info("フォールバック: 同期検索を実行")

        try:
            # 検索テキストをキーワードリストに変換
            search_text = self.ui.lineEditSearch.text().strip()
            keywords = self.search_filter_service.parse_search_input(search_text) if search_text else []

            # 日付範囲を取得
            date_range_start, date_range_end = self.get_date_range_from_slider()

            rating_filter = self._get_rating_filter_value()
            ai_rating_filter = self._get_ai_rating_filter_value()
            include_nsfw = self._resolve_include_nsfw(rating_filter, ai_rating_filter)

            # SearchFilterServiceを使用して検索条件を作成
            conditions = self.search_filter_service.create_search_conditions(
                search_type=self._get_primary_search_type(),
                keywords=keywords,
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
            )

            # 検索実行
            results, count = self.search_filter_service.execute_search_with_filters(conditions)

            # プレビュー更新
            self.update_search_preview(count)

            # 結果をシグナルで送信
            result_data = {"results": results, "count": count, "conditions": conditions}
            self.search_requested.emit(result_data)
            self.search_completed.emit(result_data)
            logger.info(f"同期検索完了: {count}件")

        except Exception as e:
            logger.error(f"同期検索実行エラー: {e}", exc_info=True)
            self.search_completed.emit({"results": [], "count": 0, "error": str(e)})

    def _on_clear_requested(self) -> None:
        """クリア要求処理"""
        self._clear_all_inputs()

        # MainWindow にクリア要求を送信
        self.filter_cleared.emit()
        logger.info("フィルター・検索をクリア")

    # === Private Methods ===

    def _update_ui_from_conditions(self, conditions: dict) -> None:
        """条件からUIを更新"""
        # 検索テキスト（チェックボックス対応）
        if conditions.get("tags"):
            self.ui.checkboxTags.setChecked(True)
            self.ui.lineEditSearch.setText(", ".join(conditions["tags"]))
            self.ui.radioAnd.setChecked(conditions.get("use_and", True))
            self.ui.radioOr.setChecked(not conditions.get("use_and", True))
        elif conditions.get("caption"):
            self.ui.checkboxCaption.setChecked(True)
            self.ui.lineEditSearch.setText(conditions["caption"])

        # 解像度
        if "resolution" in conditions:
            resolution = conditions["resolution"]
            if resolution in [
                self.ui.comboResolution.itemText(i) for i in range(self.ui.comboResolution.count())
            ]:
                self.ui.comboResolution.setCurrentText(resolution)

        # 日付範囲
        if "date_range" in conditions:
            # start_timestamp, end_timestamp = conditions["date_range"]
            # start_date = datetime.fromtimestamp(start_timestamp).date()
            # end_date = datetime.fromtimestamp(end_timestamp).date()

            self.ui.checkboxDateFilter.setChecked(True)
            # Note: Qt DesignerのUIには日付選択ウィジェットがないため、この部分は後で対応
            # 日付範囲の設定はCustomRangeSliderで行う

    def _clear_all_inputs(self) -> None:
        """全入力をクリア"""
        self.ui.lineEditSearch.clear()
        self.ui.checkboxTags.setChecked(True)
        self.ui.checkboxCaption.setChecked(False)
        self.ui.radioAnd.setChecked(True)

        self.ui.comboResolution.setCurrentIndex(0)
        self.ui.comboAspectRatio.setCurrentIndex(0)

        self.ui.checkboxDateFilter.setChecked(False)
        self.ui.frameDateRange.setVisible(False)
        # スライダーを全範囲にリセット
        self.date_range_slider.slider.setValue((0, 100))

        self.ui.checkboxOnlyUntagged.setChecked(False)
        self.ui.checkboxOnlyUncaptioned.setChecked(False)
        self.ui.checkboxExcludeDuplicates.setChecked(False)

    # === Public Methods ===

    def set_search_text(self, text: str, search_type: str = "tags") -> None:
        """検索テキストを設定"""
        self.ui.lineEditSearch.setText(text)
        if search_type == "tags":
            self.ui.checkboxTags.setChecked(True)
            self.ui.checkboxCaption.setChecked(False)
        else:
            self.ui.checkboxCaption.setChecked(True)
            self.ui.checkboxTags.setChecked(False)

    def get_current_conditions(self) -> dict[str, Any]:
        """現在の条件を取得"""
        if not self.search_filter_service:
            return {}

        # SearchFilterServiceから現在の条件を取得
        current = self.search_filter_service.get_current_conditions()
        if current:
            # SearchConditionsオブジェクトを辞書に変換
            return {
                "search_type": current.search_type,
                "keywords": current.keywords,
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
        """条件を適用"""
        self._update_ui_from_conditions(conditions)

    def update_search_preview(self, result_count: int, preview_text: str = "") -> None:
        """検索結果プレビューを更新"""
        # 大量データ警告の閾値
        LARGE_RESULT_WARNING_THRESHOLD = 10000

        if result_count > 0:
            preview = f"検索結果: {result_count}件"

            # 10000件超で警告メッセージ追加
            if result_count > LARGE_RESULT_WARNING_THRESHOLD:
                warning_msg = (
                    f"\n\n⚠️ 警告: 検索結果が {result_count:,} 件と非常に多いです。\n"
                    "サムネイル表示に時間がかかる可能性があります。\n"
                    "より具体的な条件での絞り込みをお勧めします。"
                )
                preview += warning_msg
                logger.warning(f"Large search result warning displayed: {result_count} items")

            if preview_text:
                preview += f"\n{preview_text}"
        else:
            preview = "検索結果がありません"

        logger.debug(f"検索結果プレビュー更新: {result_count}件")

    def clear_search_preview(self) -> None:
        """検索結果プレビューをクリア"""
        logger.debug("検索結果プレビューをクリア")

    def _on_apply_clicked(self) -> None:
        """適用ボタンクリック処理"""
        self._on_search_requested()

    def _on_clear_clicked(self) -> None:
        """クリアボタンクリック処理"""
        self._on_clear_requested()

    def update_pipeline_progress(self, message: str, current_progress: float, end_progress: float) -> None:
        """Pipeline進捗表示の更新 - ModernProgressManagerに移行済みため無効化"""
        # Phase 3: ポップアップ式プログレス表示への完全移行
        # WorkerServiceのModernProgressManagerが自動的にポップアップ表示を提供するため、
        # インライン表示は無効化してプログレス表示を統一
        logger.debug(
            f"Progress update delegated to ModernProgressManager: {message} ({current_progress * 100:.1f}%)"
        )

        # 既存のプログレスバーを非表示にして統一
        if hasattr(self, "progress_bar") and self.progress_bar:
            if self.progress_bar.isVisible():
                self.progress_bar.setVisible(False)
                logger.debug("Inline progress bar hidden - using popup progress display")

    def handle_pipeline_error(self, phase: str, error_info: dict) -> None:
        """Pipelineエラー処理（Phase 2対応）"""
        try:
            # Phase 3: State transition to ERROR
            self._transition_to_state(PipelineState.ERROR)

            # エラーメッセージの表示
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Pipeline {phase} error: {error_message}")

            # UI状態のリセット（エラー時は検索結果破棄）
            # キャンセルボタン削除のため、UI状態リセット処理を簡素化

            # エラー状態の通知（オプション）
            if hasattr(self, "search_completed"):
                self.search_completed.emit({"success": False, "phase": phase, "error": error_message})

        except Exception as e:
            logger.error(f"Failed to handle pipeline error: {e}")

    def clear_pipeline_results(self) -> None:
        """Pipeline結果のクリア（キャンセル・エラー時用）"""
        try:
            # Phase 3: State transition to CANCELED or IDLE
            if self._current_state == PipelineState.ERROR:
                # エラー状態からのクリアの場合はIDLEに遷移
                self._transition_to_state(PipelineState.IDLE)
            else:
                # その他の場合（キャンセル等）はCANCELED状態に遷移
                self._transition_to_state(PipelineState.CANCELED)

            # フィルター結果クリア通知
            self.filter_cleared.emit()

            logger.info("Pipeline results cleared")

        except Exception as e:
            logger.error(f"Failed to clear pipeline results: {e}")

    # Phase 3: Additional Pipeline State Management Methods

    def notify_thumbnail_loading_started(self) -> None:
        """サムネイル読み込み開始通知 (MainWindowから呼び出し)"""
        if self._current_state == PipelineState.SEARCHING:
            self._transition_to_state(PipelineState.LOADING_THUMBNAILS)
            logger.info("Thumbnail loading phase started")

    def notify_thumbnail_loading_completed(self, thumbnail_count: int) -> None:
        """サムネイル読み込み完了通知 (MainWindowから呼び出し)"""
        if self._current_state == PipelineState.LOADING_THUMBNAILS:
            self._transition_to_state(PipelineState.DISPLAYING)
            logger.info(f"Thumbnail loading completed: {thumbnail_count} thumbnails")

    def notify_thumbnail_loading_error(self, error: str) -> None:
        """サムネイル読み込みエラー通知 (MainWindowから呼び出し)"""
        logger.error(f"Thumbnail loading error: {error}")
        self._transition_to_state(PipelineState.ERROR)

    def get_current_pipeline_state(self) -> PipelineState:
        """現在のパイプライン状態を取得"""
        return self._current_state

    def is_pipeline_active(self) -> bool:
        """パイプラインがアクティブ状態かどうか"""
        return self._current_state in (PipelineState.SEARCHING, PipelineState.LOADING_THUMBNAILS)

    def force_pipeline_reset(self) -> None:
        """強制的にパイプライン状態をリセット（緊急時用）"""
        logger.warning("Force pipeline reset requested")
        self._transition_to_state(PipelineState.IDLE)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    # ログ設定の初期化
    logconf = {"level": "DEBUG", "file": "FilterSearchPanel.log"}
    initialize_logging(logconf)

    # テスト用のアプリケーション
    app = QApplication(sys.argv)

    # メインウィンドウ作成
    main_window = QMainWindow()
    main_window.setWindowTitle("FilterSearchPanel テスト")
    main_window.resize(350, 700)

    # FilterSearchPanelウィジェット作成
    filter_panel = FilterSearchPanel()

    # シグナル接続（テスト用）
    def on_search_requested(data: dict[str, Any]) -> None:
        from lorairo.utils.log import logger

        logger.debug(f"検索要求: {data}")

    def on_filter_cleared() -> None:
        from lorairo.utils.log import logger

        logger.debug("フィルタークリア")

    filter_panel.search_requested.connect(on_search_requested)
    filter_panel.filter_cleared.connect(on_filter_cleared)

    # ウィジェットをメインウィンドウに設定
    main_window.setCentralWidget(filter_panel)

    # ウィンドウ表示
    main_window.show()

    # アプリケーション実行
    sys.exit(app.exec())
