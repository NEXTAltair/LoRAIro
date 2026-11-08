# src/lorairo/gui/workers/tag_db_warmup_worker.py
"""起動時にタグ DB を背景で初期化する worker (#1438)。

タグ DB の初期化 (``genai_tag_db_tools.initialize_databases``) は HF Hub の確認 / ダウンロードを
伴い、数秒〜数分かかることがある。従来は MainWindow 構築中に GUI スレッドで同期実行され、
ウィンドウ表示前に最長 5 分以上ブロックしていた。本 worker は window を表示した後に
この初期化を背景スレッドで行い、完了後に Signal で GUI へ知らせる。
"""

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from ...services.service_container import ServiceContainer
from ...utils.log import logger
from .base import LoRAIroWorkerBase


@dataclass
class TagDbWarmupResult:
    """タグ DB warm-up の結果。

    Attributes:
        reader_ready: MergedTagReader が使える状態になったか (失敗時は False で degrade)。
        tag_management_ready: TagManagementService が構築できたか。
    """

    reader_ready: bool
    tag_management_ready: bool


class TagDbWarmupWorker(LoRAIroWorkerBase[TagDbWarmupResult]):
    """MergedTagReader と TagManagementService を背景スレッドで準備する。"""

    _OPERATION_TYPE = "tag_db_warmup"

    def __init__(self, service_container: ServiceContainer) -> None:
        """Worker を初期化する。

        Args:
            service_container: タグ DB の準備対象を持つ ServiceContainer。
        """
        super().__init__()
        self._service_container = service_container

    def execute(self) -> TagDbWarmupResult:
        """タグ DB を初期化し、reader / 管理サービスを構築する。

        失敗は致命的ではない (翻訳表示とタグ補完が無効のまま動作継続) ため、例外は握らず
        結果フラグに落とす。
        """
        container = self._service_container
        reader = container.db_manager.annotation_repo.get_merged_reader()
        self._check_cancellation()

        tag_management_ready = False
        try:
            _ = container.tag_management_service
            tag_management_ready = True
        except (RuntimeError, ValueError, OSError, SQLAlchemyError) as e:
            logger.warning(f"TagManagementService の準備に失敗 (タグ管理機能なしで継続): {e}")

        return TagDbWarmupResult(reader_ready=reader is not None, tag_management_ready=tag_management_ready)
