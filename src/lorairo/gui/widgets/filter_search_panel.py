# src/lorairo/gui/widgets/filter_search_panel.py

from datetime import datetime
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea

from ...utils.log import logger
from ..designer.FilterSearchPanel_ui import Ui_FilterSearchPanel
from ..services.search_filter_service import SearchFilterService
from ..services.worker_service import WorkerService
from .custom_range_slider import CustomRangeSlider


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

    def __init__(self, parent=None):
        super().__init__(parent)

        # SearchFilterService（依存注入）
        self.search_filter_service: SearchFilterService | None = None

        # WorkerService（依存注入）
        self.worker_service: WorkerService | None = None

        # 現在のSearchWorkerのID
        self._current_search_worker_id: str | None = None

        # UI設定
        self.ui = Ui_FilterSearchPanel()
        self.ui.setupUi(self)
        self.setup_custom_widgets()
        self.connect_signals()

        logger.debug("FilterSearchPanel initialized")

    def setup_custom_widgets(self) -> None:
        """Qt DesignerのUIに日付範囲スライダーと進捗表示を追加"""
        from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton

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

        # 進捗表示UI作成
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)

        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._on_cancel_search_requested)

        # 進捗表示レイアウト作成
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_layout.addWidget(self.cancel_button)

        # プレビューテキストエリアの下に進捗UIを追加
        main_layout = self.ui.textEditPreview.parent().layout()
        if main_layout:
            # textEditPreviewの下に進捗UIを挿入
            preview_index = main_layout.indexOf(self.ui.textEditPreview)
            main_layout.insertLayout(preview_index + 1, self.progress_layout)

    def connect_signals(self) -> None:
        """Qt DesignerのUIコンポーネントにシグナルを接続"""
        # 検索関連
        self.ui.lineEditSearch.returnPressed.connect(self._on_search_requested)
        self.ui.radioTags.toggled.connect(self._on_search_type_changed)
        self.ui.radioCaption.toggled.connect(self._on_search_type_changed)

        # 解像度フィルター
        self.ui.comboResolution.currentTextChanged.connect(self._on_resolution_changed)

        # 日付フィルター
        self.ui.checkboxDateFilter.toggled.connect(self._on_date_filter_toggled)
        self.date_range_slider.valueChanged.connect(self._on_date_range_changed)

        # アクションボタン
        self.ui.buttonApply.clicked.connect(self._on_apply_clicked)
        self.ui.buttonClear.clicked.connect(self._on_clear_clicked)

    def set_search_filter_service(self, service: SearchFilterService) -> None:
        """SearchFilterServiceを設定"""
        self.search_filter_service = service
        logger.debug("SearchFilterService set for FilterSearchPanel")

    def set_worker_service(self, service: WorkerService) -> None:
        """WorkerServiceを設定"""
        self.worker_service = service

        # WorkerServiceのシグナル接続（検索専用）
        if self.worker_service:
            self.worker_service.search_finished.connect(self._on_search_finished)
            self.worker_service.search_error.connect(self._on_search_error)

        logger.debug("WorkerService set for FilterSearchPanel")

    def _on_cancel_search_requested(self) -> None:
        """検索キャンセル処理（Pipeline対応）"""
        if self._current_search_worker_id and self.worker_service:
            logger.info(f"検索キャンセル要求: {self._current_search_worker_id}")

            # Phase 2: Pipeline全体のキャンセレーション
            # MainWindow経由でPipeline cascade cancellationを実行
            parent_window = self.parent()
            while parent_window and not hasattr(parent_window, "cancel_current_pipeline"):
                parent_window = parent_window.parent()

            if parent_window and hasattr(parent_window, "cancel_current_pipeline"):
                parent_window.cancel_current_pipeline()
                logger.info("Pipeline cancellation requested through MainWindow")
            else:
                # Fallback: 直接SearchWorkerキャンセル
                self.worker_service.cancel_search(self._current_search_worker_id)
                logger.info("Direct search worker cancellation (fallback)")

            # Pipeline結果クリア
            self.clear_pipeline_results()

    def _on_search_finished(self, result: Any) -> None:
        """検索完了イベント処理（SearchResult/dataclass想定）"""
        logger.info("検索完了イベント受信")

        try:
            # SearchWorkerの標準結果（SearchResult dataclass）
            if hasattr(result, "total_count") and hasattr(result, "image_metadata"):
                count = result.total_count
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
                error_msg = "検索結果の形式が無効です"
                logger.error(f"無効な検索結果: {result}")
                self.ui.textEditPreview.setPlainText(error_msg)
        finally:
            # 状態リセット
            self._current_search_worker_id = None
            self._reset_search_ui()

    def _on_search_error(self, error: str) -> None:
        """検索エラーイベント処理"""
        logger.error(f"検索エラー: {error}")
        self._current_search_worker_id = None

        error_msg = f"検索中にエラーが発生しました: {error}"
        self.ui.textEditPreview.setPlainText(error_msg)
        self.search_completed.emit({"results": [], "count": 0, "error": error})

        self._reset_search_ui()

    def _reset_search_ui(self) -> None:
        """検索UI状態をリセット"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.progress_bar.setValue(0)

    def _show_search_progress(self) -> None:
        """検索進捗UI表示"""
        self.progress_bar.setVisible(True)
        self.cancel_button.setVisible(True)
        self.progress_bar.setValue(10)  # 開始時の進捗
        self.search_progress_started.emit()

    # === Event Handlers ===

    def _on_resolution_changed(self, text: str) -> None:
        """解像度選択変更処理"""
        # 固定解像度選択肢のみのため処理不要

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

    def _on_search_type_changed(self) -> None:
        """検索タイプ変更時の処理"""
        # 入力フィールドの有効/無効を更新
        self._update_search_input_state()

        # プレースホルダーテキストを更新
        if self.ui.radioTags.isChecked():
            if self.ui.checkboxOnlyUntagged.isChecked():
                self.ui.lineEditSearch.setPlaceholderText("未タグ画像検索中（タグ入力無効）")
            else:
                self.ui.lineEditSearch.setPlaceholderText(
                    "検索キーワードを入力（複数タグの場合はカンマ区切り）..."
                )
        else:  # caption
            if self.ui.checkboxOnlyUncaptioned.isChecked():
                self.ui.lineEditSearch.setPlaceholderText(
                    "未キャプション画像検索中（キャプション入力無効）"
                )
            else:
                self.ui.lineEditSearch.setPlaceholderText("キャプション検索キーワードを入力...")

    def _update_search_input_state(self) -> None:
        """検索入力フィールドの有効/無効状態を更新"""
        # タグ検索で未タグ検索が有効、またはキャプション検索で未キャプション検索が有効の場合は無効化
        disabled = (self.ui.radioTags.isChecked() and self.ui.checkboxOnlyUntagged.isChecked()) or (
            self.ui.radioCaption.isChecked() and self.ui.checkboxOnlyUncaptioned.isChecked()
        )
        self.ui.lineEditSearch.setEnabled(not disabled)

    def _on_search_requested(self) -> None:
        """検索要求処理 - WorkerService経由で非同期実行"""
        if not self.search_filter_service:
            logger.warning("SearchFilterService not set, cannot execute search")
            self.ui.textEditPreview.setPlainText("SearchFilterServiceが設定されていません")
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
                ]
            ):
                self.ui.textEditPreview.setPlainText("検索条件を入力してください")
                logger.info("検索条件が未指定のため検索をスキップ")
                return

            # 日付範囲を取得
            date_range_start, date_range_end = self.get_date_range_from_slider()

            # 日付フィルターが有効だが範囲が取得できない場合の処理
            if self.ui.checkboxDateFilter.isChecked() and (
                date_range_start is None or date_range_end is None
            ):
                error_msg = "日付範囲の設定に問題があります。日付フィルターを無効にするか、範囲を再設定してください。"
                self.ui.textEditPreview.setPlainText(error_msg)
                logger.warning("日付範囲フィルターエラー: 有効だが範囲が無効")
                return

            # SearchFilterServiceを使用して検索条件を作成
            conditions = self.search_filter_service.create_search_conditions(
                search_type="tags" if self.ui.radioTags.isChecked() else "caption",
                keywords=keywords,
                tag_logic="and" if self.ui.radioAnd.isChecked() else "or",
                resolution_filter=self.ui.comboResolution.currentText(),
                aspect_ratio_filter=self.ui.comboAspectRatio.currentText(),
                date_filter_enabled=self.ui.checkboxDateFilter.isChecked(),
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                only_untagged=self.ui.checkboxOnlyUntagged.isChecked(),
                only_uncaptioned=self.ui.checkboxOnlyUncaptioned.isChecked(),
                exclude_duplicates=self.ui.checkboxExcludeDuplicates.isChecked(),
            )

            # 進捗UI表示
            self._show_search_progress()
            self.ui.textEditPreview.setPlainText("検索中...")

            # WorkerServiceで非同期検索開始
            worker_id = self.worker_service.start_search(conditions)
            if worker_id:
                self._current_search_worker_id = worker_id
                logger.info(f"非同期検索開始: {worker_id}")

                # 旧形式のシグナルも発行（後方互換性）
                self.search_requested.emit({"conditions": conditions, "worker_id": worker_id})
            else:
                error_msg = "検索の開始に失敗しました"
                logger.error("WorkerService.start_search failed")
                self.ui.textEditPreview.setPlainText(error_msg)
                self._reset_search_ui()

        except AttributeError as e:
            error_msg = "UIコンポーネントへのアクセスエラーが発生しました"
            logger.error(f"UI AttributeError: {e}", exc_info=True)
            self.ui.textEditPreview.setPlainText(error_msg)
            self._reset_search_ui()
        except ValueError as e:
            error_msg = f"入力値エラー: {e}"
            logger.error(f"検索入力値エラー: {e}")
            self.ui.textEditPreview.setPlainText(error_msg)
            self._reset_search_ui()
        except Exception as e:
            error_msg = f"予期しない検索エラーが発生しました: {str(e)[:100]}"
            logger.error(f"検索実行エラー: {e}", exc_info=True)
            self.ui.textEditPreview.setPlainText(error_msg)
            self._reset_search_ui()

    def _execute_synchronous_search(self) -> None:
        """同期検索実行（WorkerServiceが利用できない場合のフォールバック）"""
        logger.info("フォールバック: 同期検索を実行")

        # 検索中表示
        self.ui.textEditPreview.setPlainText("検索中...")

        try:
            # 検索テキストをキーワードリストに変換
            search_text = self.ui.lineEditSearch.text().strip()
            keywords = self.search_filter_service.parse_search_input(search_text) if search_text else []

            # 日付範囲を取得
            date_range_start, date_range_end = self.get_date_range_from_slider()

            # SearchFilterServiceを使用して検索条件を作成
            conditions = self.search_filter_service.create_search_conditions(
                search_type="tags" if self.ui.radioTags.isChecked() else "caption",
                keywords=keywords,
                tag_logic="and" if self.ui.radioAnd.isChecked() else "or",
                resolution_filter=self.ui.comboResolution.currentText(),
                aspect_ratio_filter=self.ui.comboAspectRatio.currentText(),
                date_filter_enabled=self.ui.checkboxDateFilter.isChecked(),
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                only_untagged=self.ui.checkboxOnlyUntagged.isChecked(),
                only_uncaptioned=self.ui.checkboxOnlyUncaptioned.isChecked(),
                exclude_duplicates=self.ui.checkboxExcludeDuplicates.isChecked(),
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
            error_msg = f"検索エラー: {str(e)[:100]}"
            logger.error(f"同期検索実行エラー: {e}", exc_info=True)
            self.ui.textEditPreview.setPlainText(error_msg)
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
        # 検索テキスト
        if conditions.get("tags"):
            self.ui.radioTags.setChecked(True)
            self.ui.lineEditSearch.setText(", ".join(conditions["tags"]))
            self.ui.radioAnd.setChecked(conditions.get("use_and", True))
            self.ui.radioOr.setChecked(not conditions.get("use_and", True))
        elif conditions.get("caption"):
            self.ui.radioCaption.setChecked(True)
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
        self.ui.radioTags.setChecked(True)
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

        self.ui.textEditPreview.setPlainText("検索結果のプレビューがここに表示されます")

    # === Public Methods ===

    def set_search_text(self, text: str, search_type: str = "tags") -> None:
        """検索テキストを設定"""
        self.ui.lineEditSearch.setText(text)
        if search_type == "tags":
            self.ui.radioTags.setChecked(True)
        else:
            self.ui.radioCaption.setChecked(True)

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
        if result_count > 0:
            preview = f"検索結果: {result_count}件"
            if preview_text:
                preview += f"\n{preview_text}"
        else:
            preview = "検索結果がありません"

        self.ui.textEditPreview.setPlainText(preview)
        logger.debug(f"検索結果プレビュー更新: {result_count}件")

    def clear_search_preview(self) -> None:
        """検索結果プレビューをクリア"""
        self.ui.textEditPreview.clear()
        logger.debug("検索結果プレビューをクリア")

    def _on_apply_clicked(self) -> None:
        """適用ボタンクリック処理"""
        self._on_search_requested()

    def _on_clear_clicked(self) -> None:
        """クリアボタンクリック処理"""
        self._on_clear_requested()

    def update_pipeline_progress(self, message: str, current_progress: float, end_progress: float) -> None:
        """Pipeline進捗表示の更新（Phase 2対応）"""
        try:
            if hasattr(self, "progress_bar") and self.progress_bar:
                # 進捗バーの値設定（0-100スケール）
                progress_value = int(current_progress * 100)
                self.progress_bar.setValue(progress_value)

                # 進捗メッセージ表示（ProgressBar format使用）
                if hasattr(self.progress_bar, "setFormat"):
                    progress_percent = int(current_progress * 100)
                    self.progress_bar.setFormat(f"{message} ({progress_percent}%)")

                # ProgressBarの表示状態確認
                if not self.progress_bar.isVisible():
                    self.progress_bar.setVisible(True)

                logger.debug(f"Pipeline progress updated: {message} ({progress_value}%)")

        except Exception as e:
            logger.error(f"Failed to update pipeline progress: {e}")

    def handle_pipeline_error(self, phase: str, error_info: dict) -> None:
        """Pipelineエラー処理（Phase 2対応）"""
        try:
            # 進捗表示のリセット
            self._reset_search_ui()

            # エラーメッセージの表示
            error_message = error_info.get("message", "Unknown error")
            logger.error(f"Pipeline {phase} error: {error_message}")

            # UI状態のリセット（エラー時は検索結果破棄）
            if hasattr(self, "cancel_button") and self.cancel_button:
                self.cancel_button.setEnabled(False)

            # エラー状態の通知（オプション）
            if hasattr(self, "search_completed"):
                self.search_completed.emit({"success": False, "phase": phase, "error": error_message})

        except Exception as e:
            logger.error(f"Failed to handle pipeline error: {e}")

    def clear_pipeline_results(self) -> None:
        """Pipeline結果のクリア（キャンセル・エラー時用）"""
        try:
            # UI状態リセット
            self._reset_search_ui()

            # フィルター結果クリア通知
            self.filter_cleared.emit()

            logger.info("Pipeline results cleared")

        except Exception as e:
            logger.error(f"Failed to clear pipeline results: {e}")


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
        print(f"検索要求: {data}")

    def on_filter_cleared() -> None:
        print("フィルタークリア")

    filter_panel.search_requested.connect(on_search_requested)
    filter_panel.filter_cleared.connect(on_filter_cleared)

    # ウィジェットをメインウィンドウに設定
    main_window.setCentralWidget(filter_panel)

    # ウィンドウ表示
    main_window.show()

    # アプリケーション実行
    sys.exit(app.exec())
