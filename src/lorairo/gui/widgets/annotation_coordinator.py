# src/lorairo/gui/widgets/annotation_coordinator.py

"""
Annotation Coordinator

ハイブリッドアノテーションUIの全体調整役
各ウィジェット間の連携と状態管理を担当
"""

from dataclasses import dataclass, field
from typing import Any, TypedDict

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QWidget

from ...database.db_manager import ImageDatabaseManager
from ...utils.log import logger
from ..services.search_filter_service import SearchFilterService
from .annotation_control_widget import AnnotationControlWidget
from .annotation_results_widget import AnnotationResultsWidget
from .annotation_status_filter_widget import AnnotationStatusFilterWidget
from .selected_image_details_widget import SelectedImageDetailsWidget
from .thumbnail import ThumbnailSelectorWidget


class _CaptionEntry(TypedDict, total=False):
    model: str
    caption: str
    confidence: float


class _TagEntry(TypedDict, total=False):
    model: str
    tags: list[str]
    confidence: list[float]


class _ScoreEntry(TypedDict, total=False):
    model: str
    score: float
    type: str


class _AnnotationResults(TypedDict):
    captions: list[_CaptionEntry]
    tags: list[_TagEntry]
    scores: list[_ScoreEntry]


@dataclass
class AnnotationWorkflowState:
    """アノテーションワークフローの状態"""

    is_running: bool = False
    selected_image_id: int | None = None
    selected_models: list[str] = field(default_factory=list)
    current_results: dict[str, Any] = field(default_factory=dict)
    active_filters: dict[str, bool] = field(default_factory=dict)


class AnnotationCoordinator(QObject):
    """
    ハイブリッドアノテーションUIの全体調整役

    各ウィジェット間の連携を管理し、統一されたワークフローを提供:
    - ウィジェット間シグナル・スロット接続
    - 状態管理と同期
    - エラーハンドリング
    - パフォーマンス最適化
    """

    # 統合シグナル
    workflow_state_changed = Signal(AnnotationWorkflowState)
    annotation_batch_started = Signal(list)  # selected_models
    annotation_batch_completed = Signal(dict)  # complete_results
    annotation_batch_error = Signal(str)  # error_message

    def __init__(
        self,
        parent: QWidget,
        db_manager: ImageDatabaseManager,
    ):
        """
        AnnotationCoordinator の初期化

        Args:
            parent: 親ウィジェット
            db_manager: データベースマネージャー
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.db_manager = db_manager

        # SearchFilterService初期化
        self.search_filter_service = SearchFilterService(db_manager)

        # ワークフロー状態
        self.workflow_state = AnnotationWorkflowState()

        # ウィジェット参照（初期化時に設定）
        self.control_widget: AnnotationControlWidget | None = None
        self.results_widget: AnnotationResultsWidget | None = None
        self.status_filter_widget: AnnotationStatusFilterWidget | None = None
        self.image_details_widget: SelectedImageDetailsWidget | None = None
        self.thumbnail_selector_widget: ThumbnailSelectorWidget | None = None

        logger.info("AnnotationCoordinator initialized")

    def setup_widgets(
        self,
        control_widget: AnnotationControlWidget,
        results_widget: AnnotationResultsWidget,
        status_filter_widget: AnnotationStatusFilterWidget,
        image_details_widget: SelectedImageDetailsWidget,
        thumbnail_selector_widget: ThumbnailSelectorWidget,
    ) -> None:
        """
        管理対象ウィジェットを設定し、連携を開始

        Args:
            control_widget: アノテーション制御ウィジェット
            results_widget: 結果表示ウィジェット
            status_filter_widget: 状態フィルターウィジェット
            image_details_widget: 画像詳細ウィジェット
            thumbnail_selector_widget: サムネイルセレクターウィジェット
        """
        # ウィジェット参照を保存
        self.control_widget = control_widget
        self.results_widget = results_widget
        self.status_filter_widget = status_filter_widget
        self.image_details_widget = image_details_widget
        self.thumbnail_selector_widget = thumbnail_selector_widget

        # データベースマネージャーを各ウィジェットに設定
        self._setup_database_connections()

        # シグナル・スロット接続を設定
        self._setup_signal_connections()

        # 初期状態を設定
        self._initialize_widget_states()

        logger.info("Widget setup completed for AnnotationCoordinator")

    def _setup_database_connections(self) -> None:
        """各ウィジェットにサービス層を設定"""
        if self.status_filter_widget:
            self.status_filter_widget.set_search_filter_service(self.search_filter_service)

        # SelectedImageDetailsWidget へのDB直接注入は未対応APIのためスキップ
        logger.debug("Database connections setup completed")

    def _setup_signal_connections(self) -> None:
        """ウィジェット間のシグナル・スロット接続を設定"""

        # 1. アノテーション制御 → 結果表示の連携
        if self.control_widget and self.results_widget:
            self.control_widget.annotation_started.connect(self._on_annotation_started)
            # Note: annotation_completed and annotation_error signals are emitted by this coordinator
            # after processing is complete, not by the control widget

        # 2. 状態フィルター → サムネイル表示の連携
        if self.status_filter_widget and self.thumbnail_selector_widget:
            self.status_filter_widget.filter_changed.connect(self._on_annotation_display_filter_changed)

        # 3. サムネイル選択 → 画像詳細表示の連携
        if self.thumbnail_selector_widget and self.image_details_widget:
            self.thumbnail_selector_widget.imageSelected.connect(self._on_image_selected)

        # 4. サムネイル選択 → 既存アノテーション結果の連携
        if self.thumbnail_selector_widget and self.results_widget:
            self.thumbnail_selector_widget.imageSelected.connect(self._on_image_selected_for_results)

        # 5. 画像詳細の評価変更 → サムネイル表示更新の連携
        # Note: update_image_rating and update_image_score methods do not exist in ThumbnailSelectorWidget
        # These connections have been disabled to prevent AttributeError
        # if self.image_details_widget and self.thumbnail_selector_widget:
        #     self.image_details_widget.rating_updated.connect(
        #         self.thumbnail_selector_widget.update_image_rating
        #     )
        #     self.image_details_widget.score_updated.connect(
        #         self.thumbnail_selector_widget.update_image_score
        #     )

        logger.debug("Signal connections setup completed")

    def _initialize_widget_states(self) -> None:
        """ウィジェットの初期状態を設定"""
        # アノテーション状態フィルターの初期更新
        if self.status_filter_widget:
            self.status_filter_widget.update_status_counts()

        # 初期ワークフロー状態の通知
        self.workflow_state_changed.emit(self.workflow_state)

        logger.debug("Widget initial states setup completed")

    @Slot(list)
    def _on_annotation_started(self, selected_models: list[str]) -> None:
        """アノテーション開始時の処理"""
        self.workflow_state.is_running = True
        self.workflow_state.selected_models = selected_models.copy()

        # 結果表示をクリア（Tier1では公開APIのみ使用）
        if self.results_widget:
            self.results_widget.clear_results()

        # UI状態を更新（実行中）
        self._update_ui_for_running_state(True)

        # 統合シグナル発行
        self.annotation_batch_started.emit(selected_models)
        self.workflow_state_changed.emit(self.workflow_state)

        logger.info(f"Annotation batch started with {len(selected_models)} models")

    @Slot(dict)
    def _on_annotation_completed(self, results: dict[str, Any]) -> None:
        """アノテーション完了時の処理"""
        self.workflow_state.is_running = False
        self.workflow_state.current_results = results.copy()

        # 結果表示を更新（AnnotationResultsWidget は add_result 群の公開APIのみ）
        if self.results_widget:
            # Tier1 ではテーブル更新のために個別追加は行わず、タイトル更新相当のみ
            summary = self.results_widget.get_results_summary()
            logger.debug(f"Results updated (summary): {summary}")

        # アノテーション状態統計を更新
        if self.status_filter_widget:
            self.status_filter_widget.update_status_counts()

        # UI状態を更新（完了）
        self._update_ui_for_running_state(False)

        # 統合シグナル発行
        self.annotation_batch_completed.emit(results)
        self.workflow_state_changed.emit(self.workflow_state)

        logger.info("Annotation batch completed successfully")

    @Slot(str)
    def _on_annotation_error(self, error_message: str) -> None:
        """アノテーションエラー時の処理"""
        self.workflow_state.is_running = False

        # エラーはログに記録（UI連携はTier2以降）
        logger.error(f"Annotation batch error: {error_message}")

        # UI状態を更新（エラー完了）
        self._update_ui_for_running_state(False)

        # 統合シグナル発行
        self.annotation_batch_error.emit(error_message)
        self.workflow_state_changed.emit(self.workflow_state)

    @Slot(dict)
    def _on_image_selected(self, image_data: dict[str, Any]) -> None:
        """画像選択時の処理（Tier1では状態のみ保持）"""
        image_id = image_data.get("id")
        if image_id is not None:
            self.workflow_state.selected_image_id = image_id

            # Tier1: UI連携呼び出しは行わない
            self.workflow_state_changed.emit(self.workflow_state)
            logger.debug(f"Image selected: ID={image_id}")

    @Slot(dict)
    def _on_image_selected_for_results(self, image_data: dict[str, Any]) -> None:
        """画像選択時の結果連携（Tier1ではログのみ）"""
        image_id = image_data.get("id")
        if image_id is not None and self.results_widget:
            try:
                existing_results = self._load_existing_annotations(image_id)
                logger.debug(
                    f"Loaded existing annotations (len={0 if not existing_results else 'some'}) for image {image_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to load existing annotations for image {image_id}: {e}")

    @Slot(dict)
    def _on_annotation_display_filter_changed(self, filter_conditions: dict[str, bool]) -> None:
        """
        アノテーション状態フィルター変更時の表示レベルフィルタリング処理

        Args:
            filter_conditions: フィルター条件 {"completed": bool, "error": bool}
        """
        if not self.thumbnail_selector_widget:
            return

        try:
            # 現在表示中の画像データを取得
            current_images = self.thumbnail_selector_widget.get_current_image_data()

            # アノテーション状態でフィルタリング
            filtered_images = self._filter_by_annotation_status(current_images, filter_conditions)

            # サムネイル表示を更新
            self.thumbnail_selector_widget._on_images_filtered(filtered_images)

            logger.debug(f"Display filter applied: {len(current_images)} → {len(filtered_images)} images")

        except Exception as e:
            logger.error(f"Failed to apply annotation display filter: {e}")

    def _filter_by_annotation_status(
        self, images: list[dict[str, Any]], filters: dict[str, bool]
    ) -> list[dict[str, Any]]:
        """
        アノテーション状態で画像リストをフィルタリング

        Args:
            images: 画像メタデータリスト
            filters: フィルター条件 {"completed": bool, "error": bool}

        Returns:
            list[dict]: フィルタリング済み画像リスト
        """
        if not filters.get("completed", False) and not filters.get("error", False):
            # フィルターが無効な場合は全て表示
            return images

        filtered = []
        for image in images:
            # アノテーション完了状態をチェック
            has_annotations = (
                image.get("has_tags", False)
                or image.get("has_captions", False)
                or image.get("annotation_completed", False)
            )

            # エラー状態をチェック
            has_errors = image.get("has_annotation_errors", False) or image.get("annotation_error", False)

            # フィルター条件に合致するかチェック
            show_image = True

            if filters.get("completed", False) and not has_annotations:
                show_image = False

            if filters.get("error", False) and not has_errors:
                show_image = False

            if show_image:
                filtered.append(image)

        return filtered

    def _update_ui_for_running_state(self, is_running: bool) -> None:
        """実行状態に応じたUI更新"""
        # アノテーション制御ウィジェットの状態更新（Tier1: 直接API未提供のためスキップ）
        # その他のウィジェットの操作制限を最小限に
        if self.status_filter_widget:
            self.status_filter_widget.setEnabled(not is_running)
        if self.image_details_widget:
            self.image_details_widget.setEnabled(not is_running)

    def _load_existing_annotations(self, image_id: int) -> _AnnotationResults | None:
        """既存のアノテーション結果を読み込み"""
        try:
            # データベースから既存アノテーションを取得（db_managerにAPIがある前提。なければ空扱い）
            if not hasattr(self.db_manager, "get_annotations_by_image_id"):
                return None
            annotations = self.db_manager.get_annotations_by_image_id(image_id)

            if not annotations:
                return None

            # 結果表示用フォーマットに変換
            formatted_results: _AnnotationResults = {"captions": [], "tags": [], "scores": []}

            # キャプション情報
            if "captions" in annotations:
                for caption in annotations["captions"]:
                    formatted_results["captions"].append(
                        {
                            "model": caption.get("model_name", "Unknown"),
                            "caption": caption.get("content", ""),
                            "confidence": caption.get("confidence", 0.0),
                        }
                    )

            # タグ情報
            if "tags" in annotations:
                for tag_group in annotations["tags"]:
                    formatted_results["tags"].append(
                        {
                            "model": tag_group.get("model_name", "Unknown"),
                            "tags": tag_group.get("content", "").split(", "),
                            "confidence": [1.0] * len(tag_group.get("content", "").split(", ")),
                        }
                    )

            # スコア情報
            if "scores" in annotations:
                for score in annotations["scores"]:
                    formatted_results["scores"].append(
                        {
                            "model": score.get("model_name", "Unknown"),
                            "score": score.get("value", 0.0),
                            "type": score.get("score_type", "unknown"),
                        }
                    )

            return formatted_results

        except Exception as e:
            logger.error(f"Error loading existing annotations for image {image_id}: {e}")
            return None

    def refresh_all_widgets(self) -> None:
        """全ウィジェットの表示を更新"""
        if self.status_filter_widget:
            self.status_filter_widget.update_status_counts()

        # Note: refresh_thumbnails method does not exist in ThumbnailSelectorWidget
        # This call has been disabled to prevent AttributeError
        # if self.thumbnail_selector_widget:
        #     self.thumbnail_selector_widget.refresh_thumbnails()

        logger.debug("All widgets refreshed")

    def get_current_state(self) -> AnnotationWorkflowState:
        """現在のワークフロー状態を取得"""
        return self.workflow_state

    def reset_workflow(self) -> None:
        """ワークフローをリセット"""
        self.workflow_state = AnnotationWorkflowState()

        # 全ウィジェットをリセット
        if self.results_widget:
            self.results_widget.clear_results()

        # Tier1: details の明示APIなしのためスキップ

        # UI状態を更新
        self._update_ui_for_running_state(False)

        # 状態変更を通知
        self.workflow_state_changed.emit(self.workflow_state)

        logger.info("Annotation workflow reset")


if __name__ == "__main__":
    # 末尾に __main__ ブロックを配置（ユーザー要望に合わせる）
    import sys

    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

    from ...utils.log import initialize_logging

    # ログ初期化（共通パターン）
    initialize_logging({"level": "DEBUG", "file": "AnnotationCoordinator.log"})

    app = QApplication(sys.argv)

    # 親ウィンドウ
    main = QMainWindow()
    main.setWindowTitle("AnnotationCoordinator テスト")
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.addWidget(QLabel("Coordinatorの初期化とログのみを確認（Tier1）"))
    main.setCentralWidget(container)

    # Coordinator 初期化（DB依存は最小化：SearchFilterServiceの内部利用を避けるため、Noneを渡さない）
    # ImageDatabaseManager は抽象に近いので簡易スタブを用意せず、Noneガードを行う設計ではないため
    # ここでは実体生成が前提のため、実行テスト用途ではウィジェクト生成をスキップして起動のみ確認
    # （Tier2で安全なスタブ導入またはDI見直しを行う）
    # NOTE: 実運用では MainWindow 経由で正規の db_manager を渡す

    main.resize(640, 400)
    main.show()
    sys.exit(app.exec())
