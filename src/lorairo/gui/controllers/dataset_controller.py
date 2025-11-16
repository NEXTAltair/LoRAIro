# src/lorairo/gui/controllers/dataset_controller.py
"""データセット選択・登録制御Controller

MainWindowの`register_images_to_db`および`select_and_process_dataset`メソッドから分離。
データセット選択→登録処理のビジネスロジックを担当。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QWidget

from ...utils.log import logger

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...gui.services.worker_service import WorkerService
    from ...storage.file_system import FileSystemManager


class DatasetController:
    """データセット選択・登録制御Controller

    Args:
        db_manager: データベース管理サービス
        file_system_manager: ファイルシステム管理サービス
        worker_service: 非同期Worker管理サービス
        parent: 親ウィンドウ（MainWindow）
    """

    def __init__(
        self,
        db_manager: ImageDatabaseManager | None,
        file_system_manager: FileSystemManager | None,
        worker_service: WorkerService | None,
        parent: QWidget | None = None,
    ) -> None:
        self.db_manager = db_manager
        self.file_system_manager = file_system_manager
        self.worker_service = worker_service
        self.parent = parent

    def select_and_register_images(
        self,
        dialog_callback: Callable[[], Path | None],
    ) -> None:
        """データセット選択→登録処理（統合メソッド）

        MainWindowのregister_images_to_db()とselect_and_process_dataset()
        両方から呼ばれる統合メソッド。

        Args:
            dialog_callback: MainWindowでQFileDialogを実行するcallback関数
        """
        logger.info("統合ワークフロー: データセット選択と自動処理開始")

        # 1. ディレクトリ選択（MainWindowでQFileDialog実行）
        directory = dialog_callback()

        if not directory:
            logger.info("ディレクトリ選択がキャンセルされました")
            return

        logger.info(f"ディレクトリ選択完了: {directory}")

        # 2. バッチ登録処理開始
        self._start_batch_registration(directory)

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
                    "WorkerServiceが初期化されていないため、バッチ登録を開始できません。",
                )
            return False

        if not self.file_system_manager:
            logger.warning("FileSystemManagerが初期化されていません")
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "FileSystemManagerが初期化されていないため、バッチ登録処理を実行できません。",
                )
            return False

        return True

    def _start_batch_registration(self, directory: Path) -> None:
        """バッチ登録処理を開始（内部メソッド）

        Args:
            directory: 選択されたデータセットディレクトリ
        """
        # Step 1: サービス検証
        if not self._validate_services():
            return

        try:
            # FileSystemManagerの初期化（新しいメソッド使用）
            output_dir = self.file_system_manager.initialize_from_dataset_selection(directory)
            logger.info(f"FileSystemManager初期化完了: output_dir={output_dir}")

            # バッチ登録開始（初期化済みFileSystemManagerを渡す）
            worker_id = self.worker_service.start_batch_registration_with_fsm(
                directory, self.file_system_manager
            )

            if worker_id:
                logger.info(f"バッチ登録開始: worker_id={worker_id}, directory={directory}")
            else:
                logger.error("バッチ登録の開始に失敗しました")

        except Exception as e:
            error_msg = f"データセット登録の開始に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(self.parent, "バッチ登録エラー", error_msg)
