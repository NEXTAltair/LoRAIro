# src/lorairo/gui/window/main_window.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow

from ...database.db_manager import ImageDatabaseManager
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.model_selection_service import ModelSelectionService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.MainWindow_ui import Ui_MainWindow
from ..services.search_filter_service import SearchFilterService
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

    # シグナル
    dataset_loaded = Signal(str)  # dataset_path
    database_registration_completed = Signal(int)  # registered_count

    # サービス属性の型定義（初期化で設定）
    config_service: ConfigurationService | None
    file_system_manager: FileSystemManager | None
    db_manager: ImageDatabaseManager | None
    worker_service: WorkerService | None
    dataset_state_manager: DatasetStateManager | None

    # ウィジェット属性の型定義（初期化で設定）
    filter_search_panel: FilterSearchPanel | None
    thumbnail_selector: ThumbnailSelectorWidget | None
    image_preview_widget: ImagePreviewWidget | None
    selected_image_details_widget: SelectedImageDetailsWidget | None

    def __init__(self, parent=None):
        super().__init__(parent)

        # 初期化失敗フラグ
        self._initialization_failed = False
        self._initialization_error: str | None = None

        try:
            # Phase 1: 基本UI設定（最優先）
            logger.info("MainWindow初期化開始 - Phase 1: UI設定")
            self.setupUi(self)
            logger.info("UI設定完了")

            # Phase 2: サービス初期化（例外を個別にキャッチ）
            logger.info("Phase 2: サービス初期化開始")
            self._initialize_services()

            # Phase 3: UI カスタマイズ（サービス依存）
            logger.info("Phase 3: UI カスタマイズ開始")
            self.setup_custom_widgets()

            # Phase 3.5: サービス統合（新規）
            logger.info("Phase 3.5: SearchFilterService統合開始")
            self._setup_search_filter_integration()

            # Phase 4: イベント接続（最終段階）
            logger.info("Phase 4: イベント接続開始")
            self._connect_events()

            logger.info("MainWindow初期化完了")

        except Exception as e:
            self._initialization_failed = True
            self._initialization_error = f"初期化エラー: {e}"
            logger.error(f"MainWindow初期化失敗: {e}", exc_info=True)

            # 基本的なUI表示は継続（エラー状態でも表示可能にする）
            try:
                self.setupUi(self)
                logger.info("エラー状態でもUI表示を継続")
            except Exception as ui_error:
                logger.error(f"UI設定も失敗: {ui_error}")
                raise  # UI設定に失敗した場合は致命的エラー

    def _initialize_services(self) -> None:
        """サービスを段階的に初期化し、例外処理を個別に行う"""

        # ConfigurationService初期化
        try:
            logger.info("  - ConfigurationService初期化中...")
            self.config_service = ConfigurationService()
            logger.info("  ✅ ConfigurationService初期化成功")
        except Exception as e:
            logger.error(f"  ❌ ConfigurationService初期化失敗: {e}")
            self.config_service = None

        # FileSystemManager初期化
        try:
            logger.info("  - FileSystemManager初期化中...")
            self.file_system_manager = FileSystemManager()
            logger.info("  ✅ FileSystemManager初期化成功")
        except Exception as e:
            logger.error(f"  ❌ FileSystemManager初期化失敗: {e}")
            self.file_system_manager = None

        # ImageDatabaseManager初期化
        try:
            logger.info("  - ImageDatabaseManager初期化中...")
            if self.config_service:
                db_path = self.config_service.get_database_directory() / "image_database.db"
            else:
                db_path = Path("lorairo_data/default_project/image_database.db")

            self.db_manager = ImageDatabaseManager(str(db_path))
            logger.info("  ✅ ImageDatabaseManager初期化成功")
        except Exception as e:
            logger.error(f"  ❌ ImageDatabaseManager初期化失敗: {e}")
            self.db_manager = None

        # WorkerService初期化
        try:
            logger.info("  - WorkerService初期化中...")
            self.worker_service = WorkerService()
            logger.info("  ✅ WorkerService初期化成功")
        except Exception as e:
            logger.error(f"  ❌ WorkerService初期化失敗: {e}")
            self.worker_service = None

        # DatasetStateManager初期化
        try:
            logger.info("  - DatasetStateManager初期化中...")
            self.dataset_state_manager = DatasetStateManager()
            logger.info("  ✅ DatasetStateManager初期化成功")
        except Exception as e:
            logger.error(f"  ❌ DatasetStateManager初期化失敗: {e}")
            self.dataset_state_manager = None

        # 初期化成功サービスの確認
        successful_services = []
        failed_services = []

        services = [
            ("ConfigurationService", self.config_service),
            ("FileSystemManager", self.file_system_manager),
            ("ImageDatabaseManager", self.db_manager),
            ("WorkerService", self.worker_service),
            ("DatasetStateManager", self.dataset_state_manager),
        ]

        for name, service in services:
            if service is not None:
                successful_services.append(name)
            else:
                failed_services.append(name)

        logger.info(f"サービス初期化結果: 成功 {len(successful_services)}/5")
        if successful_services:
            logger.info(f"  成功: {', '.join(successful_services)}")
        if failed_services:
            logger.warning(f"  失敗: {', '.join(failed_services)}")

        # 最低限必要なサービスのチェック
        if self.config_service is None:
            logger.warning("ConfigurationServiceの初期化に失敗しましたが、継続します")
        if self.db_manager is None:
            logger.warning("ImageDatabaseManagerの初期化に失敗しました - 一部機能が制限されます")

    def setup_custom_widgets(self) -> None:
        """カスタムウィジェットを設定（安全な実装）"""
        # フィルター・検索パネル
        try:
            if hasattr(self, "frameFilterSearchContent") and hasattr(
                self, "verticalLayout_filterSearchContent"
            ):
                self.filter_search_panel = FilterSearchPanel(self.frameFilterSearchContent)
                self.verticalLayout_filterSearchContent.addWidget(self.filter_search_panel)
                logger.info("フィルター・検索パネル設定完了")
            else:
                logger.warning("フィルター・検索パネル用UIコンポーネントが見つかりません")
                self.filter_search_panel = None
        except Exception as e:
            logger.error(f"フィルター・検索パネル設定エラー: {e}", exc_info=True)
            self.filter_search_panel = None

        # サムネイルセレクター（強化版）
        try:
            if (
                hasattr(self, "frameThumbnailContent")
                and hasattr(self, "verticalLayout_thumbnailContent")
                and self.dataset_state_manager
            ):
                self.thumbnail_selector = ThumbnailSelectorWidget(
                    self.frameThumbnailContent, self.dataset_state_manager
                )
                self.verticalLayout_thumbnailContent.addWidget(self.thumbnail_selector)
                logger.info("サムネイルセレクター設定完了")
            else:
                logger.warning(
                    "サムネイルセレクター用UIコンポーネントまたはdataset_state_managerが見つかりません"
                )
                self.thumbnail_selector = None
        except Exception as e:
            logger.error(f"サムネイルセレクター設定エラー: {e}", exc_info=True)
            self.thumbnail_selector = None

        # プレビューウィジェット（既存活用）
        try:
            if hasattr(self, "framePreviewDetailContent") and hasattr(
                self, "verticalLayout_previewDetailContent"
            ):
                self.image_preview_widget = ImagePreviewWidget(self.framePreviewDetailContent)
                self.verticalLayout_previewDetailContent.addWidget(self.image_preview_widget)
                logger.info("プレビューウィジェット設定完了")
            else:
                logger.warning("プレビューウィジェット用UIコンポーネントが見つかりません")
                self.image_preview_widget = None
        except Exception as e:
            logger.error(f"プレビューウィジェット設定エラー: {e}", exc_info=True)
            self.image_preview_widget = None

        # Phase 3.4: 選択画像詳細ウィジェット追加
        try:
            if hasattr(self, "verticalLayout_selectedImageDetails"):
                self.selected_image_details_widget = SelectedImageDetailsWidget()
                self.verticalLayout_selectedImageDetails.addWidget(self.selected_image_details_widget)
                logger.info("選択画像詳細ウィジェット設定完了")
            else:
                logger.warning("選択画像詳細ウィジェット用UIコンポーネントが見つかりません")
                self.selected_image_details_widget = None
        except Exception as e:
            logger.error(f"選択画像詳細ウィジェット設定エラー: {e}", exc_info=True)
            self.selected_image_details_widget = None

        # スプリッターの初期サイズ設定
        try:
            if hasattr(self, "splitterMainWorkArea"):
                self.splitterMainWorkArea.setSizes([300, 700, 400])  # フィルター:サムネイル:プレビュー
                logger.info("スプリッター初期サイズ設定完了")
        except Exception as e:
            logger.warning(f"スプリッター設定エラー: {e}")

    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")

            # ボタンイベント接続（安全な実装）
            if hasattr(self, "pushButtonSelectDirectory"):
                try:
                    self.pushButtonSelectDirectory.clicked.connect(self.select_dataset_directory)
                    logger.info("    ✅ ディレクトリ選択ボタン接続完了")
                except Exception as e:
                    logger.error(f"    ❌ ディレクトリ選択ボタン接続失敗: {e}")

            if hasattr(self, "pushButtonRegisterImages"):
                try:
                    self.pushButtonRegisterImages.clicked.connect(self.register_images_to_db)
                    logger.info("    ✅ 画像登録ボタン接続完了")
                except Exception as e:
                    logger.error(f"    ❌ 画像登録ボタン接続失敗: {e}")

            if hasattr(self, "pushButtonLoadDbImages"):
                try:
                    self.pushButtonLoadDbImages.clicked.connect(self.load_images_from_db)
                    logger.info("    ✅ DB読み込みボタン接続完了")
                except Exception as e:
                    logger.error(f"    ❌ DB読み込みボタン接続失敗: {e}")

            # ウィジェット間のイベント接続
            if self.filter_search_panel and self.thumbnail_selector:
                try:
                    # フィルター結果をサムネイルセレクターに反映
                    self.filter_search_panel.filter_applied.connect(
                        self.thumbnail_selector.apply_filter_results
                    )
                    logger.info("    ✅ フィルター→サムネイル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ フィルター→サムネイル接続失敗: {e}")

            if self.thumbnail_selector and self.image_preview_widget:
                try:
                    # サムネイル選択をプレビューに反映
                    self.thumbnail_selector.image_selected.connect(self.image_preview_widget.load_image)
                    logger.info("    ✅ サムネイル→プレビュー接続完了")
                except Exception as e:
                    logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

    # Placeholder methods for UI actions - implement these based on your requirements
    def select_dataset_directory(self):
        """データセットディレクトリ選択"""
        logger.info("データセットディレクトリ選択が呼び出されました")

    def register_images_to_db(self):
        """画像をデータベースに登録"""
        logger.info("DB画像登録が呼び出されました")

    def load_images_from_db(self):
        """データベースから画像を読み込み"""
        logger.info("DB画像読み込みが呼び出されました")

    def _resolve_optimal_thumbnail_data(
        self, image_metadata: list[dict[str, Any]]
    ) -> list[tuple[Path, int]]:
        """画像メタデータから最適なサムネイル表示用パスを解決

        512px処理済み画像が利用可能な場合はそれを使用し、
        利用不可能な場合は元画像にフォールバックする

        Args:
            image_metadata: 画像メタデータリスト

        Returns:
            list[tuple[Path, int]]: (画像パス, 画像ID) のタプルリスト
        """
        if not image_metadata:
            return []

        result = []

        for metadata in image_metadata:
            image_id = metadata["id"]
            original_path = metadata["stored_image_path"]

            try:
                # 512px処理済み画像の存在を確認
                if self.db_manager:
                    processed_image = self.db_manager.check_processed_image_exists(image_id, 512)

                    if processed_image:
                        # 512px画像のパス解決
                        from lorairo.database.db_core import resolve_stored_path

                        resolved_path = resolve_stored_path(processed_image["stored_image_path"])

                        # ファイル存在確認
                        if resolved_path.exists():
                            result.append((resolved_path, image_id))
                            continue

                # フォールバック: 元画像を使用
                result.append((Path(original_path), image_id))

            except Exception as e:
                # エラー時もフォールバック: 元画像を使用
                logger.warning(f"パス解決エラー (image_id={image_id}): {e}")
                result.append((Path(original_path), image_id))

        return result

    def _setup_image_db_write_service(self) -> None:
        """ImageDBWriteServiceを作成してselected_image_details_widgetに注入

        Phase 3.4: DB操作分離パターンの実装
        """
        from lorairo.gui.services.image_db_write_service import ImageDBWriteService

        try:
            if self.db_manager and self.selected_image_details_widget:
                # ImageDBWriteServiceを作成
                self.image_db_write_service = ImageDBWriteService(self.db_manager)

                # SelectedImageDetailsWidgetに注入
                self.selected_image_details_widget.set_image_db_write_service(self.image_db_write_service)

                logger.info("ImageDBWriteService created and injected into SelectedImageDetailsWidget")
            else:
                logger.warning(
                    "Cannot setup ImageDBWriteService: db_manager or selected_image_details_widget not available"
                )

        except Exception as e:
            logger.error(f"ImageDBWriteService setup failed: {e}", exc_info=True)

    def _create_search_filter_service(self) -> SearchFilterService:
        """
        SearchFilterServiceを適切な設定で作成（MainWindow統合用）

        Returns:
            SearchFilterService: 設定されたサービスインスタンス
        """
        try:
            # ServiceContainer経由で適切なModelSelectionServiceを注入
            service_container = get_service_container()
            model_selection_service = ModelSelectionService.create(
                db_repository=service_container.image_repository
            )

            return SearchFilterService(
                db_manager=self.db_manager, model_selection_service=model_selection_service
            )
        except Exception as e:
            logger.error(f"Failed to create SearchFilterService: {e}")
            # フォールバック: NullModelRegistryを使用した最小限の機能提供
            from ...database.db_repository import ImageRepository

            # 最小限のModelSelectionServiceを作成
            fallback_repo = ImageRepository(self.db_manager.get_db_path())
            model_selection_service = ModelSelectionService(fallback_repo)

            return SearchFilterService(
                db_manager=self.db_manager, model_selection_service=model_selection_service
            )

    def _setup_search_filter_integration(self) -> None:
        """SearchFilterService統合処理（Phase 3.5）

        FilterSearchPanelにSearchFilterServiceを注入して検索機能を有効化
        """
        try:
            if self.filter_search_panel:
                # SearchFilterServiceを作成
                search_filter_service = self._create_search_filter_service()

                # FilterSearchPanelに注入
                self.filter_search_panel.set_search_filter_service(search_filter_service)

                logger.info("SearchFilterService integration completed - FilterSearchPanel search functionality enabled")
            else:
                logger.warning("Cannot setup SearchFilterService integration: filter_search_panel not available")

        except Exception as e:
            logger.error(f"SearchFilterService integration failed: {e}", exc_info=True)

    def _setup_state_integration(self) -> None:
        """DatasetStateManagerをウィジェットに接続

        Phase 3.4: 状態管理統合パターンの実装
        """
        try:
            if (
                hasattr(self, "dataset_state")
                and self.dataset_state
                and hasattr(self, "image_preview")
                and self.image_preview
            ):
                # ImagePreviewWidgetにDatasetStateManagerを接続
                self.image_preview.set_dataset_state_manager(self.dataset_state)
                logger.info("DatasetStateManager connected to widgets")
            else:
                logger.warning(
                    "Cannot setup state integration: dataset_state or image_preview not available"
                )
        except Exception as e:
            logger.error(f"State integration setup failed: {e}", exc_info=True)


if __name__ == "__main__":
    import os
    import platform
    import sys

    from PySide6.QtWidgets import QApplication

    from ...utils.config import get_config
    from ...utils.log import initialize_logging

    def setup_test_environment():
        """テスト用Qt環境設定"""
        system = platform.system()
        if system == "Windows":
            os.environ["QT_QPA_PLATFORM"] = "windows"
            print("Windows環境: ネイティブウィンドウモード")
        elif system == "Linux":
            # devcontainer環境ではoffscreenモード
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
                print("Linux環境: offscreenモード（devcontainer想定）")
            else:
                os.environ["QT_QPA_PLATFORM"] = "xcb"
                print("Linux環境: X11モード")
        elif system == "Darwin":
            os.environ["QT_QPA_PLATFORM"] = "cocoa"
            print("macOS環境: Cocoaモード")

    # 環境設定
    setup_test_environment()

    # 設定読み込み
    try:
        config = get_config()
        initialize_logging(config.get("log", {}))
        print("設定とログ初期化完了")
    except Exception as e:
        print(f"設定読み込みエラー (継続): {e}")
        config = {}

    # QApplication作成
    app = QApplication(sys.argv)
    app.setApplicationName("MainWindow-Test")

    try:
        # MainWindow作成
        print("MainWindow作成中...")
        window = MainWindow()

        # ウィンドウ表示の確実化
        print("ウィンドウ表示中...")
        window.show()
        window.raise_()
        window.activateWindow()
        app.processEvents()

        # 環境情報出力
        print(f"ウィンドウ表示状態: visible={window.isVisible()}")
        print(f"ウィンドウサイズ: {window.size()}")
        print(f"ウィンドウタイトル: {window.windowTitle()}")

        if window.isVisible():
            print("✅ ウィンドウ表示成功")
        else:
            print("❌ ウィンドウ表示失敗")

        print("イベントループ開始...")
        # イベントループ開始
        sys.exit(app.exec())

    except Exception as e:
        print(f"エラー: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
