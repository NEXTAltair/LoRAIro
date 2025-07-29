"""
Annotation Data Display Widget

汎用アノテーション結果表示コンポーネント
タグ・キャプション・スコア情報の統一表示を提供
"""

from dataclasses import dataclass, field

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...gui.designer.AnnotationDataDisplayWidget_ui import Ui_AnnotationDataDisplayWidget
from ...utils.log import logger


@dataclass
class AnnotationData:
    """アノテーション表示用データ"""

    tags: list[str] = field(default_factory=list)
    caption: str = ""
    aesthetic_score: float | None = None
    overall_score: int = 0
    score_type: str = "Aesthetic"


class AnnotationDataDisplayWidget(QWidget, Ui_AnnotationDataDisplayWidget):
    """
    アノテーション結果の汎用表示ウィジェット

    機能:
    - タグ・キャプション・スコア情報の統一表示
    - 読み取り専用表示
    - データクリア・更新機能
    """

    # シグナル
    data_loaded = Signal(AnnotationData)  # データロード完了
    data_cleared = Signal()  # データクリア完了

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)

        # 現在のデータ
        self.current_data: AnnotationData = AnnotationData()

        # UI初期化
        self._setup_widget_properties()

        logger.debug("AnnotationDataDisplayWidget initialized")

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # テキスト編集を読み取り専用に設定
        self.textEditTags.setReadOnly(True)
        self.textEditCaption.setReadOnly(True)

        # スタイル設定
        text_edit_style = """
            QTextEdit {
                font-size: 10px;
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                padding: 6px;
            }
        """
        self.textEditTags.setStyleSheet(text_edit_style)
        self.textEditCaption.setStyleSheet(text_edit_style)

        # スコアラベルのスタイル
        score_style = "font-size: 10px; font-weight: bold; color: #495057;"
        self.labelScoreTypeValue.setStyleSheet(score_style)
        self.labelOverallValue.setStyleSheet(score_style)

    def update_data(self, data: AnnotationData) -> None:
        """アノテーションデータで表示を更新"""
        try:
            self.current_data = data

            # タグ表示更新
            self._update_tags_display(data.tags)

            # キャプション表示更新
            self._update_caption_display(data.caption)

            # スコア表示更新
            self._update_scores_display(data.aesthetic_score, data.overall_score, data.score_type)

            self.data_loaded.emit(data)
            logger.debug(f"Annotation data updated - tags: {len(data.tags)}, caption: {bool(data.caption)}")

        except Exception as e:
            logger.error(f"Error updating annotation data: {e}", exc_info=True)

    def _update_tags_display(self, tags: list[str]) -> None:
        """タグ表示を更新"""
        try:
            if tags:
                # タグをカンマ区切りで表示
                tags_text = ", ".join(tags)
                self.textEditTags.setText(tags_text)
            else:
                self.textEditTags.setText("")
                self.textEditTags.setPlaceholderText("タグが表示されます")

        except Exception as e:
            logger.error(f"Error updating tags display: {e}")

    def _update_caption_display(self, caption: str) -> None:
        """キャプション表示を更新"""
        try:
            if caption:
                self.textEditCaption.setText(caption)
            else:
                self.textEditCaption.setText("")
                self.textEditCaption.setPlaceholderText("キャプションが表示されます")

        except Exception as e:
            logger.error(f"Error updating caption display: {e}")

    def _update_scores_display(
        self, aesthetic_score: float | None, overall_score: int, score_type: str = "Aesthetic"
    ) -> None:
        """スコア表示を更新"""
        try:
            # スコアタイプラベル更新
            self.labelScoreType.setText(f"{score_type}:")

            # Aestheticスコア表示
            if aesthetic_score is not None:
                self.labelScoreTypeValue.setText(f"{aesthetic_score:.3f}")
            else:
                self.labelScoreTypeValue.setText("-")

            # 総合スコア表示
            self.labelOverallValue.setText(str(overall_score))

        except Exception as e:
            logger.error(f"Error updating scores display: {e}")

    @Slot()
    def clear_data(self) -> None:
        """表示データをクリア"""
        try:
            # データリセット
            self.current_data = AnnotationData()

            # UI要素クリア
            self.textEditTags.clear()
            self.textEditTags.setPlaceholderText("タグが表示されます")

            self.textEditCaption.clear()
            self.textEditCaption.setPlaceholderText("キャプションが表示されます")

            self.labelScoreTypeValue.setText("-")
            self.labelOverallValue.setText("0")

            self.data_cleared.emit()
            logger.debug("Annotation data display cleared")

        except Exception as e:
            logger.error(f"Error clearing annotation data: {e}", exc_info=True)

    def get_current_data(self) -> AnnotationData:
        """現在表示中のデータを取得"""
        return self.current_data

    def set_read_only(self, read_only: bool) -> None:
        """読み取り専用モード設定"""
        self.textEditTags.setReadOnly(read_only)
        self.textEditCaption.setReadOnly(read_only)

    def set_group_box_visibility(
        self, tags: bool = True, caption: bool = True, scores: bool = True
    ) -> None:
        """各グループボックスの表示/非表示制御"""
        self.groupBoxTags.setVisible(tags)
        self.groupBoxCaption.setVisible(caption)
        self.groupBoxScores.setVisible(scores)
