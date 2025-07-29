"""アノテーション結果表示ウィジェット

ModelResultTab.uiを活用してアノテーション結果を表示するための統合ウィジェット。
HybridAnnotationController から使用される。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger


@dataclass
class AnnotationResult:
    """単一モデルのアノテーション結果"""

    model_name: str
    success: bool
    processing_time: float  # 秒
    tags: list[str] = None
    caption: str = ""
    score: float = None
    error_message: str = ""
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ModelResultWidget(QWidget):
    """単一モデル結果表示ウィジェット（ModelResultTab.ui使用）"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        # UI要素の参照
        self.label_model_name: QLabel = None
        self.label_processing_time: QLabel = None
        self.label_status: QLabel = None
        self.stacked_widget_content: QStackedWidget = None
        self.text_edit_captions: QTextEdit = None
        self.label_score_value: QLabel = None
        self.progress_bar_score: QProgressBar = None
        self.text_edit_error_message: QTextEdit = None
        self.scroll_area_tags: QScrollArea = None

        # ModelResultTab.ui をロード
        self._load_model_result_ui()

    def _load_model_result_ui(self) -> None:
        """ModelResultTab.ui をロードして初期化"""
        try:
            # UIファイルパス
            ui_file_path = Path(__file__).parent.parent / "designer" / "ModelResultTab.ui"

            if not ui_file_path.exists():
                logger.error(f"ModelResultTab.ui が見つかりません: {ui_file_path}")
                self._create_fallback_ui()
                return

            # UIファイルロード
            loader = QUiLoader()
            ui_file = ui_file_path.open("r", encoding="utf-8")
            ui_widget = loader.load(ui_file)
            ui_file.close()

            if not ui_widget:
                logger.error("ModelResultTab.ui のロードに失敗しました")
                self._create_fallback_ui()
                return

            # メインレイアウトに追加
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.addWidget(ui_widget)

            # UI要素の参照を取得
            self._setup_ui_references(ui_widget)

            logger.debug("ModelResultTab.ui ロード完了")

        except Exception as e:
            logger.error(f"ModelResultTab.ui ロードエラー: {e}", exc_info=True)
            self._create_fallback_ui()

    def _setup_ui_references(self, ui_widget: QWidget) -> None:
        """UI要素の参照を設定"""
        self.label_model_name = ui_widget.findChild(QLabel, "labelModelName")
        self.label_processing_time = ui_widget.findChild(QLabel, "labelProcessingTime")
        self.label_status = ui_widget.findChild(QLabel, "labelStatus")
        self.stacked_widget_content = ui_widget.findChild(QStackedWidget, "stackedWidgetContent")
        self.text_edit_captions = ui_widget.findChild(QTextEdit, "textEditCaptions")
        self.label_score_value = ui_widget.findChild(QLabel, "labelScoreValue")
        self.progress_bar_score = ui_widget.findChild(QProgressBar, "progressBarScore")
        self.text_edit_error_message = ui_widget.findChild(QTextEdit, "textEditErrorMessage")
        self.scroll_area_tags = ui_widget.findChild(QScrollArea, "scrollAreaTags")

    def _create_fallback_ui(self) -> None:
        """フォールバック用簡易UI作成"""
        main_layout = QVBoxLayout(self)

        # エラーメッセージ
        error_label = QLabel("ModelResultTab.ui の読み込みに失敗しました。\n簡易表示モードで動作します。")
        error_label.setStyleSheet("color: #d32f2f; font-weight: bold; padding: 10px;")
        main_layout.addWidget(error_label)

        # 簡易結果表示エリア
        self.fallback_result_area = QTextEdit()
        self.fallback_result_area.setReadOnly(True)
        main_layout.addWidget(self.fallback_result_area)

    def update_result(self, result: AnnotationResult) -> None:
        """アノテーション結果で表示を更新"""
        try:
            if self.label_model_name:
                self.label_model_name.setText(f"モデル名: {result.model_name}")

            if self.label_processing_time:
                self.label_processing_time.setText(f"処理時間: {result.processing_time:.2f}s")

            if result.success:
                self._update_success_display(result)
            else:
                self._update_error_display(result)

        except Exception as e:
            logger.error(f"結果表示更新エラー: {e}", exc_info=True)
            self._update_fallback_display(result)

    def _update_success_display(self, result: AnnotationResult) -> None:
        """成功時の表示更新"""
        # ステータス更新
        if self.label_status:
            self.label_status.setText("✓ 成功")
            self.label_status.setStyleSheet("color: green; font-weight: bold;")

        # 成功ページに切り替え
        if self.stacked_widget_content:
            self.stacked_widget_content.setCurrentIndex(0)

        # キャプション表示
        if self.text_edit_captions and result.caption:
            self.text_edit_captions.setText(result.caption)

        # スコア表示
        if result.score is not None:
            if self.label_score_value:
                self.label_score_value.setText(f"{result.score:.3f}")
            if self.progress_bar_score:
                score_percentage = min(100, max(0, int(result.score * 100)))
                self.progress_bar_score.setValue(score_percentage)

        # タグ表示
        if result.tags and self.scroll_area_tags:
            self._update_tags_display(result.tags)

    def _update_error_display(self, result: AnnotationResult) -> None:
        """エラー時の表示更新"""
        # ステータス更新
        if self.label_status:
            self.label_status.setText("✗ エラー")
            self.label_status.setStyleSheet("color: red; font-weight: bold;")

        # エラーページに切り替え
        if self.stacked_widget_content:
            self.stacked_widget_content.setCurrentIndex(1)

        # エラーメッセージ表示
        if self.text_edit_error_message:
            self.text_edit_error_message.setText(result.error_message or "不明なエラーが発生しました")

    def _update_tags_display(self, tags: list[str]) -> None:
        """タグ表示を更新"""
        if not self.scroll_area_tags:
            return

        try:
            # タグ表示用ウィジェット作成
            tags_widget = QWidget()
            tags_layout = QVBoxLayout(tags_widget)
            tags_layout.setContentsMargins(4, 4, 4, 4)
            tags_layout.setSpacing(2)

            if tags:
                # タグをラベルとして表示（行折り返し対応）
                tags_text = ", ".join(tags)
                tags_label = QLabel(tags_text)
                tags_label.setWordWrap(True)
                tags_label.setStyleSheet("""
                    QLabel {
                        font-size: 10px;
                        padding: 4px;
                        background-color: #f0f8ff;
                        border: 1px solid #ddd;
                        border-radius: 2px;
                    }
                """)
                tags_layout.addWidget(tags_label)
            else:
                # タグなしの場合
                no_tags_label = QLabel("タグなし")
                no_tags_label.setStyleSheet("color: #888; font-style: italic;")
                tags_layout.addWidget(no_tags_label)

            tags_layout.addStretch()
            self.scroll_area_tags.setWidget(tags_widget)

        except Exception as e:
            logger.error(f"タグ表示更新エラー: {e}")

    def _update_fallback_display(self, result: AnnotationResult) -> None:
        """フォールバック表示更新"""
        if hasattr(self, "fallback_result_area"):
            display_text = f"""
モデル名: {result.model_name}
処理時間: {result.processing_time:.2f}秒
ステータス: {"成功" if result.success else "エラー"}

"""
            if result.success:
                if result.caption:
                    display_text += f"キャプション:\n{result.caption}\n\n"
                if result.tags:
                    display_text += f"タグ:\n{', '.join(result.tags)}\n\n"
                if result.score is not None:
                    display_text += f"スコア: {result.score:.3f}\n"
            else:
                display_text += f"エラーメッセージ:\n{result.error_message}"

            self.fallback_result_area.setText(display_text)


class AnnotationResultsWidget(QWidget):
    """アノテーション結果統合表示ウィジェット"""

    # シグナル
    result_clicked = Signal(str)  # model_name
    export_requested = Signal(list)  # results

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        # 結果データ
        self.results: dict[str, AnnotationResult] = {}

        # UI設定
        self._setup_ui()

        logger.debug("AnnotationResultsWidget初期化完了")

    def _setup_ui(self) -> None:
        """UI初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # ヘッダー領域
        self._setup_header(main_layout)

        # 結果表示エリア
        self._setup_results_display(main_layout)

    def _setup_header(self, parent_layout: QVBoxLayout) -> None:
        """ヘッダー領域設定"""
        header_frame = QFrame()
        header_frame.setMaximumHeight(40)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)

        # タイトル
        self.title_label = QLabel("アノテーション結果")
        self.title_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # エクスポートボタン
        self.export_button = QPushButton("結果をエクスポート")
        self.export_button.setMaximumSize(120, 30)
        self.export_button.clicked.connect(self._export_results)
        self.export_button.setEnabled(False)
        header_layout.addWidget(self.export_button)

        parent_layout.addWidget(header_frame)

    def _setup_results_display(self, parent_layout: QVBoxLayout) -> None:
        """結果表示エリア設定"""
        # タブウィジェット（モデル別結果表示）
        self.results_tab_widget = QTabWidget()
        self.results_tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.results_tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTabBar::tab {
                padding: 4px 8px;
                font-size: 10px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #e3f2fd;
                border-bottom: 2px solid #2196F3;
            }
        """)

        # 初期プレースホルダー
        self._add_placeholder_tab()

        parent_layout.addWidget(self.results_tab_widget)

    def _add_placeholder_tab(self) -> None:
        """プレースホルダータブ追加"""
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)

        placeholder_label = QLabel(
            "🔄 アノテーション結果がここに表示されます\n\n"
            "モデルを選択してアノテーションを実行すると、\n"
            "各モデルの結果がタブ形式で表示されます。\n\n"
            "📊 表示される情報:\n"
            "• キャプション生成結果\n"
            "• タグ生成結果\n"
            "• 品質スコア\n"
            "• 処理時間・エラー情報"
        )
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setStyleSheet("""
            color: #666; 
            font-style: italic; 
            padding: 30px; 
            font-size: 11px;
            line-height: 1.4;
            background-color: #f9f9f9;
            border: 1px dashed #ccc;
            border-radius: 4px;
        """)
        placeholder_label.setWordWrap(True)

        placeholder_layout.addWidget(placeholder_label)

        self.results_tab_widget.addTab(placeholder_widget, "結果待ち")

    def add_result(self, result: AnnotationResult) -> None:
        """アノテーション結果を追加"""
        try:
            # プレースホルダータブを削除（初回のみ）
            if self.results_tab_widget.count() == 1 and not self.results:
                self.results_tab_widget.clear()

            # 結果データ保存
            self.results[result.model_name] = result

            # モデル結果ウィジェット作成
            model_result_widget = ModelResultWidget()
            model_result_widget.update_result(result)

            # タブ追加
            tab_title = result.model_name
            if not result.success:
                tab_title += " ❌"
            elif result.score is not None:
                tab_title += f" ({result.score:.2f})"

            self.results_tab_widget.addTab(model_result_widget, tab_title)

            # エクスポートボタン有効化
            self.export_button.setEnabled(True)

            # タイトル更新
            self.title_label.setText(f"アノテーション結果 ({len(self.results)})")

            logger.debug(f"アノテーション結果追加: {result.model_name}")

        except Exception as e:
            logger.error(f"アノテーション結果追加エラー: {e}", exc_info=True)

    def clear_results(self) -> None:
        """結果をクリア"""
        self.results.clear()
        self.results_tab_widget.clear()
        self._add_placeholder_tab()
        self.export_button.setEnabled(False)
        self.title_label.setText("アノテーション結果")
        logger.debug("アノテーション結果クリア完了")

    def get_results_summary(self) -> dict[str, Any]:
        """結果サマリーを取得"""
        if not self.results:
            return {}

        successful_results = [r for r in self.results.values() if r.success]
        failed_results = [r for r in self.results.values() if not r.success]

        total_time = sum(r.processing_time for r in self.results.values())
        avg_score = None
        if successful_results and any(r.score is not None for r in successful_results):
            scores = [r.score for r in successful_results if r.score is not None]
            avg_score = sum(scores) / len(scores) if scores else None

        return {
            "total_models": len(self.results),
            "successful": len(successful_results),
            "failed": len(failed_results),
            "total_processing_time": total_time,
            "average_score": avg_score,
            "success_rate": len(successful_results) / len(self.results) if self.results else 0,
        }

    @Slot()
    def _export_results(self) -> None:
        """結果エクスポート"""
        if self.results:
            self.export_requested.emit(list(self.results.values()))
        logger.debug("結果エクスポート要求")
