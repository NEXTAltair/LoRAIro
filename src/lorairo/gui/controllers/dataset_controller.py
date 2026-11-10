# src/lorairo/gui/controllers/dataset_controller.py
"""データセット選択・登録制御Controller

MainWindowの`select_and_process_dataset`メソッドから分離。
データセット選択→登録処理のビジネスロジックを担当。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ...database.repository.dataset import DatasetRepository
from ...utils.log import logger
from ..message_box import show_critical, show_information, show_warning
from ..widgets.dataset_select_dialog import DatasetSelection

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...filesystem import FileSystemManager
    from ...gui.services.worker_service import WorkerService
    from ...services.dataset_import_service import DatasetImportResult


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

        # Kohya 取り込みの完了/失敗をポップアップで通知する (WorkerService は GUI スレッドで配信)
        if worker_service is not None:
            worker_service.dataset_import_finished.connect(self._on_dataset_import_finished)
            worker_service.dataset_import_error.connect(self._on_dataset_import_error)

    def select_and_register_images(
        self,
        dialog_callback: Callable[[], DatasetSelection | Path | None],
    ) -> None:
        """データセット選択→登録処理（統合メソッド）

        MainWindowのselect_and_process_dataset()から呼ばれる統合メソッド。

        Args:
            dialog_callback: MainWindowでダイアログを実行するcallback関数。
                Kohya 取り込みを選んだ DatasetSelection ならKohya取り込み、それ以外の
                DatasetSelection または Path なら従来の画像登録を行う。
        """
        logger.info("統合ワークフロー: データセット選択と自動処理開始")

        # 1. ディレクトリ選択（MainWindowでQFileDialog実行）
        selection = dialog_callback()

        if not selection:
            logger.info("ディレクトリ選択がキャンセルされました")
            return

        if isinstance(selection, DatasetSelection):
            if selection.is_kohya_import:
                logger.info(f"Kohya取り込み選択完了: {selection.directory}")
                self._start_dataset_import(selection)
                return
            directory = selection.directory
            folder_tags = dict(selection.folder_tags)
        else:
            directory = selection
            folder_tags = {}

        logger.info(f"ディレクトリ選択完了: {directory}")

        # 2. バッチ登録処理開始
        self._start_batch_registration(directory, folder_tags)

    def get_parent_versions_by_dataset(self) -> dict[str, list[tuple[int, str]]]:
        """既存データセットごとの版一覧 `(version_id, version_name)` を取得する。

        ダイアログ自身は DB に直接アクセスしないため、Controller 側で取得して渡す (#1478)。
        """
        image_repo = getattr(self.db_manager, "image_repo", None) if self.db_manager is not None else None
        session_factory = getattr(image_repo, "session_factory", None) if image_repo is not None else None
        if not callable(session_factory):
            return {}
        try:
            repository = DatasetRepository(session_factory=session_factory)
            versions = repository.list_versions()
        except Exception:
            logger.opt(exception=True).warning("親の版一覧の取得に失敗しました")
            return {}
        by_dataset: dict[str, list[tuple[int, str]]] = {}
        for version in versions:
            by_dataset.setdefault(version.dataset_name, []).append(
                (version.version_id, version.version_name)
            )
        return by_dataset

    def _start_dataset_import(self, selection: DatasetSelection) -> None:
        """Kohya データセット取り込みを開始する（内部メソッド）。

        Args:
            selection: Kohya 取り込みの選択結果 (設定JSONは 0 個でもよい)
        """
        if not self._validate_services():
            return

        try:
            file_system_manager = self.file_system_manager
            worker_service = self.worker_service
            assert file_system_manager is not None
            assert worker_service is not None

            file_system_manager.initialize_from_dataset_selection(selection.directory)
            overrides = list(selection.folder_overrides) if selection.folder_overrides is not None else None
            if selection.parent_version_id is not None:
                worker_id = worker_service.start_dataset_import(
                    selection.directory,
                    selection.dataset_name or selection.directory.name,
                    selection.version_name,
                    list(selection.config_files),
                    file_system_manager,
                    overrides,
                    parent_version_id=selection.parent_version_id,
                )
            else:
                worker_id = worker_service.start_dataset_import(
                    selection.directory,
                    selection.dataset_name or selection.directory.name,
                    selection.version_name,
                    list(selection.config_files),
                    file_system_manager,
                    overrides,
                )
            logger.info(f"Kohya取り込み開始: worker_id={worker_id}, directory={selection.directory}")
        except (RuntimeError, OSError, ValueError) as e:
            error_msg = f"データセット取り込みの開始に失敗しました: {e}"
            logger.opt(exception=True).error(error_msg)
            if self.parent:
                show_critical(
                    self.parent,
                    "データセット取り込みエラー",
                    "データセット取り込みの開始に失敗しました。",
                    detail=str(e),
                )

    def _on_dataset_import_finished(self, result: DatasetImportResult) -> None:
        """取り込み完了ポップアップを表示する。

        Args:
            result: 取り込み結果
        """
        if not self.parent:
            return
        show_information(
            self.parent,
            "データセット取り込み完了",
            (
                f"版 ID: {result.version_id}\n"
                f"画像数: {result.image_count}\n"
                f"スキップ数: {result.skipped_images}\n"
                f"学習テキストの無い画像数: {result.images_without_text}\n"
                f"学習設定数: {len(result.training_config_ids)}"
            ),
        )

    def _on_dataset_import_error(self, error_message: str) -> None:
        """取り込み失敗の警告ポップアップを表示する。

        Args:
            error_message: エラーメッセージ
        """
        if not self.parent:
            return
        show_warning(self.parent, "データセット取り込みエラー", error_message)

    def _validate_services(self) -> bool:
        """必須サービスの検証

        Returns:
            bool: 全サービスが有効な場合True
        """
        if not self.worker_service:
            logger.warning("WorkerServiceが初期化されていません")
            if self.parent:
                show_warning(
                    self.parent,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、バッチ登録を開始できません。",
                )
            return False

        if not self.file_system_manager:
            logger.warning("FileSystemManagerが初期化されていません")
            if self.parent:
                show_warning(
                    self.parent,
                    "サービス未初期化",
                    "FileSystemManagerが初期化されていないため、バッチ登録処理を実行できません。",
                )
            return False

        return True

    def _start_batch_registration(self, directory: Path, folder_tags: dict[Path, tuple[str, ...]]) -> None:
        """バッチ登録処理を開始（内部メソッド）

        Args:
            directory: 選択されたデータセットディレクトリ
            folder_tags: サブフォルダ (directory からの相対パス) → 共通タグ (Issue #1409)
        """
        # Step 1: サービス検証
        if not self._validate_services():
            return

        try:
            file_system_manager = self.file_system_manager
            worker_service = self.worker_service
            assert file_system_manager is not None
            assert worker_service is not None

            # FileSystemManagerの初期化（新しいメソッド使用）
            output_dir = file_system_manager.initialize_from_dataset_selection(directory)
            logger.info(f"FileSystemManager初期化完了: output_dir={output_dir}")

            # バッチ登録開始（初期化済みFileSystemManagerを渡す）
            worker_id = worker_service.start_batch_registration_with_fsm(
                directory, file_system_manager, folder_tags=folder_tags
            )

            if worker_id:
                logger.info(f"バッチ登録開始: worker_id={worker_id}, directory={directory}")
            else:
                logger.error("バッチ登録の開始に失敗しました")
                if self.parent:
                    show_warning(self.parent, "バッチ登録エラー", "バッチ登録の開始に失敗しました。")

        except Exception as e:
            error_msg = f"データセット登録の開始に失敗しました: {e}"
            logger.opt(exception=True).error(error_msg)
            if self.parent:
                show_critical(
                    self.parent,
                    "バッチ登録エラー",
                    "データセット登録の開始に失敗しました。",
                    detail=str(e),
                )
