"""進捗状態管理サービス

Worker進捗表示とステータスバー更新の統一管理を担当。
MainWindowから分離し、進捗管理ロジックを集約。

進捗は ``QStatusBar.addPermanentWidget`` で載せた常設部品 (``StatusProgressWidget`` /
``AnnotationProgressWidget``) へ表示し、``showMessage`` は操作結果の通知だけに使う (ADR 0108)。
本クラスは QObject ではないため worker の signal を直接受けない。呼び出し元は GUI スレッドの
QObject (MainWindow のスロット) で、cross-thread の signal は queued 接続で GUI スレッドへ届く。
"""

from loguru import logger
from PySide6.QtWidgets import QStatusBar

from lorairo.services.annotation_progress import AnnotationProgress

from ..widgets.annotation_progress_widget import AnnotationProgressWidget
from ..widgets.status_progress_widget import StatusProgressWidget

# 旧 batch annotation API (worker_id を持たない) 用の進捗キー
_BATCH_ANNOTATION_KEY = "batch_annotation"


class ProgressStateService:
    """進捗状態管理サービス

    Worker進捗管理、バッチ処理進捗、ステータスバー更新を統一管理。
    MainWindowから進捗管理ロジックを分離。
    """

    def __init__(self, status_bar: QStatusBar | None = None):
        """初期化

        Args:
            status_bar: ステータスバー（進捗部品の配置先と結果通知に使用）
        """
        self.status_bar = status_bar
        self._annotation_widget: AnnotationProgressWidget | None = None
        self._annotation_worker_id: str | None = None
        self._active_annotation_progress: dict[str, AnnotationProgress] = {}
        self._terminal_annotation_jobs: set[str] = set()
        self._registration_worker_id: str | None = None
        # key -> (工程名, current, total)。挿入順の末尾が最後に更新された進捗
        self._progress_entries: dict[str, tuple[str, int | None, int | None]] = {}
        self._progress_widget: StatusProgressWidget | None = None
        # 終端済み worker。終端後に遅れて届いた進捗で部品を復活させない
        self._terminated_workers: set[str] = set()
        if isinstance(status_bar, QStatusBar):
            self._progress_widget = StatusProgressWidget(status_bar)
            status_bar.addPermanentWidget(self._progress_widget)
            # addPermanentWidget 後も進捗が無い間は隠しておく
            self._progress_widget.setVisible(False)

    # ============================================================
    # バッチ登録進捗管理
    # ============================================================

    def on_batch_registration_started(self, worker_id: str) -> None:
        """バッチ登録開始時の進捗表示

        Args:
            worker_id: ワーカーID


        """
        logger.info(f"バッチ登録開始: worker_id={worker_id}")
        self._registration_worker_id = worker_id
        # 件数は最初の進捗通知まで不明なので不定進捗で表示する
        self.show_progress(worker_id, "データベース登録処理を開始しています...")

    def on_batch_registration_error(self, error_message: str) -> None:
        """バッチ登録エラー時の進捗表示

        Args:
            error_message: エラーメッセージ



        Note:
            QMessageBoxは呼び出し側（MainWindow）で表示する。
            このServiceはステータスバー更新のみ担当。
        """
        logger.error(f"バッチ登録エラー: {error_message}")
        if self._registration_worker_id is not None:
            self.finish_progress(self._registration_worker_id)
            self._registration_worker_id = None

        if self.status_bar:
            try:
                self.status_bar.showMessage(f"バッチ登録エラー: {error_message}", 8000)
            except Exception as e:
                logger.debug(f"Status bar update failed: {e}")

    def on_batch_registration_canceled(self, worker_id: str) -> None:
        """バッチ登録キャンセル時の進捗表示"""
        logger.info(f"バッチ登録キャンセル: worker_id={worker_id}")
        self.finish_progress(worker_id)

        self._show_canceled_message("バッチ登録")

    def on_batch_annotation_canceled(self, worker_id: str) -> None:
        """バッチアノテーションキャンセル時の進捗表示"""
        logger.info(f"バッチアノテーションキャンセル: worker_id={worker_id}")
        self.finish_progress(worker_id)

        self._show_canceled_message("アノテーション処理")

    def on_batch_import_canceled(self, worker_id: str) -> None:
        """バッチインポートキャンセル時の進捗表示"""
        logger.info(f"バッチインポートキャンセル: worker_id={worker_id}")
        self.finish_progress(worker_id)

        self._show_canceled_message("バッチインポート")

    def _show_canceled_message(self, operation_name: str) -> None:
        """キャンセル完了メッセージをステータスバーへ表示する。"""
        if self.status_bar:
            try:
                self.status_bar.showMessage(f"{operation_name}をキャンセルしました", 5000)
            except Exception as e:
                logger.debug(f"Status bar update failed: {e}")

    # ============================================================
    # 汎用進捗 (常設部品)
    # ============================================================

    @property
    def progress_widget(self) -> StatusProgressWidget | None:
        """ステータスバー常設の汎用進捗部品 (QStatusBar が無い場合は None)。"""
        return self._progress_widget

    def show_progress(
        self, key: str, text: str, current: int | None = None, total: int | None = None
    ) -> None:
        """進捗を常設部品へ表示する。

        同じ ``key`` の進捗は上書きする。複数の進捗があるときは最後に更新されたものを表示する。

        Args:
            key: 進捗の識別子 (worker_id 等)。``finish_progress`` で同じ値を渡して消す。
            text: 工程名 (表示テキスト)。
            current: 処理済み件数。
            total: 総件数。``None`` または 0 以下なら不定進捗。
        """
        # 最後に更新された進捗を表示するため、更新のたびに末尾へ移す
        self._progress_entries.pop(key, None)
        self._progress_entries[key] = (text, current, total)
        self._render_progress()

    def finish_progress(self, key: str) -> None:
        """進捗を取り除く。残りが無ければ部品を隠す。

        Args:
            key: ``show_progress`` に渡した識別子。未登録なら何もしない。
        """
        if self._progress_entries.pop(key, None) is not None:
            self._render_progress()

    def on_worker_terminal(self, worker_id: str) -> None:
        """Worker 終端 (成功 / 失敗 / キャンセル) でその worker の進捗を消す。

        Args:
            worker_id: 終端した worker の ID。
        """
        self._terminated_workers.add(worker_id)
        self.finish_progress(worker_id)

    def _render_progress(self) -> None:
        widget = self._progress_widget
        if widget is None:
            return
        if not self._progress_entries:
            widget.clear()
            return
        text, current, total = next(reversed(self._progress_entries.values()))
        widget.set_progress(text, current, total)

    # ============================================================
    # Worker進捗管理
    # ============================================================

    def on_worker_progress_updated(self, worker_id: str, progress: object) -> None:
        """Worker進捗更新を常設部品へ表示する。

        Args:
            worker_id: ワーカーID
            progress: 進捗情報 (``annotation_progress`` / WorkerProgress 形式 / current・total 形式)
        """
        annotation_progress = getattr(progress, "annotation_progress", None)
        if isinstance(annotation_progress, AnnotationProgress):
            self._show_annotation_progress(worker_id, annotation_progress)
            return
        if worker_id in self._terminated_workers:
            return
        # WorkerProgress (gui.workers.base) 形式: percentage / status_message / processed_count
        if hasattr(progress, "percentage") and hasattr(progress, "status_message"):
            processed_count = int(getattr(progress, "processed_count", 0) or 0)
            total_count = int(getattr(progress, "total_count", 0) or 0)
            detail = f" ({processed_count}/{total_count})" if total_count > 0 else ""
            status_message = f"{progress.status_message}{detail} - {progress.percentage}%"
            if total_count > 0:
                self.show_progress(worker_id, status_message, processed_count, total_count)
            else:
                # 件数が無い場合は percentage を 100 分率の確定進捗として扱う
                self.show_progress(worker_id, status_message, int(progress.percentage), 100)
            logger.trace(f"ワーカー進捗更新: {worker_id} - {status_message}")
        # 汎用 current/total 形式
        elif hasattr(progress, "current") and hasattr(progress, "total"):
            current = int(progress.current)
            total = int(progress.total)
            percentage = int((current / total) * 100) if total > 0 else 0
            status_message = f"処理中... {current}/{total} ({percentage}%)"
            self.show_progress(worker_id, status_message, current, total)
            logger.trace(f"ワーカー進捗更新: {worker_id} - {current}/{total} ({percentage}%)")
        else:
            logger.trace(f"ワーカー進捗更新: {worker_id} - {progress}")

    def _show_annotation_progress(self, worker_id: str, progress: AnnotationProgress) -> None:
        if progress.phase.is_terminal:
            self._terminal_annotation_jobs.add(worker_id)
            self._active_annotation_progress.pop(worker_id, None)
            if self._annotation_worker_id is not None and worker_id != self._annotation_worker_id:
                return
        else:
            if worker_id in self._terminal_annotation_jobs:
                return
            self._active_annotation_progress[worker_id] = progress
        if self._active_annotation_progress:
            worker_id, progress = max(
                self._active_annotation_progress.items(), key=lambda item: item[1].started_at
            )
        self._annotation_worker_id = worker_id
        if not isinstance(self.status_bar, QStatusBar):
            return
        if self._annotation_widget is None:
            self._annotation_widget = AnnotationProgressWidget(self.status_bar)
            self.status_bar.addPermanentWidget(self._annotation_widget, 1)
        self._annotation_widget.set_progress(progress)
        # 進行中のアノテーションが無くなったら部品を隠す (結果はサマリー / 通知側が出す)
        self._annotation_widget.setVisible(not progress.phase.is_terminal)

    def on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        """Workerバッチ進捗を常設部品へ表示する。

        Args:
            worker_id: ワーカーID
            current: 現在の処理数
            total: 総処理数
            filename: 処理中のファイル名
        """
        if worker_id in self._terminated_workers:
            return
        percentage = int((current / total) * 100) if total > 0 else 0
        status_message = f"バッチ処理中... {current}/{total} ({percentage}%) - {filename}"
        self.show_progress(worker_id, status_message, current, total)
        logger.trace(f"バッチ進捗更新: {worker_id} - {current}/{total} ({percentage}%) - {filename}")

    # ============================================================
    # アノテーション進捗管理
    # ============================================================

    def on_batch_annotation_started(self, total_images: int) -> None:
        """バッチアノテーション開始を常設部品へ表示する。

        Args:
            total_images: 総画像数
        """
        logger.info(f"バッチアノテーション開始: {total_images}画像")
        self.show_progress(
            _BATCH_ANNOTATION_KEY, f"アノテーション処理開始: {total_images}画像を処理中...", 0, total_images
        )

    def on_batch_annotation_progress(self, processed: int, total: int) -> None:
        """バッチアノテーション進捗を常設部品へ表示する。

        Args:
            processed: 処理済み画像数
            total: 総画像数
        """
        percentage = int((processed / total) * 100) if total > 0 else 0
        self.show_progress(
            _BATCH_ANNOTATION_KEY,
            f"アノテーション処理中... {processed}/{total} ({percentage}%)",
            processed,
            total,
        )
        logger.debug(f"バッチアノテーション進捗: {processed}/{total} ({percentage}%)")
        if total > 0 and processed >= total:
            self.finish_progress(_BATCH_ANNOTATION_KEY)
