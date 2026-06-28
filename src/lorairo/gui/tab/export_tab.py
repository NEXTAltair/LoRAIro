"""エクスポートタブの専用ウィジェット (Epic #942 #949 / 旧 #867 #872 #896)。

エクスポート前タグ編集パネル。検索タブ同型の **3ペイン横 splitter + 下部
ExportOverlayBar** で構成する (ADR 0080 2層タグ編集モデル)。

レイアウト:
    左   StagingTagPanel(#947)        : ステージング集合のタグ×件数集計・行内アクション
    中   ThumbnailSelectorWidget(再利用): ステージング画像のサムネグリッド
    右   ImagePreviewWidget + SelectedImageDetailsWidget(再利用、縦 splitter)
    下   ExportOverlayBar(#948)         : trigger 補完・overlay・スコープ・プレビュー・エクスポート

対象 = ステージング集合 (ADR 0055/0019)。対象 ID は ``StagingStateManager``
(ADR 0074) を SSoT とし、``staged_images_changed`` 購読でライブ更新する (#896)。

本コミット (#949 PR1) は **骨格** を提供する: レイアウト・再利用ウィジェットの
manager 接続・ステージング集合のサムネ/集計供給・QSettings 永続化まで。
ウィジェット間のシグナル配線 (タグ絞り込み→サムネ / overlay 受け / DB reject /
選択→プレビュー / エクスポート実行) は後続 PR2 で行う。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QSettings, Qt, QThread, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QSplitter, QVBoxLayout, QWidget

from ...database.db_core import resolve_stored_path
from ...services.staging_tag_aggregation import StagingTagAggregationService
from ..state.dataset_state import DatasetStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.dataset_export_widget import DatasetExportWorker
from ..widgets.export_overlay_bar import ExportOverlayBar
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.staging_tag_panel import StagingTagPanel
from ..widgets.thumbnail_selector_widget import ThumbnailSelectorWidget

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...services.service_container import ServiceContainer

# QSettings 永続化キー (splitter ごとに独立。タブ抽出での取りこぼし防止のため明示)。
_SETTINGS_MAIN_SPLITTER = "ExportTab/mainSplitterState"
_SETTINGS_PREVIEW_SPLITTER = "ExportTab/previewSplitterState"


class ExportTabWidget(QWidget):
    """エクスポートタブのルートウィジェット (Epic #942 エクスポート前タグ編集パネル)。

    3ペイン splitter + 下部 ExportOverlayBar を組み、エクスポート対象 ID を
    ステージング集合へ自治同期する。初期対象は注入された ``StagingStateManager``
    から読み、以降は ``staged_images_changed`` 購読でライブ更新する (#896)。
    """

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None = None,
        staging_state_manager: StagingStateManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """エクスポートタブを初期化する。

        Args:
            service_container: サービス依存注入コンテナ (merged reader / export service)。
            db_manager: タグ集計・id→path 解決・詳細パネルの DB 取得/編集。
            staging_state_manager: エクスポート対象の SSoT (ADR 0074)。初期対象を読み、
                ``staged_images_changed`` 購読でライブ更新する。None なら空集合で構築。
            parent: 親ウィジェット。

        Note:
            選択 SSoT は **タブローカルな** ``DatasetStateManager`` を内部生成する。
            検索タブと共有 manager を使うと、本タブの populate がグローバル画像集合を
            ステージング集合だけに上書きし検索タブの選択/プレビューを壊すため (#961 P1)。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager

        # タブローカル選択 SSoT (共有 manager を汚染しない、#961 P1)。
        self._dataset_state_manager = DatasetStateManager()
        if db_manager is not None:
            self._dataset_state_manager.set_db_manager(db_manager)

        # 非同期エクスポート worker/thread (export_requested で起動、参照保持で GC 防止)。
        self._export_worker: DatasetExportWorker | None = None
        self._export_thread: QThread | None = None

        # 現在のエクスポート対象 (ステージング集合と同期)。
        self._image_ids: list[int] = (
            staging_state_manager.get_image_ids() if staging_state_manager is not None else []
        )

        # 左ペインのタグ集計サービス (db_manager がある場合のみ)。
        self._aggregation_service: StagingTagAggregationService | None = (
            StagingTagAggregationService(db_manager) if db_manager is not None else None
        )

        self._build_ui()
        self._setup_widgets()
        self._apply_initial_sizes()
        self._restore_splitter_state()

        # 初期ステージング集合をサムネ/集計へ反映。
        self._populate(self._image_ids)

        # ステージング集合 (SSoT) をライブ購読する。clear() も changed([]) を発行するため、
        # staged_images_changed の購読だけで set / clear 双方を同期できる。
        if staging_state_manager is not None:
            staging_state_manager.staged_images_changed.connect(self.set_image_ids)

        logger.info("✅ エクスポートタブ (ExportTabWidget) 初期化完了")

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """3ペイン splitter + 下部 ExportOverlayBar を構築する。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 横 3ペイン: 左 StagingTagPanel / 中 サムネ / 右 縦splitter[プレビュー, 詳細]
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setObjectName("exportMainSplitter")

        self._staging_tag_panel = StagingTagPanel(service=self._aggregation_service)
        self._thumbnail_selector = ThumbnailSelectorWidget()
        self._image_preview_widget = ImagePreviewWidget()
        self._selected_image_details_widget = SelectedImageDetailsWidget()

        self._preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self._preview_splitter.setObjectName("exportPreviewSplitter")
        self._preview_splitter.addWidget(self._image_preview_widget)
        self._preview_splitter.addWidget(self._selected_image_details_widget)

        self._main_splitter.addWidget(self._staging_tag_panel)
        self._main_splitter.addWidget(self._thumbnail_selector)
        self._main_splitter.addWidget(self._preview_splitter)

        root.addWidget(self._main_splitter, 1)

        # 下部 overlay バー (trigger 補完・overlay・スコープ・プレビュー・エクスポート)。
        merged_reader = self._resolve_merged_reader()
        self._overlay_bar = ExportOverlayBar(reader=merged_reader)
        self._overlay_bar.export_requested.connect(self._on_export_requested)
        self._overlay_bar.validate_requested.connect(self._on_validate_requested)
        root.addWidget(self._overlay_bar)

    def _setup_widgets(self) -> None:
        """再利用ウィジェットを各 manager へ接続する (検索タブ _setup_widgets と同型)。"""
        dsm = self._dataset_state_manager

        if dsm is not None:
            self._thumbnail_selector.set_dataset_state(dsm)
            self._image_preview_widget.connect_to_data_signals(dsm)

        if self._db_manager is not None:
            self._selected_image_details_widget.set_db_manager(self._db_manager)
        merged_reader = self._resolve_merged_reader()
        if merged_reader is not None:
            self._selected_image_details_widget.set_merged_reader(merged_reader)
        if dsm is not None:
            self._selected_image_details_widget.connect_to_dataset_state_manager(dsm)

    def _apply_initial_sizes(self) -> None:
        """splitter の初期比率を設定する (検索タブと同じ 18/42/40・55/45)。"""
        self._main_splitter.setSizes([216, 504, 480])
        self._main_splitter.setStretchFactor(0, 18)
        self._main_splitter.setStretchFactor(1, 42)
        self._main_splitter.setStretchFactor(2, 40)

        self._preview_splitter.setSizes([550, 450])
        self._preview_splitter.setStretchFactor(0, 1)
        self._preview_splitter.setStretchFactor(1, 1)

    def _resolve_merged_reader(self) -> Any:
        """MergedTagReader を取得する。失敗時は None (graceful degradation)。"""
        try:
            return self._service_container.db_manager.annotation_repo.get_merged_reader()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"MergedTagReader 取得に失敗 (convert なしで継続): {e}")
            return None

    # ------------------------------------------------------------------
    # ステージング集合 → サムネ / 集計 供給
    # ------------------------------------------------------------------

    def _populate(self, image_ids: list[int]) -> None:
        """ステージング集合をタグ集計・サムネグリッド・選択 SSoT へ反映する。"""
        # 左ペイン: タグ集計
        if self._aggregation_service is not None:
            self._staging_tag_panel.load_tags(image_ids)

        # 中央: サムネグリッド (id→path 解決) + 選択 SSoT へ metadata 供給
        if self._db_manager is None:
            return
        metadata_list: list[dict[str, Any]] = []
        path_items: list[tuple[str, int]] = []
        for image_id in image_ids:
            metadata = self._db_manager.get_image_metadata(image_id)
            if metadata is None:
                continue
            metadata_list.append(metadata)
            stored_path = metadata.get("stored_image_path")
            if stored_path:
                # stored_image_path はプロジェクトルート相対のことがあるため解決する (#961 P2)。
                resolved = resolve_stored_path(str(stored_path))
                path_items.append((str(resolved), image_id))

        if self._dataset_state_manager is not None:
            self._dataset_state_manager.set_dataset_images(metadata_list)
        self._thumbnail_selector.load_thumbnails_from_paths(path_items)

    # ------------------------------------------------------------------
    # Public API (MainWindow / テストが配線)
    # ------------------------------------------------------------------

    @Slot(list)
    def set_image_ids(self, image_ids: list[int]) -> None:
        """エクスポート対象の画像 ID を更新し、サムネ・集計へ反映する。"""
        self._image_ids = list(image_ids)
        self._populate(self._image_ids)

    def refresh(self) -> None:
        """ステージング集合を再読込してエクスポート対象へ反映する (ADR 0055 安全網)。

        タブ表示時にシグナル取りこぼしがあっても、SSoT である
        ``StagingStateManager`` を読み直して対象件数の整合を取る (#896)。
        """
        if self._staging_state_manager is not None:
            self.set_image_ids(self._staging_state_manager.get_image_ids())

    def current_export_ids(self) -> list[int]:
        """現在のエクスポート対象 ID を返す (テスト・検証用)。"""
        return list(self._image_ids)

    # ------------------------------------------------------------------
    # エクスポート実行 (ExportOverlayBar からの要求受け)
    # ------------------------------------------------------------------
    # PR1 ではステージング集合をそのまま書き出す (旧 DatasetExportWidget と同等の挙動)。
    # overlay (trigger/exclude/replace) と scope の適用は PR2 で配線する。

    @Slot()
    def _on_validate_requested(self) -> None:
        """検証要求: エクスポート対象件数を確認しユーザーへ提示する。"""
        count = len(self._image_ids)
        if count == 0:
            QMessageBox.warning(self, "エクスポート検証", "エクスポート対象がありません。")
            return
        QMessageBox.information(self, "エクスポート検証", f"エクスポート対象: {count} 枚")

    @Slot()
    def _on_export_requested(self) -> None:
        """エクスポート要求: 出力先を選び、非同期 worker で書き出す。"""
        if not self._image_ids:
            QMessageBox.warning(self, "エクスポート", "エクスポート対象がありません。")
            return
        if self._export_thread is not None and self._export_thread.isRunning():
            QMessageBox.information(self, "エクスポート", "エクスポート処理が実行中です。")
            return

        directory = QFileDialog.getExistingDirectory(self, "エクスポート先ディレクトリを選択")
        if not directory:
            return

        export_format = self._overlay_bar.selected_format()
        resolution = self._overlay_bar.selected_resolution()
        # ExportOverlayBar は canonical 値 (txt_separate/txt_merged/json) を返す。
        merge_caption = export_format == "txt_merged"

        self._export_worker = DatasetExportWorker(
            export_service=self._service_container.dataset_export_service,
            image_ids=list(self._image_ids),
            output_path=Path(directory),
            resolution=resolution,
            export_format=export_format,
            merge_caption=merge_caption,
        )
        self._export_thread = QThread()
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_thread.start()
        logger.info(f"エクスポート開始: {len(self._image_ids)}枚 → {directory} (format={export_format})")

    @Slot(str)
    def _on_export_finished(self, export_path: str) -> None:
        """エクスポート完了: スレッドを後始末しユーザーへ結果を提示する。"""
        self._teardown_export_thread()
        QMessageBox.information(self, "エクスポート完了", f"エクスポートが完了しました:\n{export_path}")

    @Slot(str)
    def _on_export_error(self, message: str) -> None:
        """エクスポート失敗: スレッドを後始末しエラーを提示する。"""
        self._teardown_export_thread()
        QMessageBox.critical(self, "エクスポート失敗", f"エクスポートに失敗しました:\n{message}")

    def _teardown_export_thread(self) -> None:
        """エクスポート worker/thread を停止・破棄する。"""
        if self._export_thread is not None:
            self._export_thread.quit()
            self._export_thread.wait()
            self._export_thread = None
        self._export_worker = None

    # ------------------------------------------------------------------
    # アクセサ (タブ内配線・テスト用)
    # ------------------------------------------------------------------

    @property
    def staging_tag_panel(self) -> StagingTagPanel:
        """左ペイン StagingTagPanel を返す。"""
        return self._staging_tag_panel

    @property
    def thumbnail_selector(self) -> ThumbnailSelectorWidget:
        """中央 ThumbnailSelectorWidget を返す。"""
        return self._thumbnail_selector

    @property
    def image_preview_widget(self) -> ImagePreviewWidget:
        """右上 ImagePreviewWidget を返す。"""
        return self._image_preview_widget

    @property
    def selected_image_details_widget(self) -> SelectedImageDetailsWidget:
        """右下 SelectedImageDetailsWidget を返す。"""
        return self._selected_image_details_widget

    @property
    def overlay_bar(self) -> ExportOverlayBar:
        """下部 ExportOverlayBar を返す。"""
        return self._overlay_bar

    @property
    def main_splitter(self) -> QSplitter:
        """3ペイン横 splitter を返す (QSettings 復元・パネルトグル用)。"""
        return self._main_splitter

    @property
    def preview_splitter(self) -> QSplitter:
        """プレビュー/詳細の縦 splitter を返す (QSettings 保存・復元用)。"""
        return self._preview_splitter

    # ------------------------------------------------------------------
    # splitter 永続化 (QSettings)
    # ------------------------------------------------------------------

    def _restore_splitter_state(self) -> None:
        """QSettings から splitter 状態を復元し、#865 の orientation 巻き戻しを補正する。"""
        settings = QSettings()
        main_state = settings.value(_SETTINGS_MAIN_SPLITTER)
        if main_state is not None:
            self._main_splitter.restoreState(main_state)
        preview_state = settings.value(_SETTINGS_PREVIEW_SPLITTER)
        if preview_state is not None:
            self._preview_splitter.restoreState(preview_state)
        # restoreState は orientation も復元するため、設計上の向きを再適用する (#865)。
        self._main_splitter.setOrientation(Qt.Orientation.Horizontal)
        self._preview_splitter.setOrientation(Qt.Orientation.Vertical)

    def save_splitter_state(self) -> None:
        """splitter 状態を QSettings に保存する (MainWindow の closeEvent から呼ぶ)。"""
        settings = QSettings()
        settings.setValue(_SETTINGS_MAIN_SPLITTER, self._main_splitter.saveState())
        settings.setValue(_SETTINGS_PREVIEW_SPLITTER, self._preview_splitter.saveState())
