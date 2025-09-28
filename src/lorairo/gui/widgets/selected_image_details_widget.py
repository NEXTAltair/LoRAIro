"""
Selected Image Details Widget - 選択画像詳細表示ウィジェット

DatasetStateManagerからの画像データを受信し、選択された画像の詳細情報を表示するウィジェット。
Enhanced Event-Driven Patternによる直接データ受信とUI更新を実装。

主要機能:
- 画像メタデータの詳細表示（ファイル名、サイズ、作成日時等）
- Rating/Scoreのインライン編集（コンボボックス・スライダー）
- アノテーションデータ（タグ・キャプション）の表示
- データベース保存操作の中継

アーキテクチャ:
- Direct Widget Communication Pattern準拠
- DatasetStateManager.current_image_data_changedシグナル受信
- ImageDetails構造体による型安全なデータ管理
- AnnotationDataDisplayWidget統合による表示機能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...gui.designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from .annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    ImageDetails,
)

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


class SelectedImageDetailsWidget(QWidget, Ui_SelectedImageDetailsWidget):
    """
    選択画像詳細情報表示ウィジェット

    DatasetStateManagerから送信される画像メタデータを受信し、選択画像の詳細情報を表示。
    Enhanced Event-Driven Patternによる非同期データ更新とユーザー操作の双方向処理を実装。

    データフロー:
    1. DatasetStateManager.current_image_data_changed -> _on_image_data_received()
    2. メタデータ解析 -> _build_image_details_from_metadata()
    3. UI更新 -> _update_details_display()
    4. ユーザー編集 -> Rating/Score変更シグナル発行
    5. 保存要求 -> save_requested シグナル発行

    UI構成:
    - groupBoxImageInfo: ファイル名、サイズ、作成日時表示
    - groupBoxRatingScore: Rating選択、Score調整スライダー
    - annotationDataDisplay: タグ・キャプション表示（AnnotationDataDisplayWidget）
    - pushButtonSave: 変更内容の保存ボタン

    型安全性:
    - ImageDetails dataclassによる構造化データ管理
    - 全メタデータフィールドの型チェック・デフォルト値処理
    - None安全なデータアクセスパターン実装
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
        """
        SelectedImageDetailsWidget初期化

        UIコンポーネントの初期化、内部状態の設定、シグナル接続を実行。
        Qt Designer UIファイルからの自動生成UIと手動制御UIコンポーネントを統合。

        Args:
            parent: 親ウィジェット。Noneの場合は独立ウィジェットとして動作

        初期化プロセス:
        1. Qt基底クラス初期化（QWidget, Ui_SelectedImageDetailsWidget）
        2. 内部状態変数の初期化（current_details, current_image_id）
        3. UI参照の確立（annotation_display）
        4. シグナル・スロット接続（_setup_connections）

        注意:
        - Enhanced Event-Driven Pattern準拠の初期化
        - レガシーImageDBWriteService依存は完全削除済み
        """
        super().__init__(parent)
        self.setupUi(self)

        # 現在の画像情報
        self.current_details: ImageDetails = ImageDetails()
        self.current_image_id: int | None = None

        # UIファイルの既存AnnotationDataDisplayWidgetを参照
        self.annotation_display: AnnotationDataDisplayWidget = self.annotationDataDisplay

        # UI初期化
        self._setup_connections()

        logger.debug("SelectedImageDetailsWidget initialized")

    def _setup_connections(self) -> None:
        """
        内部シグナル・スロット接続の設定

        AnnotationDataDisplayWidgetとの内部通信を確立。
        Rating/Score編集やボタンクリックの接続はQt Designer UIファイルで定義済み。

        接続内容:
        - annotation_display.data_loaded -> _on_annotation_data_loaded
          アノテーション表示ウィジェットからのデータ読み込み完了通知

        注意:
        - UI要素の基本的なシグナル接続（ボタンクリック等）はUIファイルで自動接続
        - ここでは内部コンポーネント間の追加接続のみ実装
        """
        # アノテーション表示コンポーネントのシグナル接続
        self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

    @Slot(str)
    def _on_rating_changed(self, rating_value: str) -> None:
        """
        Rating変更時の処理（コンボボックス選択変更）

        ユーザーがRatingコンボボックスで値を変更した際の処理。
        変更検出、内部状態更新、外部通知シグナル発行を実行。

        Args:
            rating_value: 選択されたRating値（例: "SFW", "PG", "R18"）

        処理フロー:
        1. 現在画像IDの存在確認
        2. 変更検出（既存値との比較）
        3. 内部状態更新（current_details.rating_value）
        4. 外部通知（rating_updatedシグナル発行）

        注意:
        - Qt Designer UIファイルでcomboBoxRatingと自動接続済み
        - 無限ループ防止のため変更検出を実装
        """
        if self.current_image_id and rating_value != self.current_details.rating_value:
            self.current_details.rating_value = rating_value
            self.rating_updated.emit(self.current_image_id, rating_value)
            logger.debug(f"Rating changed to: {rating_value}")

    @Slot(int)
    def _on_score_changed(self, score_value: int) -> None:
        """
        Score変更時の処理（スライダー値変更）

        ユーザーがScoreスライダーで値を変更した際の処理。
        UI表示更新、変更検出、内部状態更新、外部通知シグナル発行を実行。

        Args:
            score_value: 変更されたScore値（通常0-1000の整数範囲）

        処理フロー:
        1. スコア値ラベルの即座更新（labelScoreValue）
        2. 現在画像IDの存在確認
        3. 変更検出（既存値との比較）
        4. 内部状態更新（current_details.score_value）
        5. 外部通知（score_updatedシグナル発行）

        注意:
        - Qt Designer UIファイルでsliderScoreと自動接続済み
        - ラベル更新は変更検出前に実行（即座のUI反応）
        - 無限ループ防止のため変更検出を実装
        """
        # スコア値ラベル更新
        self.labelScoreValue.setText(str(score_value))

        if self.current_image_id and score_value != self.current_details.score_value:
            self.current_details.score_value = score_value
            self.score_updated.emit(self.current_image_id, score_value)
            logger.debug(f"Score changed to: {score_value}")

    @Slot()
    def _on_save_clicked(self) -> None:
        """
        保存ボタンクリック時の処理

        現在の画像に対するRating/Score変更をデータベースに保存するための処理。
        変更データを辞書形式で構築し、外部保存処理へのシグナル発行を実行。

        処理フロー:
        1. 画像選択状態の確認（current_image_id存在チェック）
        2. 保存データ辞書の構築（image_id, rating, score）
        3. 外部保存処理への通知（save_requestedシグナル発行）

        保存データ形式:
        {
            "image_id": int,           # 対象画像ID
            "rating": str,             # Rating値（例: "SFW", "PG", "R18"）
            "score": int               # Score値（0-1000整数）
        }

        注意:
        - Qt Designer UIファイルでpushButtonSaveと自動接続済み
        - 実際の保存処理は外部コンポーネント（MainWindow等）が担当
        - 画像未選択時は警告ログ出力のみで処理中断
        """
        if not self.current_image_id:
            logger.warning("No image selected for save operation")
            return

        save_data: dict[str, Any] = {
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

    # === Enhanced Event-Driven Pattern ===

    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（状態管理なし）"""
        # 新しいデータシグナルに接続
        state_manager.current_image_data_changed.connect(self._on_image_data_received)

        logger.debug("SelectedImageDetailsWidget connected to current_image_data_changed signal")

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict[str, Any]) -> None:
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

            logger.info(f"✅ メタデータ表示成功: ID={image_id} - Enhanced Event-Driven Pattern 完全動作")

        except Exception as e:
            logger.error(
                f"メタデータ更新エラー データ:{image_data.get('id', 'Unknown')} | エラー: {e}",
                exc_info=True,
            )
            self._clear_display()

    def _build_image_details_from_metadata(self, image_data: dict[str, Any]) -> ImageDetails:
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

            # 作成日時の取得と文字列変換
            created_date = format_datetime_for_display(image_data.get("created_at"))

            # Rating/Score の取得 - 新しい配列形式のみ対応
            rating_value = ""
            score_value = 0

            # ratings配列から最初の値を取得
            if "ratings" in image_data and isinstance(image_data["ratings"], list):
                ratings_list = image_data["ratings"]
                if ratings_list and len(ratings_list) > 0:
                    first_rating = ratings_list[0]
                    if isinstance(first_rating, dict):
                        # raw_rating_valueまたはnormalized_ratingを使用
                        rating_value = first_rating.get("raw_rating_value", "") or str(first_rating.get("normalized_rating", ""))

            # scores配列から最初の値を取得
            if "scores" in image_data and isinstance(image_data["scores"], list):
                scores_list = image_data["scores"]
                if scores_list and len(scores_list) > 0:
                    first_score = scores_list[0]
                    if isinstance(first_score, dict) and "score" in first_score:
                        score_value = int(first_score["score"] * 1000) if first_score["score"] <= 1.0 else int(first_score["score"])

            # Caption/Tags の取得
            caption = ""
            tags = ""

            # メタデータからキャプションを取得
            if "captions" in image_data and isinstance(image_data["captions"], list):
                captions_list = image_data["captions"]
                if captions_list and len(captions_list) > 0:
                    first_caption = captions_list[0]
                    if isinstance(first_caption, dict) and "caption" in first_caption:
                        caption = first_caption["caption"]
                        logger.debug(f"Caption extracted: {len(caption)} characters")

            # メタデータからタグを取得
            if "tags" in image_data and isinstance(image_data["tags"], list):
                tags_list = image_data["tags"]
                tag_strings = []
                for tag_item in tags_list:
                    if isinstance(tag_item, dict) and "tag" in tag_item:
                        tag_strings.append(tag_item["tag"])
                tags = ", ".join(tag_strings)
                logger.debug(f"Tags extracted: {len(tag_strings)} items")

            # ImageDetails を構築
            details = ImageDetails(
                image_id=image_data.get("id"),
                file_name=file_name,
                file_path=image_path_str,
                image_size=image_size,
                file_size=file_size,
                created_date=created_date,
                rating_value=rating_value,
                score_value=score_value,
                caption=caption,
                tags=tags,
                annotation_data=None,  # アノテーションデータは別途取得
            )

            logger.debug(f"ImageDetails constructed from metadata: {file_name}, caption={len(caption)} chars, tags={len(tag_strings) if 'tag_strings' in locals() else 0} items, rating={rating_value}, score={score_value}")
            return details

        except Exception as e:
            logger.error(f"Error building ImageDetails from metadata: {e}", exc_info=True)
            return ImageDetails()

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

            # キャプションとタグをAnnotationDataに設定してアノテーション表示を更新
            if details.caption or details.tags:
                # ImageDetailsのcaptionとtagsからAnnotationDataを作成
                tags_list = []
                if details.tags:
                    tags_list = [tag.strip() for tag in details.tags.split(",") if tag.strip()]

                annotation_data = AnnotationData(
                    tags=tags_list,
                    caption=details.caption,
                    aesthetic_score=0.0,
                    overall_score=0,
                    score_type=""
                )

                # 既存のannotation_dataがあれば統合
                if details.annotation_data:
                    annotation_data.aesthetic_score = details.annotation_data.aesthetic_score
                    annotation_data.overall_score = details.annotation_data.overall_score
                    annotation_data.score_type = details.annotation_data.score_type
                    # 既存のタグやキャプションが優先される場合は統合
                    if details.annotation_data.tags:
                        all_tags = set(tags_list + details.annotation_data.tags)
                        annotation_data.tags = list(all_tags)
                    if details.annotation_data.caption and not details.caption:
                        annotation_data.caption = details.annotation_data.caption

                # アノテーション表示更新
                self.annotation_display.update_data(annotation_data)
                logger.info(f"Annotation display updated: caption={len(details.caption)} chars, tags={len(tags_list)} items")
            else:
                # キャプション・タグが空の場合は既存のannotation_dataのみ使用
                if details.annotation_data:
                    self.annotation_display.update_data(details.annotation_data)
                else:
                    # 完全に空の場合はクリア
                    empty_annotation = AnnotationData(tags=[], caption="", aesthetic_score=0.0, overall_score=0, score_type="")
                    self.annotation_display.update_data(empty_annotation)

        except Exception as e:
            logger.error(f"Error updating details display: {e}", exc_info=True)

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
