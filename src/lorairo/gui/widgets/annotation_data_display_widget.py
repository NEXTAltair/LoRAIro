"""
Annotation Data Display Widget

汎用アノテーション結果表示コンポーネント
タグ・キャプション・スコア情報の統一表示を提供
"""

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QTableWidgetItem, QWidget

from ...gui.designer.AnnotationDataDisplayWidget_ui import Ui_AnnotationDataDisplayWidget
from ...utils.log import logger


@dataclass
class AnnotationData:
    """アノテーション表示用データ"""

    tags: list[dict[str, Any]] = field(default_factory=list)  # Repository層から提供される詳細情報
    caption: str = ""
    aesthetic_score: float | None = None
    overall_score: int = 0
    score_type: str = "Aesthetic"


@dataclass
class ImageDetails:
    """選択画像の詳細情報"""

    image_id: int | None = None
    file_name: str = ""
    file_path: str = ""
    image_size: str = ""  # "1920x1080" format
    file_size: str = ""  # "2.5 MB" format
    created_date: str = ""  # "2025-07-29 15:30:00" format
    rating_value: str = ""  # "PG", "R", etc.
    score_value: int = 0  # 0-1000 range
    caption: str = ""  # Image caption text
    tags: str = ""  # Comma-separated tags
    annotation_data: AnnotationData | None = field(default=None)

    def __post_init__(self) -> None:
        if self.annotation_data is None:
            self.annotation_data = AnnotationData()


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)  # type: ignore  # Justification: Qt Designer generated method signature

        # 現在のデータ
        self.current_data: AnnotationData = AnnotationData()

        # UI初期化
        self._setup_widget_properties()

        logger.debug("AnnotationDataDisplayWidget initialized")

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # tableWidgetTagsは既にNoEditTriggersに設定済み（UIファイルで設定）
        # テキスト編集を読み取り専用に設定
        self.textEditCaption.setReadOnly(True)

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

    def _update_tags_display(self, tags: list[dict[str, Any]]) -> None:
        """タグ表示をテーブルで更新

        Args:
            tags: タグ詳細情報リスト（Repository層から提供）
                  [{"tag": "1girl", "model_name": "wd-v1-4", "source": "AI",
                    "confidence_score": 0.95, "is_edited_manually": False}, ...]
        """
        try:
            self.tableWidgetTags.setRowCount(len(tags))
            self.tableWidgetTags.setSortingEnabled(False)  # 更新中はソート無効

            for row, tag_dict in enumerate(tags):
                # Tag列
                tag_item = QTableWidgetItem(tag_dict["tag"])
                self.tableWidgetTags.setItem(row, 0, tag_item)

                # Model列
                model_name = tag_dict.get("model_name", "-")
                model_item = QTableWidgetItem(model_name)
                self.tableWidgetTags.setItem(row, 1, model_item)

                # Source列
                source = tag_dict.get("source", "AI")
                source_item = QTableWidgetItem(source)
                self.tableWidgetTags.setItem(row, 2, source_item)

                # Confidence列
                confidence = tag_dict.get("confidence_score")
                if confidence is not None:
                    confidence_text = f"{confidence:.2f}"
                else:
                    confidence_text = "-"
                confidence_item = QTableWidgetItem(confidence_text)
                # 数値ソート用のデータ設定
                confidence_item.setData(Qt.ItemDataRole.UserRole, confidence if confidence else -1)
                self.tableWidgetTags.setItem(row, 3, confidence_item)

                # Edited列（チェックボックス）
                edited = tag_dict.get("is_edited_manually", False)
                checkbox_item = QTableWidgetItem()
                checkbox_item.setCheckState(Qt.CheckState.Checked if edited else Qt.CheckState.Unchecked)
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # 読み取り専用
                self.tableWidgetTags.setItem(row, 4, checkbox_item)

            self.tableWidgetTags.setSortingEnabled(True)  # ソート有効化
            self.tableWidgetTags.resizeColumnsToContents()

            logger.debug(f"Updated tags display: {len(tags)} rows")

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
            self.tableWidgetTags.setRowCount(0)

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
        # tableWidgetTagsは既にNoEditTriggersに設定済み
        self.textEditCaption.setReadOnly(read_only)

    def set_group_box_visibility(
        self, tags: bool = True, caption: bool = True, scores: bool = True
    ) -> None:
        """各グループボックスの表示/非表示制御"""
        self.groupBoxTags.setVisible(tags)
        self.groupBoxCaption.setVisible(caption)
        self.groupBoxScores.setVisible(scores)


if __name__ == "__main__":
    # Tier2: ダミーデータ投入とシグナル受信ログの最小確認
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    # ログはコンソール優先
    initialize_logging({"level": "DEBUG", "file": None})
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("AnnotationDataDisplayWidget テスト (Tier2)")
    widget = AnnotationDataDisplayWidget()
    window.setCentralWidget(widget)
    window.resize(480, 360)

    # シグナル受信確認（デバッグログ）
    def _on_data_loaded(data: AnnotationData) -> None:
        from lorairo.utils.log import logger

        logger.debug(
            f"[Signal] data_loaded: tags={len(data.tags)}, caption={bool(data.caption)}, aesth={data.aesthetic_score}"
        )

    def _on_data_cleared() -> None:
        from lorairo.utils.log import logger

        logger.debug("[Signal] data_cleared")

    widget.data_loaded.connect(_on_data_loaded)
    widget.data_cleared.connect(_on_data_cleared)

    # ダミーデータを流し込み
    dummy = AnnotationData(
        tags=[
            {
                "tag": "1girl",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.95,
                "is_edited_manually": False,
            },
            {
                "tag": "flower",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.88,
                "is_edited_manually": False,
            },
            {
                "tag": "solo",
                "model_name": "wd-v1-4",
                "source": "AI",
                "confidence_score": 0.92,
                "is_edited_manually": False,
            },
        ],
        caption="A girl holding flowers in a sunny field.",
        aesthetic_score=0.732,
        overall_score=780,
        score_type="Aesthetic",
    )
    widget.update_data(dummy)

    # 一度クリアして data_cleared 発火確認
    widget.clear_data()

    window.show()
    sys.exit(app.exec())
