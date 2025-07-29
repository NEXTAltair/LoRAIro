# src/lorairo/gui/widgets/preview_detail_panel.py

from typing import Any

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...utils.log import logger
from ..state.dataset_state import DatasetStateManager


class PreviewDetailPanel(QScrollArea):
    """
    選択された画像のプレビュー、メタデータ、アノテーションを表示するパネル。
    """

    def __init__(
        self,
        parent=None,
        dataset_state: DatasetStateManager | None = None,
        db_manager: ImageDatabaseManager | None = None,
    ):
        super().__init__(parent)

        # 依存性
        self.dataset_state = dataset_state
        self.db_manager = db_manager

        # 現在の画像情報を保持
        self.current_pixmap = None
        self.current_image_id = None

        # UI設定
        self.setup_ui()

        # 状態管理との連携
        if self.dataset_state:
            self._connect_dataset_state()

        logger.debug("PreviewDetailPanel initialized")

    def setup_ui(self) -> None:
        """UI初期化"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # メインウィジェット
        main_widget = QWidget()
        self.setWidget(main_widget)

        # メインレイアウト
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(15)

        # プレビュー画像セクション
        self._create_preview_section()

        # メタデータセクション
        self._create_metadata_section()

        # アノテーションセクション
        self._create_annotations_section()

        # 初期状態: 何も選択されていない
        self._clear_display()

    def _create_preview_section(self) -> None:
        """プレビュー画像セクション作成"""
        preview_group = QGroupBox("プレビュー")
        preview_layout = QVBoxLayout(preview_group)

        # 画像表示ラベル
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(300, 300)
        self.image_label.setMaximumSize(600, 600)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setStyleSheet("""
            QLabel {
                border: 1px solid #ccc;
                background-color: #f5f5f5;
            }
        """)
        # setScaledContents(True)を削除してアスペクト比を保持

        preview_layout.addWidget(self.image_label)
        self.main_layout.addWidget(preview_group)

    def _create_metadata_section(self) -> None:
        """メタデータセクション作成"""
        metadata_group = QGroupBox("画像情報")
        metadata_layout = QVBoxLayout(metadata_group)

        # メタデータ表示領域
        self.metadata_text = QTextEdit()
        self.metadata_text.setMaximumHeight(200)
        self.metadata_text.setReadOnly(True)
        metadata_layout.addWidget(self.metadata_text)

        self.main_layout.addWidget(metadata_group)

    def _create_annotations_section(self) -> None:
        """アノテーションセクション作成"""
        annotations_group = QGroupBox("アノテーション")
        annotations_layout = QVBoxLayout(annotations_group)

        # タグセクション
        tags_frame = QFrame()
        tags_layout = QVBoxLayout(tags_frame)
        tags_layout.addWidget(QLabel("タグ:"))

        self.tags_text = QTextEdit()
        self.tags_text.setMaximumHeight(150)
        self.tags_text.setReadOnly(True)
        tags_layout.addWidget(self.tags_text)

        annotations_layout.addWidget(tags_frame)

        # キャプションセクション
        captions_frame = QFrame()
        captions_layout = QVBoxLayout(captions_frame)
        captions_layout.addWidget(QLabel("キャプション:"))

        self.captions_text = QTextEdit()
        self.captions_text.setMaximumHeight(150)
        self.captions_text.setReadOnly(True)
        captions_layout.addWidget(self.captions_text)

        annotations_layout.addWidget(captions_frame)

        # スコア・レーティングセクション
        scores_frame = QFrame()
        scores_layout = QVBoxLayout(scores_frame)
        scores_layout.addWidget(QLabel("スコア・レーティング:"))

        self.scores_text = QTextEdit()
        self.scores_text.setMaximumHeight(100)
        self.scores_text.setReadOnly(True)
        scores_layout.addWidget(self.scores_text)

        annotations_layout.addWidget(scores_frame)

        self.main_layout.addWidget(annotations_group)

    def set_dataset_state(self, dataset_state: DatasetStateManager) -> None:
        """データセット状態管理を設定"""
        if self.dataset_state:
            self._disconnect_dataset_state()

        self.dataset_state = dataset_state
        self._connect_dataset_state()

    def set_db_manager(self, db_manager: ImageDatabaseManager) -> None:
        """データベースマネージャーを設定"""
        self.db_manager = db_manager

    def _connect_dataset_state(self) -> None:
        """データセット状態管理との連携を設定"""
        if not self.dataset_state:
            return

        self.dataset_state.current_image_changed.connect(self._on_current_image_changed)
        self.dataset_state.current_image_cleared.connect(self._on_current_image_cleared)

    def _disconnect_dataset_state(self) -> None:
        """データセット状態管理との連携を解除"""
        if not self.dataset_state:
            return

        self.dataset_state.current_image_changed.disconnect(self._on_current_image_changed)
        self.dataset_state.current_image_cleared.disconnect(self._on_current_image_cleared)

    @Slot(int)
    def _on_current_image_changed(self, image_id: int) -> None:
        """現在画像変更通知を処理"""
        logger.info(f"プレビューパネル: 画像ID {image_id} の詳細を表示中")
        self._load_image_details(image_id)

    @Slot()
    def _on_current_image_cleared(self) -> None:
        """現在画像クリア通知を処理"""
        logger.info("プレビューパネル: 画像選択をクリア")
        self._clear_display()

    def _load_image_details(self, image_id: int) -> None:
        """指定された画像IDの詳細情報を読み込み表示"""
        if not self.db_manager:
            logger.warning("DatabaseManagerが設定されていません")
            self._clear_display()
            return

        try:
            # 画像メタデータを取得
            metadata = self.db_manager.get_image_metadata(image_id)
            if not metadata:
                logger.warning(f"画像ID {image_id} のメタデータが見つかりません")
                self._clear_display()
                return

            # アノテーションデータを取得
            annotations = self.db_manager.get_image_annotations(image_id)

            # UI更新
            self._display_image_preview(metadata)
            self._display_metadata(metadata)
            self._display_annotations(annotations)

        except Exception as e:
            logger.error(f"画像詳細の読み込み中にエラーが発生しました: {e}", exc_info=True)
            self._clear_display()

    def _display_image_preview(self, metadata: dict[str, Any]) -> None:
        """画像プレビューを表示"""
        try:
            # 画像パスを解決
            stored_path = metadata.get("stored_image_path")
            if not stored_path:
                self.image_label.setText("画像パスが見つかりません")
                return

            # パス解決（相対パス対応）
            image_path = resolve_stored_path(stored_path)

            if not image_path.exists():
                self.image_label.setText(f"画像ファイルが見つかりません:\\n{image_path}")
                return

            # 画像読み込み・表示
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                self.image_label.setText("画像の読み込みに失敗しました")
                self.current_pixmap = None
                return

            # 現在の画像情報を保存
            self.current_pixmap = pixmap

            # アスペクト比を保持してスケール
            self._update_image_display()
            logger.debug(f"画像プレビュー表示完了: {image_path}")

        except Exception as e:
            logger.error(f"画像プレビュー表示エラー: {e}")
            self.image_label.setText(f"画像表示エラー: {e!s}")

    def _display_metadata(self, metadata: dict[str, Any]) -> None:
        """メタデータを表示"""
        try:
            # メタデータを整理して表示
            display_items = [
                f"画像ID: {metadata.get('id', 'N/A')}",
                f"ファイルパス: {metadata.get('stored_image_path', 'N/A')}",
                f"解像度: {metadata.get('width', 'N/A')} x {metadata.get('height', 'N/A')}",
                f"ファイルサイズ: {self._format_file_size(metadata.get('file_size', 0))}",
                f"作成日時: {metadata.get('created_at', 'N/A')}",
                f"更新日時: {metadata.get('updated_at', 'N/A')}",
                f"pHash: {metadata.get('phash', 'N/A')}",
                f"UUID: {metadata.get('uuid', 'N/A')}",
            ]

            # アルファチャンネルの有無
            if "has_alpha" in metadata:
                display_items.append(f"アルファチャンネル: {'あり' if metadata['has_alpha'] else 'なし'}")

            # カラーモード
            if "mode" in metadata:
                display_items.append(f"カラーモード: {metadata['mode']}")

            metadata_text = "\n".join(display_items)
            self.metadata_text.setPlainText(metadata_text)

        except Exception as e:
            logger.error(f"メタデータ表示エラー: {e}")
            self.metadata_text.setPlainText(f"メタデータ表示エラー: {e!s}")

    def _display_annotations(self, annotations: dict[str, list[dict[str, Any]]]) -> None:
        """アノテーションデータを表示"""
        try:
            # タグ表示
            self._display_tags(annotations.get("tags", []))

            # キャプション表示
            self._display_captions(annotations.get("captions", []))

            # スコア・レーティング表示
            self._display_scores_and_ratings(annotations.get("scores", []), annotations.get("ratings", []))

        except Exception as e:
            logger.error(f"アノテーション表示エラー: {e}")
            self._display_error_state(e)

    def _display_tags(self, tags: list[dict[str, Any]]) -> None:
        """タグ情報を表示"""
        if not tags:
            self.tags_text.setPlainText("タグなし")
            return

        tag_list = []
        for tag in tags:
            tag_text = self._format_tag_text(tag)
            tag_list.append(tag_text)

        self.tags_text.setPlainText("\n".join(tag_list))

    def _format_tag_text(self, tag: dict[str, Any]) -> str:
        """タグテキストをフォーマット"""
        tag_text = tag.get("tag", "N/A")
        confidence = tag.get("confidence_score")
        model_id = tag.get("model_id")

        if confidence is not None:
            tag_text += f" (信頼度: {confidence:.3f})"
        if model_id:
            tag_text += f" [モデル: {model_id}]"

        return tag_text

    def _display_captions(self, captions: list[dict[str, Any]]) -> None:
        """キャプション情報を表示"""
        if not captions:
            self.captions_text.setPlainText("キャプションなし")
            return

        caption_list = []
        for caption in captions:
            caption_text = self._format_caption_text(caption)
            caption_list.append(caption_text)

        self.captions_text.setPlainText("\n".join(caption_list))

    def _format_caption_text(self, caption: dict[str, Any]) -> str:
        """キャプションテキストをフォーマット"""
        caption_text = caption.get("caption", "N/A")
        model_id = caption.get("model_id")

        if model_id:
            caption_text += f"\n[モデル: {model_id}]"

        return caption_text

    def _display_scores_and_ratings(
        self, scores: list[dict[str, Any]], ratings: list[dict[str, Any]]
    ) -> None:
        """スコアとレーティング情報を表示"""
        score_list = []

        # スコア情報を追加
        for score in scores:
            score_text = self._format_score_text(score)
            score_list.append(score_text)

        # レーティング情報を追加
        for rating in ratings:
            rating_text = self._format_rating_text(rating)
            score_list.append(rating_text)

        if score_list:
            self.scores_text.setPlainText("\n".join(score_list))
        else:
            self.scores_text.setPlainText("スコア・レーティングなし")

    def _format_score_text(self, score: dict[str, Any]) -> str:
        """スコアテキストをフォーマット"""
        score_value = score.get("score", "N/A")
        model_id = score.get("model_id", "N/A")
        return f"スコア: {score_value} [モデル: {model_id}]"

    def _format_rating_text(self, rating: dict[str, Any]) -> str:
        """レーティングテキストをフォーマット"""
        rating_value = rating.get("rating", "N/A")
        model_id = rating.get("model_id", "N/A")
        return f"レーティング: {rating_value} [モデル: {model_id}]"

    def _display_error_state(self, error: Exception) -> None:
        """エラー状態を表示"""
        error_message = f"アノテーション表示エラー: {error!s}"
        self.tags_text.setPlainText(error_message)
        self.captions_text.setPlainText("")
        self.scores_text.setPlainText("")

    def _update_image_display(self) -> None:
        """現在の画像を適切なサイズで表示"""
        if not self.current_pixmap:
            return

        # ラベルサイズに基づいて最大サイズを決定
        label_size = self.image_label.size()
        # 余白を考慮して少し小さめに設定
        max_width = min(label_size.width() - 20, 580)
        max_height = min(label_size.height() - 20, 580)
        max_size = QSize(max_width, max_height)

        # アスペクト比を保持してスケール
        scaled_pixmap = self.current_pixmap.scaled(
            max_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event) -> None:
        """リサイズイベント処理 - 画像表示を更新"""
        super().resizeEvent(event)
        if self.current_pixmap:
            self._update_image_display()

    def _clear_display(self) -> None:
        """表示をクリア"""
        self.image_label.clear()
        self.image_label.setText("画像を選択してください")
        self.current_pixmap = None
        self.current_image_id = None
        self.metadata_text.clear()
        self.tags_text.clear()
        self.captions_text.clear()
        self.scores_text.clear()

    def _format_file_size(self, size_bytes: int) -> str:
        """ファイルサイズを読みやすい形式でフォーマット"""
        if size_bytes == 0:
            return "0 B"

        size_units = ["B", "KB", "MB", "GB"]
        size = float(size_bytes)
        unit_index = 0

        while size >= 1024 and unit_index < len(size_units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.1f} {size_units[unit_index]}"

    def _update_preview_image(self, image_id: int) -> None:
        """プレビュー画像を更新"""
        self.current_image_id = image_id
        if image_id is not None:
            self._load_image_details(image_id)
        else:
            self._clear_display()

    def _update_metadata_display(self, metadata: dict[str, Any]) -> None:
        """メタデータ表示を更新"""
        self._display_metadata(metadata)
