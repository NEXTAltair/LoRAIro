# src/lorairo/gui/window/main_workspace_window.py

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QProgressDialog

from ...database.db_core import DefaultSessionLocal
from ...database.db_manager import ImageDatabaseManager
from ...database.db_repository import ImageRepository
from ...services.configuration_service import ConfigurationService
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..designer.MainWorkspaceWindow_ui import Ui_MainWorkspaceWindow
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.preview_detail_panel import PreviewDetailPanel
from ..widgets.thumbnail_enhanced import ThumbnailSelectorWidget


class MainWorkspaceWindow(QMainWindow, Ui_MainWorkspaceWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

    # シグナル
    dataset_loaded = Signal(str)  # dataset_path
    database_registration_completed = Signal(int)  # registered_count

    def __init__(self, parent=None):
        super().__init__(parent)

        # サービス初期化
        self.config_service = ConfigurationService()
        self.fsm = FileSystemManager()

        # データベース初期化
        image_repo = ImageRepository(session_factory=DefaultSessionLocal)
        self.db_manager = ImageDatabaseManager(image_repo, self.config_service, self.fsm)

        # ワーカーサービス初期化
        self.worker_service = WorkerService(self.db_manager, self.fsm, self)

        # 状態管理初期化
        self.dataset_state = DatasetStateManager(self)

        # 検索用プログレスダイアログ
        self.search_progress_dialog = None

        # サムネイル読み込み用プログレスダイアログ
        self.thumbnail_progress_dialog = None

        # DB登録用プログレスダイアログ
        self.registration_progress_dialog = None

        # UI設定
        self.setupUi(self)
        # 注意: setupUi()内でconnectSlotsByName()が呼ばれるため、
        # on_<objectname>_<signal>パターンのスロットが見つからない場合に警告が出る
        # これらの警告は正常動作に影響しない（手動でシグナル接続を行うため）
        self.setup_custom_widgets()
        self.setup_connections()

        # 初期状態設定
        self.initialize_state()

        logger.info("MainWorkspaceWindow initialized")

    def setup_custom_widgets(self) -> None:
        """カスタムウィジェットを設定"""
        # フィルター・検索パネル
        self.filter_search_panel = FilterSearchPanel(self.frameFilterSearchContent, self.dataset_state)
        self.verticalLayout_filterSearchContent.addWidget(self.filter_search_panel)

        # サムネイルセレクター（強化版）
        self.thumbnail_selector = ThumbnailSelectorWidget(self.frameThumbnailContent, self.dataset_state)
        self.verticalLayout_thumbnailContent.addWidget(self.thumbnail_selector)

        # プレビュー・詳細パネル
        self.preview_detail_panel = PreviewDetailPanel(
            self.framePreviewDetailContent, self.dataset_state, self.db_manager
        )
        self.verticalLayout_previewDetailContent.addWidget(self.preview_detail_panel)

        # スプリッターの初期サイズ設定
        self.splitterMainWorkArea.setSizes([300, 700, 400])  # フィルター:サムネイル:プレビュー

        # DB登録ボタンの初期化（確実に表示されるように設定）
        if hasattr(self, 'pushButtonRegisterImages'):
            self.pushButtonRegisterImages.setVisible(True)
            logger.info("DB登録ボタンを明示的に表示設定しました")
        
        # DB登録状況の初期表示
        self.update_db_status()
        
        # デバッグ: ボタン状態確認
        if hasattr(self, 'pushButtonRegisterImages'):
            logger.info(f"DB登録ボタン状態: enabled={self.pushButtonRegisterImages.isEnabled()}, visible={self.pushButtonRegisterImages.isVisible()}")
        else:
            logger.error("pushButtonRegisterImages が見つかりません！")

    def setup_connections(self) -> None:
        """シグナル・スロット接続を設定（カスタムシグナルのみ手動接続）"""
        # UI オブジェクトのシグナルは Qt の自動接続を使用（on_<objectname>_<signal> パターン）
        # ここではカスタムシグナルのみ手動接続
        
        # デバッグ: 手動でボタン接続も追加（Qt自動接続のフォールバック）
        if hasattr(self, 'pushButtonRegisterImages'):
            self.pushButtonRegisterImages.clicked.connect(self.on_pushButtonRegisterImages_clicked)
            logger.info("DB登録ボタンのシグナル接続を手動で設定しました")

        # データセット状態管理（カスタムシグナル）
        self.dataset_state.dataset_loaded.connect(self.handle_dataset_loaded)
        self.dataset_state.images_filtered.connect(self.handle_images_filtered)
        self.dataset_state.selection_changed.connect(self.handle_selection_changed)

        # ワーカーサービス（カスタムシグナル）
        self.worker_service.batch_registration_finished.connect(self.handle_batch_registration_finished)
        self.worker_service.worker_progress_updated.connect(self.handle_worker_progress_updated)
        self.worker_service.search_finished.connect(self.handle_search_finished)
        self.worker_service.search_error.connect(self.handle_search_error)
        self.worker_service.thumbnail_finished.connect(self.handle_thumbnail_finished)
        self.worker_service.thumbnail_error.connect(self.handle_thumbnail_error)

        # フィルター・検索パネル（カスタムシグナル）
        self.filter_search_panel.search_requested.connect(self.handle_search_requested)
        self.filter_search_panel.filter_cleared.connect(self.handle_filter_cleared)

    def initialize_state(self) -> None:
        """初期状態を設定"""
        # デフォルト設定の読み込み
        default_dataset_path = self.config_service.get_setting("directories", "dataset", "")
        if default_dataset_path and Path(default_dataset_path).exists():
            self.lineEditDatasetPath.setText(default_dataset_path)
            self.dataset_state.set_dataset_path(Path(default_dataset_path))
            # 既存データセットがある場合は自動読み込み
            self.load_dataset(Path(default_dataset_path))
            # 既存のDB画像データを読み込み
            self._refresh_dataset_from_db()
        else:
            # データセット未選択時のヘルプ表示
            self.labelStatus.setText("画像ディレクトリを選択して、データベースに登録してください")

    # === Qt Auto-Connected Slots (on_<objectname>_<signal> pattern) ===

    @Slot()
    def on_pushButtonSelectDataset_clicked(self) -> None:
        """データセット選択ボタンクリック（Qt自動接続）"""
        current_path = self.lineEditDatasetPath.text()
        initial_dir = current_path if current_path and Path(current_path).exists() else str(Path.home())

        dataset_path = QFileDialog.getExistingDirectory(
            self,
            "データセットディレクトリを選択",
            initial_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )

        if dataset_path:
            self.load_dataset(Path(dataset_path))

    @Slot()
    def on_actionOpenDataset_triggered(self) -> None:
        """データセット選択アクション（Qt自動接続）"""
        # ボタンと同じ処理
        self.on_pushButtonSelectDataset_clicked()

    @Slot()
    def on_pushButtonSettings_clicked(self) -> None:
        """設定ボタンクリック（Qt自動接続）"""
        # TODO: 設定ダイアログの実装
        QMessageBox.information(self, "情報", "設定画面は実装中です。")

    @Slot()
    def on_actionSettings_triggered(self) -> None:
        """設定アクション（Qt自動接続）"""
        # ボタンと同じ処理
        self.on_pushButtonSettings_clicked()

    @Slot()
    def on_pushButtonAnnotate_clicked(self) -> None:
        """アノテーションボタンクリック（Qt自動接続）"""
        if not self.dataset_state.selected_image_ids:
            QMessageBox.information(self, "情報", "アノテーション対象の画像を選択してください。")
            return

        # TODO: アノテーション処理の実装
        QMessageBox.information(self, "情報", "アノテーション機能は実装中です。")

    @Slot()
    def on_actionAnnotation_triggered(self) -> None:
        """アノテーションアクション（Qt自動接続）"""
        # ボタンと同じ処理
        self.on_pushButtonAnnotate_clicked()

    @Slot()
    def on_pushButtonExport_clicked(self) -> None:
        """エクスポートボタンクリック（Qt自動接続）"""
        if not self.dataset_state.has_images():
            QMessageBox.information(self, "情報", "エクスポート対象の画像がありません。")
            return

        # TODO: エクスポート処理の実装
        QMessageBox.information(self, "情報", "エクスポート機能は実装中です。")

    @Slot()
    def on_actionExport_triggered(self) -> None:
        """エクスポートアクション（Qt自動接続）"""
        # ボタンと同じ処理
        self.on_pushButtonExport_clicked()

    @Slot(bool)
    def on_actionToggleFilterPanel_toggled(self, visible: bool) -> None:
        """フィルターパネル表示切り替え（Qt自動接続）"""
        self.frameFilterSearchPanel.setVisible(visible)

    @Slot(bool)
    def on_actionTogglePreviewPanel_toggled(self, visible: bool) -> None:
        """プレビューパネル表示切り替え（Qt自動接続）"""
        self.framePreviewDetailPanel.setVisible(visible)

    @Slot()
    def on_actionSelectAll_triggered(self) -> None:
        """全選択アクション（Qt自動接続）"""
        if self.dataset_state.has_filtered_images():
            all_ids = [img.get("id") for img in self.dataset_state.filtered_images if "id" in img]
            self.dataset_state.set_selected_images(all_ids)

    @Slot()
    def on_actionDeselectAll_triggered(self) -> None:
        """全選択解除アクション（Qt自動接続）"""
        self.dataset_state.clear_selection()

    @Slot(int)
    def on_sliderThumbnailSize_valueChanged(self, size: int) -> None:
        """サムネイルサイズスライダー変更（Qt自動接続）"""
        self.handle_thumbnail_size_changed(size)

    @Slot(bool)
    def on_pushButtonLayoutMode_toggled(self, grid_mode: bool) -> None:
        """レイアウトモードボタン切り替え（Qt自動接続）"""
        self.handle_layout_mode_toggled(grid_mode)

    @Slot()
    def on_actionExit_triggered(self) -> None:
        """終了アクション（Qt自動接続）"""
        self.close()

    @Slot()
    def on_pushButtonRegisterImages_clicked(self) -> None:
        """DB登録ボタンクリック（Qt自動接続）"""
        logger.info("=== DB登録ボタンがクリックされました ===")
        dataset_path = self.dataset_state.dataset_path
        if not dataset_path or not dataset_path.exists():
            QMessageBox.warning(self, "警告", "有効なデータセットディレクトリを選択してください。")
            return

        # UI更新
        self.labelStatus.setText("画像をデータベースに登録中...")
        self.progressBarRegistration.setVisible(True)
        self.progressBarRegistration.setValue(0)
        self.pushButtonRegisterImages.setEnabled(False)

        # 【重要修正】FileSystemManagerを初期化
        self._initialize_filesystem_for_registration()

        # バッチ登録開始
        try:
            self._show_registration_progress_dialog()
            worker_id = self.worker_service.start_batch_registration(dataset_path)
            logger.info(f"バッチ登録ワーカー開始: {worker_id}")
        except Exception as e:
            logger.error(f"バッチ登録開始エラー: {e}")
            QMessageBox.critical(self, "エラー", f"データベース登録エラー:\n{e}")
            self._close_registration_progress_dialog()
            self.progressBarRegistration.setVisible(False)
            self.pushButtonRegisterImages.setEnabled(True)

    # === Dataset Management ===

    def load_dataset(self, dataset_path: Path) -> None:
        """データセットディレクトリを設定（自動DB登録機能復活）"""
        logger.info(f"データセットディレクトリ設定: {dataset_path}")

        # UI更新
        self.lineEditDatasetPath.setText(str(dataset_path))
        self.labelStatus.setText("データセットディレクトリを設定しました")

        # 状態更新
        self.dataset_state.set_dataset_path(dataset_path)

        # 設定保存
        self.config_service.update_setting("directories", "dataset", str(dataset_path))

        # DB登録状況を更新
        self.update_db_status()

        # 【復活機能】自動DB登録を開始（旧MainWindowと同じ動作）
        self.start_auto_batch_registration(dataset_path)

    def start_auto_batch_registration(self, dataset_path: Path) -> None:
        """自動バッチ登録開始（旧MainWindowの機能復活）"""
        logger.info(f"自動DB登録を開始: {dataset_path}")
        
        # UI更新（自動処理であることを表示）
        self.labelStatus.setText("新しい画像を自動検出してデータベースに登録中...")
        self.progressBarRegistration.setVisible(True)
        self.progressBarRegistration.setValue(0)
        self.pushButtonRegisterImages.setEnabled(False)

        # 【重要修正】FileSystemManagerを初期化
        self._initialize_filesystem_for_registration()

        # バッチ登録開始（手動登録と同じワーカーを使用）
        try:
            self._show_registration_progress_dialog()
            worker_id = self.worker_service.start_batch_registration(dataset_path)
            logger.info(f"自動バッチ登録ワーカー開始: {worker_id}")
        except Exception as e:
            logger.error(f"自動バッチ登録開始エラー: {e}")
            # エラー時は手動登録モードに戻す
            self._close_registration_progress_dialog()
            self.progressBarRegistration.setVisible(False)
            self.pushButtonRegisterImages.setEnabled(True)
            self.labelStatus.setText(f"自動登録エラー: {e} - 手動で「画像をDB登録」ボタンを押してください")

    @Slot(object)
    def handle_batch_registration_finished(self, result) -> None:
        """バッチ登録完了処理"""
        logger.info(f"バッチ登録完了: 登録={result.registered_count}, スキップ={result.skipped_count}")

        # UI更新
        self._close_registration_progress_dialog()
        self.progressBarRegistration.setVisible(False)
        self.pushButtonRegisterImages.setEnabled(True)

        # データセット画像情報を取得
        try:
            # 【修正】現在のディレクトリに含まれる全画像をDBから取得
            # 新規登録＋重複スキップされた画像の両方を表示する
            if self.dataset_state.dataset_path:
                logger.info(f"登録完了後の画像取得開始: {self.dataset_state.dataset_path}")
                # 現在のパスに関連する全画像を取得
                image_metadata = self._get_images_from_current_directory()
                logger.info(f"取得した画像メタデータ: {len(image_metadata)}件")
                
                # データセット状態更新
                self.dataset_state.set_dataset_images(image_metadata)
            else:
                logger.warning("データセットパスが設定されていません")
                self.dataset_state.set_dataset_images([])

            # ステータス更新（自動/手動を区別）
            if result.registered_count > 0:
                self.labelStatus.setText(
                    f"DB登録完了: {result.registered_count}件登録, {result.skipped_count}件スキップ"
                )
            else:
                self.labelStatus.setText(
                    f"DB登録完了: 新しい画像なし ({result.skipped_count}件は既に登録済み)"
                )

            # DB状況更新
            self.update_db_status()

            # シグナル発行
            self.database_registration_completed.emit(result.registered_count)

        except Exception as e:
            logger.error(f"バッチ登録後処理エラー: {e}")
            QMessageBox.warning(self, "警告", f"データセット情報取得エラー:\n{e}")

    def update_db_status(self) -> None:
        """データベース登録状況を更新"""
        try:
            if self.dataset_state.dataset_path:
                # データベース接続確認と画像数確認
                total_images = len(self.dataset_state.all_images) if self.dataset_state.all_images else 0
                self.labelDbInfo.setText(f"データベース: {total_images}件の画像が登録済み")

                # デバッグ情報をログに出力
                logger.info(f"DB状況更新 - パス: {self.dataset_state.dataset_path}, 画像数: {total_images}")

                # 登録ボタンの状態制御（表示と有効化）
                self.pushButtonRegisterImages.setVisible(True)
                self.pushButtonRegisterImages.setEnabled(bool(self.dataset_state.dataset_path))

                # 画像数が0の場合、DBから再取得を試行
                if total_images == 0 and self.dataset_state.dataset_path:
                    self._refresh_dataset_from_db()
            else:
                self.labelDbInfo.setText("データベース: データセット未選択")
                self.pushButtonRegisterImages.setVisible(True)
                self.pushButtonRegisterImages.setEnabled(False)
        except Exception as e:
            logger.warning(f"DB状況更新エラー: {e}")
            self.labelDbInfo.setText("データベース: 状況不明")
            self.pushButtonRegisterImages.setVisible(True)
            self.pushButtonRegisterImages.setEnabled(False)

    def _refresh_dataset_from_db(self) -> None:
        """データベースから画像データを再取得（現在のデータセットパスのみ）"""
        try:
            # 現在のデータセットパスが設定されていない場合は何もしない
            if not self.dataset_state.dataset_path:
                logger.info("データセットパスが未設定のため、DB検索をスキップします")
                self.dataset_state.set_dataset_images([])
                return
                
            current_path_str = str(self.dataset_state.dataset_path)
            logger.info(f"新しいデータセットパス選択: {current_path_str}")
            
            # 【修正】新しいパス選択時は一旦クリアし、DB登録後に再取得される
            # ただし、既にDB登録済みの画像があるかもしれないのでチェック
            logger.info("新しいパス選択のため、画像リストをクリアします（DB登録後に更新されます）")
            self.dataset_state.set_dataset_images([])
            
        except Exception as e:
            logger.error(f"データベースからの画像取得エラー: {e}")
            self.dataset_state.set_dataset_images([])

    # === Database Management ===

    # === State Management Event Handlers ===

    @Slot(int)
    def handle_dataset_loaded(self, image_count: int) -> None:
        """データセット読み込み完了処理"""
        self.labelThumbnailCount.setText(f"画像: {image_count}件")
        self.dataset_loaded.emit(str(self.dataset_state.dataset_path))

    @Slot(list)
    def handle_images_filtered(self, filtered_images: list) -> None:
        """画像フィルター処理"""
        self.labelThumbnailCount.setText(f"画像: {len(filtered_images)}件")

    @Slot(list)
    def handle_selection_changed(self, selected_image_ids: list) -> None:
        """選択変更処理"""
        selection_count = len(selected_image_ids)
        if selection_count > 0:
            self.labelStatus.setText(f"{selection_count}件の画像を選択中")
        else:
            self.labelStatus.setText("準備完了")

    @Slot(str, object)
    def handle_worker_progress_updated(self, worker_id: str, progress) -> None:
        """ワーカー進捗更新処理"""
        if worker_id.startswith("batch_reg"):
            # バッチ登録進捗をプログレスバーに反映
            self.progressBarRegistration.setValue(progress.percentage)
            if hasattr(progress, "status_message") and progress.status_message:
                self.labelStatus.setText(progress.status_message)
            
            # プログレスダイアログも更新
            if self.registration_progress_dialog:
                self.registration_progress_dialog.setValue(progress.percentage)
                if hasattr(progress, "status_message") and progress.status_message:
                    self.registration_progress_dialog.setLabelText(progress.status_message)
        elif worker_id.startswith("thumbnail"):
            # サムネイル読み込み進捗を反映
            if self.thumbnail_progress_dialog:
                self.thumbnail_progress_dialog.setValue(progress.percentage)
                if hasattr(progress, "status_message") and progress.status_message:
                    self.thumbnail_progress_dialog.setLabelText(progress.status_message)

    # === UI Control Actions ===

    @Slot(int)
    def handle_thumbnail_size_changed(self, size: int) -> None:
        """サムネイルサイズ変更処理"""
        self.dataset_state.set_thumbnail_size(size)

    @Slot(bool)
    def handle_layout_mode_toggled(self, grid_mode: bool) -> None:
        """レイアウトモード切り替え処理"""
        mode = "grid" if grid_mode else "list"
        self.dataset_state.set_layout_mode(mode)
        self.pushButtonLayoutMode.setText("Grid" if grid_mode else "List")

    # === Search and Filter Handlers ===

    @Slot(dict)
    def handle_search_requested(self, conditions: dict) -> None:
        """検索要求を処理（非同期対応）"""
        try:
            logger.info(f"検索条件受信: {conditions}")

            # 既存の検索は自動キャンセルされる（WorkerServiceで処理）
            self._close_search_progress_dialog()

            # プログレスダイアログを表示
            self._show_search_progress_dialog()

            # データベース検索のための条件をクリーンアップ
            db_conditions = {
                condition_key: condition_value
                for condition_key, condition_value in conditions.items()
                if not condition_key.startswith("_")
            }

            # UI状態の更新
            self.labelStatus.setText("検索中...")
            self.filter_search_panel.update_search_preview(0, "検索中...")

            # 非同期検索開始（条件を保存）
            self._pending_search_conditions = conditions
            worker_id = self.worker_service.start_search(db_conditions)
            logger.info(f"非同期検索開始: {worker_id}")

        except Exception as e:
            logger.error(f"検索開始中にエラーが発生しました: {e}", exc_info=True)
            self.labelStatus.setText("検索エラーが発生しました")
            self.filter_search_panel.update_search_preview(0)
            self._close_search_progress_dialog()
            QMessageBox.warning(self, "検索エラー", f"検索開始中にエラーが発生しました:\n{e!s}")

    @Slot()
    def handle_filter_cleared(self) -> None:
        """フィルタークリア要求を処理"""
        try:
            logger.info("フィルタークリア要求受信")

            # データベースから全画像を再取得
            self._refresh_dataset_from_db()

            # DatasetStateのフィルターをクリア
            self.dataset_state.clear_filter()

            # UI状態の更新
            self.labelStatus.setText("フィルターをクリアしました")

            # FilterSearchPanelのプレビューをクリア
            self.filter_search_panel.clear_search_preview()

        except Exception as e:
            logger.error(f"フィルタークリア処理中にエラーが発生しました: {e}", exc_info=True)
            self.labelStatus.setText("フィルタークリアエラーが発生しました")

    @Slot(object)
    def handle_search_finished(self, search_result) -> None:
        """検索完了処理"""
        try:
            logger.info(f"検索完了: {len(search_result.image_metadata)}件")

            # ワーカーIDはWorkerServiceで自動管理される

            # プログレスダイアログを閉じる
            self._close_search_progress_dialog()

            # 元の検索条件を取得
            original_conditions = getattr(self, "_pending_search_conditions", {})
            use_two_stage = original_conditions.get("_use_two_stage", False)

            if use_two_stage:
                # 2段階フィルタリングのフロントエンド処理を実行
                frontend_conditions = original_conditions.get("_frontend_conditions", {})
                if frontend_conditions:
                    image_metadata = self._apply_frontend_filtering(
                        search_result.image_metadata, frontend_conditions
                    )
                    logger.info(f"2段階フィルタリング後: {len(image_metadata)}件")
                else:
                    image_metadata = search_result.image_metadata
            else:
                image_metadata = search_result.image_metadata

            # UI状態の更新
            self.labelStatus.setText(f"検索完了: {len(image_metadata)}件が見つかりました")
            self.filter_search_panel.update_search_preview(len(image_metadata))

            # サムネイル読み込み開始（大量の場合は非同期で処理）
            if len(image_metadata) > 50:  # 閾値を設定
                # 大量の場合は非同期で処理
                logger.info(f"大量検索結果({len(image_metadata)}件) - 非同期サムネイル読み込みを開始")

                # DatasetStateに結果を適用（サムネイル読み込み前に）
                self.dataset_state.apply_filter_results(image_metadata, original_conditions)

                # サムネイル読み込み開始
                self._start_thumbnail_loading(image_metadata)
            else:
                # 少量の場合は同期的に読み込み
                logger.info(f"少量検索結果({len(image_metadata)}件) - 同期サムネイル読み込みを開始")

                # DatasetStateに結果を適用
                self.dataset_state.apply_filter_results(image_metadata, original_conditions)

                # 同期的にサムネイル読み込み（少量なので問題なし）
                # load_images_from_metadata は内部で閾値判定を行うため、直接呼び出す
                self.thumbnail_selector.load_images_from_metadata(image_metadata)

        except Exception as e:
            logger.error(f"検索完了処理中にエラーが発生しました: {e}", exc_info=True)
            self.labelStatus.setText("検索結果処理エラーが発生しました")
            self.filter_search_panel.update_search_preview(0)
            self._close_search_progress_dialog()

    @Slot(str)
    def handle_search_error(self, error_message: str) -> None:
        """検索エラー処理"""
        logger.error(f"検索エラー: {error_message}")

        # プログレスダイアログを閉じる
        self._close_search_progress_dialog()

        # UI状態の更新
        self.labelStatus.setText("検索エラーが発生しました")
        self.filter_search_panel.update_search_preview(0)

        # エラーダイアログ表示
        QMessageBox.warning(self, "検索エラー", f"検索中にエラーが発生しました:\n{error_message}")

        # ワーカーIDはWorkerServiceで自動管理される

    def _show_search_progress_dialog(self) -> None:
        """検索用プログレスダイアログを表示"""
        if self.search_progress_dialog:
            self.search_progress_dialog.close()

        self.search_progress_dialog = QProgressDialog("検索中...", "キャンセル", 0, 0, self)
        self.search_progress_dialog.setWindowTitle("画像検索")
        self.search_progress_dialog.setModal(False)  # 非モーダルに変更
        self.search_progress_dialog.setMinimumDuration(0)  # 即座に表示
        self.search_progress_dialog.setWindowModality(
            Qt.WindowModality.ApplicationModal
        )  # アプリケーションレベルでモーダル
        self.search_progress_dialog.canceled.connect(self._cancel_search)
        self.search_progress_dialog.show()

        # ダイアログを前面に表示
        self.search_progress_dialog.raise_()
        self.search_progress_dialog.activateWindow()

    def _close_search_progress_dialog(self) -> None:
        """検索用プログレスダイアログを閉じる"""
        if self.search_progress_dialog:
            try:
                # シグナル接続を解除してから閉じる
                self.search_progress_dialog.canceled.disconnect()
                self.search_progress_dialog.close()
                self.search_progress_dialog.deleteLater()
                self.search_progress_dialog = None
                logger.debug("検索プログレスダイアログを閉じました")
            except Exception as dialog_error:
                logger.warning(f"プログレスダイアログ終了エラー: {dialog_error}")
                self.search_progress_dialog = None

    def _cancel_search(self) -> None:
        """検索をキャンセル"""
        # WorkerServiceで現在のワーカーをキャンセル
        if self.worker_service.current_search_worker_id:
            self.worker_service.cancel_search(self.worker_service.current_search_worker_id)

        self.labelStatus.setText("検索がキャンセルされました")
        self.filter_search_panel.update_search_preview(0)

    def _apply_frontend_filtering(self, image_list: list[dict], frontend_conditions: dict) -> list[dict]:
        """フロントエンドフィルタリングを適用"""
        filtered_results = image_list

        # 日付範囲フィルタリング
        if "date_range" in frontend_conditions:
            min_timestamp, max_timestamp = frontend_conditions["date_range"]
            filtered_results = self._filter_by_date_range(filtered_results, min_timestamp, max_timestamp)
            logger.info(f"日付フィルタリング後: {len(filtered_results)}件")

        return filtered_results

    def _filter_by_date_range(
        self, image_list: list[dict], min_timestamp: int, max_timestamp: int
    ) -> list[dict]:
        """日付範囲でフィルタリング（フロントエンド処理）"""
        from datetime import datetime

        filtered_images = []
        for image_data in image_list:
            # created_at または updated_at を使用（DBから取得されるデータは常にdatetimeオブジェクト）
            date_value = image_data.get("created_at") or image_data.get("updated_at")

            # datetimeオブジェクトからタイムスタンプに変換
            if date_value is None:
                continue
            image_timestamp = int(date_value.timestamp())

            # 範囲内かチェック
            if min_timestamp <= image_timestamp <= max_timestamp:
                filtered_images.append(image_data)

        return filtered_images

    # === Thumbnail Loading ===

    def _start_thumbnail_loading(self, image_metadata: list[dict]) -> None:
        """サムネイル読み込み開始（非同期処理）"""
        try:
            # サムネイルサイズを取得
            thumbnail_size = self.dataset_state.thumbnail_size
            if isinstance(thumbnail_size, int):
                from PySide6.QtCore import QSize

                thumbnail_size = QSize(thumbnail_size, thumbnail_size)

            # 進捗ダイアログを表示
            self._show_thumbnail_progress_dialog()

            # 非同期サムネイル読み込み開始
            worker_id = self.worker_service.start_thumbnail_loading(image_metadata, thumbnail_size)
            logger.info(f"サムネイル読み込み開始: {len(image_metadata)}件 (ID: {worker_id})")

        except Exception as e:
            logger.error(f"サムネイル読み込み開始エラー: {e}", exc_info=True)
            self._close_thumbnail_progress_dialog()

    @Slot(object)
    def handle_thumbnail_finished(self, thumbnail_result) -> None:
        """サムネイル読み込み完了処理"""
        try:
            logger.info(f"サムネイル読み込み完了: {len(thumbnail_result.loaded_thumbnails)}件")

            # プログレスダイアログを閉じる
            self._close_thumbnail_progress_dialog()

            # サムネイルをUIに適用
            self.thumbnail_selector.load_thumbnails_from_result(thumbnail_result)

        except Exception as e:
            logger.error(f"サムネイル読み込み完了処理中にエラーが発生しました: {e}", exc_info=True)
            self._close_thumbnail_progress_dialog()

    @Slot(str)
    def handle_thumbnail_error(self, error_message: str) -> None:
        """サムネイル読み込みエラー処理"""
        logger.error(f"サムネイル読み込みエラー: {error_message}")

        # プログレスダイアログを閉じる
        self._close_thumbnail_progress_dialog()

        # エラーメッセージ表示
        QMessageBox.warning(
            self,
            "サムネイル読み込みエラー",
            f"サムネイル読み込み中にエラーが発生しました:\n{error_message}",
        )

    def _show_thumbnail_progress_dialog(self) -> None:
        """サムネイル読み込み用プログレスダイアログを表示"""
        if self.thumbnail_progress_dialog:
            self.thumbnail_progress_dialog.close()

        self.thumbnail_progress_dialog = QProgressDialog(
            "サムネイル読み込み中...", "キャンセル", 0, 100, self
        )
        self.thumbnail_progress_dialog.setWindowTitle("サムネイル読み込み")
        self.thumbnail_progress_dialog.setModal(False)
        self.thumbnail_progress_dialog.setMinimumDuration(0)
        self.thumbnail_progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.thumbnail_progress_dialog.canceled.connect(self._cancel_thumbnail_loading)
        self.thumbnail_progress_dialog.show()

        # ダイアログを前面に表示
        self.thumbnail_progress_dialog.raise_()
        self.thumbnail_progress_dialog.activateWindow()

    def _close_thumbnail_progress_dialog(self) -> None:
        """サムネイル読み込み用プログレスダイアログを閉じる"""
        if self.thumbnail_progress_dialog:
            try:
                self.thumbnail_progress_dialog.canceled.disconnect()
                self.thumbnail_progress_dialog.close()
                self.thumbnail_progress_dialog.deleteLater()
                self.thumbnail_progress_dialog = None
                logger.debug("サムネイル読み込みプログレスダイアログを閉じました")
            except Exception as dialog_error:
                logger.warning(f"サムネイル読み込みプログレスダイアログ終了エラー: {dialog_error}")
                self.thumbnail_progress_dialog = None

    def _cancel_thumbnail_loading(self) -> None:
        """サムネイル読み込みをキャンセル"""
        if self.worker_service.current_thumbnail_worker_id:
            self.worker_service.cancel_thumbnail_loading(self.worker_service.current_thumbnail_worker_id)

        self.labelStatus.setText("サムネイル読み込みがキャンセルされました")

    def _show_registration_progress_dialog(self) -> None:
        """DB登録用プログレスダイアログを表示"""
        if self.registration_progress_dialog:
            self.registration_progress_dialog.close()

        self.registration_progress_dialog = QProgressDialog(
            "画像をデータベースに登録中...", "キャンセル", 0, 100, self
        )
        self.registration_progress_dialog.setWindowTitle("データベース登録")
        self.registration_progress_dialog.setModal(False)
        self.registration_progress_dialog.setMinimumDuration(0)
        self.registration_progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.registration_progress_dialog.canceled.connect(self._cancel_registration)
        self.registration_progress_dialog.show()

        # ダイアログを前面に表示
        self.registration_progress_dialog.raise_()
        self.registration_progress_dialog.activateWindow()

    def _close_registration_progress_dialog(self) -> None:
        """DB登録用プログレスダイアログを閉じる"""
        if self.registration_progress_dialog:
            try:
                self.registration_progress_dialog.canceled.disconnect()
                self.registration_progress_dialog.close()
                self.registration_progress_dialog.deleteLater()
                self.registration_progress_dialog = None
                logger.debug("DB登録プログレスダイアログを閉じました")
            except Exception as dialog_error:
                logger.warning(f"DB登録プログレスダイアログ終了エラー: {dialog_error}")
                self.registration_progress_dialog = None

    def _cancel_registration(self) -> None:
        """DB登録キャンセル"""
        logger.info("ユーザーによるDB登録キャンセル要求")
        # TODO: ワーカーキャンセル機能を実装
        self._close_registration_progress_dialog()

    def _initialize_filesystem_for_registration(self) -> None:
        """DB登録用にFileSystemManagerを初期化"""
        try:
            # データベースディレクトリを取得または生成
            database_dir = self.config_service.get_database_directory()
            logger.info(f"設定から取得したデータベースディレクトリ: {database_dir}")

            if not database_dir or database_dir == Path("database"):
                # デフォルトまたは設定がない場合、database_base_dirを使用
                base_dir = Path(
                    self.config_service.get_setting("directories", "database_base_dir", "lorairo_data")
                )
                # プロジェクトディレクトリを自動生成
                from datetime import datetime
                project_name = f"batch_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                database_dir = base_dir / project_name
                logger.info(f"新しいプロジェクトディレクトリを作成: {database_dir}")
                # 設定を更新
                self.config_service.update_setting("directories", "database_dir", str(database_dir))
            else:
                logger.info(f"既存のプロジェクトディレクトリを使用: {database_dir}")

            # FileSystemManagerの初期化 - 基本的なディレクトリ構造のみ作成
            self.fsm.initialize(database_dir)
            logger.info(f"FileSystemManager初期化完了: {database_dir}")

        except Exception as e:
            logger.error(f"FileSystemManager初期化エラー: {e}")
            raise

    def _get_images_from_current_directory(self) -> list[dict]:
        """現在のディレクトリに含まれる画像をDBから取得"""
        try:
            if not self.dataset_state.dataset_path:
                return []
                
            current_path = self.dataset_state.dataset_path
            logger.info(f"ディレクトリ内画像を検索: {current_path}")
            
            # ディレクトリ内の画像ファイル一覧を取得
            image_files = list(self.fsm.get_image_files(current_path))
            if not image_files:
                logger.info("ディレクトリに画像ファイルが見つかりません")
                return []
                
            logger.info(f"ディレクトリ内画像ファイル: {len(image_files)}件")
            
            # 各画像ファイルに対してDBから重複チェック→メタデータ取得
            image_metadata = []
            for image_path in image_files:
                try:
                    # pHashベースの重複チェックでimage_idを取得
                    duplicate_result = self.db_manager.detect_duplicate_image(image_path)
                    if duplicate_result:
                        # 既存画像が見つかった場合、メタデータを取得
                        metadata = self.db_manager.get_image_metadata(duplicate_result)
                        if metadata:
                            image_metadata.append(metadata)
                            logger.debug(f"DB画像取得: {image_path.name} -> ID {duplicate_result}")
                except Exception as e:
                    logger.warning(f"画像メタデータ取得エラー: {image_path.name} - {e}")
                    
            logger.info(f"DB内の画像メタデータ取得完了: {len(image_metadata)}件")
            return image_metadata
            
        except Exception as e:
            logger.error(f"ディレクトリ内画像取得エラー: {e}")
            return []

    # === Window Management ===

    def closeEvent(self, event) -> None:
        """ウィンドウクローズイベント"""
        # プログレスダイアログを閉じる
        self._close_search_progress_dialog()
        self._close_thumbnail_progress_dialog()
        self._close_registration_progress_dialog()

        # アクティブワーカーのチェック
        if self.worker_service.get_active_worker_count() > 0:
            reply = QMessageBox.question(
                self,
                "確認",
                "処理中のタスクがあります。終了しますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            # ワーカーをキャンセル
            self.worker_service.cancel_all_workers()
            self.worker_service.wait_for_all_workers(5000)  # 5秒待機

        # 設定保存
        try:
            # ウィンドウサイズ・位置を保存（将来実装）
            pass
        except Exception as e:
            logger.warning(f"設定保存エラー: {e}")

        event.accept()

    # === Utility Methods ===

    def get_window_state_summary(self) -> dict:
        """ウィンドウ状態サマリーを取得"""
        return {
            "dataset_loaded": self.dataset_state.has_images(),
            "active_workers": self.worker_service.get_active_worker_count(),
            "selected_images": len(self.dataset_state.selected_image_ids),
            "filter_panel_visible": self.frameFilterSearchPanel.isVisible(),
            "preview_panel_visible": self.framePreviewDetailPanel.isVisible(),
            "db_image_count": len(self.dataset_state.all_images),
            "filtered_image_count": len(self.dataset_state.filtered_images),
        }
