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

骨格 (#949 PR1) に続き、ウィジェット間のシグナル配線を行う (#949 follow-up):
タグ絞り込み→中央サムネ + scope counts / ⊘ 出力除外・⇄ 置換 (橙=一時) → overlay /
✎ reject(DB) (青=永続) → 全 staged 画像の DB soft-reject / サムネ選択 → ライブ
プレビュー / スコープ (全/絞込) → エクスポート対象。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QSettings, Qt, QThread, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox, QSplitter, QVBoxLayout, QWidget

from ...database.db_core import resolve_stored_path
from ...services.export_overlay import ExportOverlayPlan, ScopedOverlayRule
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

        # 左ペインのタグ絞り込み状態 (#949)。None = 絞り込みなし (全 staged 表示)。
        self._active_filter_tag: str | None = None
        self._filtered_ids: list[int] = list(self._image_ids)
        # エクスポート適用スコープ ("all" = 全 staged / "filtered" = 絞り込み結果のみ)。
        self._scope: str = "all"

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
        # refinement リコメンド (#931): 共有 RefinementService を注入。
        # tagdb 初期化失敗でもタブを巻き込まず degrade する (refinement は付加機能のため非致命)。
        try:
            self._selected_image_details_widget.set_refinement_service(
                self._service_container.refinement_service
            )
        except Exception as e:
            # graceful degradation (#931): どの初期化エラーでもタブを生かす意図で広く捕捉。
            logger.warning(f"RefinementService 配線をスキップ (tagdb 不可?): {e}")
        if dsm is not None:
            self._selected_image_details_widget.connect_to_dataset_state_manager(dsm)

        self._connect_panel_signals()

    def _connect_panel_signals(self) -> None:
        """StagingTagPanel / overlay bar / 選択 のシグナルを配線する (#949 follow-up)。

        - 左ペインのタグ絞り込み → 中央サムネ + scope counts
        - ⊘ 出力除外 / ⇄ 置換 (橙=一時) → ExportOverlayBar の overlay
        - ✎ reject(DB) (青=永続) → 全 staged 画像の DB soft-reject
        - サムネ選択 (DSM 経由) → ExportOverlayBar のライブプレビュー
        - スコープ切替 → エクスポート対象の全/絞込
        """
        panel = self._staging_tag_panel
        panel.filter_tag_changed.connect(self._on_filter_tag_changed)
        panel.overlay_exclude_requested.connect(self._overlay_bar.add_overlay_exclude)
        panel.overlay_replace_requested.connect(self._overlay_bar.add_overlay_replace)
        panel.db_reject_everywhere_requested.connect(self._on_db_reject_everywhere)

        self._dataset_state_manager.current_image_data_changed.connect(self._on_current_image_data_changed)
        # 選択クリア (絞り込み/ステージング変更で対象外になった場合) も overlay プレビューへ伝える。
        # clear_current_image() は current_image_cleared を emit する (data_changed ではない) ため
        # 個別に購読する (Codex P2)。
        self._dataset_state_manager.current_image_cleared.connect(self._on_current_image_cleared)
        self._overlay_bar.scope_changed.connect(self._on_scope_changed)

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
        """ステージング集合をタグ集計・サムネグリッド・選択 SSoT へ反映する。

        ステージング集合が変わるたびにタグ絞り込みはリセットし (全 staged 表示)、
        中央サムネと scope counts を全件で再構築する。
        """
        # 左ペイン: タグ集計
        if self._aggregation_service is not None:
            self._staging_tag_panel.load_tags(image_ids)

        # ステージング集合の変化で絞り込みは解除する (#949)。
        self._active_filter_tag = None
        self._filtered_ids = list(image_ids)
        self._render_thumbnails(image_ids)
        self._overlay_bar.set_scope_counts(len(image_ids), len(image_ids))

    def _render_thumbnails(self, image_ids: list[int]) -> None:
        """指定 ID 集合のサムネグリッドと選択 SSoT を再構築する (#949)。

        ``_populate`` (全 staged) とタグ絞り込み (部分集合) の両方から呼ばれる。
        絞り込みで現在選択画像が表示集合から外れた場合は current image をクリアし、
        右ペイン/プレビューが非表示画像を表示し続けるのを防ぐ (#961 P2)。
        """
        current_id = self._dataset_state_manager.current_image_id
        if current_id is not None and current_id not in set(image_ids):
            self._dataset_state_manager.clear_current_image()

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
    # StagingTagPanel / overlay bar / 選択 シグナルハンドラ (#949 follow-up)
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_filter_tag_changed(self, tag: str | None) -> None:
        """左ペインのタグ絞り込みを中央サムネへ反映する (#949)。

        tag=None で全 staged を表示、tag 指定でそのタグを持つ staged 画像のみ表示する。
        絞り込み結果は scope counts と (scope=filtered 時の) エクスポート対象にも使う。
        """
        if tag is None or self._aggregation_service is None:
            self._active_filter_tag = None
            self._filtered_ids = list(self._image_ids)
        else:
            self._active_filter_tag = tag
            self._filtered_ids = self._aggregation_service.images_with_tag(self._image_ids, tag)
        self._render_thumbnails(self._filtered_ids)
        self._overlay_bar.set_scope_counts(len(self._image_ids), len(self._filtered_ids))

    @Slot(str)
    def _on_db_reject_everywhere(self, tag: str) -> None:
        """選択タグを全 staged 画像で DB soft-reject し、集計/サムネを更新する (#949)。

        青=DB 永続操作。取り消し不可のため確認ダイアログを出す。
        """
        if self._db_manager is None or not self._image_ids:
            return
        reply = QMessageBox.question(
            self,
            "DB reject",
            f"タグ「{tag}」を staged {len(self._image_ids)} 枚すべてで DB から reject します。\n"
            "この操作は取り消せません。続行しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        rejected = self._db_manager.soft_reject_tag_batch(self._image_ids, tag)
        logger.info(f"DB reject(全 staged): tag={tag!r}, reject={rejected}枚")
        # load_tags() は内部で絞り込みをリセットし filter_tag_changed(None) を同期 emit して
        # _active_filter_tag を None に上書きするため、再適用前にアクティブタグを退避する (Codex P2)。
        active = self._active_filter_tag
        # 集計とサムネキャッシュを最新化し、退避した絞り込みを維持して再描画する。
        if self._aggregation_service is not None:
            self._staging_tag_panel.load_tags(self._image_ids)
        self._dataset_state_manager.refresh_images(self._image_ids)
        self._on_filter_tag_changed(active)

    @Slot(dict)
    def _on_current_image_data_changed(self, image_data: dict[str, Any]) -> None:
        """選択画像を ExportOverlayBar へ渡しライブプレビューを更新する (#949)。"""
        if not image_data:
            self._overlay_bar.set_selected_image(None, [])
            return
        image_id = image_data.get("id")
        db_tags = [t["tag"] for t in image_data.get("tags", []) if isinstance(t, dict) and t.get("tag")]
        self._overlay_bar.set_selected_image(image_id, db_tags)

    @Slot()
    def _on_current_image_cleared(self) -> None:
        """選択クリア時に ExportOverlayBar のライブプレビューも空にする (#949, Codex P2)。"""
        self._overlay_bar.set_selected_image(None, [])

    @Slot(str)
    def _on_scope_changed(self, scope: str) -> None:
        """エクスポート適用スコープ ("all" | "filtered") を更新する (#949)。"""
        self._scope = scope

    def _effective_export_ids(self) -> list[int]:
        """scope と changed-since を反映した実エクスポート対象 ID を返す。

        scope=filtered のときは ``_filtered_ids`` のキャッシュではなく、現在のタグ絞り込み
        条件を **DB から再計算** して基底にする。詳細ペインのタグ編集や DB reject で対象タグの
        付与状況が変わっても、export 時点の最新状態で書き出す (Codex P2)。validate/export の
        たびに現在の UI 設定から再計算し、stale な対象で書き出す事故を防ぐ (#962 / #621)。
        """
        if (
            self._scope == "filtered"
            and self._active_filter_tag is not None
            and self._aggregation_service is not None
        ):
            base_ids = self._aggregation_service.images_with_tag(self._image_ids, self._active_filter_tag)
        else:
            base_ids = list(self._image_ids)
        if not self._overlay_bar.changed_since_enabled():
            return base_ids
        since = self._overlay_bar.changed_since()
        return self._service_container.dataset_export_service.filter_changed_since(
            base_ids,
            since,
        )

    # ------------------------------------------------------------------
    # エクスポート実行 (ExportOverlayBar からの要求受け)
    # ------------------------------------------------------------------
    # PR1 ではステージング集合をそのまま書き出す (旧 DatasetExportWidget と同等の挙動)。
    # overlay (trigger/exclude/replace) と scope の適用は PR2 で配線する。

    @Slot()
    def _on_validate_requested(self) -> None:
        """検証要求: エクスポート対象件数を確認しユーザーへ提示する。"""
        if not self._image_ids:
            QMessageBox.warning(self, "エクスポート検証", "エクスポート対象がありません。")
            return
        effective_ids = self._effective_export_ids()
        count = len(effective_ids)
        if count == 0:
            QMessageBox.warning(
                self,
                "エクスポート検証",
                "changed-since 条件に一致するエクスポート対象がありません。",
            )
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

        effective_ids = self._effective_export_ids()
        if not effective_ids:
            QMessageBox.warning(
                self,
                "エクスポート",
                "changed-since 条件に一致するエクスポート対象がありません。",
            )
            return

        directory = QFileDialog.getExistingDirectory(self, "エクスポート先ディレクトリを選択")
        if not directory:
            return

        export_format = self._overlay_bar.selected_format()
        resolution = self._overlay_bar.selected_resolution()
        # ExportOverlayBar は canonical 値 (txt_separate/txt_merged/json) を返す。
        merge_caption = export_format == "txt_merged"

        # 出力 overlay (trigger/exclude/replace) を全 staged 画像へグローバル適用する。
        # preview と書き出しを一致させるため (#961 P1)。空 overlay は None でレガシー挙動を維持。
        # scope (全/絞込) の絞り込みは filter 配線が入る後続 PR で対応する。
        overlay = self._overlay_bar.current_overlay()
        overlay_plan = (
            None if overlay.is_noop else ExportOverlayPlan(rules=[ScopedOverlayRule(None, overlay)])
        )

        worker = DatasetExportWorker(
            export_service=self._service_container.dataset_export_service,
            image_ids=effective_ids,
            output_path=Path(directory),
            resolution=resolution,
            export_format=export_format,
            merge_caption=merge_caption,
            overlay_plan=overlay_plan,
        )
        worker.finished.connect(self._on_export_finished)
        worker.error.connect(self._on_export_error)
        self._export_worker = worker
        self._start_export_worker(worker)
        logger.info(f"エクスポート開始: {len(effective_ids)}枚 → {directory} (format={export_format})")

    def _start_export_worker(self, worker: DatasetExportWorker) -> None:
        """worker を専用 QThread で起動する (テストは本メソッドを差し替えて同期実行する)。"""
        thread = QThread()
        self._export_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()

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

    def shutdown(self) -> None:
        """実行中のエクスポート thread を停止する (ウィンドウ閉鎖時に呼ぶ、#961 P2)。

        埋め込みウィジェットの ``closeEvent`` はウィンドウ閉鎖で必ずしも発火しないため、
        MainWindow の closeEvent からも本メソッドを呼んで thread の取り残しを防ぐ。
        詳細ペインの refinement worker も停止する (タブ単独クローズ経路対策、#931 P2)。
        """
        self._teardown_export_thread()
        self._selected_image_details_widget.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:
        """タブ単体クローズ時にエクスポート thread を後始末する (#961 P2)。"""
        self.shutdown()
        super().closeEvent(event)

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
