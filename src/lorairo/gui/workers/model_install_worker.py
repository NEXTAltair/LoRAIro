# src/lorairo/gui/workers/model_install_worker.py
"""ローカル ML モデルの明示インストールワーカー (Issue #754, ADR 0066 §5)。

未インストールモデルの初回使用時、推論ジョブの前段で実行される
`model_install` ジョブの実体。iam-lib の明示ダウンロード API を呼び出し、
byte 進捗を WorkerProgress として GUI へ通知する。
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from image_annotator_lib import ModelInstallCancelledError

from ...utils.log import logger
from .base import CancellationError, LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...annotations.annotator_adapter import AnnotatorLibraryAdapter
    from ...database.db_manager import ImageDatabaseManager


@dataclass
class ModelInstallResult:
    """モデルインストールジョブの結果。

    Attributes:
        installed_models: インストール完了したモデル名リスト。
    """

    installed_models: list[str] = field(default_factory=list)


def _format_bytes_mb(num_bytes: int) -> str:
    """byte 数を MB 表記の文字列へ変換する。"""
    return f"{num_bytes / (1024 * 1024):.1f}"


class ModelInstallWorker(LoRAIroWorkerBase[ModelInstallResult]):
    """ローカル ML モデルを進捗付きで明示ダウンロードするワーカー。

    複数モデルを順次インストールし、全体進捗 (モデル数 x モデル内 byte 進捗)
    を percentage として報告する。キャンセル要求は threading.Event 経由で
    iam-lib のダウンロードループへ伝播する。
    """

    _OPERATION_TYPE = "model_install"

    def __init__(
        self,
        annotator_adapter: "AnnotatorLibraryAdapter",
        model_names: list[str],
        db_manager: "ImageDatabaseManager | None" = None,
    ) -> None:
        """ModelInstallWorker を初期化する。

        Args:
            annotator_adapter: iam-lib への委譲アダプター。
            model_names: インストール対象のモデル名リスト (iam-lib モデル名)。
            db_manager: エラーレコード保存用 (任意)。
        """
        super().__init__(db_manager)
        self._annotator_adapter = annotator_adapter
        self._model_names = list(model_names)
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """キャンセル要求をダウンロードループ (iam-lib 側) にも伝播する。"""
        super().cancel()
        self._cancel_event.set()

    def execute(self) -> ModelInstallResult:
        """対象モデルを順次インストールする。

        Returns:
            ModelInstallResult: インストール完了したモデル名リスト。

        Raises:
            CancellationError: キャンセル要求により中断された場合。
        """
        total_models = len(self._model_names)
        installed: list[str] = []
        logger.info(f"モデルインストール開始: {total_models}件 ({', '.join(self._model_names)})")

        for index, model_name in enumerate(self._model_names):
            self._check_cancellation()
            self._report_progress(
                percentage=int(index * 100 / total_models) if total_models else 100,
                status_message=f"{model_name} をダウンロード中...",
                current_item=model_name,
                processed_count=index,
                total_count=total_models,
            )
            try:
                self._annotator_adapter.install_model(
                    model_name,
                    progress_callback=self._build_progress_callback(index, total_models, model_name),
                    cancel_event=self._cancel_event,
                )
            except ModelInstallCancelledError as e:
                raise CancellationError(f"モデルインストールがキャンセルされました: {model_name}") from e
            installed.append(model_name)
            logger.debug(f"モデルインストール完了: {model_name} ({index + 1}/{total_models})")

        self._report_progress(
            percentage=100,
            status_message=f"モデルインストール完了: {total_models}件",
            processed_count=total_models,
            total_count=total_models,
        )
        logger.info(f"モデルインストール完了: {total_models}件")
        return ModelInstallResult(installed_models=installed)

    def _build_progress_callback(
        self, index: int, total_models: int, model_name: str
    ) -> Callable[[int, int], None]:
        """1 モデル分の byte 進捗を全体進捗へ変換する callback を生成する。

        ダウンロードスレッドから呼ばれるため、Qt シグナル emit のみ行う
        (シグナルはスレッドセーフ)。テーブル再描画の負荷を抑えるため、
        モデル内進捗率 (整数 %) が変化したときだけ通知する。

        Args:
            index: 現在のモデルのインデックス (0 始まり)。
            total_models: 対象モデル総数。
            model_name: 現在のモデル名。
        """
        last_reported_pct = -1

        def _on_progress(downloaded_bytes: int, total_bytes: int) -> None:
            nonlocal last_reported_pct
            if total_bytes <= 0:
                return
            model_pct = min(100, int(downloaded_bytes * 100 / total_bytes))
            if model_pct == last_reported_pct:
                return
            last_reported_pct = model_pct
            overall_pct = int((index * 100 + model_pct) / total_models) if total_models else model_pct
            message = (
                f"{model_name} をダウンロード中 {model_pct}% "
                f"({_format_bytes_mb(downloaded_bytes)}/{_format_bytes_mb(total_bytes)} MB)"
            )
            self._report_progress_throttled(
                percentage=overall_pct,
                status_message=message,
                current_item=model_name,
                processed_count=index,
                total_count=total_models,
            )

        return _on_progress
