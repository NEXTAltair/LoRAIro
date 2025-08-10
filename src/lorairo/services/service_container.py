"""ServiceContainer - LoRAIroサービス一元管理

Phase 2: 既存サービスとPhase 1新サービスの統合管理
Phase 4: 実ライブラリ統合での依存関係解決
"""

from typing import Any, Optional, cast

from ..database.db_core import DefaultSessionLocal
from ..database.db_manager import ImageDatabaseManager
from ..database.db_repository import ImageRepository
from ..storage.file_system import FileSystemManager
from ..utils.log import logger
from .configuration_service import ConfigurationService
from .image_processing_service import ImageProcessingService

# from .annotation_batch_processor import BatchProcessor
from .model_registry_protocol import ModelRegistryServiceProtocol, NullModelRegistry

# from .model_sync_service import ModelSyncService


class ServiceContainer:
    """LoRAIroサービス依存関係一元管理コンテナ

    既存サービス（Configuration, ImageProcessing等）と
    Phase 1新サービス（ModelSync, AnnotatorLib等）の統合管理

    シングルトンパターンで全アプリケーションでの一意性保証
    """

    _instance: Optional["ServiceContainer"] = None
    _initialized: bool = False

    def __new__(cls) -> "ServiceContainer":
        """シングルトンインスタンス作成"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """ServiceContainer初期化

        重複初期化を防ぐため、_initializedフラグで制御
        """
        if ServiceContainer._initialized:
            return

        logger.info("ServiceContainer初期化開始")

        # コアサービス初期化
        self._config_service: ConfigurationService | None = None
        self._file_system_manager: FileSystemManager | None = None
        self._image_repository: ImageRepository | None = None
        self._db_manager: ImageDatabaseManager | None = None
        self._image_processing_service: ImageProcessingService | None = None

        # Phase 1新サービス初期化
        # self._model_sync_service: ModelSyncService | None = None
        self._model_registry: ModelRegistryServiceProtocol | None = None
        # self._batch_processor: BatchProcessor | None = None

        # Phase 4: プロダクション統合モード制御
        self._use_production_mode: bool = True

        ServiceContainer._initialized = True
        logger.info("ServiceContainer初期化完了")

    @property
    def config_service(self) -> ConfigurationService:
        """設定サービス取得（遅延初期化）"""
        if self._config_service is None:
            self._config_service = ConfigurationService()
            logger.debug("ConfigurationService初期化完了")
        return self._config_service

    @config_service.deleter
    def config_service(self) -> None:
        """設定サービス削除（テスト用）"""
        self._config_service = None

    @property
    def file_system_manager(self) -> FileSystemManager:
        """ファイルシステムマネージャー取得（遅延初期化）"""
        if self._file_system_manager is None:
            self._file_system_manager = FileSystemManager()
            logger.debug("FileSystemManager初期化完了")
        return self._file_system_manager

    @property
    def image_repository(self) -> ImageRepository:
        """画像リポジトリ取得（遅延初期化）"""
        if self._image_repository is None:
            self._image_repository = ImageRepository(session_factory=DefaultSessionLocal)
            logger.debug("ImageRepository初期化完了")
        return self._image_repository

    @image_repository.deleter
    def image_repository(self) -> None:
        """画像リポジトリ削除（テスト用）"""
        self._image_repository = None

    @property
    def db_manager(self) -> ImageDatabaseManager:
        """データベースマネージャー取得（遅延初期化）"""
        if self._db_manager is None:
            self._db_manager = ImageDatabaseManager(
                self.image_repository, self.config_service, self.file_system_manager
            )
            logger.debug("ImageDatabaseManager初期化完了")
        return self._db_manager

    @property
    def image_processing_service(self) -> ImageProcessingService:
        """画像処理サービス取得（遅延初期化）"""
        if self._image_processing_service is None:
            self._image_processing_service = ImageProcessingService(
                self.config_service, self.file_system_manager, self.db_manager
            )
            logger.debug("ImageProcessingService初期化完了")
        return self._image_processing_service

    # @property
    # def model_sync_service(self) -> ModelSyncService:
    #     """モデル同期サービス取得（遅延初期化）
    #
    #     Phase 4: 実ライブラリ統合 - ModelRegistryServiceProtocolと連携
    #     """
    #     if self._model_sync_service is None:
    #         # Phase 4: 実ModelRegistryServiceProtocolを注入
    #         self._model_sync_service = ModelSyncService(
    #             self.image_repository,
    #             self.config_service,
    #             model_registry=self.model_registry,  # Phase 4で実装注入
    #         )
    #         logger.info("ModelSyncService初期化完了（Phase 4プロダクション統合）")
    #     return self._model_sync_service

    @property
    def model_registry(self) -> ModelRegistryServiceProtocol:
        """モデルレジストリサービス取得（遅延初期化）

        Protocol-basedモデルレジストリ使用
        フォールバック: NullModelRegistry使用
        """
        if self._model_registry is None:
            # Protocol-basedモデルレジストリ使用
            self._model_registry = NullModelRegistry()
            logger.info("モデルレジストリ初期化完了（Protocol-based）")
        return self._model_registry

    # @property
    # def batch_processor(self) -> BatchProcessor:
    #     """バッチプロセッサー取得（遅延初期化）"""
    #     if self._batch_processor is None:
    #         self._batch_processor = BatchProcessor(
    #             self.model_registry, self.config_service
    #         )
    #         logger.debug("BatchProcessor初期化完了")
    #     return self._batch_processor

    def get_service_summary(self) -> dict[str, Any]:
        """サービス初期化状況のサマリー取得

        Returns:
            dict[str, Any]: サービス初期化状況
        """
        return {
            "initialized_services": {
                "config_service": self._config_service is not None,
                "file_system_manager": self._file_system_manager is not None,
                "image_repository": self._image_repository is not None,
                "db_manager": self._db_manager is not None,
                "image_processing_service": self._image_processing_service is not None,
                # "model_sync_service": self._model_sync_service is not None,
                "model_registry": self._model_registry is not None,
                # "batch_processor": self._batch_processor is not None,
            },
            "container_initialized": ServiceContainer._initialized,
            "phase": "Phase 4 (Production Integration)"
            if self._use_production_mode
            else "Phase 1-2 (Mock Implementation)",
        }

    def reset_container(self) -> None:
        """ServiceContainer状態リセット（主にテスト用）

        注意: 本番環境では使用しないこと
        """
        logger.warning("ServiceContainer状態リセット実行")

        # 全サービスインスタンスクリア
        self._config_service = None
        self._file_system_manager = None
        self._image_repository = None
        self._db_manager = None
        self._image_processing_service = None
        # self._model_sync_service = None
        self._model_registry = None
        # self._batch_processor = None

        # クラスレベルリセット
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

        logger.warning("ServiceContainer状態リセット完了")

    def set_production_mode(self, enable: bool) -> None:
        """プロダクションモード設定（主にテスト用）

        Args:
            enable: True=実ライブラリ使用, False=Mock強制使用
        """
        if self._use_production_mode != enable:
            old_mode = "Production" if self._use_production_mode else "Mock"
            new_mode = "Production" if enable else "Mock"

            logger.info(f"ServiceContainer動作モード変更: {old_mode} -> {new_mode}")

            # モード変更時は関連サービスをリセット
            if self._model_registry is not None:
                logger.info("モード変更によりModelRegistryをリセットします")
                self._model_registry = None
            # if self._model_sync_service is not None:
            #     logger.info("モード変更によりModelSyncServiceをリセットします")
            #     self._model_sync_service = None
            # if self._batch_processor is not None:
            #     logger.info("モード変更によりBatchProcessorをリセットします")
            #     self._batch_processor = None

            self._use_production_mode = enable

    def is_production_mode(self) -> bool:
        """現在のプロダクションモード確認

        Returns:
            bool: True=実ライブラリ使用, False=Mock使用
        """
        return self._use_production_mode


# 便利な関数でサービス取得を簡略化
def get_service_container() -> ServiceContainer:
    """ServiceContainerシングルトンインスタンス取得"""
    return ServiceContainer()


def get_config_service() -> ConfigurationService:
    """設定サービス取得（便利関数）"""
    return get_service_container().config_service


# def get_model_sync_service() -> ModelSyncService:
#     """モデル同期サービス取得（便利関数）"""
#     return get_service_container().model_sync_service


def get_model_registry() -> ModelRegistryServiceProtocol:
    """モデルレジストリサービス取得（便利関数）

    Protocol-basedモデルレジストリを返す
    """
    return get_service_container().model_registry


# def get_batch_processor() -> BatchProcessor:
#     """バッチプロセッサー取得（便利関数）"""
#     return get_service_container().batch_processor
