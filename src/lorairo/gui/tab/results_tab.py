"""結果タブの専用ウィジェット (Epic #867 / #870)。

ステージング集合の品質トリアージ (読み取り専用) を表示する `ResultsWidget` を
ホストする。固有の振る舞い (accept / unaccept / 一括 accept・再計算) を所有し、
ステージング集合は `StagingStateManager` を DI 購読する (ADR 0074)。
MainWindow は本ウィジェットを配置し依存を注入するだけ (glue)。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...services.quality_issue_detection_service import QualityIssueDetectionService
from ...services.tag_suggestion_service import TagSuggestionService
from ...utils.log import logger
from ..state.staging_state import StagingStateManager
from ..widgets.annotation_review_batch_widget import AnnotationReviewBatchWidget
from ..widgets.results_widget import _VIRTUALIZE_THRESHOLD, ResultsWidget

if TYPE_CHECKING:
    from ...services.annotation_review_service import AnnotationReviewService
    from ...services.annotation_review_store import AnnotationReviewStore
    from ..workers.manager import WorkerManager


class ResultsTabWidget(QWidget):
    """結果タブのルートウィジェット (Wireframes v11 Frame 5 · Results)。

    ステージング集合の各画像を `QualityIssueDetectionService` でトリアージし、
    `ResultsWidget` に表示する。accept 操作で DB の reviewed 状態を更新する。
    """

    manual_review_requested = Signal(int)
    review_target_selection_requested = Signal()
    review_target_list_requested = Signal()
    running_status_changed = Signal(str)
    review_result_saved = Signal(int)

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

        self._annotation_review_widget = AnnotationReviewBatchWidget(self)
        self._annotation_review_widget.manual_review_requested.connect(self.manual_review_requested)
        self._annotation_review_widget.target_selection_requested.connect(
            self.review_target_selection_requested
        )
        self._annotation_review_widget.target_list_requested.connect(self.review_target_list_requested)
        self._annotation_review_widget.running_status_changed.connect(self.running_status_changed)
        self._annotation_review_widget.review_result_saved.connect(self.review_result_saved)
        self._annotation_review_widget.setVisible(False)
        self._annotation_review_widget.set_tag_suggestion_service(self._resolve_tag_suggestion_service())
        if staging_state_manager is not None:
            staging_state_manager.staged_images_changed.connect(self._on_review_scope_changed)

        self._results_widget = ResultsWidget(parent=self)
        self._results_widget.accept_requested.connect(self._on_accept)
        self._results_widget.unaccept_requested.connect(self._on_unaccept)
        self._results_widget.accept_clean_requested.connect(self._on_accept_clean)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._annotation_review_widget)
        layout.addWidget(self._results_widget)

    @property
    def results_widget(self) -> ResultsWidget:
        """内包する `ResultsWidget` を返す (タブ内配線・テスト用)。"""
        return self._results_widget

    @property
    def annotation_review_widget(self) -> AnnotationReviewBatchWidget:
        """ステージ済み画像のアノテーションチェックと保存結果を表示する。"""
        return self._annotation_review_widget

    @property
    def _review_batch_widget(self) -> AnnotationReviewBatchWidget:
        """レビューバッチウィジェット参照 (#1545)。"""
        return self._annotation_review_widget

    def set_annotation_review_services(
        self,
        service: AnnotationReviewService,
        store: AnnotationReviewStore,
        worker_manager: WorkerManager | None = None,
    ) -> None:
        # MainWindow calls refresh when this tab opens; avoid threads during its construction.
        self._annotation_review_widget.set_services(
            service, store, worker_manager, load_history=self.isVisible()
        )
        self._annotation_review_widget.setVisible(True)
        self._update_review_scope()

    def _resolve_tag_suggestion_service(self) -> TagSuggestionService | None:
        """関連タグ入力の補完候補ソースを db_manager の tagdb reader から構築する (#1439)。

        Returns:
            MergedTagReader を引けた場合は TagSuggestionService、引けなければ None
            (関連タグ入力は補完なしで動作する)。
        """
        if self._db_manager is None:
            return None
        try:
            # 初期化は起動しない (#1438)。未準備なら補完なしで始め、on_tag_db_ready() で後付けする。
            merged_reader = self._db_manager.annotation_repo.peek_merged_reader()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"MergedTagReader 取得に失敗 (タグ補完なしで継続): {e}")
            return None
        return TagSuggestionService(merged_reader) if merged_reader is not None else None

    def on_tag_db_ready(self) -> None:
        """背景で tag DB の準備が終わった後に、関連タグ入力の補完を有効化する (#1438)。"""
        self._annotation_review_widget.set_tag_suggestion_service(self._resolve_tag_suggestion_service())

    def set_annotation_review_unavailable_reason(self, reason: str) -> None:
        self._annotation_review_widget.set_unavailable_reason(reason)
        self._annotation_review_widget.setVisible(True)

    def _update_review_scope(self) -> None:
        ids = (
            list(self._staging_state_manager.get_staged_items())
            if self._staging_state_manager is not None
            else []
        )
        self._on_review_scope_changed(ids)

    @Slot(list)
    def _on_review_scope_changed(self, image_ids: list[int]) -> None:
        items = self._staging_state_manager.get_staged_items() if self._staging_state_manager else {}
        self._annotation_review_widget.set_image_names(
            {image_id: item[0] for image_id, item in items.items()}
        )
        self._annotation_review_widget.set_image_ids(image_ids)

    def shutdown(self) -> None:
        self._annotation_review_widget.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """キーボードナビゲーション操作を内包する ResultsWidget へ委譲する (#1545)。"""
        focus = self.focusWidget()
        review_widget = getattr(self, "_review_batch_widget", self._annotation_review_widget)
        if (
            focus is not None
            and review_widget is not None
            and (focus is review_widget or review_widget.isAncestorOf(focus))
        ):
            super().keyPressEvent(event)
            return

        if self._results_widget.handle_navigation_key(event.key(), event.modifiers()):
            event.accept()
            return
        super().keyPressEvent(event)

    @Slot(int)
    def _on_accept(self, image_id: int) -> None:
        """Results 行の accept: reviewed_at を設定し、該当行とサマリを差分更新する (#1545)。"""
        if self._db_manager:
            self._db_manager.mark_image_reviewed(image_id, reviewed=True)
        if not self._results_widget.set_image_reviewed(image_id, reviewed=True):
            self.refresh()

    @Slot(int)
    def _on_unaccept(self, image_id: int) -> None:
        """Results 行の accept 取消: reviewed_at を解除し、該当行とサマリを差分更新する (#1545)。"""
        if self._db_manager:
            self._db_manager.mark_image_reviewed(image_id, reviewed=False)
        if not self._results_widget.set_image_reviewed(image_id, reviewed=False):
            self.refresh()

    @Slot(list)
    def _on_accept_clean(self, image_ids: list[int]) -> None:
        """問題なし画像を 1 トランザクションで一括 accept し、表示を更新する (#1545)。"""
        if not image_ids:
            return
        if self._db_manager:
            batch_fn = getattr(self._db_manager, "mark_images_reviewed_batch", None)
            if callable(batch_fn):
                batch_fn(image_ids, reviewed=True)
            else:
                for image_id in image_ids:
                    self._db_manager.mark_image_reviewed(image_id, reviewed=True)
            logger.info(f"一括 accept 完了: {len(image_ids)} 件")
        if not self._results_widget.set_images_reviewed(image_ids, reviewed=True):
            self.refresh()

    def refresh(self) -> None:
        """ステージング集合のトリアージを再計算して描画する (タブ表示時に呼ぶ)。"""
        self._update_review_scope()
        self._annotation_review_widget.refresh()
        if not self._db_manager or self._staging_state_manager is None:
            self._results_widget.clear()
            return

        staged_items = self._staging_state_manager.get_staged_items()
        image_ids = list(staged_items.keys())
        if not image_ids:
            self._results_widget.clear()
            return

        # DB 取得は N+1 を避けるため一括で行う (#1140)。ステージング全画像分の
        # metadata / annotations をバッチクエリでまとめて引く (旧実装は 1 画像 4 クエリの
        # 直列ループで GUI スレッドが数分ブロックしていた)。
        # metadata はアノテーションを別バッチで取るため include_annotations=False にして
        # 二重フェッチを避ける (Codex #1143 P2-1)。
        metadata_by_id = {
            m["id"]: m
            for m in self._db_manager.get_images_metadata_batch(image_ids, include_annotations=False)
        }
        annotations_by_id = self._db_manager.get_image_annotations_batch(image_ids)

        results = []
        valid_ids: list[int] = []
        image_names: dict[int, str] = {}
        for image_id in image_ids:
            metadata = metadata_by_id.get(image_id)
            if metadata is None:
                continue
            annotations = annotations_by_id.get(image_id, {})
            filename = self._resolve_image_filename(metadata, staged_items.get(image_id))
            if filename is not None:
                image_names[image_id] = filename
            image_meta = {
                "uuid": metadata.get("uuid"),
                "width": metadata.get("width"),
                "height": metadata.get("height"),
                "reviewed_at": metadata.get("reviewed_at"),
                "filename": filename,
            }
            results.append(self._quality_service.detect_image(image_id, image_meta, annotations))
            valid_ids.append(image_id)

        if not results:
            self._results_widget.clear()
            return

        # 大規模時 (ResultsWidget が per-row 描画を諦める degrade 域) は行サムネイルを
        # ほぼ描かないため、最低解像度パスの一括取得をスキップする (Codex #1143 P2-3)。
        # degrade でも残る clean-audit の抜き取り行 (少数) は metadata の stored_image_path
        # フォールバックでサムネイルを賄う。
        degrade = len(results) >= _VIRTUALIZE_THRESHOLD
        low_res_by_id = {} if degrade else self._db_manager.get_low_res_image_paths_batch(valid_ids)

        # 行内サムネイル用のパスを解決する (#1104)。View は DB を持たないため、パス解決は
        # このタブ (glue) が担って display に渡す。
        image_paths: dict[int, str] = {}
        for image_id in valid_ids:
            path = self._resolve_thumbnail_path(metadata_by_id[image_id], low_res_by_id.get(image_id))
            if path is not None:
                image_paths[image_id] = path

        summary = self._quality_service.summarize(results)
        self._results_widget.display(summary, results, image_paths, image_names)

    @staticmethod
    def _resolve_image_filename(
        metadata: dict[str, object],
        staged_item: tuple[str, str] | None,
    ) -> str | None:
        """metadata またはステージング項目から表示用の画像ファイル名を解決する (#1545)。"""
        for key in ("filename", "file_name", "original_image_path", "stored_image_path", "image_path"):
            raw = metadata.get(key)
            if isinstance(raw, str) and raw.strip():
                return Path(raw).name
        if staged_item is not None:
            for item_part in staged_item:
                if isinstance(item_part, str) and item_part.strip():
                    return Path(item_part).name
        return None

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
