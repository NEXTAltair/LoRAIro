# src/lorairo/gui/window/main_window.py

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.model_selection_service import ModelSelectionService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
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

    # ウィジェット属性の型定義（Qt Designerで生成）
    filterSearchPanel: FilterSearchPanel  # Qt Designer生成
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
        """カスタムウィジェットを設定（Qt Designer生成ウィジェット直接使用版）"""

        logger.info("🔍 カスタムウィジェット設定開始")

        # Qt Designer生成済みウィジェットの検証
        if not hasattr(self, "filterSearchPanel"):
            logger.error("❌ filterSearchPanel not found - Qt Designer UI generation failed")
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定", RuntimeError("filterSearchPanel attribute missing from setupUi()")
            )
            return
        if not isinstance(self.filterSearchPanel, FilterSearchPanel):
            logger.error(
                f"❌ filterSearchPanel type mismatch - expected FilterSearchPanel, got {type(self.filterSearchPanel)}"
            )
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定",
                RuntimeError(f"filterSearchPanel type validation failed: {type(self.filterSearchPanel)}"),
            )
            return

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
        """その他のカスタムウィジェット設定"""

        # ThumbnailSelectorWidget設定
        if hasattr(self, "thumbnailSelectorWidget") and self.thumbnailSelectorWidget:
            try:
                # ThumbnailSelectorWidgetの追加設定があればここに実装
                self.thumbnail_selector = self.thumbnailSelectorWidget
                logger.info("✅ ThumbnailSelectorWidget設定完了")
            except Exception as e:
                logger.error(f"ThumbnailSelectorWidget設定エラー: {e}")

        # ImagePreviewWidget設定
        if hasattr(self, "imagePreviewWidget") and self.imagePreviewWidget:
            try:
                # ImagePreviewWidgetの追加設定があればここに実装
                self.image_preview_widget = self.imagePreviewWidget
                logger.info("✅ ImagePreviewWidget設定完了")
            except Exception as e:
                logger.error(f"ImagePreviewWidget設定エラー: {e}")

        # その他のウィジェット設定...
        logger.debug("その他のカスタムウィジェット設定完了")

    def _setup_responsive_splitter(self) -> None:
        """レスポンシブスプリッターサイズ設定"""
        try:
            # 現在のウィンドウサイズを取得
            window_width = self.width()
            if window_width < 800:  # 最小サイズ保証
                window_width = 1400  # デフォルト幅

            # 新しい比率: 左20%, 中央55%, 右25%
            left_ratio = 0.20
            center_ratio = 0.55  # サムネイルエリアを拡大
            right_ratio = 0.25

            # 最小・最大サイズ制限
            min_left = 280
            max_left = 400
            min_center = 500  # サムネイル表示に必要な最小幅
            min_right = 350

            # 計算されたサイズ
            calc_left = int(window_width * left_ratio)
            calc_center = int(window_width * center_ratio)
            calc_right = int(window_width * right_ratio)

            # 制限適用
            final_left = max(min_left, min(max_left, calc_left))
            final_center = max(min_center, calc_center)
            final_right = max(min_right, calc_right)

            # サイズ適用
            self.splitterMainWorkArea.setSizes([final_left, final_center, final_right])

            logger.debug(
                f"スプリッターサイズ設定: {final_left}:{final_center}:{final_right} "
                f"(ウィンドウ幅: {window_width}px)"
            )

        except Exception as e:
            # フォールバック: 改善された固定サイズ
            logger.warning(f"動的サイズ計算失敗、フォールバック使用: {e}")
            self.splitterMainWorkArea.setSizes([320, 800, 380])  # 改善された比率

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

            # Phase 2: Sequential Worker Pipeline 統合シグナル接続
            self._setup_worker_pipeline_signals()

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

    def _setup_worker_pipeline_signals(self) -> None:
        """WorkerService pipeline signal connections setup"""
        if not self.worker_service:
            logger.warning("WorkerService not available - pipeline signals not connected")
            return

        try:
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

        except Exception as e:
            logger.error(f"Pipeline signals connection failed: {e}", exc_info=True)

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

        # WorkerService存在チェック（型安全性）
        if not self.worker_service:
            logger.error("WorkerService not available - thumbnail loading skipped")
            return

        # ThumbnailSelector存在チェック
        if not self.thumbnail_selector:
            logger.error("ThumbnailSelector not available - thumbnail loading skipped")
            return

        try:
            # サムネイルレイアウト用の image_data を事前設定
            image_data = [
                (Path(item["stored_image_path"]), item["id"])
                for item in search_result.image_metadata
                if "stored_image_path" in item and "id" in item
            ]
            self.thumbnail_selector.image_data = image_data
            logger.info(f"ThumbnailSelectorWidget.image_data set: {len(image_data)} items")

            # サムネイルサイズ取得（フォールバック付き）
            thumbnail_size = getattr(self.thumbnail_selector, "thumbnail_size", None)
            if not thumbnail_size or thumbnail_size.isEmpty():
                from PySide6.QtCore import QSize

                thumbnail_size = QSize(128, 128)
                logger.info("Using default thumbnail size: 128x128")

            # ThumbnailWorker開始 - 修正されたパラメータで呼び出し
            worker_id = self.worker_service.start_thumbnail_load(search_result, thumbnail_size)
            logger.info(
                f"ThumbnailWorker started automatically after search: {worker_id} "
                f"({len(search_result.image_metadata)} images, size={thumbnail_size.width()}x{thumbnail_size.height()})"
            )

        except Exception as e:
            logger.error(f"Failed to start automatic thumbnail loading: {e}")
            # エラー発生時もUI状態をクリア
            if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
                self.thumbnail_selector.clear_thumbnails()

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
            if hasattr(self, "filterSearchPanel") and hasattr(
                self.filterSearchPanel, "hide_progress_after_completion"
            ):
                self.filterSearchPanel.hide_progress_after_completion()

        except Exception as e:
            logger.error(f"Failed to update ThumbnailSelectorWidget: {e}", exc_info=True)

    def _on_pipeline_search_started(self, worker_id: str) -> None:
        """Pipeline検索フェーズ開始時の進捗表示"""
        if hasattr(self, "filterSearchPanel") and hasattr(
            self.filterSearchPanel, "update_pipeline_progress"
        ):
            self.filterSearchPanel.update_pipeline_progress("検索中...", 0.0, 0.3)

    def _on_pipeline_thumbnail_started(self, worker_id: str) -> None:
        """Pipelineサムネイル生成フェーズ開始時の進捗表示"""
        if hasattr(self, "filterSearchPanel") and hasattr(
            self.filterSearchPanel, "update_pipeline_progress"
        ):
            self.filterSearchPanel.update_pipeline_progress("サムネイル読込中...", 0.3, 1.0)

    def _on_pipeline_search_error(self, error_message: str) -> None:
        """Pipeline検索エラー時の処理（検索結果破棄）"""
        logger.error(f"Pipeline search error: {error_message}")
        if hasattr(self, "filterSearchPanel") and hasattr(self.filterSearchPanel, "handle_pipeline_error"):
            self.filterSearchPanel.handle_pipeline_error("search", {"message": error_message})
        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()

    def _on_pipeline_thumbnail_error(self, error_message: str) -> None:
        """Pipelineサムネイル生成エラー時の処理（検索結果破棄）"""
        logger.error(f"Pipeline thumbnail error: {error_message}")
        if hasattr(self, "filterSearchPanel") and hasattr(self.filterSearchPanel, "handle_pipeline_error"):
            self.filterSearchPanel.handle_pipeline_error("thumbnail", {"message": error_message})
        # 検索結果破棄（要求仕様通り）
        if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
            self.thumbnail_selector.clear_thumbnails()
        # エラー時もプログレスバーを非表示
        if hasattr(self, "filterSearchPanel") and hasattr(
            self.filterSearchPanel, "hide_progress_after_completion"
        ):
            self.filterSearchPanel.hide_progress_after_completion()

    def _on_batch_registration_started(self, worker_id: str) -> None:
        """Batch registration started signal handler"""
        logger.info(f"バッチ登録開始: worker_id={worker_id}")

        # UI feedback - show user that processing has started
        try:
            self.statusBar().showMessage("データベース登録処理を開始しています...")
        except Exception as e:
            logger.debug(f"Status bar update failed: {e}")

        # TODO: プログレスバーなどのUI進捗表示をバッチ登録に追加

    def _on_batch_registration_finished(self, result: Any) -> None:
        """Batch registration finished signal handler"""
        logger.info(f"バッチ登録完了: result={type(result)}")

        # Clear statusbar processing message
        try:
            self.statusBar().clearMessage()
        except Exception as e:
            logger.debug(f"Status bar clear failed: {e}")

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
                if hasattr(self, "database_registration_completed"):
                    self.database_registration_completed.emit(registered)

                QMessageBox.information(self, "バッチ登録完了", success_message)
                logger.info(f"バッチ登録統計: 登録={registered}, スキップ={skipped}, エラー={errors}")

            else:
                # Fallback for unexpected result format
                logger.warning(f"Unexpected batch registration result format: {result}")
                QMessageBox.information(
                    self,
                    "バッチ登録完了",
                    f"バッチ登録が完了しましたが、詳細情報を取得できませんでした。\n結果: {result}",
                )

        except Exception as e:
            # Proper error logging instead of silent failure
            logger.error(f"バッチ登録完了処理中にエラー: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "バッチ登録完了",
                f"バッチ登録は完了しましたが、結果の表示中にエラーが発生しました:\n{e}",
            )

    def _on_batch_registration_error(self, error_message: str) -> None:
        """Batch registration error signal handler"""
        QMessageBox.critical(
            self, "バッチ登録エラー", f"バッチ登録中にエラーが発生しました:\n\n{error_message}"
        )

    def _on_worker_progress_updated(self, worker_id: str, progress: Any) -> None:
        """Worker progress update signal handler"""
        try:
            # Extract progress information
            if hasattr(progress, "current") and hasattr(progress, "total"):
                current = progress.current
                total = progress.total
                percentage = int((current / total) * 100) if total > 0 else 0

                # Update status bar with progress
                status_message = f"処理中... {current}/{total} ({percentage}%)"
                self.statusBar().showMessage(status_message)

                logger.debug(f"ワーカー進捗更新: {worker_id} - {current}/{total} ({percentage}%)")

            else:
                logger.debug(f"ワーカー進捗更新: {worker_id} - {progress}")

        except Exception as e:
            logger.warning(f"進捗更新処理エラー: {e}")

    def _on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """Worker batch progress update signal handler"""
        try:
            percentage = int((current / total) * 100) if total > 0 else 0

            # Update status bar with detailed batch progress
            status_message = f"バッチ処理中... {current}/{total} ({percentage}%) - {filename}"
            self.statusBar().showMessage(status_message)

            logger.debug(f"バッチ進捗更新: {worker_id} - {current}/{total} ({percentage}%) - {filename}")

        except Exception as e:
            logger.warning(f"バッチ進捗更新処理エラー: {e}")

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
                self.worker_service.cancel_thumbnail_load(self.worker_service.current_thumbnail_worker_id)
                logger.info("Thumbnail worker cancelled in pipeline")

            # キャンセル時の結果破棄（要求仕様通り）
            if self.thumbnail_selector and hasattr(self.thumbnail_selector, "clear_thumbnails"):
                self.thumbnail_selector.clear_thumbnails()

            # キャンセル時もプログレスバーを非表示
            if hasattr(self, "filterSearchPanel") and hasattr(
                self.filterSearchPanel, "hide_progress_after_completion"
            ):
                self.filterSearchPanel.hide_progress_after_completion()

            logger.info("Pipeline cancellation completed")

        except Exception as e:
            logger.error(f"Pipeline cancellation failed: {e}", exc_info=True)

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
        """データセット選択と自動処理開始（統合ワークフロー）

        ユーザーがpushButtonSelectDatasetをクリックした際に実行される統合ワークフロー。
        ディレクトリ選択後、自動的にデータベース登録・サムネイル生成処理を開始する。

        処理フロー:
        1. ディレクトリ選択ダイアログ表示
        2. 選択後、バッチ登録処理を自動開始
        3. DatabaseRegistrationWorker起動
        4. サムネイル生成・検索機能有効化
        """
        logger.info("統合ワークフロー: データセット選択と自動処理開始")

        # ディレクトリ選択実行
        directory = self.select_dataset_directory()

        if directory:
            logger.info(f"ディレクトリ選択完了: {directory}")
            logger.info("自動的にバッチ登録処理を開始します...")

            # 既存の成功パターン（register_images_to_db）と同じ処理フローを実行
            self._start_batch_registration(directory)
        else:
            logger.info("ディレクトリ選択がキャンセルされました")

    def _start_batch_registration(self, directory: Path) -> None:
        """バッチ登録処理を開始（内部メソッド）"""
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
                self._handle_critical_initialization_failure("FileSystemManager", RuntimeError(error_msg))
                return

            # 選択されたディレクトリの親ディレクトリに出力する
            output_dir = directory.parent / "lorairo_output"
            self.file_system_manager.initialize(output_dir)

            # バッチ登録開始（初期化済みFileSystemManagerを渡す）
            worker_id = self.worker_service.start_batch_registration_with_fsm(
                directory, self.file_system_manager
            )
            if worker_id:
                logger.info(f"バッチ登録開始: worker_id={worker_id}, directory={directory}")
            else:
                logger.error("バッチ登録の開始に失敗しました")
        except Exception as e:
            QMessageBox.critical(self, "バッチ登録エラー", f"データセット登録の開始に失敗しました: {e}")

    def register_images_to_db(self) -> None:
        """画像をデータベースに登録（完全なワークフロー：ディレクトリ選択 + バッチ登録開始）"""
        directory = self.select_dataset_directory()
        if directory:
            self._start_batch_registration(directory)

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

    def resizeEvent(self, event) -> None:
        """ウィンドウリサイズイベント - スプリッターサイズを動的調整"""
        try:
            super().resizeEvent(event)

            # スプリッターが存在し、初期化が完了している場合のみ調整
            if hasattr(self, "splitterMainWorkArea") and self.splitterMainWorkArea is not None:
                # リサイズ完了後に調整（イベントループで遅延実行）
                QTimer.singleShot(50, self._adjust_splitter_on_resize)

        except Exception as e:
            logger.warning(f"リサイズイベント処理エラー: {e}")

    def _adjust_splitter_on_resize(self) -> None:
        """リサイズ後のスプリッター調整（遅延実行用）"""
        try:
            # 現在のサイズが変更されている場合のみ再計算
            current_width = self.width()

            # 小さすぎる場合はスキップ（初期化中の可能性）
            if current_width < 600:
                return

            self._setup_responsive_splitter()
            logger.debug(f"リサイズ後スプリッター調整完了: {current_width}px")

        except Exception as e:
            logger.warning(f"リサイズ後の調整エラー: {e}")

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
        """SearchFilterService統合処理（シンプル・直接的アプローチ）

        filterSearchPanelにSearchFilterServiceを注入して検索機能を有効化
        """
        # 前提条件チェック
        if not hasattr(self, "filterSearchPanel") or not self.filterSearchPanel:
            logger.error("❌ filterSearchPanel not available - SearchFilterService integration skipped")
            return

        if not self.db_manager:
            logger.error("❌ db_manager not available - SearchFilterService integration skipped")
            return

        logger.info(f"SearchFilterService注入開始: filterSearchPanel(id={id(self.filterSearchPanel)})")

        try:
            # SearchFilterService作成
            logger.info("SearchFilterService作成中...")
            search_filter_service = self._create_search_filter_service()

            if not search_filter_service:
                raise RuntimeError("SearchFilterService作成失敗")
            logger.info(f"SearchFilterService作成成功: {type(search_filter_service)}")

            # SearchFilterService注入
            logger.info("SearchFilterService注入実行...")
            self.filterSearchPanel.set_search_filter_service(search_filter_service)

            # 注入検証
            injected_service = getattr(self.filterSearchPanel, "search_filter_service", None)
            if injected_service is None:
                raise RuntimeError("SearchFilterService注入後もNone")
            if injected_service is not search_filter_service:
                raise RuntimeError("SearchFilterService注入後のインスタンス不一致")

            logger.info("SearchFilterService注入検証: 成功")

            # WorkerService統合（オプショナル）
            if self.worker_service:
                logger.info("WorkerService統合中...")
                self.filterSearchPanel.set_worker_service(self.worker_service)

                worker_service_check = getattr(self.filterSearchPanel, "worker_service", None)
                if worker_service_check:
                    logger.info("WorkerService統合成功")
                else:
                    logger.warning("WorkerService統合失敗 - 非同期検索は利用できません")
            else:
                logger.warning("WorkerService not available - 同期検索モードで動作")

            # 最終確認
            final_search_service = getattr(self.filterSearchPanel, "search_filter_service", None)
            final_worker_service = getattr(self.filterSearchPanel, "worker_service", None)

            logger.info(
                f"SearchFilterService統合完了 - "
                f"SearchFilterService: {final_search_service is not None}, "
                f"WorkerService: {final_worker_service is not None}"
            )

        except Exception as e:
            logger.error(f"SearchFilterService統合失敗: {e}", exc_info=True)
            logger.warning("検索機能は利用できませんが、その他の機能は正常に動作します")

    def open_settings(self) -> None:
        """設定ウィンドウを開く"""
        try:
            from PySide6.QtWidgets import QDialog

            from ...gui.designer.ConfigurationWindow_ui import Ui_ConfigurationWindow

            # 設定ダイアログの作成
            config_dialog = QDialog(self)
            config_ui = Ui_ConfigurationWindow()
            config_ui.setupUi(config_dialog)

            # ダイアログのタイトル設定
            config_dialog.setWindowTitle("設定")
            config_dialog.setModal(True)

            # 現在の設定値の読み込み（ConfigurationServiceが利用可能な場合）
            if self.config_service:
                # TODO: 設定値をUIに反映する処理をここに追加
                logger.info("設定ダイアログに現在の設定値を読み込み")
            else:
                logger.warning("ConfigurationServiceが利用できないため、デフォルト設定で表示")

            # ダイアログを表示
            result = config_dialog.exec()

            if result == QDialog.DialogCode.Accepted:
                # OK が押された場合、設定を保存
                if self.config_service:
                    # TODO: UIから設定値を取得して保存する処理をここに追加
                    logger.info("設定が更新されました")
                else:
                    logger.warning("ConfigurationServiceが利用できないため、設定を保存できませんでした")
            else:
                logger.info("設定ダイアログがキャンセルされました")

        except Exception as e:
            error_msg = f"設定ウィンドウの表示に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "設定エラー", error_msg)

    def start_annotation(self) -> None:
        """アノテーション処理を開始"""
        try:
            # WorkerServiceの存在確認
            if not self.worker_service:
                QMessageBox.warning(
                    self,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、アノテーション処理を開始できません。",
                )
                return

            # TODO: 実際の実装では、選択された画像とモデルを取得する必要があります
            # 現在は仮実装として空のリストを使用
            images = []  # 実際には選択された画像リストを取得
            phash_list = []  # 実際にはpHashリストを取得
            models = ["gpt-4o-mini"]  # 実際には選択されたモデルリストを取得

            if not images:
                QMessageBox.information(
                    self,
                    "画像未選択",
                    "アノテーション処理を行う画像を選択してください。",
                )
                return

            if not models:
                QMessageBox.warning(
                    self,
                    "モデル未選択",
                    "アノテーション処理に使用するモデルを選択してください。",
                )
                return

            # アノテーション処理開始
            worker_id = self.worker_service.start_annotation(images, phash_list, models)

            if worker_id:
                logger.info(
                    f"アノテーション処理開始: {len(images)}画像, {len(models)}モデル (ID: {worker_id})"
                )
                QMessageBox.information(
                    self,
                    "アノテーション開始",
                    f"アノテーション処理を開始しました。\n画像: {len(images)}件\nモデル: {', '.join(models)}",
                )
            else:
                logger.error("アノテーション処理の開始に失敗しました")
                QMessageBox.critical(
                    self,
                    "アノテーション開始エラー",
                    "アノテーション処理の開始に失敗しました。",
                )

        except Exception as e:
            error_msg = f"アノテーション処理の開始に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "アノテーションエラー", error_msg)

    def export_data(self) -> None:
        """データセットエクスポート機能を開く"""
        try:
            # Get current image selection
            current_image_ids = self._get_current_selected_images()

            if not current_image_ids:
                QMessageBox.warning(
                    self,
                    "エクスポート",
                    "エクスポートする画像が選択されていません。\n"
                    "フィルタリング条件を設定して画像を表示するか、\n"
                    "サムネイル表示で画像を選択してください。",
                )
                return

            logger.info(f"データセットエクスポート開始: {len(current_image_ids)}画像")

            # Create and show export dialog
            from ..widgets.dataset_export_widget import DatasetExportWidget

            export_dialog = DatasetExportWidget(
                service_container=self.service_container, initial_image_ids=current_image_ids, parent=self
            )

            # Connect export completion signal
            export_dialog.export_completed.connect(self._on_export_completed)

            # Show as modal dialog
            export_dialog.exec()

        except Exception as e:
            error_msg = f"データセットエクスポート画面の表示に失敗しました: {e!s}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "エラー", f"エクスポート機能の起動に失敗しました。\n\n{e!s}")

    def _on_export_completed(self, path: str) -> None:
        """Export completion handler"""
        logger.info(f"データセットエクスポート完了: {path}")

    def _get_current_selected_images(self) -> list[int]:
        """現在表示・選択中の画像IDリストを取得"""
        try:
            # First priority: explicitly selected images
            if self.dataset_state_manager and self.dataset_state_manager.selected_image_ids:
                selected_ids = self.dataset_state_manager.selected_image_ids
                logger.debug(f"選択画像を使用: {len(selected_ids)}件")
                return selected_ids

            # Second priority: all currently filtered/displayed images
            if self.dataset_state_manager and self.dataset_state_manager.has_filtered_images():
                filtered_images = self.dataset_state_manager.filtered_images
                filtered_ids = [img.get("id") for img in filtered_images if img.get("id")]
                logger.debug(f"表示中の画像を使用: {len(filtered_ids)}件")
                return filtered_ids

            # No images available
            logger.warning("エクスポート可能な画像が見つかりません")
            return []

        except Exception as e:
            logger.error(f"選択画像の取得に失敗: {e}")
            return []


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
