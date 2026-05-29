"""
Batch Tag Add Widget - バッチタグ追加ウィジェット

複数画像に対して1つのタグを一括追加するための専用ウィジェット。
MainWindow 右パネルのタブとして配置され、バッチ操作を担当。

主要機能:
- StagingWidget によるステージングリスト管理（最大500枚）
- タグの正規化とバリデーション
- バッチタグ追加操作

アーキテクチャ:
- QTabWidget のタブ3（バッチタグ追加）に配置
- DatasetStateManager から選択画像 ID を取得
- 保存時に tag_add_requested シグナルを発行
- MainWindow が ImageDBWriteService 経由で一括保存処理を実行
- ステージング責務は StagingWidget に委譲（ADR 0041）
"""

from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from ...gui.designer.BatchTagAddWidget_ui import Ui_BatchTagAddWidget
from ...utils.log import logger
from .staging_widget import StagingWidget

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


def normalize_tag(tag: str) -> str:
    """タグを正規化する（TagCleaner.clean_format() + lower + strip）。

    Args:
        tag: 入力タグ文字列

    Returns:
        正規化されたタグ。TagCleaner.clean_format() が None を返す場合は空文字列。
    """
    cleaned: str | None = TagCleaner.clean_format(tag)
    if cleaned is None:
        return ""
    return cleaned.strip().lower()


class BatchTagAddWidget(QWidget):
    """
    バッチタグ追加ウィジェット

    複数画像に対して1つのタグを一括追加。
    ステージング管理は内部 StagingWidget に委譲し、タグ正規化を担当。

    データフロー:
    1. "選択中の画像を追加" -> StagingWidget.add_selected_images() 経由でステージングに追加
    2. ステージングリストに追加（最大500枚、重複なし）
    3. タグ入力 -> 正規化（lower + strip）
    4. "追加" -> tag_add_requested シグナル発行
    5. MainWindow が ImageDBWriteService.add_tag_batch() で DB 更新

    後方互換性:
    - _staged_images プロパティ: StagingWidget.get_staged_items() へ委譲
      main_window._get_staged_image_paths_for_annotation() が
      `._staged_images.items()` で参照するため、互換プロパティで維持する（Wave 2 で移行）
    - _on_clear_staging_clicked(): main_window._handle_batch_tag_add() が直接呼び出す
    - _refresh_staging_list_ui(): main_window が hasattr 確認後呼び出す
    - add_selected_images_to_staging(): main_window から呼ばれる公開 API
    - add_image_ids_to_staging(): main_window から呼ばれる公開 API
    - set_dataset_state_manager(): main_window から呼ばれる公開 API

    UI 構成:
    - stagingWidget: ステージング（StagingWidget プロモーション）
    - lineEditTag: タグ入力フィールド
    - pushButtonAddTag: タグを追加

    ステージングリスト仕様:
    - 最大500枚まで
    - 重複なし（set 管理）
    - 追加順を保持（OrderedDict）
    """

    # シグナル
    staged_images_changed = Signal(list)  # list[int] - ステージング画像IDリスト（StagingWidget から再公開）
    tag_add_requested = Signal(list, str)  # (image_ids, tag) - タグ追加要求
    staging_cleared = Signal()  # ステージングリストクリア（StagingWidget から再公開）

    # 定数（StagingWidget と同値を公開, main_window / テストが参照する）
    MAX_STAGING_IMAGES = StagingWidget.MAX_STAGING_IMAGES

    def __init__(self, parent: QWidget | None = None):
        """
        BatchTagAddWidget 初期化

        UIコンポーネントの初期化、内部 StagingWidget との接続、シグナル再公開を実行。

        Args:
            parent: 親ウィジェット
        """
        super().__init__(parent)
        logger.debug("BatchTagAddWidget.__init__() called")

        # DatasetStateManager への参照（後で set_dataset_state_manager() で設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # UI 設定
        self.ui = Ui_BatchTagAddWidget()
        setup_ui = cast(Callable[[QWidget], None], self.ui.setupUi)
        setup_ui(self)

        # StagingWidget は BatchTagAddWidget_ui.py のプロモーションで生成済み
        # self.ui.stagingWidget が StagingWidget インスタンス
        self._staging_widget: StagingWidget = self.ui.stagingWidget

        # StagingWidget シグナルを BatchTagAddWidget シグナルとして再公開
        self._staging_widget.staged_images_changed.connect(self.staged_images_changed)
        self._staging_widget.staging_cleared.connect(self.staging_cleared)

        logger.info("BatchTagAddWidget initialized")

    # ------------------------------------------------------------------
    # 公開 API（main_window / 外部から呼ばれる）
    # ------------------------------------------------------------------

    def set_dataset_state_manager(self, dataset_state_manager: "DatasetStateManager") -> None:
        """DatasetStateManager への参照を設定する。

        Args:
            dataset_state_manager: DatasetStateManager インスタンス
        """
        self._dataset_state_manager = dataset_state_manager
        self._staging_widget.set_dataset_state_manager(dataset_state_manager)
        logger.debug("DatasetStateManager reference set in BatchTagAddWidget")

    def add_selected_images_to_staging(self) -> None:
        """外部から選択画像をステージングに追加するための公開 API。"""
        self._staging_widget.add_selected_images()

    def add_image_ids_to_staging(self, image_ids: list[int]) -> None:
        """外部から指定画像 ID をステージングに追加する公開 API。

        Args:
            image_ids: 追加する画像 ID リスト
        """
        if not image_ids:
            logger.info("No visible image ids provided for staging")
            return
        self._staging_widget.add_image_ids(image_ids)

    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]":
        """ステージング中の画像メタデータを返す公開 API。

        ADR 0041 (#550 D): main_window はこの公開アクセサ経由でステージング画像の
        path を構築する (旧来の _staged_images private 参照から移行)。

        Returns:
            {image_id: (filename, stored_path)} の OrderedDict（追加順）。
        """
        return self._staging_widget.get_staged_items()

    # ------------------------------------------------------------------
    # 後方互換プロパティ（Wave 2 で main_window.py 移行後に削除予定）
    # ------------------------------------------------------------------

    @property
    def _staged_images(self) -> "OrderedDict[int, tuple[str, str]]":
        """ステージング画像メタデータへの後方互換アクセサ。

        ADR 0041 (#550 D) で main_window は公開 get_staged_items() 経由へ移行済み。
        本プロパティは BatchTagAddWidget の既存テスト (`widget._staged_images`) が
        参照するため StagingWidget.get_staged_items() へ委譲して維持する。
        """
        return self._staging_widget.get_staged_items()

    # ------------------------------------------------------------------
    # 内部スロット（main_window から直接呼ばれるものを含む）
    # ------------------------------------------------------------------

    @Slot()
    def _on_add_selected_clicked(self) -> None:
        """「選択中の画像を追加」ボタンクリックハンドラ。

        DatasetStateManager.selected_image_ids から ID を取得しステージングに追加。
        main_window が hasattr 確認後直接呼び出すことがある。
        """
        self._staging_widget.add_selected_images()

    @Slot()
    def _on_clear_staging_clicked(self) -> None:
        """「クリア」ボタンクリックハンドラ。

        ステージングリストを全削除。
        main_window._handle_batch_tag_add() が成功時に直接呼び出す。
        """
        self._staging_widget.clear()

    def _refresh_staging_list_ui(self) -> None:
        """ステージングリスト UI を再描画する。

        main_window が hasattr 確認後呼び出す。StagingWidget へ委譲。
        """
        self._staging_widget._refresh_staging_list_ui()

    # ------------------------------------------------------------------
    # タグ操作
    # ------------------------------------------------------------------

    def _normalize_tag(self, tag: str) -> str:
        """タグを正規化する（モジュールレベル normalize_tag() に委譲）。

        Args:
            tag: 入力タグ文字列

        Returns:
            正規化されたタグ（TagCleaner.clean_format() + lower + strip）
        """
        return normalize_tag(tag)

    @Slot()
    def _on_add_tag_clicked(self) -> None:
        """「追加」ボタンクリックハンドラ。

        タグを正規化し、tag_add_requested シグナルを発行。

        バリデーション:
        - ステージング画像数チェック
        - 空タグチェック
        - 正規化後の空文字チェック
        """
        # ステージング画像チェック
        staged = self._staging_widget.get_staged_items()
        if not staged:
            logger.warning("No images in staging list")
            QMessageBox.warning(
                self,
                "タグ追加エラー",
                "ステージングリストに画像がありません。\n画像を選択してからタグを追加してください。",
            )
            return

        # タグ入力取得
        tag_input = self.ui.lineEditTag.text()

        # 空タグチェック
        if not tag_input.strip():
            logger.warning("Empty tag input")
            QMessageBox.warning(self, "タグ追加エラー", "タグを入力してください。")
            return

        # タグ正規化
        normalized_tag = self._normalize_tag(tag_input)

        if not normalized_tag:
            logger.warning("Tag normalization resulted in empty string")
            QMessageBox.warning(
                self,
                "タグ追加エラー",
                f"タグ '{tag_input.strip()}' の正規化に失敗しました。",
            )
            return

        # シグナル発行
        image_ids = list(staged.keys())
        logger.info(f"Tag add requested: {normalized_tag} for {len(image_ids)} images")
        self.tag_add_requested.emit(image_ids, normalized_tag)

        # 成功後: タグ入力フィールドをクリア
        self.ui.lineEditTag.clear()

    def attach_tag_input_to(self, container: QWidget) -> None:
        """タグ入力 UI を外部コンテナへ移動してステージング一覧と分離する。

        Args:
            container: タグ入力 UI の移動先コンテナ
        """
        tag_input = self.ui.groupBoxTagInput
        if tag_input.parent() is not container:
            tag_input.setParent(container)
            if container.layout() is None:
                layout = QVBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
            container_layout = container.layout()
            assert container_layout is not None
            container_layout.addWidget(tag_input)

        splitter = getattr(self.ui, "splitterBatchTagStaging", None)
        if splitter:
            idx = splitter.indexOf(tag_input)
            if idx != -1:
                splitter.widget(idx).hide()
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
