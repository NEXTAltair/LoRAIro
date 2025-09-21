"""
Selected Image Details Widget

選択画像の詳細情報表示とインライン編集機能を提供
画像基本情報、アノテーション概要、Rating/Score の編集機能
# TODO: 他のウィジェットの機能も直に実装してあるので修正が必要､レイアウトはここに定義しない
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...gui.designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from ...utils.log import logger
from .annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    ImageDetails,
)

if TYPE_CHECKING:
    from ..services.image_db_write_service import ImageDBWriteService


class SelectedImageDetailsWidget(QWidget, Ui_SelectedImageDetailsWidget):
    """
    選択画像詳細情報ウィジェット

    機能:
    - 画像基本情報表示
    - アノテーション概要表示
    - Rating/Score のインライン編集
    - データベース保存機能
    """

    # シグナル
    image_details_loaded = Signal(ImageDetails)  # 画像詳細読み込み完了
    rating_updated = Signal(int, str)  # Rating 更新 (image_id, rating_value)
    score_updated = Signal(int, int)  # Score 更新 (image_id, score_value)
    save_requested = Signal(dict)  # 保存要求 {image_id, rating, score}

    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)

        # Phase 3.2: DB操作分離 - ImageDBWriteService依存注入パターン
        self.image_db_write_service: ImageDBWriteService | None = None

        # 現在の画像情報
        self.current_details: ImageDetails = ImageDetails()
        self.current_image_id: int | None = None

        # 共通コンポーネント取得 - AnnotationDataDisplayWidget
        self.annotation_display: AnnotationDataDisplayWidget | None = None
        self._setup_annotation_display()

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()

        # Phase 3.3: Enhanced Event-Driven Pattern (状態管理なし)
        logger.debug("SelectedImageDetailsWidget initialized with Enhanced Event-Driven Pattern support")

    def _setup_annotation_display(self) -> None:
        """AnnotationDataDisplayWidget を最下部に配置"""
        try:
            # 共通コンポーネントとして AnnotationDataDisplayWidget を作成
            self.annotation_display = AnnotationDataDisplayWidget(self)

            # メインレイアウトに追加
            self.verticalLayoutMain.addWidget(self.annotation_display)

            logger.debug("AnnotationDataDisplayWidget added to SelectedImageDetailsWidget")

        except Exception as e:
            logger.error(f"Error setting up annotation display: {e}", exc_info=True)

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # Rating コンボボックス変更
        self.comboBoxRating.currentTextChanged.connect(self._on_rating_changed)

        # Score スライダー変更
        self.sliderScore.valueChanged.connect(self._on_score_changed)

        # 保存ボタン（Rating用とScore用）
        self.pushButtonSaveRating.clicked.connect(self._on_save_clicked)
        self.pushButtonSaveScore.clicked.connect(self._on_save_clicked)

        # アノテーション表示コンポーネントのシグナル
        if self.annotation_display:
            self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # Rating コンボボックス設定
        rating_options = ["", "PG", "PG-13", "R", "X", "XXX"]
        self.comboBoxRating.addItems(rating_options)
        self.comboBoxRating.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
        """)

        # Score スライダー設定 (0-1000 範囲)
        self.sliderScore.setMinimum(0)
        self.sliderScore.setMaximum(1000)
        self.sliderScore.setValue(0)
        self.sliderScore.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
        """)

        # スコア値ラベル
        self.labelScoreValue.setStyleSheet("font-size: 10px; font-weight: bold; color: #333;")

        # 保存ボタン
        button_style = """
            QPushButton {
                font-size: 10px;
                padding: 4px 8px;
                border: 1px solid #4CAF50;
                border-radius: 3px;
                background-color: #f0f8f0;
                color: #2E7D32;
            }
            QPushButton:hover {
                background-color: #e8f5e8;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaa;
                border-color: #ddd;
            }
        """

        # 保存ボタンにスタイル適用
        self.pushButtonSaveRating.setStyleSheet(button_style)
        self.pushButtonSaveScore.setStyleSheet(button_style)

        # 情報ラベルスタイル
        info_label_style = "font-size: 9px; font-weight: bold; color: #333;"
        value_label_style = "font-size: 9px; color: #666;"

        # 各ラベルにスタイル適用
        for label_name in [
            "labelFileName",
            "labelImageSize",
            "labelFileSize",
            "labelCreatedDate",
        ]:
            label = getattr(self, label_name, None)
            if label:
                label.setStyleSheet(info_label_style)

        for label_name in [
            "labelFileNameValue",
            "labelImageSizeValue",
            "labelFileSizeValue",
            "labelCreatedDateValue",
        ]:
            label = getattr(self, label_name, None)
            if label:
                label.setStyleSheet(value_label_style)

    @Slot(str)
    def _on_rating_changed(self, rating_value: str) -> None:
        """Rating 変更時の処理"""
        if self.current_image_id and rating_value != self.current_details.rating_value:
            self.current_details.rating_value = rating_value
            self.rating_updated.emit(self.current_image_id, rating_value)
            logger.debug(f"Rating changed to: {rating_value}")

    @Slot(int)
    def _on_score_changed(self, score_value: int) -> None:
        """Score 変更時の処理"""
        # スコア値ラベル更新
        self.labelScoreValue.setText(str(score_value))

        if self.current_image_id and score_value != self.current_details.score_value:
            self.current_details.score_value = score_value
            self.score_updated.emit(self.current_image_id, score_value)
            logger.debug(f"Score changed to: {score_value}")

    @Slot()
    def _on_save_clicked(self) -> None:
        """保存ボタンクリック時の処理"""
        if not self.current_image_id:
            logger.warning("No image selected for save operation")
            return

        save_data = {
            "image_id": self.current_image_id,
            "rating": self.current_details.rating_value,
            "score": self.current_details.score_value,
        }

        self.save_requested.emit(save_data)
        logger.debug(f"Save requested for image {self.current_image_id}")

    @Slot(AnnotationData)
    def _on_annotation_data_loaded(self, data: AnnotationData) -> None:
        """アノテーション表示データ読み込み完了時の処理"""
        self.current_details.annotation_data = data
        logger.debug("Annotation data loaded in details widget")

    def set_image_db_write_service(self, service: "ImageDBWriteService") -> None:
        """Phase 1-2依存注入パターン継承"""
        self.image_db_write_service = service
        logger.debug("ImageDBWriteService set for SelectedImageDetailsWidget")

    # === Phase 3.3: Enhanced Event-Driven Pattern ===

    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（状態管理なし）"""
        # 新しいデータシグナルに接続
        state_manager.current_image_data_changed.connect(self._on_image_data_received)

        logger.debug("SelectedImageDetailsWidget connected to current_image_data_changed signal")

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict) -> None:
        """
        画像データ受信時のメタデータ更新（純粋表示専用）

        DatasetStateManagerから直接送信される完全な画像メタデータを受信し、
        詳細情報表示を更新します。検索機能への依存を完全に排除。
        """
        try:
            logger.info(
                f"📨 SelectedImageDetailsWidget: current_image_data_changed シグナル受信 - データサイズ: {len(image_data) if image_data else 0}"
            )

            # 空データの場合は表示をクリア
            if not image_data:
                logger.debug("Empty image data received, clearing details display")
                self._clear_display()
                return

            # 画像IDを取得
            image_id = image_data.get("id")
            if not image_id:
                logger.warning(f"画像ID未設定 | メタデータ: {list(image_data.keys())}")
                self._clear_display()
                return

            logger.debug(f"🔍 画像データ受信: ID={image_id}")

            # メタデータから詳細情報を構築
            details = self._build_image_details_from_metadata(image_data)

            # UI更新
            self._update_details_display(details)

            # 現在の詳細情報保存
            self.current_details = details
            self.current_image_id = image_id

            # シグナル発行
            self.image_details_loaded.emit(details)

            logger.info(
                f"✅ メタデータ表示成功: ID={image_id} - Enhanced Event-Driven Pattern 完全動作"
            )

        except Exception as e:
            logger.error(
                f"メタデータ更新エラー データ:{image_data.get('id', 'Unknown')} | エラー: {e}",
                exc_info=True,
            )
            self._clear_display()

    def _build_image_details_from_metadata(self, image_data: dict) -> ImageDetails:
        """メタデータから ImageDetails を構築"""
        try:
            # ファイル名の取得
            image_path_str = image_data.get("stored_image_path", "")
            file_name = Path(image_path_str).name if image_path_str else "Unknown"

            # 画像サイズの構築 (width x height)
            width = image_data.get("width", 0)
            height = image_data.get("height", 0)
            image_size = f"{width} x {height}" if width and height else "Unknown"

            # ファイルサイズの取得
            file_size_bytes = image_data.get("file_size_bytes")
            if file_size_bytes:
                # バイトを適切な単位に変換
                if file_size_bytes >= 1024 * 1024:
                    file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"
                elif file_size_bytes >= 1024:
                    file_size = f"{file_size_bytes / 1024:.1f} KB"
                else:
                    file_size = f"{file_size_bytes} bytes"
            else:
                file_size = "Unknown"

            # 作成日時の取得
            created_date = image_data.get("created_at", "Unknown")
            if created_date and created_date != "Unknown":
                # ISO形式を読みやすい形式に変換
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                    created_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass  # 変換に失敗した場合は元の値を使用

            # Rating/Score の取得
            rating_value = image_data.get("rating", "") or ""
            score_value = image_data.get("score", 0) or 0

            # ImageDetails を構築
            details = ImageDetails(
                file_name=file_name,
                image_size=image_size,
                file_size=file_size,
                created_date=created_date,
                rating_value=rating_value,
                score_value=score_value,
                annotation_data=None  # アノテーションデータは別途取得
            )

            logger.debug(f"ImageDetails constructed from metadata: {file_name}")
            return details

        except Exception as e:
            logger.error(f"Error building ImageDetails from metadata: {e}", exc_info=True)
            return ImageDetails()

    # === Legacy Methods (移行期のサポート) ===

    def load_image_details(self, image_id: int) -> None:
        """指定画像IDの詳細情報をロード（Phase 3.2: ImageDBWriteService使用）"""
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not available for loading image details")
            return

        try:
            self.current_image_id = image_id

            # ImageDBWriteServiceから画像情報取得
            details = self.image_db_write_service.get_image_details(image_id)

            # UI更新
            self._update_details_display(details)

            # 現在の詳細情報保存
            self.current_details = details

            self.image_details_loaded.emit(details)
            logger.debug(f"Image details loaded for ID: {image_id} (via ImageDBWriteService)")

        except Exception as e:
            logger.error(f"Error loading image details for ID {image_id}: {e}", exc_info=True)
            self._clear_display()

    # Phase 3.2: DB操作分離 - 以下のメソッドはImageDBWriteServiceに移行済み
    # def _fetch_image_details(self, image_id: int) -> ImageDetails:
    #     """廃止予定: ImageDBWriteService.get_image_details()を使用"""

    # Phase 3.2: DB操作分離 - 以下のメソッドはImageDBWriteServiceに移行済み
    # def _fetch_annotation_data(self, session: Any, image_id: int) -> AnnotationData:
    #     """廃止予定: ImageDBWriteService.get_annotation_data()を使用"""

    def _update_details_display(self, details: ImageDetails) -> None:
        """詳細情報表示を更新"""
        try:
            # 画像基本情報更新
            self.labelFileNameValue.setText(details.file_name)
            self.labelImageSizeValue.setText(details.image_size)
            self.labelFileSizeValue.setText(details.file_size)
            self.labelCreatedDateValue.setText(details.created_date)

            # Rating/Score 更新
            self._update_rating_score_display(details.rating_value, details.score_value)

            # アノテーション表示更新
            if self.annotation_display and details.annotation_data:
                self.annotation_display.update_data(details.annotation_data)

        except Exception as e:
            logger.error(f"Error updating details display: {e}")

    def _update_rating_score_display(self, rating_value: str, score_value: int) -> None:
        """Rating/Score 表示を更新"""
        try:
            # シグナルブロック
            self.comboBoxRating.blockSignals(True)
            self.sliderScore.blockSignals(True)

            # Rating コンボボックス設定
            if rating_value:
                index = self.comboBoxRating.findText(rating_value)
                if index >= 0:
                    self.comboBoxRating.setCurrentIndex(index)
            else:
                self.comboBoxRating.setCurrentIndex(0)

            # Score スライダー設定
            self.sliderScore.setValue(score_value)
            self.labelScoreValue.setText(str(score_value))

        finally:
            # シグナルブロック解除
            self.comboBoxRating.blockSignals(False)
            self.sliderScore.blockSignals(False)

    def _clear_display(self) -> None:
        """表示をクリア"""
        try:
            # 基本情報クリア
            self.labelFileNameValue.setText("-")
            self.labelImageSizeValue.setText("-")
            self.labelFileSizeValue.setText("-")
            self.labelCreatedDateValue.setText("-")

            # Rating/Score クリア
            self._update_rating_score_display("", 0)

            # アノテーション表示クリア
            if self.annotation_display:
                self.annotation_display.clear_data()

            # 現在のデータリセット
            self.current_details = ImageDetails()
            self.current_image_id = None

            logger.debug("Image details display cleared")

        except Exception as e:
            logger.error(f"Error clearing display: {e}")

    def get_current_details(self) -> ImageDetails:
        """現在表示中の詳細情報を取得"""
        return self.current_details

    def set_enabled_state(self, enabled: bool) -> None:
        """ウィジェット全体の有効/無効状態を設定"""
        self.comboBoxRating.setEnabled(enabled)
        self.sliderScore.setEnabled(enabled)
        self.pushButtonSaveRating.setEnabled(enabled)
        self.pushButtonSaveScore.setEnabled(enabled)

        if self.annotation_display:
            self.annotation_display.setEnabled(enabled)

        if not enabled:
            logger.debug("SelectedImageDetailsWidget disabled")
        else:
            logger.debug("SelectedImageDetailsWidget enabled")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # アプリケーションのエントリポイント
    def main():
        """アプリケーションのメイン実行関数"""
        app = QApplication(sys.argv)

        # ウィジェットのインスタンスを作成
        widget = SelectedImageDetailsWidget()

        # --- テスト用のダミーデータ ---
        dummy_annotation = AnnotationData(
            tags=["tag1", "tag2", "1girl", "solo"],
            caption="A beautiful illustration of a girl.",
            aesthetic_score=6.5,
            overall_score=850,
            score_type="Aesthetic",
        )

        dummy_details = ImageDetails(
            image_id=1,
            file_name="example_image_01.png",
            image_size="512x768",
            file_size="850 KB",
            created_date="2024-05-20 14:30:00",
            rating_value="PG",
            score_value=850,
            annotation_data=dummy_annotation,
        )
        # --- ここまでダミーデータ ---

        # データをウィジェットにロード
        # 本来は image_db_write_service 経由でロードされるが、
        # 単体テストのため、内部メソッドを直接呼び出してUIを更新する
        widget.current_image_id = dummy_details.image_id
        widget.current_details = dummy_details
        widget._update_details_display(dummy_details)  # type: ignore
        widget.set_enabled_state(True)  # 最初から操作可能にする

        # ウィジェットを表示
        widget.setWindowTitle("Selected Image Details - Test")
        widget.show()

        sys.exit(app.exec())

    main()
