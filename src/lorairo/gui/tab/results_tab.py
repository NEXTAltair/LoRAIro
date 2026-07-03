"""結果タブの専用ウィジェット (Epic #867 / #870)。

ステージング集合の品質トリアージ (読み取り専用) を表示する `ResultsWidget` を
ホストする。固有の振る舞い (accept / unaccept / 一括 accept・再計算) を所有し、
ステージング集合は `StagingStateManager` を DI 購読する (ADR 0074)。
MainWindow は本ウィジェットを配置し依存を注入するだけ (glue)。
"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

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

        results = []
        image_paths: dict[int, str] = {}
        for image_id in image_ids:
            metadata = self._db_manager.get_image_metadata(image_id)
            if metadata is None:
                continue
            annotations = self._db_manager.get_image_annotations(image_id)
            image_meta = {
                "uuid": metadata.get("uuid"),
                "width": metadata.get("width"),
                "height": metadata.get("height"),
                "reviewed_at": metadata.get("reviewed_at"),
            }
            results.append(self._quality_service.detect_image(image_id, image_meta, annotations))
            # 行内サムネイル用のパスを解決する (#1104)。低解像度処理済み画像を優先し、
            # 無ければオリジナルの stored path にフォールバックする。View は DB を持た
            # ないため、パス解決はこのタブ (glue) が担って display に渡す。
            path = self._resolve_thumbnail_path(image_id, metadata)
            if path is not None:
                image_paths[image_id] = path

        if not results:
            self._results_widget.clear()
            return

        summary = self._quality_service.summarize(results)
        self._results_widget.display(summary, results, image_paths)

    def _resolve_thumbnail_path(self, image_id: int, metadata: dict[str, object]) -> str | None:
        """行内サムネイル用の画像パスを解決する (#1104)。

        低解像度処理済み画像 (512px サムネイル) を優先し、無ければオリジナルの
        ``stored_image_path`` にフォールバックする。いずれも無ければ None。
        """
        if self._db_manager is not None:
            low_res = self._db_manager.get_low_res_image_path(image_id)
            if isinstance(low_res, str) and low_res:
                return low_res
        stored = metadata.get("stored_image_path")
        if isinstance(stored, str) and stored:
            return stored
        return None
