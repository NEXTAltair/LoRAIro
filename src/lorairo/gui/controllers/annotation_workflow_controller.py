"""アノテーションワークフロー制御Controller

MainWindow.start_annotation()から抽出したアノテーションワークフロー制御ロジック。
DatasetControllerパターンに従い、依存性注入とcallbackパターンを使用。
"""

from collections.abc import Callable

from loguru import logger
from PySide6.QtWidgets import QMessageBox, QWidget

from lorairo.gui.services.worker_service import WorkerService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.selection_state_service import SelectionStateService


class AnnotationWorkflowController:
    """アノテーション処理ワークフロー制御Controller

    MainWindow.start_annotation()から抽出。
    画像選択→モデル選択→アノテーション実行のワークフロー全体を制御。

    DatasetControllerパターン準拠:
    - 依存性注入（constructor injection）
    - Callbackパターン（GUI操作はMainWindowに委譲）
    - サービス層へのビジネスロジック委譲
    """

    def __init__(
        self,
        worker_service: WorkerService,
        selection_state_service: SelectionStateService,
        config_service: ConfigurationService,
        parent: QWidget | None = None,
    ):
        """初期化

        Args:
            worker_service: Worker管理サービス（必須）
            selection_state_service: 画像選択状態管理サービス
            config_service: 設定管理サービス
            parent: 親ウィジェット（QMessageBox用、Noneも可）
        """
        self.worker_service = worker_service
        self.selection_state_service = selection_state_service
        self.config_service = config_service
        self.parent = parent

    def start_annotation_workflow(
        self,
        model_selection_callback: Callable[[list[str]], str | None],
    ) -> None:
        """アノテーションワークフロー実行

        ワークフロー:
        1. サービス検証
        2. 選択画像取得（SelectionStateService経由）
        3. 利用可能モデル取得（ConfigurationService経由）
        4. モデル選択ダイアログ表示（callback）
        5. バッチアノテーション開始（AnnotationService経由）

        Args:
            model_selection_callback: モデル選択ダイアログ表示callback
                利用可能モデルリストを受け取り、選択されたモデル名を返す。
                キャンセル時はNone。
        """
        try:
            # Step 1: サービス検証
            if not self._validate_services():
                return

            # Step 2: 選択画像取得
            image_paths = self._get_selected_image_paths()
            if not image_paths:
                return

            # Step 3: 利用可能モデル取得
            available_models = self._get_available_models()

            # Step 4: モデル選択ダイアログ表示（callback）
            selected_model = model_selection_callback(available_models)
            if not selected_model:
                logger.info("モデル選択がキャンセルされました")
                return

            logger.info(f"ユーザー選択モデル: {selected_model}")

            # Step 5: バッチアノテーション開始
            self._start_batch_annotation(image_paths, [selected_model])

        except Exception as e:
            error_msg = f"アノテーション処理の開始に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(
                    self.parent,
                    "アノテーション開始エラー",
                    error_msg,
                )

    def _validate_services(self) -> bool:
        """必須サービスの検証

        Returns:
            bool: 全サービスが有効な場合True
        """
        if not self.worker_service:
            logger.warning("WorkerServiceが初期化されていません")
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、アノテーション処理を実行できません。",
                )
            return False

        if not self.selection_state_service:
            logger.warning("SelectionStateServiceが初期化されていません")
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "SelectionStateServiceが初期化されていないため、画像を選択できません。",
                )
            return False

        return True

    def _get_selected_image_paths(self) -> list[str]:
        """選択画像パスリスト取得

        Returns:
            list[str]: 画像パスリスト。エラー時は空リスト。
        """
        try:
            image_paths = self.selection_state_service.get_selected_image_paths()
            logger.debug(f"選択画像を取得: {len(image_paths)}件")

            if not image_paths:
                logger.warning("画像パスリストが空です")
                if self.parent:
                    QMessageBox.information(
                        self.parent,
                        "画像データ取得エラー",
                        "選択された画像のパスを取得できませんでした。\n"
                        "データベースの状態を確認してください。",
                    )
                return []

            return image_paths

        except ValueError as e:
            # SelectionStateService.get_selected_image_paths()からのエラー
            logger.info(f"画像選択エラー: {e}")
            if self.parent:
                QMessageBox.information(
                    self.parent,
                    "画像未選択",
                    str(e),
                )
            return []

        except Exception as e:
            logger.error(f"画像パス取得中にエラー: {e}", exc_info=True)
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "画像データ取得エラー",
                    f"画像パスの取得中にエラーが発生しました: {e}",
                )
            return []

    def _get_available_models(self) -> list[str]:
        """利用可能なモデルリスト取得

        ConfigurationServiceから動的にモデルリストを取得します。

        Returns:
            list[str]: 利用可能なモデル名リスト
        """
        if not self.config_service:
            logger.warning("ConfigurationServiceが未設定")
            return []

        return self.config_service.get_available_annotation_models()

    def _start_batch_annotation(self, image_paths: list[str], models: list[str]) -> None:
        """バッチアノテーション開始

        Args:
            image_paths: 画像パスリスト
            models: モデル名リスト
        """
        try:
            logger.info(f"バッチアノテーション処理開始: {len(image_paths)}画像, {len(models)}モデル")

            # WorkerService.start_enhanced_batch_annotation()を呼び出し
            # Signal経由で進捗・完了・エラーがハンドラに通知される
            self.worker_service.start_enhanced_batch_annotation(
                image_paths=image_paths,
                models=models,
            )

            # 非ブロッキング通知
            status_msg = f"アノテーション処理を開始: {len(image_paths)}画像, モデル: {models[0]}"
            logger.info(status_msg)

        except Exception as e:
            error_msg = f"バッチアノテーション開始に失敗: {e}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(
                    self.parent,
                    "アノテーション実行エラー",
                    error_msg,
                )
            raise
