"""アノテーションタブの専用ウィジェット (Epic #867 / #868)。

MainWindow に散在していたパイプライン構成ビュー・モデル選択 SSoT・stage ピッカー
往復・preset 配線・送信前プリフライト・推論台帳・run bar・batch tag フローを
``AnnotateTabWidget`` へ集約する。MainWindow には worker dispatch・settings・
statusBar 等の横断 glue だけを残す。

このファイルは #868 の **凍結契約スタブ** として先行 commit される (placeholder-swap)。
本実装 (Track A) は ``__init__`` 本体と各メソッドを埋めるが、**下記の公開シグネチャ
(コンストラクタ DI 契約 / Signal / プロパティ / スロット) は変更しないこと**。
MainWindow rewire (Track B) はこの契約に対してコードを書く。

== 凍結契約 (後続タブの雛形) ==
- コンストラクタ: ``AnnotateTabWidget(*, service_container, db_manager,
  staging_state_manager, dataset_state_manager, parent=None)``
- Signal (タブ → MainWindow glue):
    - ``annotation_execute_requested = Signal()`` — run bar 実行ボタン
    - ``configure_key_requested = Signal(str)`` — picker の needs key → 設定導線 (provider)
    - ``tag_add_requested = Signal(list, str)`` — batch tag 追加 (image_ids, tag)
    - ``staged_images_changed = Signal(list)`` — 内包 BatchTagAddWidget から再公開
    - ``staging_cleared = Signal()`` — 同上
- スロット / API (MainWindow → タブ):
    - ``set_staging_target(image_ids: list[int]) -> None`` — staging SSoT fan-out からの同期
      (件数・対象 ID を受けて run bar / pipeline / preflight を再計算)
    - ``add_image_ids_to_staging(image_ids: list[int]) -> None`` — サムネ「ステージへ送る」導線
    - ``refresh() -> None`` — タブ表示時の再計算 (results/errors と同型)
- 実行系 getter (MainWindow.start_annotation が読む):
    - ``selected_litellm_model_ids() -> list[str]``
    - ``stage_confidence_thresholds() -> dict[str, float]`` (#851)
    - ``get_staged_items() -> dict[int, tuple[str, str]]``
    - ``run_options() -> RunOptions``
- プロパティ (タブ内配線・テスト用):
    - ``batch_model_selection`` / ``pipeline_stage_table`` / ``preflight_summary_widget``
      / ``inference_ledger_widget`` / ``batch_tag_add_widget``
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...services.service_container import ServiceContainer
from ..state.dataset_state import DatasetStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.batch_tag_add_widget import BatchTagAddWidget
from ..widgets.inference_ledger_widget import InferenceLedgerWidget
from ..widgets.model_selection_widget import ModelSelectionWidget
from ..widgets.pipeline_stage_table_widget import PipelineStageTableWidget
from ..widgets.preflight_summary_widget import PreflightSummaryWidget
from ..widgets.run_settings_dialog import RunOptions


class AnnotateTabWidget(QWidget):
    """アノテーションタブのルートウィジェット (Wireframes v11 Frame 2 · Annotate)。

    PENDING: Issue #868 本実装 (Track A) — 本クラスは凍結契約スタブ。
    """

    annotation_execute_requested = Signal()
    configure_key_requested = Signal(str)
    tag_add_requested = Signal(list, str)
    staged_images_changed = Signal(list)
    staging_cleared = Signal()

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        staging_state_manager: StagingStateManager | None,
        dataset_state_manager: DatasetStateManager | None,
        parent: QWidget | None = None,
    ) -> None:
        """アノテーションタブを初期化する。

        Args:
            service_container: モデル選択・コスト概算・config への依存注入コンテナ。
            db_manager: 送信前プリフライトの rating 取得・アノテ結果読み書きに使う。
            staging_state_manager: アノテ対象 (= ステージング集合 SSoT)。
            dataset_state_manager: ステージングのパス解決・選択画像追加導線に使う。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager
        self._dataset_state_manager = dataset_state_manager

        # PENDING: Issue #868 — AnnotateTab.ui の load + placeholder swap +
        # pipeline/preset/picker/preflight/run bar 配線をここで構築する。
        # 下記の DI-free leaf widget 生成は契約 (プロパティ非 Optional) を満たすための
        # 暫定スケルトン。Track A が .ui ベースの本構築へ置き換える。
        self._pipeline_stage_table = PipelineStageTableWidget(parent=self)
        self._preflight_summary_widget = PreflightSummaryWidget(parent=self)
        self._inference_ledger_widget = InferenceLedgerWidget(parent=self)
        self._batch_model_selection = ModelSelectionWidget(parent=self, mode="advanced")
        self._batch_tag_add_widget = BatchTagAddWidget(parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    # -- プロパティ (タブ内配線・テスト用) -----------------------------------

    @property
    def batch_model_selection(self) -> ModelSelectionWidget:
        """モデル選択 SSoT ウィジェットを返す。"""
        return self._batch_model_selection

    @property
    def pipeline_stage_table(self) -> PipelineStageTableWidget:
        """パイプラインステージ表ウィジェットを返す。"""
        return self._pipeline_stage_table

    @property
    def preflight_summary_widget(self) -> PreflightSummaryWidget:
        """送信前プリフライト card を返す。"""
        return self._preflight_summary_widget

    @property
    def inference_ledger_widget(self) -> InferenceLedgerWidget:
        """推論台帳ウィジェットを返す。"""
        return self._inference_ledger_widget

    @property
    def batch_tag_add_widget(self) -> BatchTagAddWidget:
        """バッチタグ追加ウィジェットを返す。"""
        return self._batch_tag_add_widget

    # -- スロット / API (MainWindow → タブ) ----------------------------------

    @Slot(list)
    def set_staging_target(self, image_ids: list[int]) -> None:
        """ステージング集合 (アノテ対象) を更新し UI を再計算する。

        staging SSoT は MainWindow 所有。その fan-out からこのスロットで対象 ID を
        push する。run bar スコープ・実行ボタン・pipeline panel・preflight を再描画する。

        Args:
            image_ids: 現在のステージング画像 ID リスト。
        """
        # PENDING: Issue #868 本実装 (Track A)

    @Slot(list)
    def add_image_ids_to_staging(self, image_ids: list[int]) -> None:
        """選択画像をステージングへ追加する (サムネ「ステージへ送る」導線)。

        Args:
            image_ids: ステージングへ追加する画像 ID リスト。
        """
        # PENDING: Issue #868 本実装 (Track A)

    @Slot()
    def refresh(self) -> None:
        """タブ表示時に preflight 集計・pipeline panel・推論台帳を再計算する。"""
        # PENDING: Issue #868 本実装 (Track A)

    # -- 実行系 getter (MainWindow.start_annotation が読む) --------------------

    def selected_litellm_model_ids(self) -> list[str]:
        """選択中のモデル (litellm_model_id) を返す。"""
        # PENDING: Issue #868 本実装 (Track A)
        return []

    def stage_confidence_thresholds(self) -> dict[str, float]:
        """stage ピッカーで設定された conf-min 閾値 (litellm_model_id → 閾値) を返す (#851)。"""
        # PENDING: Issue #868 本実装 (Track A)
        return {}

    def get_staged_items(self) -> dict[int, tuple[str, str]]:
        """ステージング項目 (image_id → (name, stored_path)) を返す。"""
        # PENDING: Issue #868 本実装 (Track A)
        return {}

    def run_options(self) -> RunOptions:
        """実行詳細設定 (RunOptions) を返す。"""
        # PENDING: Issue #868 本実装 (Track A)
        return RunOptions()
