"""検索タブ (ワークベンチ) の専用ウィジェット (Epic #867 / #869)。

MainWindow の検索タブ (tabWorkspace) のオーケストレーション —
データセット選択 / DB 検索 / サムネ表示 / プレビュー・詳細編集 / 3 ペイン splitter /
ステージング・エクスポート導線 — を ``SearchTabWidget`` へ集約する。MainWindow には
worker dispatch・PipelineControlService 所有・staging fan-out・タブ間遷移・settings 等の
横断 glue だけを残す。

本実装 (Track A) は ``SearchTab.ui`` を ``setupUi`` で展開して
``class SearchTabWidget(QWidget, Ui_SearchTab)`` を構成し、各 widget の DI 配線・
検索/サムネ pipeline 配線・splitter (#865 orientation 再適用) をタブ内に閉じ込める。
**下記の公開シグネチャ (コンストラクタ DI / Signal / スロット / プロパティ) は
凍結契約であり変更しない**。MainWindow rewire (Track B) はこの契約に対してコードを書く。

== 凍結契約 ==
- コンストラクタ: ``SearchTabWidget(*, service_container, db_manager,
  dataset_state_manager, staging_state_manager, worker_service, parent=None)``
- Signal (タブ → MainWindow glue):
    - ``stage_to_annotation_requested = Signal(list)`` — 選択画像をアノテへステージ
    - ``status_message = Signal(str)`` — statusBar 表示要求 (quick tag 書込結果など、#896)
    - ``export_requested = Signal()`` — エクスポートタブ遷移
    - ``dataset_selection_requested = Signal()`` — データセット選択+登録 dispatch
    - ``settings_requested = Signal()`` — 設定ダイアログ
    - ``search_error_occurred = Signal(str)`` — pipeline エラー (error_notification 更新用)
- スロット (MainWindow → タブ):
    - ``refresh() -> None`` — タブ表示時の再計算
    - ``set_db_info(text: str, tooltip: str = "") -> None`` — DB 状態バー更新
    - ``set_dataset_path(path: str) -> None`` — データセットパス表示更新
    - ``set_export_target_count(count: int) -> None`` — エクスポート対象件数ラベル
    - ``load_images_from_db() -> None`` — 起動時/再読込時の検索開始
    - ``toggle_filter_panel() -> None`` / ``toggle_preview_panel() -> None`` —
      menubar action からのパネル開閉 (splitter サイズ退避/復元はタブが所有)
- プロパティ (タブ内配線・テスト・PipelineControlService 注入用):
    - ``filter_search_panel`` / ``thumbnail_selector`` / ``image_preview_widget``
      / ``selected_image_details_widget`` / ``main_splitter``
"""

from typing import Any

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtWidgets import QSplitter, QWidget
from sqlalchemy.exc import SQLAlchemyError

from ...database.db_manager import ImageDatabaseManager
from ...filesystem import FileSystemManager
from ...services.model_selection_service import ModelSelectionService
from ...services.refinement_service import RefinementService
from ...services.service_container import ServiceContainer
from ...utils.log import logger
from ..designer.SearchTab_ui import Ui_SearchTab
from ..message_box import show_critical
from ..services.crop_dialog_launcher import CropDialogLauncher
from ..services.crop_relation_service import CropRelationService
from ..services.image_db_write_service import ImageDBWriteService
from ..services.search_filter_service import SearchFilterService
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.quick_tag_dialog import QuickTagDialog
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail_selector_widget import ThumbnailSelectorWidget


class SearchTabWidget(QWidget, Ui_SearchTab):
    """検索タブのルートウィジェット (Wireframes v11 Frame 1 · Search / Workbench)。

    ``SearchTab.ui`` を ``setupUi`` で展開し、データセット選択バー・DB 状態バー・
    3 ペイン work area (フィルタ / サムネ / プレビュー・詳細) ・アクションツールバーを
    常設する。各 widget の状態管理接続・検索フィルタ統合・rating/score 編集・パネル
    トグルをタブ内に閉じ込め、横断 glue は Signal で MainWindow へ委譲する。
    """

    stage_to_annotation_requested = Signal(list)
    status_message = Signal(str)  # statusBar 表示要求 (quick tag 書込結果など、#896)
    export_requested = Signal()
    dataset_selection_requested = Signal()
    settings_requested = Signal()
    search_error_occurred = Signal(str)

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        dataset_state_manager: DatasetStateManager | None,
        staging_state_manager: StagingStateManager | None,
        worker_service: WorkerService | None,
        parent: QWidget | None = None,
    ) -> None:
        """検索タブを初期化する。

        Args:
            service_container: SearchFilterService 生成 / favorite filters / merged reader。
            db_manager: rating/score 書込・詳細取得。
            dataset_state_manager: 選択 SSoT (thumbnail/preview/details 接続)。
            staging_state_manager: エクスポート対象・ステージング件数。
            worker_service: 検索 → サムネ pipeline driver。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._dataset_state_manager = dataset_state_manager
        self._staging_state_manager = staging_state_manager
        self._worker_service = worker_service

        self.setupUi(self)

        # rating/score 書込サービス (詳細パネル編集に使う)。_setup_image_db_write_service で生成。
        self._image_db_write_service: ImageDBWriteService | None = None
        # クロップ導線 (#1346)。_setup_crop_integration で生成 (db_manager 未注入なら None)。
        self._crop_dialog_launcher: CropDialogLauncher | None = None
        # パネルトグル時の splitter サイズ退避領域 (#865 とは別の表示/非表示制御)
        self._main_splitter_sizes_before_filter_hide: list[int] | None = None
        self._main_splitter_sizes_before_preview_hide: list[int] | None = None

        # .ui の object 名で公開される widget を内部参照へエイリアスする
        self._filter_search_panel: FilterSearchPanel = self.filterSearchPanel
        self._thumbnail_selector: ThumbnailSelectorWidget = self.thumbnailSelectorWidget
        self._image_preview_widget: ImagePreviewWidget = self.imagePreviewWidget
        self._selected_image_details_widget: SelectedImageDetailsWidget = self.selectedImageDetailsWidget
        self._main_splitter: QSplitter = self.splitterMainWorkArea

        # 各 widget の状態管理接続・検索フィルタ統合・編集サービス・Signal 配線
        self._setup_widgets()
        self._setup_search_filter_integration()
        self._setup_image_db_write_service()
        self._setup_crop_integration()
        self._connect_thumbnail_preview_signals()
        self._connect_details_widget_signals()
        self._connect_dataset_state_signals()
        self._connect_entry_signals()

        # #865: .ui を SSoT とする splitter orientation を初期適用する
        self.apply_designed_splitter_orientations()

        # DB 状態バーの初期表示
        self._update_database_status_label()
        logger.info("✅ 検索タブ (SearchTabWidget) 初期化完了")

    # -- 初期化: widget 状態管理接続 ------------------------------------------

    def _setup_widgets(self) -> None:
        """サムネ/プレビュー/詳細/splitter の状態管理接続と初期サイズを設定する。"""
        dsm = self._dataset_state_manager

        # サムネイルセレクタ: 選択 SSoT を注入
        if dsm is not None:
            self._thumbnail_selector.set_dataset_state(dsm)
            logger.debug("ThumbnailSelectorWidget DatasetStateManager接続完了")
        else:
            logger.warning("DatasetStateManager未初期化 - ThumbnailSelectorWidget接続をスキップ")

        # 検索を介さない一覧更新 (クロップ保存直後など、#1346) でもサムネイルを要求できるよう、
        # 検索完了を待たずに WorkerService を注入する。
        if self._worker_service is not None:
            self._thumbnail_selector.set_worker_service(self._worker_service)
            logger.debug("ThumbnailSelectorWidget WorkerService接続完了")

        # 画像プレビュー: データシグナル接続
        if dsm is not None:
            self._image_preview_widget.connect_to_data_signals(dsm)
            logger.debug("ImagePreviewWidget データシグナル接続完了")

        # 選択画像詳細: DB Manager / MergedTagReader / 選択シグナル接続
        if self._db_manager is not None:
            self._selected_image_details_widget.set_db_manager(self._db_manager)
        merged_reader = self._service_container.db_manager.annotation_repo.get_merged_reader()
        self._selected_image_details_widget.set_merged_reader(merged_reader)
        # refinement リコメンド (#931): RefinementService を注入。ignore 保存先は注入された
        # db_manager の session factory に追従させ、「表示 DB」と「ignore 保存 DB」の乖離を防ぐ
        # (#978)。db_manager 未注入時のみ container のアクティブ DB へフォールバックする。
        # tagdb 初期化失敗 (base DB 欠損/オフライン初回起動等) でもタブ全体を巻き込まず、
        # merged-reader と同様に degrade する (refinement は付加機能のため非致命)。
        try:
            self._selected_image_details_widget.set_refinement_service(self._resolve_refinement_service())
        except Exception as e:
            # tagdb 不可時の graceful degradation (#931): refinement は付加機能のため、
            # どの初期化エラーでもタブを生かす意図で広く捕捉する。
            logger.warning(f"RefinementService 配線をスキップ (tagdb 不可?): {e}")
        # tagdb userdb 系書き込み (#989): 翻訳追加 / type 補正。tagdb 不可でも degrade する。
        try:
            self._selected_image_details_widget.set_tag_management_service(
                self._service_container.tag_management_service
            )
        except Exception as e:
            logger.warning(f"TagManagementService 配線をスキップ (tagdb 不可?): {e}")
        if dsm is not None:
            self._selected_image_details_widget.connect_to_dataset_state_manager(dsm)
            logger.debug("SelectedImageDetailsWidget DatasetStateManager接続完了")

        # 3 ペイン work area (左:フィルタ 中:サムネ 右:プレビュー・詳細) の初期比率
        self._main_splitter.setSizes([216, 504, 480])
        self._main_splitter.setStretchFactor(0, 18)
        self._main_splitter.setStretchFactor(1, 42)
        self._main_splitter.setStretchFactor(2, 40)

        # 右カラム内のプレビュー/詳細スプリッター (上:プレビュー 下:詳細)
        self.splitterPreviewDetails.setSizes([550, 450])
        self.splitterPreviewDetails.setStretchFactor(0, 1)
        self.splitterPreviewDetails.setStretchFactor(1, 1)
        logger.debug("検索タブ splitter 初期化完了")

    def _resolve_refinement_service(self) -> RefinementService:
        """注入された db_manager の DB に ignore を保存する RefinementService を解決する (#978)。

        タブに注入された db_manager の session factory へ ignore 保存を追従させる。
        db_manager 未注入時のみ container のアクティブ DB プロパティへフォールバックする。

        Returns:
            ignore 保存先が表示 DB と一致した RefinementService。
        """
        if self._db_manager is not None:
            return self._service_container.create_refinement_service(
                self._db_manager.image_repo.session_factory
            )
        return self._service_container.refinement_service

    def _setup_search_filter_integration(self) -> None:
        """filterSearchPanel に SearchFilterService / WorkerService / お気に入りフィルタを注入する。

        検索機能は必須のため、SearchFilterService 生成に失敗した場合は例外を送出して
        タブ構築を中止する (MainWindow 側で致命的エラーとして扱われる)。
        """
        search_filter_service = self._create_search_filter_service()
        self._filter_search_panel.set_search_filter_service(search_filter_service)

        if self._worker_service is not None:
            self._filter_search_panel.set_worker_service(self._worker_service)
            logger.info("✅ SearchFilterService統合完了 (WorkerService統合済み)")
        else:
            logger.info("✅ SearchFilterService統合完了 (同期検索モード)")

        favorite_filters_service = self._service_container.favorite_filters_service
        self._filter_search_panel.set_favorite_filters_service(favorite_filters_service)
        logger.debug("FavoriteFiltersService統合完了")

    def _create_search_filter_service(self) -> SearchFilterService:
        """SearchFilterService を生成する (ServiceContainer 経由でモデル選択を構築)。

        Returns:
            設定済みの SearchFilterService インスタンス。

        Raises:
            ValueError: db_manager が未初期化、または生成に失敗した場合。
        """
        if self._db_manager is None:
            raise ValueError("ImageDatabaseManager is required but not available")

        repo = self._service_container.db_manager.model_repo
        model_selection_service = ModelSelectionService.create(db_repository=repo)
        return SearchFilterService(
            db_manager=self._db_manager, model_selection_service=model_selection_service
        )

    def _setup_image_db_write_service(self) -> None:
        """ImageDBWriteService を生成し、詳細パネルの編集シグナルを接続する。

        SelectedImageDetailsWidget が編集シグナル (rating_updated / score_updated /
        save_requested) を持たない (閲覧専用) 構成では接続をスキップする。
        """
        if self._db_manager is None:
            logger.warning("db_manager未初期化 - ImageDBWriteService設定をスキップ")
            return

        self._image_db_write_service = ImageDBWriteService(self._db_manager)
        widget = self._selected_image_details_widget
        if (
            hasattr(widget, "rating_updated")
            and hasattr(widget, "score_updated")
            and hasattr(widget, "save_requested")
        ):
            widget.rating_updated.connect(self._on_rating_update_requested)
            widget.score_updated.connect(self._on_score_update_requested)
            widget.save_requested.connect(self._on_save_requested)
            logger.debug("ImageDBWriteService 編集シグナル接続完了")
        else:
            logger.debug("SelectedImageDetailsWidget は閲覧専用 - 編集シグナル未接続")

    # -- 初期化: Signal 配線 ---------------------------------------------------

    def shutdown(self) -> None:
        """タブが持つ worker を停止する (ウィンドウ閉鎖時、MainWindow.closeEvent から呼ぶ)。

        クロップダイアログのタグ翻訳 worker (#1355) と詳細ペインの worker を止め、
        QThread がウィジェットより長生きして Qt teardown 警告になるのを防ぐ。
        """
        if self._crop_dialog_launcher is not None:
            self._crop_dialog_launcher.shutdown()
        self._selected_image_details_widget.shutdown()

    def _setup_crop_integration(self) -> None:
        """クロップ導線 (#1346) を配線する。

        一覧の右クリックとプレビューのボタンは ``crop_requested(image_id)`` を上げるだけで、
        ダイアログ生成・保存・結果の中継は :class:`CropDialogLauncher` が担う。詳細カラムの
        関連画像セクションには :class:`CropRelationService` を注入する。
        """
        if self._db_manager is None:
            logger.warning("db_manager 未初期化 - クロップ導線をスキップ")
            return

        # 登録経路 (WorkerService / DatasetController) と同じ FileSystemManager を共有する。
        # ServiceContainer 側の FSM は GUI では初期化されない (set_active_project は CLI 経路のみ)。
        worker_fsm = getattr(self._worker_service, "fsm", None)
        fsm = (
            worker_fsm
            if isinstance(worker_fsm, FileSystemManager)
            else self._service_container.file_system_manager
        )
        # 候補/採用タグの翻訳表示 (#1355)。get_merged_reader は tagdb 不可なら None を返す
        # (詳細カラムと同じ graceful degradation)。
        merged_reader = self._db_manager.annotation_repo.get_merged_reader()
        self._crop_dialog_launcher = CropDialogLauncher(
            db_manager=self._db_manager,
            fsm=fsm,
            merged_reader=merged_reader,
            parent=self,
        )
        self._crop_dialog_launcher.crop_saved.connect(self._on_crop_saved)

        self._thumbnail_selector.set_crop_action_enabled(True)
        self._thumbnail_selector.crop_requested.connect(self._on_crop_requested)
        self._image_preview_widget.set_crop_action_visible(True)
        self._image_preview_widget.crop_requested.connect(self._on_crop_requested)

        self._selected_image_details_widget.set_crop_relation_service(CropRelationService(self._db_manager))
        self._selected_image_details_widget.related_image_activated.connect(
            self._on_related_image_activated
        )
        logger.debug("クロップ導線 (一覧/プレビュー → CropDialogLauncher) 配線完了")

    @Slot(int)
    def _on_crop_requested(self, image_id: int) -> None:
        """一覧 / プレビューからのクロップ要求でダイアログを開く。

        Args:
            image_id: クロップ元となる画像 ID (子画像を指定すれば孫を作る)。
        """
        if self._crop_dialog_launcher is None:
            logger.warning("クロップ導線未配線 - クロップ要求を無視")
            return
        self._crop_dialog_launcher.open_for_image(image_id, parent=self)

    @Slot(int, int)
    def _on_crop_saved(self, parent_image_id: int, child_image_id: int) -> None:
        """クロップ保存成功を一覧・詳細へ反映する。

        再検索 (``load_images_from_db``) は使わない。フィルタ未指定だと検索自体が
        スキップされ、一覧に子画像が載らないため (Codex P2)。DB から子のメタデータを
        引いて一覧の画像集合へ直接追加し、サムネイルの現在ページを読み直す。

        Args:
            parent_image_id: 切り出し元となった画像 ID。
            child_image_id: 作成されたクロップ画像 ID。
        """
        dsm = self._dataset_state_manager
        if dsm is None:
            # 選択 SSoT が無いタブ構成でも、詳細カラムの親子表示だけは追従させる
            self._selected_image_details_widget.refresh_related_images()
        else:
            metadata = self._fetch_child_metadata(child_image_id)
            if metadata is not None:
                dsm.add_image(metadata)
                self._thumbnail_selector.refresh_current_page()
            dsm.set_current_image(child_image_id)
        self.status_message.emit(
            f"クロップ画像を作成しました (元: {parent_image_id} → 新規: {child_image_id})"
        )

    def _fetch_child_metadata(self, child_image_id: int) -> dict[str, Any] | None:
        """一覧へ載せるためのクロップ画像メタデータを取得する。

        Args:
            child_image_id: 作成されたクロップ画像 ID。

        Returns:
            画像メタデータ。取得できなければ None (一覧追加をスキップする)。
        """
        if self._db_manager is None:
            return None
        try:
            metadata: dict[str, Any] | None = self._db_manager.get_image_metadata(child_image_id)
        except SQLAlchemyError:
            logger.opt(exception=True).error(
                f"クロップ画像のメタデータ取得に失敗しました: image_id={child_image_id}"
            )
            return None
        if metadata is None:
            logger.warning(f"クロップ画像のメタデータが見つかりません: image_id={child_image_id}")
        return metadata

    @Slot(int)
    def _on_related_image_activated(self, image_id: int) -> None:
        """関連画像セクションの行クリックで対象画像へ遷移する。

        Args:
            image_id: 遷移先の画像 ID。
        """
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager 未初期化 - 関連画像への遷移をスキップ")
            return
        self._dataset_state_manager.set_current_image(image_id)

    def _connect_thumbnail_preview_signals(self) -> None:
        """サムネイル → プレビュー間の接続と、ステージ/クイックタグの上方 emit を行う。"""
        self._thumbnail_selector.image_selected.connect(self._image_preview_widget.load_image)
        if hasattr(self._thumbnail_selector, "stage_selected_requested"):
            self._thumbnail_selector.stage_selected_requested.connect(self.stage_to_annotation_requested)
        if hasattr(self._thumbnail_selector, "quick_tag_requested"):
            # #896: クイックタグはタブ内で完結 (ダイアログ起動 + 書込)。MainWindow へは bubble しない。
            self._thumbnail_selector.quick_tag_requested.connect(self._show_quick_tag_dialog)
        logger.debug("サムネイル → プレビュー接続完了")

    # -- クイックタグ書込 (#896: MainWindow から移送) -------------------------

    def _show_quick_tag_dialog(self, image_ids: list[int]) -> None:
        """サムネ右クリックのクイックタグダイアログを表示する。

        Args:
            image_ids: タグを追加する画像 ID のリスト。
        """
        if not image_ids:
            logger.warning("Quick tag dialog requested with empty image list")
            return

        dialog = QuickTagDialog(image_ids, parent=self)
        dialog.tag_add_requested.connect(self._handle_quick_tag_add)
        dialog.exec()

    def _handle_quick_tag_add(self, image_ids: list[int], tag: str) -> None:
        """クイックタグダイアログからのタグ追加要求を処理する。

        書込は rating/score 編集と同じ ``ImageDBWriteService`` を再利用し、成功時は
        ``dataset_state_manager`` のキャッシュを更新する (#896, 書込共有口=案A)。

        Args:
            image_ids: 対象画像の ID リスト。
            tag: 追加するタグ (正規化済み)。
        """
        logger.info(f"Quick tag add: tag='{tag}' for {len(image_ids)} images")

        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService not initialized")
            success = False
        else:
            success = self._image_db_write_service.add_tag_batch(image_ids, tag)
            if success and self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_images(image_ids)

        if success:
            self.status_message.emit(f"クイックタグ '{tag}' を追加しました")
            logger.info(f"Quick tag add completed: tag='{tag}', {len(image_ids)} images updated")
        else:
            show_critical(self, "タグ追加失敗", f"クイックタグ '{tag}' の追加に失敗しました。")
            logger.error(f"Failed quick tag add: tag='{tag}', image_count={len(image_ids)}")

    def _connect_details_widget_signals(self) -> None:
        """SelectedImageDetailsWidget の Rating/Score シグナルをタブ内ハンドラへ接続する。"""
        widget = self._selected_image_details_widget
        widget.rating_changed.connect(self._handle_rating_changed)
        widget.score_changed.connect(self._handle_score_changed)
        widget.batch_rating_changed.connect(self._handle_batch_rating_changed)
        widget.batch_score_changed.connect(self._handle_batch_score_changed)
        logger.debug("SelectedImageDetailsWidget シグナル接続完了")

    def _connect_dataset_state_signals(self) -> None:
        """DatasetStateManager の選択変更を rating/score バッチ表示更新へ接続する。"""
        if self._dataset_state_manager is None:
            return
        self._dataset_state_manager.selection_changed.connect(self._handle_selection_changed_for_rating)
        logger.debug("DatasetStateManager selection_changed シグナル接続完了")

    def _connect_entry_signals(self) -> None:
        """データセット選択 / 設定 / ステージ / エクスポートの入口を上方 Signal へ橋渡しする。"""
        self.pushButtonSelectDataset.clicked.connect(self._on_select_dataset_clicked)
        self.pushButtonSettings.clicked.connect(self._on_settings_clicked)
        self.pushButtonStageToBatchTag.clicked.connect(self._on_stage_to_annotation_clicked)
        self.btnExportData.clicked.connect(self._on_export_clicked)
        logger.debug("検索タブ 入口 Signal 接続完了")

    @Slot()
    def _on_select_dataset_clicked(self) -> None:
        """データセット選択ボタン → MainWindow へ選択+登録 dispatch を要求する。"""
        self.dataset_selection_requested.emit()

    @Slot()
    def _on_settings_clicked(self) -> None:
        """設定ボタン → MainWindow へ設定ダイアログ表示を要求する。"""
        self.settings_requested.emit()

    @Slot()
    def _on_stage_to_annotation_clicked(self) -> None:
        """「選択をステージングへ」 → 現在選択中の画像 ID を載せて上方 emit する。"""
        image_ids = (
            list(self._dataset_state_manager.selected_image_ids)
            if self._dataset_state_manager is not None
            else []
        )
        self.stage_to_annotation_requested.emit(image_ids)

    @Slot()
    def _on_export_clicked(self) -> None:
        """エクスポートボタン → MainWindow へエクスポートタブ遷移を要求する。"""
        self.export_requested.emit()

    # -- プロパティ (タブ内配線・テスト・pipeline 注入用) ----------------------

    @property
    def filter_search_panel(self) -> FilterSearchPanel:
        """フィルタ検索パネルを返す。"""
        return self._filter_search_panel

    @property
    def thumbnail_selector(self) -> ThumbnailSelectorWidget:
        """サムネイルセレクタを返す (PipelineControlService 注入用)。"""
        return self._thumbnail_selector

    @property
    def image_preview_widget(self) -> ImagePreviewWidget:
        """画像プレビューを返す。"""
        return self._image_preview_widget

    @property
    def selected_image_details_widget(self) -> SelectedImageDetailsWidget:
        """選択画像の詳細 (rating/score 編集) を返す。"""
        return self._selected_image_details_widget

    @property
    def main_splitter(self) -> QSplitter:
        """3 ペイン横 splitter を返す (QSettings 復元・パネルトグル用)。"""
        return self._main_splitter

    @property
    def preview_splitter(self) -> QSplitter:
        """プレビュー/詳細の縦 splitter を返す (QSettings 保存・復元用)。"""
        return self.splitterPreviewDetails

    # -- #865: splitter orientation 再適用 ------------------------------------

    def apply_designed_splitter_orientations(self) -> None:
        """splitter の orientation を .ui 設計値へ再適用する (#865)。

        ``QSplitter.restoreState()`` は sizes だけでなく orientation も復元するため、
        QSettings に保存された旧レイアウトの向きが新レイアウトを巻き戻す回帰がある。
        Track B が ``main_splitter`` 経由で restoreState を呼んだ後に本メソッドを呼ぶと、
        .ui を SSoT とする向き (work area=Horizontal / preview-details=Vertical) を
        確実に復旧できる。
        """
        self._main_splitter.setOrientation(Qt.Orientation.Horizontal)
        self.splitterPreviewDetails.setOrientation(Qt.Orientation.Vertical)

    # -- #896: splitter サイズ状態の自治 (QSettings save/restore) --------------

    def save_layout_state(self, settings: QSettings) -> None:
        """splitter サイズ状態を QSettings に保存する (#869: 両 splitter 必須)。

        Args:
            settings: 書き込み先 QSettings。
        """
        settings.setValue("splitter/main_work_area", self._main_splitter.saveState())
        settings.setValue("splitter/preview_details", self.splitterPreviewDetails.saveState())

    def restore_layout_state(self, settings: QSettings) -> bool:
        """splitter サイズ状態を QSettings から復元する。

        ``QSplitter.restoreState()`` は orientation も復元するため、復元後に
        ``apply_designed_splitter_orientations()`` で .ui 設計値へ戻す (#865)。

        Args:
            settings: 読み出し元 QSettings。

        Returns:
            いずれかの splitter を復元した場合 True。
        """
        restored = False
        main_state = settings.value("splitter/main_work_area")
        if main_state:
            self._main_splitter.restoreState(main_state)
            restored = True
        preview_state = settings.value("splitter/preview_details")
        if preview_state:
            self.splitterPreviewDetails.restoreState(preview_state)
            restored = True
        if restored:
            self.apply_designed_splitter_orientations()
        return restored

    # -- スロット (MainWindow → タブ) ----------------------------------------

    @Slot()
    def refresh(self) -> None:
        """タブ表示時の再計算 (results/errors と同型)。"""
        self._update_database_status_label()

    @Slot(str, str)
    def set_db_info(self, text: str, tooltip: str = "") -> None:
        """DB 状態バーのテキストとツールチップを更新する。"""
        self.labelDbInfo.setText(text)
        self.labelDbInfo.setToolTip(tooltip)

    @Slot(str)
    def set_dataset_path(self, path: str) -> None:
        """データセットパス表示を更新する。"""
        self.lineEditDatasetPath.setText(path)

    @Slot(int)
    def set_export_target_count(self, count: int) -> None:
        """エクスポート対象件数ラベルを更新する (staging fan-out から駆動)。"""
        self.labelExportTarget.setText(f"エクスポート対象: {count} 枚")

    @Slot()
    def load_images_from_db(self) -> None:
        """起動時/再読込時に現在のフィルタ条件で検索を開始する。

        検索は filterSearchPanel が SSoT として WorkerService 経由で実行し、
        その結果は worker イベント → MainWindow の PipelineControlService 経由で
        サムネイルへ反映される (タブは pipeline を所有しない)。
        """
        # 検索トリガは filterSearchPanel が一手に持つ (条件構築は UI 状態に依存するため)。
        if hasattr(self._filter_search_panel, "_on_search_requested"):
            self._filter_search_panel._on_search_requested()
        else:
            logger.warning("filterSearchPanel に検索トリガが見つかりません - 検索をスキップ")

    @Slot()
    def toggle_filter_panel(self) -> None:
        """フィルタパネルの表示/非表示を切り替える (splitter サイズ退避/復元)。"""
        panel = self.frameFilterSearchPanel
        # isVisible() は祖先の表示状態に影響されるため、widget 自身の hide 状態
        # (isHidden) を基準にトグルする (タブ未表示時でも正しく反転する)。
        new_visible = panel.isHidden()
        if not new_visible:
            self._main_splitter_sizes_before_filter_hide = self._main_splitter.sizes()
        panel.setVisible(new_visible)
        if new_visible and self._main_splitter_sizes_before_filter_hide is not None:
            self._main_splitter.setSizes(self._main_splitter_sizes_before_filter_hide)
        logger.debug(f"フィルタパネル表示: {new_visible}")

    @Slot()
    def toggle_preview_panel(self) -> None:
        """プレビュー/詳細パネルの表示/非表示を切り替える (splitter サイズ退避/復元)。"""
        panel = self.framePreviewDetailPanel
        # isVisible() は祖先の表示状態に影響されるため、widget 自身の hide 状態
        # (isHidden) を基準にトグルする (タブ未表示時でも正しく反転する)。
        new_visible = panel.isHidden()
        if not new_visible:
            self._main_splitter_sizes_before_preview_hide = self._main_splitter.sizes()
        panel.setVisible(new_visible)
        if new_visible and self._main_splitter_sizes_before_preview_hide is not None:
            self._main_splitter.setSizes(self._main_splitter_sizes_before_preview_hide)
        logger.debug(f"プレビューパネル表示: {new_visible}")

    # -- DB 状態バー ----------------------------------------------------------

    def _update_database_status_label(self) -> None:
        """DB 状態バーを現在のプロジェクトディレクトリに合わせて更新する。"""
        from ...database.db_core import IMG_DB_PATH, get_current_project_root, get_user_tag_db_path

        try:
            project_root = get_current_project_root().resolve()
            image_db_path = IMG_DB_PATH.resolve()
            tooltip_lines = [f"画像DB: {image_db_path}"]
            tag_db_path = get_user_tag_db_path()
            if tag_db_path:
                tooltip_lines.append(f"タグDB: {tag_db_path.resolve()}")
            self.set_db_info(f"データベース: {project_root}", "\n".join(tooltip_lines))
        except (OSError, RuntimeError) as e:
            logger.warning(f"データベース表示の更新に失敗: {e}")

    # -- rating/score 編集ハンドラ -------------------------------------------

    def _on_rating_update_requested(self, image_id: int, rating: str) -> None:
        """詳細パネルの Rating 更新シグナルハンドラ (ImageDBWriteService 経由)。"""
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_rating(image_id, rating):
            logger.debug(f"Rating更新: image_id={image_id}, rating={rating}")
        else:
            logger.error(f"Rating更新失敗: image_id={image_id}, rating={rating}")

    def _on_score_update_requested(self, image_id: int, score: int) -> None:
        """詳細パネルの Score 更新シグナルハンドラ (ImageDBWriteService 経由)。"""
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_score(image_id, score):
            logger.debug(f"Score更新: image_id={image_id}, score={score}")
        else:
            logger.error(f"Score更新失敗: image_id={image_id}, score={score}")

    def _on_save_requested(self, save_data: dict[str, Any]) -> None:
        """詳細パネルの保存要求 (rating + score の一括書込) を処理する。"""
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        image_id = save_data.get("image_id")
        if image_id is None:
            logger.warning("保存要求に image_id がありません")
            return
        rating = save_data.get("rating")
        score = save_data.get("score")
        if rating:
            self._image_db_write_service.update_rating(image_id, rating)
        if score is not None:
            self._image_db_write_service.update_score(image_id, score)
        logger.debug(f"保存完了: image_id={image_id}, rating={rating}, score={score}")

    def _handle_rating_changed(self, image_id: int, rating: str) -> None:
        """単一 Rating 変更を書き込み、成功時にキャッシュを更新する。"""
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_rating(image_id, rating):
            if self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_image(image_id)
            logger.debug(f"Rating更新成功: image_id={image_id}, rating={rating}")
        else:
            logger.error(f"Rating更新失敗: image_id={image_id}, rating={rating}")

    def _handle_score_changed(self, image_id: int, score: int) -> None:
        """単一 Score 変更を書き込み、成功時にキャッシュを更新する。"""
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_score(image_id, score):
            if self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_image(image_id)
            logger.debug(f"Score更新成功: image_id={image_id}, score={score}")
        else:
            logger.error(f"Score更新失敗: image_id={image_id}, score={score}")

    def _handle_batch_rating_changed(self, image_ids: list[int], rating: str) -> None:
        """複数選択への Rating バッチ変更を書き込み、成功時にキャッシュを一括更新する。"""
        logger.info(f"バッチRating変更: {len(image_ids)}件, rating='{rating}'")
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_rating_batch(image_ids, rating):
            if self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_images(image_ids)
            logger.info("バッチRating更新完了")

    def _handle_batch_score_changed(self, image_ids: list[int], score: int) -> None:
        """複数選択への Score バッチ変更を書き込み、成功時にキャッシュを一括更新する。"""
        logger.info(f"バッチScore変更: {len(image_ids)}件, score={score}")
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService未初期化")
            return
        if self._image_db_write_service.update_score_batch(image_ids, score):
            if self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_images(image_ids)
            logger.info("バッチScore更新完了")

    def _handle_selection_changed_for_rating(self, image_ids: list[int]) -> None:
        """選択変更に応じて詳細パネルの rating/score 表示を更新する。

        0 件: 表示クリア / 1 件: 単一表示 / 2 件以上: バッチ表示。

        Args:
            image_ids: 選択画像 ID リスト。
        """
        widget = self._selected_image_details_widget
        if not hasattr(widget, "_rating_score_widget"):
            return
        rating_widget = widget._rating_score_widget

        if len(image_ids) == 0:
            # 詳細パネルの表示ライフサイクルは current_image_data_changed 経由の単一画像選択
            # (SelectedImageDetailsWidget._on_image_data_received) が SSoT で、バッチ選択
            # (selected_image_ids) とは独立している。selection_changed([]) が来ても詳細ウィジェットが
            # 画像を表示中 (widget.current_image_id is not None) なら full clear しない (#1222):
            # _clear_display は current_image_id=None にし、直後に完了する tag_metadata /
            # refinement worker の結果を image_id 照合で破棄させ、タグ / キャプションが空のまま
            # 復旧しなくなる。
            #
            # 判定は DSM の _all_images ではなく詳細ウィジェット自身の current_image_id で行う:
            # set_current_image の cache-miss 経路 (登録ビューからの表示要求等) で DSM キャッシュ外の
            # 画像を DB 直読みして表示している場合、DSM.get_image_by_id は None を返すが表示は有効で、
            # ここで消すと表示中画像を誤ってクリアしてしまう (#1228 Codex P2)。詳細表示の全クリアは
            # current_image_data_changed({}) 経由 (dataset reset 等) が担当する。
            if widget.current_image_id is not None:
                # rating エディタが直前のバッチ選択 (populate_from_selection) で batch モードの
                # ままだと、deselect 後に Save すると stale な複数選択へバッチ書き込みしてしまう
                # (#1228 Codex P2)。表示中画像の詳細から rating を single モードへ戻す
                # (populate_from_image_data が _is_batch_mode を False にする)。current_details は
                # 表示時に設定済みで、DSM キャッシュ外から DB 直読みした表示画像でも有効。
                details = widget.current_details
                if details is not None:
                    # dict 形状は SelectedImageDetailsWidget._update_details_display と揃える。
                    rating_widget.populate_from_image_data(
                        {
                            "id": details.image_id,
                            "rating": details.manual_rating_value or "----",
                            "score_value": details.manual_score_value,
                            "ai_rating": details.ai_rating_value or "----",
                            "ai_score_value": details.ai_score_value,
                        }
                    )
                logger.debug(
                    "選択リスト空だが詳細パネルが画像表示中 - full clear 抑止 + rating 単一化 (#1222/#1228)"
                )
                return
            widget._clear_display()
            logger.debug("選択なし・表示画像なし - 詳細表示をクリア")
        elif len(image_ids) == 1:
            if self._dataset_state_manager is not None:
                image_data = self._dataset_state_manager.get_image_by_id(image_ids[0])
                if image_data:
                    rating_widget.populate_from_image_data(image_data)
                    logger.debug(f"単一選択: rating widget更新 image_id={image_ids[0]}")
        else:
            if self._db_manager is not None:
                rating_widget.populate_from_selection(image_ids, self._db_manager)
                logger.debug(f"バッチモード: {len(image_ids)}件")
