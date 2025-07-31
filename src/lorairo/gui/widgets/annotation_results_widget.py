"""
Annotation Results Widget

機能別アノテーション結果表示機能を提供
キャプション・タグ・スコア結果のタブ形式表示とモデル比較
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ...utils.log import logger
from ..designer.AnnotationResultsWidget_ui import Ui_AnnotationResultsWidget


@dataclass
class AnnotationResult:
    """単一モデルのアノテーション結果"""

    model_name: str
    function_type: str  # "caption", "tags", "scores"
    content: str  # 結果内容（タグならカンマ区切り、キャプションなら文章、スコアなら数値）
    processing_time: float  # 処理時間（秒）
    success: bool = True
    error_message: str = ""
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AnnotationResultsWidget(QWidget, Ui_AnnotationResultsWidget):
    """
    アノテーション結果統合表示ウィジェット

    機能:
    - タブ式結果表示（機能別：キャプション/タグ/スコア）
    - テーブル形式モデル別結果表示
    - ソート機能付きテーブル
    - 結果エクスポート機能
    """

    # シグナル
    result_selected = Signal(str, str)  # モデル名, 機能タイプ
    export_requested = Signal(list)  # 結果リスト

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)

        # 結果データ
        self.caption_results: dict[str, AnnotationResult] = {}
        self.tags_results: dict[str, AnnotationResult] = {}
        self.scores_results: dict[str, AnnotationResult] = {}

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()
        self._setup_tables()

        logger.debug("AnnotationResultsWidget initialized")

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # テーブル選択変更
        self.tableWidgetCaption.itemSelectionChanged.connect(
            lambda: self._on_table_selection_changed("caption")
        )
        self.tableWidgetTags.itemSelectionChanged.connect(lambda: self._on_table_selection_changed("tags"))
        self.tableWidgetScores.itemSelectionChanged.connect(
            lambda: self._on_table_selection_changed("scores")
        )

        # タブ変更
        self.tabWidgetResults.currentChanged.connect(self._on_tab_changed)

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # タイトルラベルスタイル
        self.labelResultsTitle.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: #333;
                padding: 4px 0px;
            }
        """)

        # タブウィジェットスタイル
        self.tabWidgetResults.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTabBar::tab {
                padding: 6px 12px;
                font-size: 10px;
                margin-right: 2px;
                border: 1px solid #ddd;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
            }
            QTabBar::tab:selected {
                background-color: #e3f2fd;
                border-bottom: 2px solid #2196F3;
                font-weight: bold;
            }
            QTabBar::tab:!selected {
                background-color: #f5f5f5;
            }
            QTabBar::tab:hover {
                background-color: #f0f8ff;
            }
        """)

    def _setup_tables(self) -> None:
        """結果表示テーブルを設定"""
        tables = [
            ("caption", self.tableWidgetCaption, ["モデル名", "キャプション", "処理時間"]),
            ("tags", self.tableWidgetTags, ["モデル名", "タグ", "処理時間"]),
            ("scores", self.tableWidgetScores, ["モデル名", "スコア", "処理時間"]),
        ]

        for table_type, table_widget, headers in tables:
            try:
                # カラム設定
                table_widget.setColumnCount(len(headers))
                table_widget.setHorizontalHeaderLabels(headers)

                # ヘッダー設定
                header = table_widget.horizontalHeader()
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # モデル名
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 内容
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 処理時間

                # テーブルスタイル
                table_widget.setStyleSheet("""
                    QTableWidget {
                        font-size: 9px;
                        gridline-color: #e0e0e0;
                        selection-background-color: #e3f2fd;
                        alternate-background-color: #f9f9f9;
                    }
                    QTableWidget::item {
                        padding: 6px;
                        border-bottom: 1px solid #f0f0f0;
                    }
                    QHeaderView::section {
                        font-size: 9px;
                        font-weight: bold;
                        background-color: #f5f5f5;
                        border: 1px solid #ddd;
                        padding: 6px;
                    }
                """)

                # 選択・ソート設定
                table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                table_widget.setAlternatingRowColors(True)
                table_widget.setSortingEnabled(True)

                logger.debug(f"Table setup completed for {table_type}")

            except Exception as e:
                logger.error(f"Error setting up {table_type} table: {e}")

    @Slot()
    def _on_table_selection_changed(self, function_type: str) -> None:
        """テーブル選択変更時の処理"""
        try:
            # 現在のタブに対応するテーブル取得
            table_widget = getattr(self, f"tableWidget{function_type.title()}")
            current_row = table_widget.currentRow()

            if current_row >= 0:
                model_name_item = table_widget.item(current_row, 0)
                if model_name_item:
                    model_name = model_name_item.text()
                    self.result_selected.emit(model_name, function_type)
                    logger.debug(f"Result selected: {model_name} ({function_type})")

        except Exception as e:
            logger.error(f"Error handling table selection: {e}")

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        """タブ変更時の処理"""
        try:
            tab_names = ["caption", "tags", "scores"]
            if 0 <= index < len(tab_names):
                current_function = tab_names[index]
                logger.debug(f"Results tab changed to: {current_function}")

        except Exception as e:
            logger.error(f"Error handling tab change: {e}")

    def add_result(self, result: AnnotationResult) -> None:
        """アノテーション結果を追加"""
        try:
            # 機能タイプに応じて結果を格納
            if result.function_type == "caption":
                self.caption_results[result.model_name] = result
                self._update_caption_table()
            elif result.function_type == "tags":
                self.tags_results[result.model_name] = result
                self._update_tags_table()
            elif result.function_type == "scores":
                self.scores_results[result.model_name] = result
                self._update_scores_table()

            # タイトル更新
            self._update_results_title()

            logger.debug(f"Added {result.function_type} result from {result.model_name}")

        except Exception as e:
            logger.error(f"Error adding result: {e}", exc_info=True)

    def _update_caption_table(self) -> None:
        """キャプションテーブルを更新"""
        try:
            table = self.tableWidgetCaption
            results = self.caption_results

            # テーブルクリア
            table.setRowCount(0)

            # 結果を追加
            for row, (model_name, result) in enumerate(results.items()):
                table.insertRow(row)

                # モデル名
                model_item = QTableWidgetItem(model_name)
                model_item.setFlags(model_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 0, model_item)

                # キャプション内容
                if result.success:
                    content_item = QTableWidgetItem(result.content)
                    content_item.setToolTip(result.content)  # 長いテキスト用ツールチップ
                else:
                    content_item = QTableWidgetItem(f"[エラー] {result.error_message}")
                    content_item.setForeground(Qt.GlobalColor.red)

                content_item.setFlags(content_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 1, content_item)

                # 処理時間
                time_item = QTableWidgetItem(f"{result.processing_time:.2f}s")
                time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 2, time_item)

        except Exception as e:
            logger.error(f"Error updating caption table: {e}")

    def _update_tags_table(self) -> None:
        """タグテーブルを更新"""
        try:
            table = self.tableWidgetTags
            results = self.tags_results

            # テーブルクリア
            table.setRowCount(0)

            # 結果を追加
            for row, (model_name, result) in enumerate(results.items()):
                table.insertRow(row)

                # モデル名
                model_item = QTableWidgetItem(model_name)
                model_item.setFlags(model_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 0, model_item)

                # タグ内容
                if result.success:
                    # タグをカンマ区切りで表示、ツールチップにも設定
                    tags_display = result.content
                    content_item = QTableWidgetItem(tags_display)
                    content_item.setToolTip(tags_display)
                else:
                    content_item = QTableWidgetItem(f"[エラー] {result.error_message}")
                    content_item.setForeground(Qt.GlobalColor.red)

                content_item.setFlags(content_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 1, content_item)

                # 処理時間
                time_item = QTableWidgetItem(f"{result.processing_time:.2f}s")
                time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 2, time_item)

        except Exception as e:
            logger.error(f"Error updating tags table: {e}")

    def _update_scores_table(self) -> None:
        """スコアテーブルを更新"""
        try:
            table = self.tableWidgetScores
            results = self.scores_results

            # テーブルクリア
            table.setRowCount(0)

            # 結果を追加
            for row, (model_name, result) in enumerate(results.items()):
                table.insertRow(row)

                # モデル名
                model_item = QTableWidgetItem(model_name)
                model_item.setFlags(model_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 0, model_item)

                # スコア内容
                if result.success:
                    try:
                        score_value = float(result.content)
                        content_item = QTableWidgetItem(f"{score_value:.3f}")
                    except ValueError:
                        content_item = QTableWidgetItem(result.content)
                else:
                    content_item = QTableWidgetItem(f"[エラー] {result.error_message}")
                    content_item.setForeground(Qt.GlobalColor.red)

                content_item.setFlags(content_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 1, content_item)

                # 処理時間
                time_item = QTableWidgetItem(f"{result.processing_time:.2f}s")
                time_item.setFlags(time_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 2, time_item)

        except Exception as e:
            logger.error(f"Error updating scores table: {e}")

    def _update_results_title(self) -> None:
        """結果タイトルを更新"""
        try:
            total_results = len(self.caption_results) + len(self.tags_results) + len(self.scores_results)
            self.labelResultsTitle.setText(f"アノテーション結果 ({total_results})")

        except Exception as e:
            logger.error(f"Error updating results title: {e}")

    def clear_results(self) -> None:
        """結果をクリア"""
        try:
            # データクリア
            self.caption_results.clear()
            self.tags_results.clear()
            self.scores_results.clear()

            # テーブルクリア
            self.tableWidgetCaption.setRowCount(0)
            self.tableWidgetTags.setRowCount(0)
            self.tableWidgetScores.setRowCount(0)

            # タイトル更新
            self.labelResultsTitle.setText("アノテーション結果")

            logger.debug("All annotation results cleared")

        except Exception as e:
            logger.error(f"Error clearing results: {e}")

    def get_results_by_function(self, function_type: str) -> dict[str, AnnotationResult]:
        """指定機能タイプの結果を取得"""
        if function_type == "caption":
            return self.caption_results.copy()
        elif function_type == "tags":
            return self.tags_results.copy()
        elif function_type == "scores":
            return self.scores_results.copy()
        else:
            return {}

    def get_all_results(self) -> list[AnnotationResult]:
        """すべての結果を取得"""
        all_results = []
        all_results.extend(self.caption_results.values())
        all_results.extend(self.tags_results.values())
        all_results.extend(self.scores_results.values())
        return all_results

    def get_results_summary(self) -> dict[str, Any]:
        """結果サマリーを取得"""
        try:
            all_results: list[AnnotationResult] = self.get_all_results()
            successful_results = [r for r in all_results if r.success]
            failed_results = [r for r in all_results if not r.success]

            total_time = sum(r.processing_time for r in all_results) if all_results else 0
            avg_time = total_time / len(all_results) if all_results else 0

            return {
                "total_results": len(all_results),
                "successful": len(successful_results),
                "failed": len(failed_results),
                "success_rate": len(successful_results) / len(all_results) if all_results else 0,
                "total_processing_time": total_time,
                "average_processing_time": avg_time,
                "caption_count": len(self.caption_results),
                "tags_count": len(self.tags_results),
                "scores_count": len(self.scores_results),
            }

        except Exception as e:
            logger.error(f"Error generating results summary: {e}")
            return {}

    def set_current_tab(self, function_type: str) -> None:
        """指定機能タイプのタブを選択"""
        try:
            tab_mapping = {"caption": 0, "tags": 1, "scores": 2}
            if function_type in tab_mapping:
                self.tabWidgetResults.setCurrentIndex(tab_mapping[function_type])
                logger.debug(f"Switched to {function_type} tab")

        except Exception as e:
            logger.error(f"Error setting current tab: {e}")

    def export_results(self, function_type: str | None = None) -> None:
        """結果をエクスポート"""
        try:
            if function_type:
                results = list(self.get_results_by_function(function_type).values())
            else:
                results = self.get_all_results()

            if results:
                self.export_requested.emit(results)
                logger.debug(f"Export requested for {len(results)} results")
            else:
                logger.warning("No results available for export")

        except Exception as e:
            logger.error(f"Error exporting results: {e}")

    def set_enabled_state(self, enabled: bool) -> None:
        """ウィジェット全体の有効/無効状態を設定"""
        self.tabWidgetResults.setEnabled(enabled)
        self.tableWidgetCaption.setEnabled(enabled)
        self.tableWidgetTags.setEnabled(enabled)
        self.tableWidgetScores.setEnabled(enabled)

        if not enabled:
            logger.debug("AnnotationResultsWidget disabled")
        else:
            logger.debug("AnnotationResultsWidget enabled")
