# src/lorairo/gui/window/main_window.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.model_selection_service import ModelSelectionService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.MainWindow_ui import Ui_MainWindow
from ..services.image_db_write_service import ImageDBWriteService
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

    def _initialize_services(self) -> None:
        """サービスを段階的に初期化し、致命的コンポーネントは強制終了"""

        # ServiceContainer（必須）
        try:
            logger.info("  - ServiceContainer/ImageDatabaseManager初期化中...")
            service_container = get_service_container()
            self.db_manager = service_container.db_manager
            if not self.db_manager:
                raise RuntimeError("ServiceContainer経由でImageDatabaseManagerを取得できません")
            logger.info("  ✅ ImageDatabaseManager初期化成功（ServiceContainer統一）")
        except Exception as e:
            self._handle_critical_initialization_failure("ServiceContainer/ImageDatabaseManager", e)
            return

        # ConfigurationService（必須）
        try:
            logger.info("  - ConfigurationService初期化中...")
            self.config_service = ConfigurationService()
            logger.info("  ✅ ConfigurationService初期化成功")
        except Exception as e:
            self._handle_critical_initialization_failure("ConfigurationService", e)
            return

        # 非致命的サービス（ログして継続）
        try:
            logger.info("  - FileSystemManager初期化中...")
            self.file_system_manager = FileSystemManager()
            logger.info("  ✅ FileSystemManager初期化成功")
        except Exception as e:
            logger.error(f"  ❌ FileSystemManager初期化失敗（継続）: {e}")
            self.file_system_manager = None

        try:
            logger.info("  - WorkerService初期化中...")
            if self.db_manager and self.file_system_manager:
                self.worker_service = WorkerService(self.db_manager, self.file_system_manager)
                logger.info("  ✅ WorkerService初期化成功")
            else:
                raise RuntimeError(
                    "db_manager または file_system_manager が未初期化のため WorkerService を作成できません"
                )
        except Exception as e:
            logger.error(f"  ❌ WorkerService初期化失敗（継続）: {e}")
            self.worker_service = None

        try:
            logger.info("  - DatasetStateManager初期化中...")
            self.dataset_state_manager = DatasetStateManager()
            logger.info("  ✅ DatasetStateManager初期化成功")
        except Exception as e:
            logger.error(f"  ❌ DatasetStateManager初期化失敗（継続）: {e}")
            self.dataset_state_manager = None

        # 初期化結果サマリー
        successful_services = []
        failed_services = []

        services = [
            ("ConfigurationService", self.config_service),
            ("ImageDatabaseManager", self.db_manager),
            ("FileSystemManager", self.file_system_manager),
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
            logger.warning(f"  失敗（非致命的）: {', '.join(failed_services)}")

        logger.info("致命的サービス（ConfigurationService, ImageDatabaseManager）初期化完了")

    def _handle_critical_initialization_failure(self, component_name: str, error: Exception) -> None:
        """致命的初期化失敗時の処理

        Args:
            component_name: 失敗したコンポーネント名
            error: 発生した例外
        """
        error_message = (
            f"致命的な初期化エラーが発生しました。\n\n"
            f"コンポーネント: {component_name}\n"
            f"エラー: {error!s}\n\n"
            f"アプリケーションを終了します。\n"
            f"問題が解決しない場合は、設定ファイルの確認または再インストールをお試しください。"
        )

        logger.critical(f"Critical initialization failure - {component_name}: {error}")

        # ユーザーへの通知（GUI利用可能なら）
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("LoRAIro - 致命的エラー")
            msg_box.setText(error_message)
            msg_box.exec()
        except Exception:
            # GUI不可の場合はコンソール出力
            print(f"\n{'=' * 60}")
            print("LoRAIro - 致命的エラー")
            print(f"{'=' * 60}")
            print(error_message)
            print(f"{'=' * 60}\n")

        # アプリケーション終了
        import sys

        sys.exit(1)

    def setup_custom_widgets(self) -> None:
        """カスタムウィジェットを設定（致命的コンポーネントチェック実装）"""
        # フィルター・検索パネル（Designer生成専用・必須）
        try:
            if hasattr(self, "filterSearchPanel") and self.filterSearchPanel:
                self.filter_search_panel = self.filterSearchPanel  # type: ignore[attr-defined]
                logger.info("フィルター・検索パネル(Designer生成)を使用")
                logger.debug(f"FilterSearchPanel instance ID: {id(self.filter_search_panel)}")
            else:
                # 致命的エラー: メイン機能が利用不可
                raise RuntimeError(
                    "Designer生成filterSearchPanelが見つかりません - UIファイルの破損またはバージョン不整合の可能性"
                )
        except Exception as e:
            self._handle_critical_initialization_failure("FilterSearchPanel", e)
            return  # この行は実行されないが明示的記述

        # サムネイルセレクター（UI配置済みウィジェットへの参照取得）
        try:
            logger.debug(
                f"ThumbnailSelectorWidget接続チェック - hasattr: {hasattr(self, 'thumbnailSelectorWidget')}"
            )
            logger.debug(
                f"DatasetStateManager存在チェック - dataset_state_manager: {self.dataset_state_manager is not None}"
            )

            if hasattr(self, "thumbnailSelectorWidget") and self.dataset_state_manager:
                self.thumbnail_selector = self.thumbnailSelectorWidget  # type: ignore[attr-defined]
                logger.info(f"ThumbnailSelectorWidget参照取得成功: {type(self.thumbnail_selector)}")

                # DatasetStateManagerとの接続
                self.thumbnail_selector.set_dataset_state(self.dataset_state_manager)
                logger.info("DatasetStateManager接続完了")

                # 基本プロパティ確認
                logger.debug(f"ThumbnailSize: {getattr(self.thumbnail_selector, 'thumbnail_size', 'NONE')}")
                logger.debug(f"ImageData count: {len(getattr(self.thumbnail_selector, 'image_data', []))}")

                logger.info("サムネイルセレクター（UI配置済み）設定完了")
            else:
                missing_components = []
                if not hasattr(self, "thumbnailSelectorWidget"):
                    missing_components.append("thumbnailSelectorWidget")
                if not self.dataset_state_manager:
                    missing_components.append("dataset_state_manager")

                logger.warning(f"UI配置済みコンポーネントが見つかりません（継続）: {missing_components}")
                self.thumbnail_selector = None
        except Exception as e:
            logger.error(f"サムネイルセレクター設定エラー（継続）: {e}", exc_info=True)
            self.thumbnail_selector = None

        # プレビューウィジェット（非致命的）
        try:
            if hasattr(self, "framePreviewDetailContent") and hasattr(
                self, "verticalLayout_previewDetailContent"
            ):
                self.image_preview_widget = ImagePreviewWidget(self.framePreviewDetailContent)
                self.verticalLayout_previewDetailContent.addWidget(self.image_preview_widget)

                # DatasetStateManagerとの接続を追加
                if self.dataset_state_manager:
                    self.image_preview_widget.set_dataset_state_manager(self.dataset_state_manager)
                    logger.info("ImagePreviewWidget - DatasetStateManager接続完了")
                else:
                    logger.warning("DatasetStateManagerが利用できないためImagePreviewWidget接続をスキップ")

                logger.info("プレビューウィジェット設定完了")
            else:
                logger.warning("プレビューウィジェット用UIコンポーネントが見つかりません（継続）")
                self.image_preview_widget = None
        except Exception as e:
            logger.error(f"プレビューウィジェット設定エラー（継続）: {e}", exc_info=True)
            self.image_preview_widget = None

        # 選択画像詳細ウィジェット（非致命的）
        try:
            if hasattr(self, "verticalLayout_selectedImageDetails"):
                self.selected_image_details_widget = SelectedImageDetailsWidget()
                self.verticalLayout_selectedImageDetails.addWidget(self.selected_image_details_widget)
                logger.info("選択画像詳細ウィジェット設定完了")
            else:
                logger.warning("選択画像詳細ウィジェット用UIコンポーネントが見つかりません（継続）")
                self.selected_image_details_widget = None
        except Exception as e:
            logger.error(f"選択画像詳細ウィジェット設定エラー（継続）: {e}", exc_info=True)
            self.selected_image_details_widget = None

        # スプリッターの初期サイズ設定（非致命的）
        try:
            if hasattr(self, "splitterMainWorkArea"):
                self.splitterMainWorkArea.setSizes([300, 700, 400])  # フィルター:サムネイル:プレビュー
                logger.info("スプリッター初期サイズ設定完了")
        except Exception as e:
            logger.warning(f"スプリッター設定エラー（継続）: {e}")

    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")

            # ボタンイベント接続（安全な実装）
            if hasattr(self, "pushButtonSelectDataset"):
                try:
                    self.pushButtonSelectDataset.clicked.connect(self.select_dataset_directory)
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
            if self.thumbnail_selector and self.image_preview_widget:
                try:
                    # サムネイル選択をプレビューに反映
                    self.thumbnail_selector.image_selected.connect(self.image_preview_widget.load_image)
                    logger.info("    ✅ サムネイル→プレビュー接続完了")
                except Exception as e:
                    logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

            # Phase 2: Sequential Worker Pipeline 統合シグナル接続
            self._setup_worker_pipeline_signals()

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

    def _setup_worker_pipeline_signals(self) -> None:
        """Phase 2: Sequential Worker Pipeline シグナル接続設定"""
        if not self.worker_service:
            logger.warning("WorkerService not available - Sequential Pipeline signals not connected")
            return

        try:
            # SearchWorker完了 → ThumbnailWorker自動起動
            self.worker_service.search_finished.connect(self._on_search_completed_start_thumbnail)

            # ThumbnailWorker完了 → ThumbnailSelectorWidget更新
            self.worker_service.thumbnail_finished.connect(self._on_thumbnail_completed_update_display)

            # Pipeline進捗統合表示
            self.worker_service.search_started.connect(self._on_pipeline_search_started)
            self.worker_service.thumbnail_started.connect(self._on_pipeline_thumbnail_started)

            # Pipeline エラー・キャンセレーション処理
            self.worker_service.search_error.connect(self._on_pipeline_search_error)
            self.worker_service.thumbnail_error.connect(self._on_pipeline_thumbnail_error)

            # Batch Registration signals (Phase 2 addition)
            self.worker_service.batch_registration_started.connect(self._on_batch_registration_started)
            self.worker_service.batch_registration_finished.connect(self._on_batch_registration_finished)
            self.worker_service.batch_registration_error.connect(self._on_batch_registration_error)

            logger.info("    ✅ Sequential Worker Pipeline signals connected")

        except Exception as e:
            logger.error(f"    ❌ Sequential Worker Pipeline signals connection failed: {e}")

    def _on_search_completed_start_thumbnail(self, search_result: Any) -> None:
        """SearchWorker完了時にThumbnailWorkerを自動起動"""
        if not search_result or not hasattr(search_result, "image_metadata"):
            logger.warning("Search completed but no valid results - Thumbnail loading skipped")
            return

        if not search_result.image_metadata:
            logger.info("Search completed with 0 results - Thumbnail loading skipped")
            # サムネイル領域をクリア（要求仕様通り）
            if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
                self.thumbnail_selector.clear_thumbnails()
            return

        try:
            # サムネイルレイアウト用の image_data を事前設定
            if self.thumbnail_selector:
                image_data = [
                    (Path(item["stored_image_path"]), item["id"])
                    for item in search_result.image_metadata
                    if "stored_image_path" in item and "id" in item
                ]
                self.thumbnail_selector.image_data = image_data
                logger.info(f"ThumbnailSelectorWidget.image_data set: {len(image_data)} items")

            # ThumbnailWorker開始 - SearchResultオブジェクトを渡す
            default_thumbnail_size = QSize(150, 150)  # デフォルトサムネイルサイズ
            worker_id = self.worker_service.start_thumbnail_loading(search_result, default_thumbnail_size)
            logger.info(
                f"ThumbnailWorker started automatically after search: {worker_id} ({len(search_result.image_metadata)} images)"
            )

        except Exception as e:
            logger.error(f"Failed to start automatic thumbnail loading: {e}", exc_info=True)

    def _on_thumbnail_completed_update_display(self, thumbnail_result: Any) -> None:
        """ThumbnailWorker完了時にThumbnailSelectorWidget更新"""
        if not self.thumbnail_selector:
            logger.warning("ThumbnailSelectorWidget not available - thumbnail display update skipped")
            return

        try:
            # ThumbnailSelectorWidget統合（既存メソッド活用）
            if hasattr(self.thumbnail_selector, "load_thumbnails_from_result"):
                self.thumbnail_selector.load_thumbnails_from_result(thumbnail_result)
                logger.info("ThumbnailSelectorWidget updated with results")
            else:
                logger.warning("ThumbnailSelectorWidget.load_thumbnails_from_result method not found")

            # パイプライン完了後にプログレスバーを非表示
            if hasattr(self.filter_search_panel, "hide_progress_after_completion"):
                self.filter_search_panel.hide_progress_after_completion()

        except Exception as e:
            logger.error(f"Failed to update ThumbnailSelectorWidget: {e}", exc_info=True)

    def _on_pipeline_search_started(self, worker_id: str) -> None:
        """Pipeline検索フェーズ開始時の進捗表示"""
        if hasattr(self.filter_search_panel, "update_pipeline_progress"):
            self.filter_search_panel.update_pipeline_progress("検索中...", 0.0, 0.3)

    def _on_pipeline_thumbnail_started(self, worker_id: str) -> None:
        """Pipelineサムネイル生成フェーズ開始時の進捗表示"""
        if hasattr(self.filter_search_panel, "update_pipeline_progress"):
            self.filter_search_panel.update_pipeline_progress("サムネイル読込中...", 0.3, 1.0)

    def _on_pipeline_search_error(self, error_message: str) -> None:
        """Pipeline検索エラー時の処理（検索結果破棄）"""
        logger.error(f"Pipeline search error: {error_message}")
        if hasattr(self.filter_search_panel, "handle_pipeline_error"):
            self.filter_search_panel.handle_pipeline_error("search", {"message": error_message})
        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()

    def _on_pipeline_thumbnail_error(self, error_message: str) -> None:
        """Pipelineサムネイル生成エラー時の処理（検索結果破棄）"""
        logger.error(f"Pipeline thumbnail error: {error_message}")
        if hasattr(self.filter_search_panel, "handle_pipeline_error"):
            self.filter_search_panel.handle_pipeline_error("thumbnail", {"message": error_message})
        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()
        # エラー時もプログレスバーを非表示
        if hasattr(self.filter_search_panel, "hide_progress_after_completion"):
            self.filter_search_panel.hide_progress_after_completion()

    def _on_batch_registration_started(self, worker_id: str) -> None:
        """Batch registration started signal handler"""
        # Remove verbose logging - just handle the signal silently
        # TODO: Add UI feedback for batch registration start (progress bar, status text)

    def _on_batch_registration_finished(self, result: Any) -> None:
        """Batch registration finished signal handler"""
        try:
            # Extract results from DatabaseRegistrationResult
            if hasattr(result, "registered_count"):
                registered = result.registered_count
                skipped = result.skipped_count
                errors = result.error_count
                processing_time = result.total_processing_time

                success_message = (
                    f"バッチ登録完了！\n\n"
                    f"登録: {registered}件\n"
                    f"スキップ: {skipped}件\n"
                    f"エラー: {errors}件\n"
                    f"処理時間: {processing_time:.2f}秒"
                )

                # Emit completion signal for other components
                self.database_registration_completed.emit(registered)

                QMessageBox.information(self, "バッチ登録完了", success_message)

        except Exception:
            # Silent error handling - no verbose logging
            pass

    def _on_batch_registration_error(self, error_message: str) -> None:
        """Batch registration error signal handler"""
        QMessageBox.critical(
            self, "バッチ登録エラー", f"バッチ登録中にエラーが発生しました:\n\n{error_message}"
        )

    def cancel_current_pipeline(self) -> None:
        """現在のPipeline全体をキャンセル"""
        if not self.worker_service:
            logger.warning("WorkerService not available - Pipeline cancellation skipped")
            return

        try:
            # SearchWorker + ThumbnailWorker の cascade cancellation
            if (
                hasattr(self.worker_service, "current_search_worker_id")
                and self.worker_service.current_search_worker_id
            ):
                self.worker_service.cancel_search(self.worker_service.current_search_worker_id)
                logger.info("Search worker cancelled in pipeline")

            if (
                hasattr(self.worker_service, "current_thumbnail_worker_id")
                and self.worker_service.current_thumbnail_worker_id
            ):
                self.worker_service.cancel_thumbnail_loading(
                    self.worker_service.current_thumbnail_worker_id
                )
                logger.info("Thumbnail worker cancelled in pipeline")

            # キャンセル時の結果破棄（要求仕様通り）
            if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
                self.thumbnail_selector.clear_thumbnails()

            # キャンセル時もプログレスバーを非表示
            if hasattr(self.filter_search_panel, "hide_progress_after_completion"):
                self.filter_search_panel.hide_progress_after_completion()

            logger.info("Pipeline cancellation completed")

        except Exception as e:
            logger.error(f"Pipeline cancellation failed: {e}", exc_info=True)

    # Placeholder methods for UI actions - implement these based on your requirements
    def select_dataset_directory(self) -> None:
        """データセットディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "データセットディレクトリを選択してください",
            "",  # 初期ディレクトリ
            QFileDialog.Option.ShowDirsOnly,
        )

        if directory:
            # WorkerServiceが利用可能かチェック
            if not self.worker_service:
                QMessageBox.warning(
                    self,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、バッチ登録を開始できません。",
                )
                return

            try:
                # FileSystemManagerの初期化（必須）
                if not self.file_system_manager:
                    # 致命的エラー - アプリケーション終了
                    error_msg = "FileSystemManagerが初期化されていません。バッチ登録処理を実行できません。"
                    logger.critical(f"Critical error during batch registration: {error_msg}")
                    self._handle_critical_initialization_failure(
                        "FileSystemManager", RuntimeError(error_msg)
                    )
                    return

                # 選択されたディレクトリの親ディレクトリに出力する
                output_dir = Path(directory).parent / "lorairo_output"
                self.file_system_manager.initialize(output_dir)

                # バッチ登録開始（初期化済みFileSystemManagerを渡す）
                worker_id = self.worker_service.start_batch_registration_with_fsm(
                    Path(directory), self.file_system_manager
                )
            except Exception as e:
                QMessageBox.critical(self, "バッチ登録エラー", f"データセット登録の開始に失敗しました: {e}")

    def register_images_to_db(self) -> None:
        """画像をデータベースに登録（データセットディレクトリ選択に転送）"""
        self.select_dataset_directory()

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
        SearchFilterService作成（ServiceContainer統一）

        Returns:
            SearchFilterService: 設定されたサービスインスタンス
        """
        try:
            # ServiceContainer経由で一貫したサービス取得
            service_container = get_service_container()
            repo = service_container.image_repository
            model_selection_service = ModelSelectionService.create(db_repository=repo)

            dbm = self.db_manager

            if not dbm:
                raise ValueError("ImageDatabaseManager is required but not available")

            return SearchFilterService(db_manager=dbm, model_selection_service=model_selection_service)

        except Exception as e:
            logger.error(f"Failed to create SearchFilterService: {e}", exc_info=True)
            # 致命的エラーとして扱う（フォールバック中止）
            raise ValueError("SearchFilterService作成不可") from e

    def _setup_search_filter_integration(self) -> None:
        """SearchFilterService統合処理（Phase 3.5）致命的チェック実装

        FilterSearchPanelにSearchFilterServiceを注入して検索機能を有効化
        """
        # 前提条件チェック（致命的）
        if not self.filter_search_panel:
            self._handle_critical_initialization_failure(
                "SearchFilterService統合",
                RuntimeError("filter_search_panel が None - setup_custom_widgets() の失敗"),
            )
            return

        if not self.db_manager:
            self._handle_critical_initialization_failure(
                "SearchFilterService統合", RuntimeError("db_manager が None - ServiceContainer初期化失敗")
            )
            return

        # 同一性確認の追加（GPT5指摘対応）
        if hasattr(self, "filterSearchPanel") and self.filterSearchPanel:
            if self.filter_search_panel is not self.filterSearchPanel:
                logger.warning(
                    f"FilterSearchPanel インスタンス不一致を検出 - 修正中: "
                    f"filter_search_panel={id(self.filter_search_panel)}, "
                    f"filterSearchPanel={id(self.filterSearchPanel)}"
                )
                # Designer生成UIを確実に使用
                self.filter_search_panel = self.filterSearchPanel
                logger.info("Designer生成filterSearchPanelに修正完了")

            # 同一性確認ログ（明示的検証）
            logger.debug(
                f"FilterSearchPanel 同一性確認: "
                f"filter_search_panel is filterSearchPanel = {self.filter_search_panel is self.filterSearchPanel}"
            )
            logger.debug(f"Instance ID: {id(self.filter_search_panel)}")

        # 統合処理実行
        try:
            search_filter_service = self._create_search_filter_service()
            self.filter_search_panel.set_search_filter_service(search_filter_service)

            # WorkerService設定
            if self.worker_service:
                self.filter_search_panel.set_worker_service(self.worker_service)
                logger.info("WorkerService integrated into FilterSearchPanel")
            else:
                logger.warning(
                    "WorkerService not available - FilterSearchPanel will use synchronous search"
                )
            logger.info(
                "SearchFilterService integration completed - FilterSearchPanel search functionality enabled"
            )
        except Exception as e:
            self._handle_critical_initialization_failure("SearchFilterService統合", e)


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
