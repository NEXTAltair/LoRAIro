# src/lorairo/gui/window/main_window.py

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.data_transform_service import DataTransformService
from ...services.model_selection_service import ModelSelectionService
from ...services.selection_state_service import SelectionStateService
from ...services.service_container import ServiceContainer
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..controllers.annotation_workflow_controller import AnnotationWorkflowController
from ..controllers.dataset_controller import DatasetController
from ..controllers.export_controller import ExportController
from ..controllers.settings_controller import SettingsController
from ..services.image_db_write_service import ImageDBWriteService
from ..services.pipeline_control_service import PipelineControlService
from ..services.progress_state_service import ProgressStateService
from ..services.result_handler_service import ResultHandlerService
from ..services.search_filter_service import SearchFilterService
from ..services.widget_setup_service import WidgetSetupService
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

    # Service/Controller層属性
    selection_state_service: SelectionStateService | None
    dataset_controller: DatasetController | None
    annotation_workflow_controller: AnnotationWorkflowController | None
    settings_controller: SettingsController | None
    export_controller: ExportController | None
    data_transform_service: DataTransformService | None
    result_handler_service: ResultHandlerService | None
    pipeline_control_service: PipelineControlService | None

    @property
    def service_container(self) -> ServiceContainer:
        """ServiceContainer singleton instance"""
        return ServiceContainer()

    # ウィジェット属性の型定義（Qt Designerで生成）
    filterSearchPanel: FilterSearchPanel  # Qt Designer生成
    thumbnail_selector: ThumbnailSelectorWidget | None
    image_preview_widget: ImagePreviewWidget | None
    selected_image_details_widget: SelectedImageDetailsWidget | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 初期化失敗フラグ
        self._initialization_failed = False
        self._initialization_error: str | None = None

        try:
            # Phase 1: 基本UI設定（最優先）
            logger.info("MainWindow初期化開始 - Phase 1: UI設定")
            self.setupUi(self)
            logger.info("UI設定完了")

            # サービス初期化（例外を個別にキャッチ）
            logger.info("サービス初期化開始")
            self._initialize_services()

            # Phase 3: UI カスタマイズ（サービス依存）
            logger.info("Phase 3: UI カスタマイズ開始")
            self.setup_custom_widgets()

            # Phase 3.5: サービス統合（新規）
            logger.info("Phase 3.5: SearchFilterService統合開始")
            self._setup_search_filter_integration()

            # Service統合（DataTransform/ResultHandler/PipelineControl）
            logger.info("Service層統合開始")
            self._setup_phase24_services()

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

        # WorkerService初期化（クリティカル化）
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
            logger.critical(f"  ❌ WorkerService初期化失敗（致命的）: {e}")
            self._handle_critical_initialization_failure("WorkerService", e)
            return

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

        logger.info(f"サービス初期化結果: 成功 {len(successful_services)}/6")
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
        """カスタムウィジェットを設定（Qt Designer生成ウィジェット直接使用版）"""

        logger.info("🔍 カスタムウィジェット設定開始")

        # Qt Designer生成済みウィジェットの検証
        if not hasattr(self, "filterSearchPanel"):
            logger.error("❌ filterSearchPanel not found - Qt Designer UI generation failed")
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定", RuntimeError("filterSearchPanel attribute missing from setupUi()")
            )
            return
        # filterSearchPanelは型定義により保証されているため、isinstance不要

        # FilterSearchPanel interface validation
        required_methods = ["set_search_filter_service", "set_worker_service"]
        missing_methods = [
            method for method in required_methods if not hasattr(self.filterSearchPanel, method)
        ]

        if missing_methods:
            logger.error(f"❌ filterSearchPanel missing required methods: {missing_methods}")
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定",
                RuntimeError(f"filterSearchPanel interface validation failed: missing {missing_methods}"),
            )
            return

        logger.info(
            f"✅ filterSearchPanel validation successful: {type(self.filterSearchPanel)} (ID: {id(self.filterSearchPanel)})"
        )

        # その他のカスタムウィジェット設定
        self._setup_other_custom_widgets()

        logger.info("カスタムウィジェット設定完了")

    def _setup_other_custom_widgets(self) -> None:
        """その他のカスタムウィジェット設定（WidgetSetupServiceに委譲）"""
        WidgetSetupService.setup_all_widgets(self, self.dataset_state_manager)

        # 状態管理接続の検証
        self._verify_state_management_connections()

        # Service/Controller層初期化

        # SelectionStateService初期化
        try:
            logger.info("  - SelectionStateService初期化中...")
            self.selection_state_service = SelectionStateService(
                dataset_state_manager=self.dataset_state_manager,
                db_repository=self.db_manager.repository if self.db_manager else None,
            )
            logger.info("  ✅ SelectionStateService初期化成功")
        except Exception as e:
            logger.error(f"  ❌ SelectionStateService初期化失敗（継続）: {e}")
            self.selection_state_service = None

        # DatasetController初期化
        try:
            logger.info("  - DatasetController初期化中...")
            self.dataset_controller = DatasetController(
                db_manager=self.db_manager,
                file_system_manager=self.file_system_manager,
                worker_service=self.worker_service,
                parent=self,
            )
            logger.info("  ✅ DatasetController初期化成功")
        except Exception as e:
            logger.error(f"  ❌ DatasetController初期化失敗（継続）: {e}")
            self.dataset_controller = None

        # AnnotationWorkflowController初期化
        try:
            logger.info("  - AnnotationWorkflowController初期化中...")
            self.annotation_workflow_controller = AnnotationWorkflowController(
                worker_service=self.worker_service,
                selection_state_service=self.selection_state_service,
                config_service=self.config_service,
                parent=self,
            )
            logger.info("  ✅ AnnotationWorkflowController初期化成功")
        except Exception as e:
            logger.error(f"  ❌ AnnotationWorkflowController初期化失敗（継続）: {e}")
            self.annotation_workflow_controller = None

        # SettingsController初期化
        try:
            logger.info("  - SettingsController初期化中...")
            self.settings_controller = SettingsController(
                config_service=self.config_service,
                parent=self,
            )
            logger.info("  ✅ SettingsController初期化成功")
        except Exception as e:
            logger.error(f"  ❌ SettingsController初期化失敗（継続）: {e}")
            self.settings_controller = None

        # ExportController初期化
        try:
            logger.info("  - ExportController初期化中...")
            self.export_controller = ExportController(
                selection_state_service=self.selection_state_service,
                service_container=self.service_container,
                parent=self,
            )
            logger.info("  ✅ ExportController初期化成功")
        except Exception as e:
            logger.error(f"  ❌ ExportController初期化失敗（継続）: {e}")
            self.export_controller = None

        # その他のウィジェット設定...
        logger.debug("その他のカスタムウィジェット設定完了")

    def _verify_state_management_connections(self) -> None:
        """状態管理接続の検証（SelectionStateServiceに委譲）"""
        if self.selection_state_service:
            self.selection_state_service.verify_state_management_connections(
                thumbnail_selector=getattr(self, "thumbnail_selector", None),
                image_preview_widget=getattr(self, "image_preview_widget", None),
                selected_image_details_widget=getattr(self, "selected_image_details_widget", None),
            )
        else:
            logger.error("SelectionStateServiceが初期化されていません - 接続検証をスキップ")


    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")

            # ウィジェット間のイベント接続（複雑な動的接続）
            if self.thumbnail_selector and self.image_preview_widget:
                try:
                    # サムネイル選択をプレビューに反映
                    self.thumbnail_selector.image_selected.connect(self.image_preview_widget.load_image)
                    logger.info("    ✅ サムネイル→プレビュー接続完了")
                except Exception as e:
                    logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

            # Sequential Worker Pipeline 統合シグナル接続
            self._setup_worker_pipeline_signals()

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

    def _setup_worker_pipeline_signals(self) -> None:
        """WorkerService pipeline signal connections setup"""
        if not self.worker_service:
            logger.warning("WorkerService not available - pipeline signals not connected")
            return

        # Verify WorkerService has required signals
        required_signals = [
            "search_finished",
            "search_started",
            "search_error",
            "thumbnail_finished",
            "thumbnail_started",
            "thumbnail_error",
            "batch_registration_started",
            "batch_registration_finished",
            "batch_registration_error",
            "worker_progress_updated",
            "worker_batch_progress",
        ]

        missing_signals = [
            signal for signal in required_signals if not hasattr(self.worker_service, signal)
        ]

        if missing_signals:
            logger.error(f"WorkerService missing required signals: {missing_signals}")
            return

        # Core pipeline connections
        self.worker_service.search_finished.connect(self._on_search_completed_start_thumbnail)
        self.worker_service.thumbnail_finished.connect(self._on_thumbnail_completed_update_display)

        # Progress tracking connections
        self.worker_service.search_started.connect(self._on_pipeline_search_started)
        self.worker_service.thumbnail_started.connect(self._on_pipeline_thumbnail_started)

        # Error handling connections
        self.worker_service.search_error.connect(self._on_pipeline_search_error)
        self.worker_service.thumbnail_error.connect(self._on_pipeline_thumbnail_error)

        # Batch registration connections
        self.worker_service.batch_registration_started.connect(self._on_batch_registration_started)
        self.worker_service.batch_registration_finished.connect(self._on_batch_registration_finished)
        self.worker_service.batch_registration_error.connect(self._on_batch_registration_error)

        # Progress feedback connections
        self.worker_service.worker_progress_updated.connect(self._on_worker_progress_updated)
        self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.info("WorkerService pipeline signals connected (13 connections)")


    def _on_search_completed_start_thumbnail(self, search_result: Any) -> None:
        """SearchWorker完了時にThumbnailWorkerを自動起動（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_search_completed(search_result)
        else:
            logger.error("PipelineControlService が初期化されていません - サムネイル読み込みをスキップ")

    def _on_thumbnail_completed_update_display(self, thumbnail_result: Any) -> None:
        """ThumbnailWorker完了時にThumbnailSelectorWidget更新（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_thumbnail_completed(thumbnail_result)
        else:
            logger.error("PipelineControlService が初期化されていません - サムネイル表示更新をスキップ")

    def _on_pipeline_search_started(self, _worker_id: str) -> None:
        """Pipeline検索フェーズ開始時の進捗表示（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_search_started(_worker_id)
        else:
            logger.warning("PipelineControlService が初期化されていません - 進捗表示をスキップ")

    def _on_pipeline_thumbnail_started(self, _worker_id: str) -> None:
        """Pipelineサムネイル生成フェーズ開始時の進捗表示（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_thumbnail_started(_worker_id)
        else:
            logger.warning("PipelineControlService が初期化されていません - 進捗表示をスキップ")

    def _on_pipeline_search_error(self, error_message: str) -> None:
        """Pipeline検索エラー時の処理（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_search_error(error_message)
        else:
            logger.error("PipelineControlService が初期化されていません - エラー処理をスキップ")

    def _on_pipeline_thumbnail_error(self, error_message: str) -> None:
        """Pipelineサムネイル生成エラー時の処理（PipelineControlServiceに委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.on_thumbnail_error(error_message)
        else:
            logger.error("PipelineControlService が初期化されていません - エラー処理をスキップ")

    def _on_batch_registration_started(self, worker_id: str) -> None:
        """Batch registration started signal handler（ProgressStateServiceに委譲）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_registration_started(worker_id)
        else:
            logger.warning("ProgressStateService が初期化されていません - 進捗表示をスキップ")

    def _on_batch_registration_finished(self, result: Any) -> None:
        """Batch registration finished signal handler（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_batch_registration_finished(
                result, status_bar=self.statusBar(), completion_signal=self.database_registration_completed
            )
        else:
            # Fallback: Service未初期化時は簡易通知のみ
            logger.info(f"バッチ登録完了: result={type(result)}")
            self.statusBar().showMessage("バッチ登録完了", 5000)

    def _on_batch_registration_error(self, error_message: str) -> None:
        """Batch registration error signal handler（ProgressStateServiceに委譲 + QMessageBox）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_registration_error(error_message)

        # QMessageBoxはMainWindowで表示（UI要素のため）
        QMessageBox.critical(
            self, "バッチ登録エラー", f"バッチ登録中にエラーが発生しました:\n\n{error_message}"
        )

    def _on_worker_progress_updated(self, worker_id: str, progress: Any) -> None:
        """Worker progress update signal handler（ProgressStateServiceに委譲）"""
        if self.progress_state_service:
            self.progress_state_service.on_worker_progress_updated(worker_id, progress)
        else:
            logger.warning("ProgressStateService が初期化されていません - 進捗表示をスキップ")

    def _on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """Worker batch progress update signal handler（ProgressStateServiceに委譲）"""
        if self.progress_state_service:
            self.progress_state_service.on_worker_batch_progress(worker_id, current, total, filename)
        else:
            logger.warning("ProgressStateService が初期化されていません - 進捗表示をスキップ")

    # AnnotationService signal handlers (Phase 5 Stage 3)
    def _on_annotation_finished(self, result: Any) -> None:
        """単発アノテーション完了ハンドラ（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_annotation_finished(result, status_bar=self.statusBar())
        else:
            logger.info(f"アノテーション完了: {result}")
            self.statusBar().showMessage("アノテーション処理が完了しました", 5000)

    def _on_annotation_error(self, error_msg: str) -> None:
        """アノテーションエラーハンドラ（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_annotation_error(error_msg, status_bar=self.statusBar())
        else:
            logger.error(f"アノテーションエラー: {error_msg}")
            self.statusBar().showMessage(f"エラー: {error_msg}", 8000)

    def _on_batch_annotation_started(self, total_images: int) -> None:
        """バッチアノテーション開始ハンドラ（ProgressStateServiceに委譲）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_annotation_started(total_images)
        else:
            logger.warning("ProgressStateService が初期化されていません - 進捗表示をスキップ")

    def _on_batch_annotation_progress(self, processed: int, total: int) -> None:
        """バッチアノテーション進捗ハンドラ（ProgressStateServiceに委譲）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_annotation_progress(processed, total)
        else:
            logger.warning("ProgressStateService が初期化されていません - 進捗表示をスキップ")

    def _on_batch_annotation_finished(self, result: Any) -> None:
        """バッチアノテーション完了ハンドラ（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_batch_annotation_finished(
                result, status_bar=self.statusBar()
            )
        else:
            logger.info(f"バッチアノテーション完了: {result}")
            self.statusBar().showMessage("バッチアノテーション完了", 5000)

    def _on_model_sync_completed(self, sync_result: Any) -> None:
        """モデル同期完了ハンドラ（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_model_sync_completed(
                sync_result, status_bar=self.statusBar()
            )
        else:
            logger.info(f"モデル同期完了: {sync_result}")
            self.statusBar().showMessage("モデル同期完了", 5000)

    def cancel_current_pipeline(self) -> None:
        """現在のPipeline全体をキャンセル（PipelineControlService委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.cancel_current_pipeline()
        else:
            logger.warning("PipelineControlService未初期化 - Pipeline cancellation skipped")

    # Placeholder methods for UI actions - implement these based on your requirements
    def select_dataset_directory(self) -> Path | None:
        """データセットディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "データセットディレクトリを選択してください",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        return Path(directory) if directory else None

    def select_and_process_dataset(self) -> None:
        """データセット選択と自動処理開始（DatasetControllerに委譲）"""
        self._execute_dataset_registration()

    def register_images_to_db(self) -> None:
        """画像をデータベースに登録（DatasetControllerに委譲）"""
        self._execute_dataset_registration()

    def _execute_dataset_registration(self) -> None:
        """データセット登録の実行（共通メソッド）"""
        if self.dataset_controller:
            self.dataset_controller.select_and_register_images(
                dialog_callback=self.select_dataset_directory
            )
        else:
            logger.error("DatasetControllerが初期化されていません")
            QMessageBox.warning(
                self,
                "エラー",
                "DatasetControllerが初期化されていないため、データセット登録を開始できません。",
            )

    def load_images_from_db(self) -> None:
        """データベースから画像を読み込み、検索パイプラインを開始"""
        self._on_search_completed_start_thumbnail(True)

    def _resolve_optimal_thumbnail_data(
        self, image_metadata: list[dict[str, Any]]
    ) -> list[tuple[Path, int]]:
        """画像メタデータから最適なサムネイル表示用パスを解決（DataTransformService委譲）

        Args:
            image_metadata: 画像メタデータリスト

        Returns:
            list[tuple[Path, int]]: (画像パス, 画像ID) のタプルリスト
        """
        if self.data_transform_service:
            return self.data_transform_service.resolve_optimal_thumbnail_paths(image_metadata)

        # Fallback: Service未初期化時は元画像のみ使用
        return [(Path(metadata["stored_image_path"]), metadata["id"]) for metadata in image_metadata]



    def _setup_image_db_write_service(self) -> None:
        """ImageDBWriteServiceを作成してselected_image_details_widgetに注入

        Phase 3.4: DB操作分離パターンの実装
        """
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
        """SearchFilterService統合処理

        filterSearchPanelにSearchFilterServiceを注入して検索機能を有効化
        """
        if not hasattr(self, "filterSearchPanel") or not self.filterSearchPanel:
            logger.error("filterSearchPanel not available - SearchFilterService integration skipped")
            return

        if not self.db_manager:
            logger.error("db_manager not available - SearchFilterService integration skipped")
            return

        try:
            search_filter_service = self._create_search_filter_service()
            self.filterSearchPanel.set_search_filter_service(search_filter_service)

            if self.worker_service:
                self.filterSearchPanel.set_worker_service(self.worker_service)
                logger.info("SearchFilterService統合完了（WorkerService統合済み）")
            else:
                logger.info("SearchFilterService統合完了（同期検索モード）")

        except Exception as e:
            logger.error(f"SearchFilterService統合失敗: {e}", exc_info=True)
            logger.warning("検索機能は利用できませんが、その他の機能は正常に動作します")

    def _setup_phase24_services(self) -> None:
        """Service層の初期化と統合

        DataTransformService, ResultHandlerService, PipelineControlServiceを初期化。
        MainWindowから抽出されたロジックをService層に委譲する。
        """
        try:
            # DataTransformService初期化（Stage 4-1）
            logger.info("  - DataTransformService初期化中...")
            self.data_transform_service = DataTransformService(db_manager=self.db_manager)
            logger.info("  ✅ DataTransformService初期化成功")

            # ResultHandlerService初期化（Stage 4-2）
            logger.info("  - ResultHandlerService初期化中...")
            self.result_handler_service = ResultHandlerService(parent=self)
            logger.info("  ✅ ResultHandlerService初期化成功")

            # PipelineControlService初期化（Stage 4-3）
            logger.info("  - PipelineControlService初期化中...")
            self.pipeline_control_service = PipelineControlService(
                worker_service=self.worker_service,
                thumbnail_selector=self.thumbnail_selector,
                filter_search_panel=self.filterSearchPanel if hasattr(self, "filterSearchPanel") else None,
            )
            logger.info("  ✅ PipelineControlService初期化成功")

            # ProgressStateService初期化
            logger.info("  - ProgressStateService初期化中...")
            self.progress_state_service = ProgressStateService(status_bar=self.statusBar())
            logger.info("  ✅ ProgressStateService初期化成功")

            logger.info("Service層統合完了")

        except Exception as e:
            logger.error(f"Service層統合失敗: {e}", exc_info=True)
            logger.warning("一部のService機能は利用できませんが、その他の機能は正常に動作します")
            self.data_transform_service = None
            self.result_handler_service = None
            self.pipeline_control_service = None
            self.progress_state_service = None

    def open_settings(self) -> None:
        """設定ウィンドウを開く（SettingsControllerに委譲）"""
        if self.settings_controller:
            self.settings_controller.open_settings_dialog()
        else:
            logger.error("SettingsControllerが初期化されていません")
            QMessageBox.warning(
                self, "設定エラー", "SettingsControllerが初期化されていないため、設定を開けません。"
            )

    def start_annotation(self) -> None:
        """アノテーション処理を開始（AnnotationWorkflowController統合版）"""
        if not self.annotation_workflow_controller:
            QMessageBox.warning(
                self,
                "コントローラー未初期化",
                "AnnotationWorkflowControllerが初期化されていないため、アノテーション処理を開始できません。",
            )
            return

        # AnnotationWorkflowControllerに委譲
        self.annotation_workflow_controller.start_annotation_workflow(
            model_selection_callback=self._show_model_selection_dialog
        )

    def _show_model_selection_dialog(self, available_models: list[str]) -> str | None:
        """モデル選択ダイアログ表示（Callbackパターン）

        Args:
            available_models: 利用可能なモデル名リスト

        Returns:
            str | None: 選択されたモデル名、キャンセル時はNone
        """
        from PySide6.QtWidgets import QInputDialog

        selected_model, ok = QInputDialog.getItem(
            self,
            "モデル選択",
            "アノテーションに使用するモデルを選択してください:",
            available_models,
            0,  # デフォルト選択
            False,  # 編集不可
        )

        return selected_model if ok else None

    def export_data(self) -> None:
        """データセットエクスポート機能を開く（ExportControllerに委譲）"""
        if self.export_controller:
            self.export_controller.open_export_dialog()
        else:
            logger.error("ExportControllerが初期化されていません")
            QMessageBox.warning(
                self, "エラー", "ExportControllerが初期化されていないため、エクスポートを開始できません。"
            )
