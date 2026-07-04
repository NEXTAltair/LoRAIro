"""結果タブの専用ウィジェット (Epic #867 / #870)。

ステージング集合の品質トリアージ (読み取り専用) を表示する `ResultsWidget` を
ホストする。固有の振る舞い (accept / unaccept / 一括 accept・再計算) を所有し、
ステージング集合は `StagingStateManager` を DI 購読する (ADR 0074)。
MainWindow は本ウィジェットを配置し依存を注入するだけ (glue)。
"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...services.quality_issue_detection_service import QualityIssueDetectionService
from ...utils.log import logger
from ..state.staging_state import StagingStateManager
from ..widgets.results_widget import ResultsWidget


class ResultsTabWidget(QWidget):
    """結果タブのルートウィジェット (Wireframes v11 Frame 5 · Results)。

    ステージング集合の各画像を `QualityIssueDetectionService` でトリアージし、
    `ResultsWidget` に表示する。accept 操作で DB の reviewed 状態を更新する。
    """

    def __init__(
        self,
        *,
        db_manager: ImageDatabaseManager | None,
        staging_state_manager: StagingStateManager | None,
        parent: QWidget | None = None,
    ) -> None:
        """結果タブを初期化する。

        Args:
            db_manager: 画像メタデータ/アノテーション取得と reviewed 更新に使う。
            staging_state_manager: トリアージ対象 (ステージング集合) の SSoT。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager
        self._quality_service = QualityIssueDetectionService()

        self._results_widget = ResultsWidget(parent=self)
        self._results_widget.accept_requested.connect(self._on_accept)
        self._results_widget.unaccept_requested.connect(self._on_unaccept)
        self._results_widget.accept_clean_requested.connect(self._on_accept_clean)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._results_widget)

    @property
    def results_widget(self) -> ResultsWidget:
        """内包する `ResultsWidget` を返す (タブ内配線・テスト用)。"""
        return self._results_widget

    @Slot(int)
    def _on_accept(self, image_id: int) -> None:
        """Results 行の accept: reviewed_at を設定して再描画する。"""
        if self._db_manager:
            self._db_manager.mark_image_reviewed(image_id, reviewed=True)
        self.refresh()

    @Slot(int)
    def _on_unaccept(self, image_id: int) -> None:
        """Results 行の accept 取消: reviewed_at を解除して再描画する。"""
        if self._db_manager:
            self._db_manager.mark_image_reviewed(image_id, reviewed=False)
        self.refresh()

    @Slot(list)
    def _on_accept_clean(self, image_ids: list[int]) -> None:
        """問題なし画像を一括 accept して再描画する。"""
        if self._db_manager:
            for image_id in image_ids:
                self._db_manager.mark_image_reviewed(image_id, reviewed=True)
            logger.info(f"一括 accept 完了: {len(image_ids)} 件")
        self.refresh()

    def refresh(self) -> None:
        """ステージング集合のトリアージを再計算して描画する (タブ表示時に呼ぶ)。"""
        if not self._db_manager or self._staging_state_manager is None:
            self._results_widget.clear()
            return

        image_ids = list(self._staging_state_manager.get_staged_items().keys())
        if not image_ids:
            self._results_widget.clear()
            return

        # DB 取得は N+1 を避けるため一括で行う (#1140)。ステージング全画像分の
        # metadata / annotations / 最低解像度パスを 3 回のバッチクエリでまとめて引く
        # (旧実装は 1 画像 4 クエリの直列ループで GUI スレッドが数分ブロックしていた)。
        metadata_by_id = {m["id"]: m for m in self._db_manager.get_images_metadata_batch(image_ids)}
        annotations_by_id = self._db_manager.get_image_annotations_batch(image_ids)
        low_res_by_id = self._db_manager.get_low_res_image_paths_batch(image_ids)

        results = []
        image_paths: dict[int, str] = {}
        for image_id in image_ids:
            metadata = metadata_by_id.get(image_id)
            if metadata is None:
                continue
            annotations = annotations_by_id.get(image_id, {})
            image_meta = {
                "uuid": metadata.get("uuid"),
                "width": metadata.get("width"),
                "height": metadata.get("height"),
                "reviewed_at": metadata.get("reviewed_at"),
            }
            results.append(self._quality_service.detect_image(image_id, image_meta, annotations))
            # 行内サムネイル用のパスを解決する (#1104)。View は DB を持たないため、
            # パス解決はこのタブ (glue) が担って display に渡す。
            path = self._resolve_thumbnail_path(metadata, low_res_by_id.get(image_id))
            if path is not None:
                image_paths[image_id] = path

        if not results:
            self._results_widget.clear()
            return

        summary = self._quality_service.summarize(results)
        self._results_widget.display(summary, results, image_paths)

    def _resolve_thumbnail_path(self, metadata: dict[str, object], low_res_path: str | None) -> str | None:
        """行内サムネイル用の画像パスを解決する (#1104 / バッチ化 #1140)。

        低解像度処理済み画像 (512px サムネイル) を優先し、無ければオリジナルの
        ``stored_image_path`` にフォールバックする。いずれも無ければ None。

        DB の格納パスはプロジェクトルート相対のことがあるため、View へ渡す前に
        ``resolve_stored_path`` でプロジェクトルート基準の絶対パスへ解決する
        (相対のままだとサムネイル読込がプロセスの cwd 基準になり外れる。#961 P2 と同型)。

        Args:
            metadata: 対象画像の metadata dict (``stored_image_path`` フォールバック用)。
            low_res_path: バッチ取得済みの最低解像度パス (無ければ None)。
        """
        candidate: str | None = None
        if isinstance(low_res_path, str) and low_res_path:
            candidate = low_res_path
        if candidate is None:
            stored = metadata.get("stored_image_path")
            if isinstance(stored, str) and stored:
                candidate = stored
        if candidate is None:
            return None
        return str(resolve_stored_path(candidate))
