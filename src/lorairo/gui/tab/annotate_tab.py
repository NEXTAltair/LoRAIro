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
  staging_state_manager, dataset_state_manager,
  model_selection_state_manager=None, parent=None)``
  (#884: model_selection_state_manager を追加、後方互換のため既定値 None)
- Signal (タブ → MainWindow glue):
    - ``annotation_execute_requested = Signal(str)`` — run bar 実行ボタン。
      引数は dispatch_mode ("sync" / "batch_api"、#1099: 実行ボタン自体がモードを持つ)
    - ``configure_key_requested = Signal(str)`` — picker の needs key → 設定導線 (provider)
    - ``status_message = Signal(str)`` — statusBar 表示要求 (batch tag 書込結果など、#896)
    - ``staged_images_changed = Signal(list)`` — 内包 BatchTagAddWidget から再公開
    - ``staging_cleared = Signal()`` — 同上
- スロット / API (MainWindow → タブ):
    - ``set_staging_target(image_ids: list[int]) -> None`` — staging SSoT fan-out からの同期
      (件数・対象 ID を受けて run bar / pipeline / preflight を再計算)
    - ``add_image_ids_to_staging(image_ids: list[int]) -> None`` — サムネ「ステージへ送る」導線
    - ``refresh() -> None`` — タブ表示時の再計算 (results/errors と同型)
- 実行系 getter (MainWindow.start_annotation が読む):
    - ``selected_litellm_model_ids() -> list[str]``
    - ``get_staged_items() -> dict[int, tuple[str, str]]``
    - ``run_options() -> RunOptions``
- プロパティ (タブ内配線・テスト用):
    - ``batch_model_selection`` / ``pipeline_stage_table`` / ``preflight_summary_widget``
      / ``inference_ledger_widget`` / ``batch_tag_add_widget``
"""

import json
from dataclasses import replace
from typing import Any

from PySide6.QtCore import QObject, QSettings, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from ...database.db_core import resolve_stored_path
from ...database.db_manager import ImageDatabaseManager
from ...services.dispatch_projection_service import batch_eligible_litellm_ids
from ...services.model_route_service import (
    RoutePreference,
    build_available_providers,
    canonical_key,
    detect_route,
    is_webapi_model_id,
    parse_route_preference,
    required_provider_for,
)
from ...services.model_selection_service import ModelSelectionService
from ...services.pipeline_composition import PipelineCompositionService, PipelineStage, StageModelInfo
from ...services.provider_batch_capability import is_omni_moderation_model
from ...services.provider_batch_service import ProviderBatchError
from ...services.service_container import ServiceContainer
from ...services.tag_suggestion_service import TagSuggestionService
from ...utils.log import logger
from .. import theme
from ..designer.AnnotateTab_ui import Ui_AnnotateTab
from ..message_box import show_critical, show_information, show_warning
from ..services.image_db_write_service import ImageDBWriteService
from ..state.dataset_state import DatasetStateManager
from ..state.model_selection_state import ModelSelectionStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.annotation_filter_widget import AnnotationFilterWidget
from ..widgets.batch_tag_add_widget import BatchTagAddWidget
from ..widgets.image_comparison_dialog import ImageComparisonLauncher
from ..widgets.inference_ledger_widget import InferenceLedgerWidget
from ..widgets.model_selection_widget import ModelSelectionWidget
from ..widgets.pipeline_stage_table_widget import PipelinePreset, PipelineStageTableWidget
from ..widgets.preflight_summary_widget import PreflightSummaryWidget
from ..widgets.run_settings_dialog import RunOptions, RunSettingsDialog
from ..widgets.stage_model_picker_dialog import StageModelPickerDialog

# 保存済みプリセット (#1186): QSettings キーと、組込みプリセットと衝突しない preset_id 名前空間
_CUSTOM_PRESETS_SETTINGS_KEY = "annotate_tab/custom_presets"
_CUSTOM_PRESET_PREFIX = "custom:"
# #1537: Default プリセットで選択する代表モデルの上限数
_DEFAULT_PRESET_MAX_MODELS = 5
# #1544: バッチタグ書き込み worker thread の shutdown 待機上限 (ms)
_BATCH_TAG_SHUTDOWN_WAIT_MS = 5000


class _BatchTagWriteWorker(QObject):
    """バッチタグ書き込みを GUI スレッド外で実行する worker (#1544)。"""

    finished_with_result = Signal(list, str, bool)  # (image_ids, tag, success)
    finished = Signal()

    def __init__(
        self,
        write_service: ImageDBWriteService | None,
        image_ids: list[int],
        tag: str,
    ) -> None:
        super().__init__()
        self._write_service = write_service
        self._image_ids = list(image_ids)
        self._tag = tag

    @Slot()
    def run(self) -> None:
        """add_tag_batch を実行し、完了シグナルを送出する。"""
        success = False
        try:
            if self._write_service is not None:
                success = bool(self._write_service.add_tag_batch(self._image_ids, self._tag))
            else:
                logger.warning("ImageDBWriteService not initialized")
        except Exception as e:
            logger.opt(exception=e).error(
                f"Batch tag write worker failed: tag='{self._tag}', count={len(self._image_ids)}: {e}"
            )
            success = False
        finally:
            self.finished_with_result.emit(self._image_ids, self._tag, success)
            self.finished.emit()


_ACTIVE_BATCH_TAG_RUNNERS: set[tuple[QThread, _BatchTagWriteWorker]] = set()


class AnnotateTabWidget(QWidget, Ui_AnnotateTab):
    """アノテーションタブのルートウィジェット (Wireframes v11 Frame 2 · Annotate)。

    ``AnnotateTab.ui`` を ``setupUi`` で展開し、placeholder を実ウィジェットへ swap した
    うえで、パイプライン構成ビュー・送信前プリフライト・推論台帳・run bar を
    ``groupBoxAnnotation`` に常設する。ステージング集合の SSoT は MainWindow が所有し、
    その fan-out を :meth:`set_staging_target` で受けて UI を再計算する。
    """

    annotation_execute_requested = Signal(str)  # dispatch_mode ("sync" / "batch_api")、#1099
    configure_key_requested = Signal(str)
    status_message = Signal(str)  # statusBar 表示要求 (image_ids バッチタグ書込結果など、#896)
    staged_images_changed = Signal(list)
    staging_cleared = Signal()

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        staging_state_manager: StagingStateManager | None,
        dataset_state_manager: DatasetStateManager | None,
        model_selection_state_manager: ModelSelectionStateManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """アノテーションタブを初期化する。

        Args:
            service_container: モデル選択・コスト概算・config への依存注入コンテナ。
            db_manager: 送信前プリフライトの rating 取得・アノテ結果読み書きに使う。
            staging_state_manager: アノテ対象 (= ステージング集合 SSoT)。
            dataset_state_manager: ステージングのパス解決・選択画像追加導線に使う。
            model_selection_state_manager: 選択モデル集合 SSoT (#884, ADR 0076)。
                None の場合は従来どおり ModelSelectionWidget の checkbox 状態を読む。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager
        self._dataset_state_manager = dataset_state_manager
        self._model_selection_state_manager = model_selection_state_manager
        # バッチタグ書込サービス (#896: MainWindow から移送)。db_manager から自前構築する。
        self._image_db_write_service = ImageDBWriteService(db_manager) if db_manager else None
        # widget ↔ state manager 双方向同期の再帰ガード
        self._syncing_model_selection = False

        self.setupUi(self)

        # #1156: 実行ボタン連打による多重投入を防ぐ再入ガード。実行開始〜終端シグナルの間 True。
        self._execute_in_flight = False

        # パイプライン構成サービスと送信前プリフライト・推論台帳の集計状態
        self._pipeline_composition_service = PipelineCompositionService()
        self._pipeline_staged_count = 0
        # 送信前プリフライト card (Issue #837) の集計対象。ステージング集合の image_id。
        self._pipeline_staged_image_ids: list[int] = []
        # 実行詳細設定 (Issue #789)。詳細設定モーダルの確定値を保持する。
        self._pipeline_run_options = RunOptions()
        # #1537 / #1538: プリセット適用状態および offscreen 選択モデルの保持
        self._active_preset_id: str | None = None
        self._last_preset_model_ids: set[str] = set()
        self._extra_selected_model_ids: list[str] = []
        # #1544: 非同期バッチタグ書き込み状態・worker 管理
        self._batch_tag_write_in_progress = False
        self._batch_tag_runners: set[tuple[QThread, _BatchTagWriteWorker]] = set()
        # #1515: モデル情報・コストマップ・ステージ構成・rating プリフライトのキャッシュ
        self._cached_cost_map: dict[str, tuple[float | None, float | None]] | None = None
        self._cached_loaded_models: list[Any] | None = None
        self._cached_stage_info_by_id: dict[str, StageModelInfo] | None = None
        self._cached_stage_info_service: object | None = None
        self._last_composed_selected_ids: tuple[str, ...] | None = None
        self._cached_ratings_by_id: dict[int, str | None] = {}
        self._cached_ratings_db_manager: object | None = None

        # .ui placeholder を実ウィジェットへ swap (BatchTagAddWidget / フィルタ / モデル選択)
        self._batch_tag_add_widget = self._swap_batch_tag_add_widget()
        self._attach_tag_input()
        self._batch_annotation_filter = self._swap_annotation_filter()
        self._batch_model_selection = self._swap_model_selection()
        self._connect_filter_to_model()

        # パイプライン構成ビュー・preflight・推論台帳・run bar を常設配置
        self._build_pipeline_composition_panel()

        # BatchTagAddWidget の DI と上方向 re-emit を配線
        self._wire_batch_tag_add_widget()

        # 初回描画
        self._refresh_pipeline_panel([])
        self._refresh_preflight_summary()
        logger.info("✅ AnnotateTabWidget initialized")

    # -- placeholder swap (構築) ----------------------------------------------

    def _swap_batch_tag_add_widget(self) -> BatchTagAddWidget:
        """``batchTagWidgetPlaceholder`` を BatchTagAddWidget に差し替える。"""
        widget = BatchTagAddWidget()
        widget.setObjectName("batchTagAddWidget")
        widget.set_tag_suggestion_service(self._resolve_tag_suggestion_service())
        index = self.splitterBatchTagMain.indexOf(self.batchTagWidgetPlaceholder)
        self.splitterBatchTagMain.replaceWidget(index, widget)
        self.batchTagWidgetPlaceholder.deleteLater()
        return widget

    def _resolve_tag_suggestion_service(self) -> TagSuggestionService | None:
        """バッチタグ入力の補完候補ソースを構築する (Issue #1439)。

        Returns:
            MergedTagReader を引けた場合は TagSuggestionService、引けなければ None
            (タグ入力は補完なしで動作する)。
        """
        # 初期化は起動しない (#1438)。未準備なら補完なしで始め、on_tag_db_ready() で後付けする。
        try:
            merged_reader = self._service_container.db_manager.annotation_repo.peek_merged_reader()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"MergedTagReader 取得に失敗 (タグ補完なしで継続): {e}")
            return None
        return TagSuggestionService(merged_reader) if merged_reader is not None else None

    def on_tag_db_ready(self) -> None:
        """背景で tag DB の準備が終わった後に、バッチタグ入力の補完を有効化する (#1438)。"""
        self._batch_tag_add_widget.set_tag_suggestion_service(self._resolve_tag_suggestion_service())

    def _attach_tag_input(self) -> None:
        """タグ追加入力を ``batchTagInputPlaceholder`` へ移設する。"""
        self._batch_tag_add_widget.attach_tag_input_to(self.batchTagInputPlaceholder)

    def _swap_annotation_filter(self) -> AnnotationFilterWidget:
        """``annotationFilterPlaceholder`` を AnnotationFilterWidget に差し替える。

        #845: 絞り込みは per-stage ピッカー (+pick…) のレールへ集約する。常設インライン
        UI は畳むが、``filter_changed`` → model 連携の SSoT として残すため生成はする。
        """
        layout = self.verticalLayout_annotation
        index = layout.indexOf(self.annotationFilterPlaceholder)
        layout.removeWidget(self.annotationFilterPlaceholder)
        self.annotationFilterPlaceholder.setParent(None)
        self.annotationFilterPlaceholder.deleteLater()

        widget = AnnotationFilterWidget(parent=self.groupBoxAnnotation)
        widget.setObjectName("batchAnnotationFilter")
        layout.insertWidget(index, widget)
        widget.setVisible(False)  # #845: 非表示 SSoT
        return widget

    def _swap_model_selection(self) -> ModelSelectionWidget:
        """``modelSelectionPlaceholder`` を ModelSelectionWidget に差し替える。

        #845: モデル選択は per-stage ピッカーへ集約するため非表示。ただし選択状態
        (model_checkbox_widgets) はピッカー適用・実行・pipeline 購読の SSoT として保持する。
        global lookup を避けるため :class:`ModelSelectionService` は DI で生成して渡す。
        """
        layout = self.verticalLayout_annotation
        index = layout.indexOf(self.modelSelectionPlaceholder)
        layout.removeWidget(self.modelSelectionPlaceholder)
        self.modelSelectionPlaceholder.setParent(None)
        self.modelSelectionPlaceholder.deleteLater()

        model_service = ModelSelectionService.create(
            db_repository=self._service_container.db_manager.model_repo
        )
        widget = ModelSelectionWidget(
            parent=self.groupBoxAnnotation,
            model_selection_service=model_service,
            mode="advanced",
        )
        widget.setObjectName("batchModelSelection")
        layout.insertWidget(index, widget)
        widget.setVisible(False)  # #845: 非表示 SSoT

        # batch annotation では外側の環境フィルターを唯一の操作面にする
        if hasattr(widget, "executionEnvCombo"):
            widget.executionEnvCombo.setVisible(False)
        widget.set_annotation_only_filtering(True)
        return widget

    def _connect_filter_to_model(self) -> None:
        """AnnotationFilterWidget の出力を ModelSelectionWidget へ伝播する。"""
        self._batch_annotation_filter.filter_changed.connect(self._apply_filter_to_model)
        # アノテーション走査用デフォルトフィルター (upscaler 除外)
        self._batch_model_selection.apply_filters(annotation_only=True)

    def _apply_filter_to_model(self, filters: dict[str, object]) -> None:
        """AnnotationFilterWidget の出力を ModelSelectionWidget.apply_filters へ変換する。

        Args:
            filters: ``{capabilities: list[str], environment: str | None}`` の絞り込み状態。
        """
        capabilities_raw = filters.get("capabilities", [])
        capabilities = capabilities_raw if isinstance(capabilities_raw, list) else []
        environment = filters.get("environment")
        execution_env: str | None = None
        if isinstance(environment, str):
            execution_env = {"api": "APIモデルのみ", "local": "ローカルモデルのみ"}.get(environment)
        self._batch_model_selection.apply_filters(
            provider=None,
            capabilities=capabilities,
            exclude_local=False,
            execution_env=execution_env,
            annotation_only=True,
        )

    def _build_pipeline_composition_panel(self) -> None:
        """アノテーショングループにパイプライン構成ビューを常設する。

        Wireframes v11 Frame 2A/2B。ModelSelectionWidget の選択を購読して
        TAGS/CAPTION/SCORE/RATING への自動仕分け・推論台帳をリアルタイム表示する。
        各ステージ行の「+ 追加」/ primary チップの × はチェック状態の ON/OFF に変換する
        (SSoT は選択モデル集合)。
        """
        layout = self.verticalLayout_annotation

        self._pipeline_stage_table = PipelineStageTableWidget(parent=self.groupBoxAnnotation)
        # DS AnnotateScreen 順: ステージ表 → 送信前プリフライト → 推論台帳
        self._preflight_summary_widget = PreflightSummaryWidget(parent=self.groupBoxAnnotation)
        self._inference_ledger_widget = InferenceLedgerWidget(parent=self.groupBoxAnnotation)
        layout.addWidget(self._pipeline_stage_table)
        layout.addWidget(self._preflight_summary_widget)
        layout.addWidget(self._inference_ledger_widget)

        # 実行詳細設定モーダルを開く導線 (Issue #789、DS Frame 3 run bar「詳細設定 ▸」)
        self._btn_run_settings = QPushButton("詳細設定 ▸", self.groupBoxAnnotation)
        self._btn_run_settings.setObjectName("btnPipelineRunSettings")
        self._btn_run_settings.clicked.connect(self._open_run_settings)

        # run bar (Issue #849): scope 表示 + 詳細設定 + 実行ボタンを横一列に配置
        run_bar = self._build_pipeline_run_bar()
        layout.addWidget(run_bar)

        # .ui 由来の btnAnnotationExecute は run bar に統合したため非表示にする (Issue #849)
        self.btnAnnotationExecute.setVisible(False)

        # Signal 配線
        self._batch_model_selection.model_selection_changed.connect(self._on_pipeline_models_changed)
        self._batch_model_selection.model_options_changed.connect(self.reconcile_model_selection)
        self._pipeline_stage_table.add_model_requested.connect(self._on_pipeline_add_model_requested)
        self._pipeline_stage_table.remove_model_requested.connect(self._on_pipeline_remove_model_requested)
        # preset 配線 (Issue #847): preset chip 選択 / 保存要求をハンドラへ接続
        self._pipeline_stage_table.preset_selected.connect(self._on_pipeline_preset_selected)
        self._pipeline_stage_table.save_preset_requested.connect(self._on_pipeline_save_preset_requested)
        # 送信前プリフライト配線 (#1558): 事前レーティング判定要求をハンドラへ接続
        self._preflight_summary_widget.run_rating_preflight_requested.connect(
            self._on_run_rating_preflight_requested
        )
        # 保存済みカスタムプリセットを chip 行へ復元する (#1186)
        self._refresh_custom_preset_chips(self._load_custom_presets())

        # モデル選択 SSoT を gui/state/ へ hoist (#884, ADR 0076)
        if self._model_selection_state_manager is not None:
            self._batch_model_selection.model_selection_changed.connect(
                self._on_widget_model_selection_changed
            )
            self._model_selection_state_manager.selection_changed.connect(
                self._on_state_model_selection_changed
            )

        self._update_annotation_target_ui(self._pipeline_staged_count)

    def _build_pipeline_run_bar(self) -> QWidget:
        """パイプライン実行バーウィジェットを構築する (Issue #849, #1099)。

        左側にスコープ表示ラベル、右側に詳細設定ボタンと2つの実行ボタン
        (「同期実行」「Batch API 実行」) を横並びに配置する。各実行ボタンは押下時の
        dispatch_mode を :data:`annotation_execute_requested` に載せて発火し、MainWindow
        glue が実 run flow へ委譲する (#1099: モードはダイアログでなくボタンが持つ)。

        Returns:
            run bar ウィジェット。
        """
        bar = QWidget(self.groupBoxAnnotation)
        bar.setObjectName("pipelineRunBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 4, 0, 0)
        bar_layout.setSpacing(8)

        # スコープ表示ラベル (左側)
        scope_label = QLabel(self._run_bar_scope_text(0), bar)
        scope_label.setObjectName("runBarScopeLabel")
        scope_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        self._run_bar_scope_label = scope_label
        bar_layout.addWidget(scope_label)

        # ドライラン表示インジケーター (#1558)
        self._dry_run_indicator = QLabel("ドライラン（DB未保存）", bar)
        self._dry_run_indicator.setObjectName("dryRunIndicatorLabel")
        self._dry_run_indicator.setStyleSheet(theme.badge_qss("warn"))
        self._dry_run_indicator.setVisible(bool(self._pipeline_run_options.dry_run))
        bar_layout.addWidget(self._dry_run_indicator)

        bar_layout.addStretch(1)

        # 詳細設定ボタン (btnPipelineRunSettings を run bar へ再配置)
        bar_layout.addWidget(self._btn_run_settings)

        # 同期実行ボタン (#1099: dispatch_mode="sync")
        sync_btn = QPushButton(self._run_bar_sync_execute_text(0), bar)
        sync_btn.setObjectName("btnPipelineExecuteSync")
        sync_btn.setEnabled(False)
        sync_btn.clicked.connect(lambda: self._on_execute_clicked("sync"))
        self._btn_sync_execute = sync_btn
        bar_layout.addWidget(sync_btn)

        # Batch API 実行ボタン (#1099: dispatch_mode="batch_api")
        batch_btn = QPushButton(self._run_bar_batch_execute_text(0), bar)
        batch_btn.setObjectName("btnPipelineExecuteBatchApi")
        batch_btn.setEnabled(False)
        batch_btn.clicked.connect(lambda: self._on_execute_clicked("batch_api"))
        self._btn_batch_api_execute = batch_btn
        bar_layout.addWidget(batch_btn)

        return bar

    def _on_execute_clicked(self, dispatch_mode: str) -> None:
        """実行ボタン押下で dispatch_mode を確定して実行要求を発火する (#1099)。

        押下したボタンが持つ dispatch_mode を確定値 (RunOptions) へ反映し、
        :data:`annotation_execute_requested` に載せて MainWindow glue へ委譲する。
        詳細設定ダイアログの dispatch_mode UI は撤去済みで、モードはボタンが SSoT。

        Args:
            dispatch_mode: "sync" (同期実行) または "batch_api" (Batch API 実行)。
        """
        # #1156: 実行中 / 開始判定中 (start_annotation のダイアログ表示でイベントループが
        # 回る間を含む) の再クリックを塞ぎ、連打による同一ジョブの多重投入を防ぐ。
        if self._execute_in_flight:
            return
        self._execute_in_flight = True
        self._pipeline_run_options = replace(self._pipeline_run_options, dispatch_mode=dispatch_mode)
        self.annotation_execute_requested.emit(dispatch_mode)

    def set_execution_running(self, running: bool) -> None:
        """実行中は両実行ボタンを無効化し「実行中…」表示、終端で再有効化する (#1156)。

        MainWindow glue が ``start_annotation`` の成否と worker 終端シグナル
        (enhanced_annotation_finished/error/canceled)・async dispatch thread 終了に応じて
        呼ぶ。``running=True`` で多重投入を防ぎ、``False`` で staging 件数に応じて再有効化する。
        開始前に拒否された場合 (start_annotation=False) は False で即再有効化する。

        Args:
            running: 実行中なら True (無効化)、終了/拒否なら False (再有効化)。
        """
        self._execute_in_flight = running
        # ボタン状態は _update_annotation_target_ui が _execute_in_flight を見て決める。
        self._update_annotation_target_ui(self._pipeline_staged_count)

    @staticmethod
    def _run_bar_scope_text(count: int) -> str:
        """run bar のスコープ表示テキストを生成する。"""
        return f"ステージング集合のみ · staged {count} · 実行 → Jobs タブへ"

    @staticmethod
    def _run_bar_sync_execute_text(count: int) -> str:
        """run bar の同期実行ボタンテキストを生成する (#1099)。"""
        return f"▶ 同期実行 · {count}枚"

    @staticmethod
    def _run_bar_batch_execute_text(count: int) -> str:
        """run bar の Batch API 実行ボタンテキストを生成する (#1099)。"""
        return f"▶ Batch API 実行 · {count}枚"

    def _wire_batch_tag_add_widget(self) -> None:
        """BatchTagAddWidget へ共有 SSoT を注入し、各 Signal を上方向へ再公開する。

        staging SSoT は MainWindow 所有。BatchTagAddWidget のユーザー操作は本タブの
        同名 Signal へ re-emit して MainWindow の SSoT へ伝える。SSoT の fan-out は
        逆方向に :meth:`set_staging_target` で本タブへ戻る (ADR 0074)。
        """
        if self._dataset_state_manager is not None:
            self._batch_tag_add_widget.set_dataset_state_manager(self._dataset_state_manager)
        if self._staging_state_manager is not None:
            self._batch_tag_add_widget.set_staging_state_manager(self._staging_state_manager)

        self._batch_tag_add_widget.staged_images_changed.connect(self.staged_images_changed)
        self._batch_tag_add_widget.staging_cleared.connect(self.staging_cleared)
        # #896: batch tag 書込はタブ内で処理し、MainWindow へは bubble しない。
        self._batch_tag_add_widget.tag_add_requested.connect(self._handle_batch_tag_add)
        # #1399: ステージングの「比較…」から読み取り専用の比較画面を開く。
        self._image_comparison_launcher = ImageComparisonLauncher(
            self._db_manager, self, self._dataset_state_manager
        )
        self._batch_tag_add_widget.compare_requested.connect(self._image_comparison_launcher.open)

    def shutdown(self) -> None:
        """タブが持つ比較画面およびバッチタグ書き込みの worker を止める (ウィンドウ閉鎖時、MainWindow.closeEvent から呼ぶ)。"""
        self._image_comparison_launcher.shutdown()
        for runner in list(self._batch_tag_runners):
            thread, worker = runner
            thread.quit()
            if thread.wait(_BATCH_TAG_SHUTDOWN_WAIT_MS):
                try:
                    thread.started.disconnect(worker.run)
                except (RuntimeError, TypeError):
                    pass
                self._batch_tag_runners.discard(runner)
                _ACTIVE_BATCH_TAG_RUNNERS.discard(runner)
                self._batch_tag_write_in_progress = False
            else:
                logger.warning(
                    "バッチタグ書き込み worker が時間内に停止しませんでした。完了まで参照を保持します"
                )

    def has_pending_batch_tag_writes(self) -> bool:
        """バッチタグ書き込み worker が未完了かを返す (プロジェクト切替の可否判定用、#1547)。"""
        return bool(self._batch_tag_runners)

    # -- バッチタグ書込 (#896: MainWindow から移送, #1544: 非同期 worker 化) -----

    def _execute_batch_tag_write(self, image_ids: list[int], tag: str) -> bool:
        """バッチタグ書き込みと dataset キャッシュ更新を実行する。

        Args:
            image_ids: 対象画像の ID リスト。
            tag: 追加するタグ (正規化済み)。

        Returns:
            成功した場合 True。
        """
        if self._image_db_write_service is None:
            logger.warning("ImageDBWriteService not initialized")
            return False

        success = self._image_db_write_service.add_tag_batch(image_ids, tag)
        if success and self._dataset_state_manager is not None:
            self._dataset_state_manager.refresh_images(image_ids)
        return success

    def _handle_batch_tag_add(self, image_ids: list[int], tag: str) -> None:
        """BatchTagAddWidget からのバッチタグ追加シグナルを非同期 worker で処理する (#1544)。

        Args:
            image_ids: 対象画像の ID リスト。
            tag: 追加するタグ (正規化済み)。
        """
        if not image_ids:
            logger.warning("Batch tag add requested with empty image list")
            return
        if self._batch_tag_write_in_progress:
            logger.debug("Batch tag add ignored: write already in progress")
            return

        logger.info(f"Batch tag add requested: tag='{tag}' for {len(image_ids)} images")
        self._batch_tag_write_in_progress = True
        self._batch_tag_add_widget.set_busy(True)
        self._start_batch_tag_write_worker(image_ids, tag)

    def _start_batch_tag_write_worker(self, image_ids: list[int], tag: str) -> None:
        """バッチタグ書き込みを専用 QThread で開始する (#1544, ADR 0044)。"""
        thread = QThread()
        worker = _BatchTagWriteWorker(self._image_db_write_service, image_ids, tag)
        worker.moveToThread(thread)
        runner = (thread, worker)
        _ACTIVE_BATCH_TAG_RUNNERS.add(runner)
        self._batch_tag_runners.add(runner)

        thread.started.connect(worker.run)
        worker.finished_with_result.connect(self._on_batch_tag_write_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._on_batch_tag_thread_finished(runner))
        thread.finished.connect(thread.deleteLater)

        thread.start()

    @Slot(list, str, bool)
    def _on_batch_tag_write_finished(self, image_ids: list[int], tag: str, success: bool) -> None:
        """バッチタグ書き込み完了時に UI・キャッシュ・ステージングを更新する (#1544)。"""
        self._batch_tag_write_in_progress = False
        self._batch_tag_add_widget.set_busy(False)
        if success:
            if self._dataset_state_manager is not None:
                self._dataset_state_manager.refresh_images(image_ids)
            # 完了したバッチ対象 ID のみをステージングから除外 (非同期書込中に追加された画像は保持)
            if self._staging_state_manager is not None:
                self._staging_state_manager.remove_image_ids(image_ids)

            self.status_message.emit(f"タグ '{tag}' を {len(image_ids)} 件の画像に追加しました")
            logger.info(
                f"Batch tag add completed successfully: tag='{tag}', {len(image_ids)} images updated"
            )
        else:
            show_critical(self, "タグ追加失敗", f"タグ '{tag}' の追加に失敗しました。")
            logger.error(f"Failed to add tag in batch: tag='{tag}', image_count={len(image_ids)}")

    def _on_batch_tag_thread_finished(self, runner: tuple[QThread, _BatchTagWriteWorker]) -> None:
        """バッチタグ worker thread 終了時に参照解放する (#1544)。"""
        thread, worker = runner
        thread.wait()
        try:
            thread.started.disconnect(worker.run)
        except (RuntimeError, TypeError):
            pass
        self._batch_tag_runners.discard(runner)
        _ACTIVE_BATCH_TAG_RUNNERS.discard(runner)

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
        count = len(image_ids) if image_ids else 0
        self._pipeline_staged_count = count
        self._pipeline_staged_image_ids = list(image_ids) if image_ids else []
        self._update_annotation_target_ui(count)
        self._refresh_pipeline_panel()
        self._refresh_preflight_summary()

    @Slot(list)
    def add_image_ids_to_staging(self, image_ids: list[int]) -> None:
        """選択画像をステージングへ追加する (サムネ「ステージへ送る」導線)。

        Args:
            image_ids: ステージングへ追加する画像 ID リスト。
        """
        self._batch_tag_add_widget.add_image_ids_to_staging(image_ids)

    @Slot()
    def refresh(self) -> None:
        """タブ表示時に preflight 集計・pipeline panel・推論台帳を再計算する。"""
        self._invalidate_model_caches()
        self._cached_ratings_by_id.clear()
        self._refresh_pipeline_panel()
        self._refresh_preflight_summary()

    def _invalidate_model_caches(self) -> None:
        """モデル一覧・StageModelInfo・コストマップのキャッシュを破棄する (#1515)。"""
        self._cached_cost_map = None
        self._cached_loaded_models = None
        self._cached_stage_info_by_id = None
        self._cached_stage_info_service = None
        self._last_composed_selected_ids = None

    def _load_all_models_cached(self) -> list[Any]:
        """ModelSelectionService.load_models() の結果をキャッシュ付きで返す (#1515)。"""
        service = getattr(self._batch_model_selection, "model_selection_service", None)
        if service is None:
            return []
        if self._cached_loaded_models is not None and self._cached_stage_info_service is service:
            return self._cached_loaded_models
        raw_models = service.load_models()
        models = raw_models if isinstance(raw_models, list) else []
        self._cached_loaded_models = models
        self._cached_stage_info_service = service
        self._cached_stage_info_by_id = None
        return models

    # -- 実行系 getter (MainWindow.start_annotation が読む) --------------------

    def refresh_model_selection(self) -> None:
        """設定保存後・実行直前に最新の経路と選択状態を同期する。"""
        self._invalidate_model_caches()
        self._batch_model_selection.update_model_display()
        # 同一表示で rebuild が省略されても stale な SSoT を検証する。
        self.reconcile_model_selection()

    @Slot()
    def reconcile_model_selection(self) -> None:
        """利用できなくなった経路を解除し、有効な offscreen 選択は維持する。"""
        self._invalidate_model_caches()
        selectable = self._batch_model_selection.selectable_litellm_model_ids()
        selected = [mid for mid in self.selected_litellm_model_ids() if mid in selectable]
        self._extra_selected_model_ids = [
            mid for mid in self._extra_selected_model_ids if mid in selectable
        ]
        self._batch_model_selection.set_selected_models(selected)
        self._sync_widget_selection_to_state(selected)
        self._refresh_pipeline_panel(selected)

    def _sync_widget_selection_to_state(self, selected: list[str] | None = None) -> None:
        """widget の programmatic な選択変更を state manager (SSoT) へ反映する (#884)。

        ``ModelCheckboxWidget.set_selected`` / ``ModelSelectionWidget.set_selected_models``
        は checkbox signal を抑制するため ``model_selection_changed`` 経由の同期
        (:meth:`_on_widget_model_selection_changed`) が走らない。picker / preset / × など
        の programmatic 変更後に本メソッドで checkbox の ground-truth を SSoT へ押し出す。

        Args:
            selected: SSoT へ反映する選択集合の明示指定。checkbox widget はフィルタで
                隠れた行を列挙できないため、プリセット適用など「意図した集合」が
                確定している経路では widget 読み戻しでなくこちらを渡す (#1186 Codex P2)。
                None なら従来どおり widget の ground-truth を読む。
        """
        if self._model_selection_state_manager is None or self._syncing_model_selection:
            return
        self._syncing_model_selection = True
        try:
            self._model_selection_state_manager.set_selected(
                self._batch_model_selection.get_selected_models() if selected is None else list(selected)
            )
        finally:
            self._syncing_model_selection = False

    def _on_widget_model_selection_changed(self, litellm_model_ids: list[str]) -> None:
        """ModelSelectionWidget の選択変化を state manager (SSoT) へ反映する (#884)。

        Args:
            litellm_model_ids: widget が emit した選択済み litellm_model_id リスト。
        """
        if self._syncing_model_selection or self._model_selection_state_manager is None:
            return
        self._syncing_model_selection = True
        try:
            self._model_selection_state_manager.set_selected(list(litellm_model_ids))
        finally:
            self._syncing_model_selection = False

    def _on_state_model_selection_changed(self, litellm_model_ids: list[str]) -> None:
        """state manager (SSoT) の変化を ModelSelectionWidget (view) へ反映する (#884)。

        Args:
            litellm_model_ids: manager が emit した選択済み litellm_model_id リスト。
        """
        if self._syncing_model_selection:
            return
        self._syncing_model_selection = True
        try:
            self._batch_model_selection.set_selected_models(list(litellm_model_ids))
            self._refresh_pipeline_panel(list(litellm_model_ids))
        finally:
            self._syncing_model_selection = False

    def selected_litellm_model_ids(self) -> list[str]:
        """選択中のモデル (litellm_model_id) を返す。

        SSoT は ``ModelSelectionStateManager`` (#884)。未注入時は従来どおり
        ``ModelSelectionWidget`` の checkbox state と offscreen 保持分を読む。
        """
        if self._model_selection_state_manager is not None:
            raw = self._model_selection_state_manager.get_selected()
            return [m for m in raw if isinstance(m, str)] if isinstance(raw, list) else []
        raw_widget = self._batch_model_selection.get_selected_models()
        widget_selected = (
            [m for m in raw_widget if isinstance(m, str)] if isinstance(raw_widget, list) else []
        )
        if not self._extra_selected_model_ids:
            return widget_selected
        seen = set(widget_selected)
        return widget_selected + [mid for mid in self._extra_selected_model_ids if mid not in seen]

    def get_staged_items(self) -> dict[int, tuple[str, str]]:
        """ステージング項目 (image_id → (name, stored_path)) を返す。"""
        return self._batch_tag_add_widget.get_staged_items()

    def run_options(self) -> RunOptions:
        """実行詳細設定 (RunOptions) を返す。"""
        return self._pipeline_run_options

    def set_run_options(self, options: RunOptions) -> None:
        """実行詳細設定 (RunOptions) をセットし、UI表示を同期する (#1558)。"""
        self._pipeline_run_options = options
        if hasattr(self, "_dry_run_indicator"):
            self._dry_run_indicator.setVisible(bool(options.dry_run))

    def staged_id_path_map(self) -> dict[int, str]:
        """ステージング画像の {image_id: 解決済みファイルパス} を返す (#896 PR4a)。

        :meth:`get_staged_items` の stored_path を実ファイルパスに解決し、存在する
        ものだけ返す。同期 / async dispatch の双方で使う。DatasetStateManager 未注入時は
        パス解決の前提が揃わないため空辞書を返す。

        Returns:
            {image_id: ファイルパス}。対象なし / 解決不能時は空辞書。
        """
        staged_items = self.get_staged_items()
        if not staged_items:
            return {}

        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not available for path resolution")
            return {}

        id_path_map: dict[int, str] = {}
        for image_id, (_, stored_path) in staged_items.items():
            if stored_path:
                resolved = resolve_stored_path(stored_path)
                if resolved and resolved.exists():
                    id_path_map[image_id] = str(resolved)
                else:
                    logger.debug(f"画像パスが存在しない: ID={image_id}, path={stored_path}")

        logger.debug(f"ステージング画像パスを取得: {len(id_path_map)}件")
        return id_path_map

    def staged_image_paths(self) -> list[str]:
        """ステージング画像のファイルパスリストを返す (#896 PR4a)。

        Returns:
            list[str]: 画像ファイルパスリスト。対象なし時は空リスト。
        """
        return list(self.staged_id_path_map().values())

    def show_model_selection_dialog(self, available_models: list[str]) -> str | None:
        """モデル選択ダイアログを表示する (Callback パターン、#896 PR4a)。

        Args:
            available_models: 利用可能なモデル名リスト。

        Returns:
            str | None: 選択されたモデル名。キャンセル時は None。
        """
        selected_model, ok = QInputDialog.getItem(
            self,
            "モデル選択",
            "アノテーションに使用するモデルを選択してください:",
            available_models,
            0,  # デフォルト選択
            False,  # 編集不可
        )
        return selected_model if ok else None

    # -- 実行詳細設定 (Issue #789) --------------------------------------------

    def _open_run_settings(self) -> None:
        """実行詳細設定モーダルを開き、確定値を保持する (Issue #789, #1558)。

        OK 時の :class:`RunOptions` を ``self._pipeline_run_options`` に格納する。
        """
        dialog = RunSettingsDialog(
            self._pipeline_staged_count, parent=self, current=self._pipeline_run_options
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_run_options(dialog.run_options())
            logger.info(f"実行詳細設定を更新: {self._pipeline_run_options}")
            # dispatch_mode 変更を INFERENCE LEDGER のレーン分割へ反映する (#884 Phase 4b)
            self._refresh_pipeline_panel()

    # -- パイプライン構成ビュー (Phase 6a/6b) ---------------------------------

    def _find_rating_model_ids(self) -> list[str]:
        """レーティング判定に対応する利用可能モデル ID 一覧を取得する (#1558)。"""
        all_models = self._load_all_models_cached()
        active_models = [m for m in all_models if getattr(m, "available", True)]
        all_infos = self._build_stage_model_infos([m.litellm_model_id for m in active_models])
        return [
            info.litellm_model_id
            for info in self._filter_available_stage_model_infos(all_infos)
            if PipelineStage.RATING in info.fill_stages()
        ]

    def _on_run_rating_preflight_requested(self) -> None:
        """事前レーティング判定を実行する (#1558)。

        ステージング画像のレーティング未判定分を解消するため、RATING ステージ対応モデルを
        選択して同期アノテーションを実行する。
        """
        if self._pipeline_staged_count == 0:
            show_information(self, "画像未選択", "ステージングに画像がありません。")
            return

        rating_ids = self._find_rating_model_ids()
        if not rating_ids:
            show_warning(
                self,
                "モデル未検出",
                "レーティング判定に対応したモデルが見つかりません。\n"
                "モデル設定からレーティング対応モデルを有効化してください。",
            )
            return

        checkbox_widgets = getattr(self._batch_model_selection, "model_checkbox_widgets", None)
        if isinstance(checkbox_widgets, dict):
            self._extra_selected_model_ids = [mid for mid in rating_ids if mid not in checkbox_widgets]
        else:
            self._extra_selected_model_ids = []
        self._batch_model_selection.set_selected_models(rating_ids)
        self._sync_widget_selection_to_state(rating_ids)

        self._active_preset_id = None
        self._last_preset_model_ids = set()
        if hasattr(self._pipeline_stage_table, "set_active_preset"):
            self._pipeline_stage_table.set_active_preset(None)

        self._last_composed_selected_ids = None
        self._refresh_pipeline_panel()
        self._on_execute_clicked("sync")

    def _on_pipeline_models_changed(self, selected_litellm_model_ids: list[str]) -> None:
        """モデル選択変化でパイプライン構成ビューを再計算する (Phase 6a, #1558)。"""
        self._refresh_pipeline_panel(list(selected_litellm_model_ids))
        self._update_annotation_target_ui(self._pipeline_staged_count)

    def _on_pipeline_preset_selected(self, preset_id: str) -> None:
        """プリセット chip 選択に応じてモデル割当を切り替える (Issue #847, #1537)。

        batchModelSelection (SSoT) の選択状態を全 OFF にしてから、preset_id に
        対応するモデルのみ ON にする。active preset 表示は Signal emit なしに更新する。

        Args:
            preset_id: 選択されたプリセットの ID (PipelinePreset.preset_id)。
        """
        all_models = self._load_all_models_cached()
        # ADR 0038: 廃止 (discontinued_at 設定済み = available False) モデルは UI の
        # モデル一覧に出ないため、プリセット適用でも候補から除外する (Codex P2)
        active_models = [m for m in all_models if m.available]
        all_infos = self._build_stage_model_infos([m.litellm_model_id for m in active_models])

        # プリセットに対応する litellm_model_id を絞り込んで一括セット
        if preset_id.startswith(_CUSTOM_PRESET_PREFIX):
            resolved = self._resolve_custom_preset_model_ids(preset_id, all_infos)
            if resolved is None:
                self._pipeline_stage_table.set_active_preset(self._active_preset_id)
                return
            preset_ids = resolved
        else:
            preset_ids = self._filter_model_ids_for_preset(preset_id, all_infos)

        # #1537: 既にモデルが選択されており、かつプリセット構成と異なる場合は上書き前に確認する
        current_ids = self.selected_litellm_model_ids()
        if current_ids and set(current_ids) != set(preset_ids):
            reply = QMessageBox.question(
                self,
                "プリセットの上書き確認",
                f"現在 {len(current_ids)} 件のモデルが選択されています。\n"
                f"プリセットを適用して現在の選択を置き換えますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._pipeline_stage_table.set_active_preset(self._active_preset_id)
                return

        checkbox_widgets = getattr(self._batch_model_selection, "model_checkbox_widgets", None)
        if isinstance(checkbox_widgets, dict):
            self._extra_selected_model_ids = [mid for mid in preset_ids if mid not in checkbox_widgets]
        else:
            self._extra_selected_model_ids = []
        self._batch_model_selection.set_selected_models(preset_ids)
        # プリセットの意図した集合を SSoT へ直接反映する。widget 読み戻しだと
        # アノテーションフィルタで隠れた行が黙って脱落する (#1186 Codex P2)
        self._sync_widget_selection_to_state(preset_ids)

        # アクティブプリセット表示を同期 (Signal emit なし)
        self._active_preset_id = preset_id
        self._last_preset_model_ids = set(preset_ids)
        self._pipeline_stage_table.set_active_preset(preset_id)

        self._last_composed_selected_ids = None
        self._refresh_pipeline_panel()
        logger.info(f"プリセット '{preset_id}' を適用: {len(preset_ids)} 件のモデルを選択")

    def _deduplicate_stage_model_infos(self, infos: list[StageModelInfo]) -> list[StageModelInfo]:
        """同一 canonical_key を持つ複数経路 (direct / openrouter) を preferred 1 件に畳み込む (#1537, #1538)。

        ``ModelSelectionWidget.selectable_litellm_model_ids`` / ``select_preferred_route`` と同じく
        config の ``model_selection.route_preference`` を尊重する。
        """
        available_providers = self._available_api_providers()
        preference = self._route_preference()
        grouped: dict[str, list[StageModelInfo]] = {}
        order: list[str] = []
        for info in infos:
            ckey = canonical_key(info.litellm_model_id) if info.is_api else info.litellm_model_id
            if ckey not in grouped:
                grouped[ckey] = []
                order.append(ckey)
            grouped[ckey].append(info)

        result: list[StageModelInfo] = []
        for ckey in order:
            group = grouped[ckey]
            if not group[0].is_api:
                result.append(group[0])
                continue
            direct = next((i for i in group if detect_route(i.litellm_model_id) == "direct"), None)
            openrouter = next((i for i in group if detect_route(i.litellm_model_id) == "openrouter"), None)
            chosen: StageModelInfo | None
            if preference == "direct":
                chosen = direct
            elif preference == "openrouter":
                chosen = openrouter
            elif (
                direct is not None
                and required_provider_for(direct.litellm_model_id, direct.provider) in available_providers
            ):
                chosen = direct
            elif (
                openrouter is not None
                and required_provider_for(openrouter.litellm_model_id, openrouter.provider)
                in available_providers
            ):
                chosen = openrouter
            else:
                chosen = direct or openrouter or group[0]
            if chosen is not None:
                result.append(chosen)
        return result

    def _filter_available_stage_model_infos(self, all_infos: list[StageModelInfo]) -> list[StageModelInfo]:
        """利用可能 (ローカルまたは API キー設定済み) かつ経路重複排除済みのモデルのみ返す (#1537)。"""
        available_providers = self._available_api_providers()
        deduped = self._deduplicate_stage_model_infos(all_infos)
        return [
            info
            for info in deduped
            if not info.is_api
            or required_provider_for(info.litellm_model_id, info.provider) in available_providers
        ]

    @staticmethod
    def _select_default_preset_model_ids(available_infos: list[StageModelInfo]) -> list[str]:
        """default プリセット用に各ステージの代表モデルを優先して最大 5 件選出する (#1537)。"""
        eligible = [info for info in available_infos if info.fill_stages()]
        if len(eligible) <= _DEFAULT_PRESET_MAX_MODELS:
            return [info.litellm_model_id for info in eligible]

        picked_ids: set[str] = set()
        for stage in (
            PipelineStage.TAGS,
            PipelineStage.CAPTION,
            PipelineStage.SCORE,
            PipelineStage.RATING,
        ):
            for info in eligible:
                if info.litellm_model_id not in picked_ids and stage in info.fill_stages():
                    picked_ids.add(info.litellm_model_id)
                    break
            if len(picked_ids) >= _DEFAULT_PRESET_MAX_MODELS:
                break

        for info in eligible:
            if len(picked_ids) >= _DEFAULT_PRESET_MAX_MODELS:
                break
            picked_ids.add(info.litellm_model_id)

        return [info.litellm_model_id for info in eligible if info.litellm_model_id in picked_ids]

    def _filter_model_ids_for_preset(self, preset_id: str, all_infos: list[StageModelInfo]) -> list[str]:
        """プリセット ID に対応するモデル ID リストを返す (#847, #1537)。

        API キー未設定の WebAPI モデルは選択対象から除外し、各プリセットは以下の
        capability フィルタを適用する:
        - default: 利用可能モデルからステージ代表モデルを優先して最大 5 件
        - tags_only: tags capability を持つが multimodal でないモデル
        - full_caption: multimodal または caption capability を持つモデル
        - score_rate: scores または ratings capability を持つモデル

        Args:
            preset_id: PipelinePreset.preset_id。
            all_infos: 全モデルの StageModelInfo リスト。

        Returns:
            プリセットに割り当てるモデルの litellm_model_id リスト。
        """
        available_infos = self._filter_available_stage_model_infos(all_infos)
        if preset_id == "default":
            return self._select_default_preset_model_ids(available_infos)
        if preset_id == "tags_only":
            return [
                info.litellm_model_id
                for info in available_infos
                if "tags" in info.capabilities and not info.is_multimodal
            ]
        if preset_id == "full_caption":
            return [
                info.litellm_model_id
                for info in available_infos
                if info.is_multimodal or "caption" in info.capabilities
            ]
        if preset_id == "score_rate":
            return [
                info.litellm_model_id
                for info in available_infos
                if "scores" in info.capabilities or "ratings" in info.capabilities
            ]
        # 未知のプリセット: デフォルト上限内のモデルを安全なフォールバックとして返す
        logger.warning(f"未知のプリセット ID: {preset_id} — デフォルト上限内のモデルを選択します")
        return self._select_default_preset_model_ids(available_infos)

    def _on_pipeline_save_preset_requested(self) -> None:
        """現在のモデル構成を名前付きプリセットとして保存する (Issue #1186)。

        QSettings へ {名前: litellm_model_id リスト} を JSON で永続化し、
        プリセット chip 行へ保存済みプリセットとして追加する (同名は上書き)。

        選択集合は checkbox widget でなく選択 SSoT (`selected_litellm_model_ids`)
        から読む。widget はアノテーションフィルタで隠れた行を列挙できず、
        「現状の保存」が不完全なプリセットになる (Codex P2)。
        """
        selected_ids = self.selected_litellm_model_ids()
        if not selected_ids:
            show_warning(self, "プリセット保存", "モデルが選択されていないため保存できません。")
            return

        name, ok = QInputDialog.getText(self, "プリセットを保存", "プリセット名:")
        name = name.strip()
        if not ok or not name:
            return

        presets = self._load_custom_presets()
        presets[name] = list(selected_ids)
        self._save_custom_presets(presets)
        self._refresh_custom_preset_chips(presets)
        self._pipeline_stage_table.set_active_preset(f"{_CUSTOM_PRESET_PREFIX}{name}")
        logger.info(f"プリセット '{name}' を保存: モデル {len(selected_ids)} 件")

    def _resolve_custom_preset_model_ids(
        self, preset_id: str, all_infos: list[StageModelInfo]
    ) -> list[str] | None:
        """保存済みプリセットの litellm_model_id を現在利用可能なモデルに絞って返す (#1186)。

        Args:
            preset_id: ``custom:`` 前置きの preset_id。
            all_infos: 全モデルの StageModelInfo リスト。

        Returns:
            適用するモデル ID リスト。プリセットが見つからない場合は None。
        """
        name = preset_id.removeprefix(_CUSTOM_PRESET_PREFIX)
        stored = self._load_custom_presets().get(name)
        if stored is None:
            logger.warning(f"保存済みプリセット '{name}' が見つかりません — 適用をスキップします")
            return None
        # DB に存在しても API key 未設定の WebAPI モデルは選択不能 (needs key) なので除外する。
        # membership だけで通すと set_selected_models が disabled 行を強制チェックし、
        # 実行不能なモデルが選択集合に混入する (Codex P2)。provider は picker の
        # needs-key 判定と同じ required_provider_for で正規化する (unknown/alias/大文字
        # の DB provider 値でも key 設定済みモデルを黙って落とさない、Codex P2)
        available_providers = self._available_api_providers()
        available = {
            info.litellm_model_id
            for info in all_infos
            if not info.is_api
            or required_provider_for(info.litellm_model_id, info.provider) in available_providers
        }
        resolved = [model_id for model_id in stored if model_id in available]
        if len(resolved) < len(stored):
            logger.info(
                f"プリセット '{name}': 保存時の {len(stored)} 件中 {len(resolved)} 件が現在利用可能"
            )
        return resolved

    def _preset_settings(self) -> QSettings:
        """カスタムプリセット永続化用の QSettings を返す (テストで差し替え可能な継ぎ目)。"""
        return QSettings()

    def _load_custom_presets(self) -> dict[str, list[str]]:
        """QSettings から保存済みプリセットを読み出す (#1186)。

        Returns:
            {プリセット名: litellm_model_id リスト}。未保存・破損時は空 dict。
        """
        raw = self._preset_settings().value(_CUSTOM_PRESETS_SETTINGS_KEY, "")
        if not raw:
            return {}
        try:
            data = json.loads(str(raw))
        except json.JSONDecodeError:
            logger.warning("保存済みプリセットの読み込みに失敗しました (JSON 不正) — 空として扱います")
            return {}
        if not isinstance(data, dict):
            return {}
        presets: dict[str, list[str]] = {}
        for name, model_ids in data.items():
            if isinstance(name, str) and isinstance(model_ids, list):
                presets[name] = [model_id for model_id in model_ids if isinstance(model_id, str)]
        return presets

    def _save_custom_presets(self, presets: dict[str, list[str]]) -> None:
        """保存済みプリセットを QSettings へ JSON で書き込む (#1186)。"""
        settings = self._preset_settings()
        settings.setValue(_CUSTOM_PRESETS_SETTINGS_KEY, json.dumps(presets, ensure_ascii=False))
        settings.sync()

    def _refresh_custom_preset_chips(self, presets: dict[str, list[str]]) -> None:
        """保存済みプリセットをステージテーブルの chip 行へ反映する (#1186)。"""
        chips = [
            PipelinePreset(f"{_CUSTOM_PRESET_PREFIX}{name}", name, len(model_ids))
            for name, model_ids in sorted(presets.items())
        ]
        self._pipeline_stage_table.set_custom_presets(chips)

    def _update_preset_counts(self) -> None:
        """組込プリセット chip のモデル件数バッジを実データに同期する (#1537, #1515)。"""
        if not hasattr(self._pipeline_stage_table, "update_preset_counts"):
            return
        all_models = self._load_all_models_cached()
        active_models = [m for m in all_models if getattr(m, "available", True)]
        all_infos = (
            self._build_stage_model_infos([m.litellm_model_id for m in active_models])
            if active_models
            else []
        )
        counts = {
            preset_id: len(self._filter_model_ids_for_preset(preset_id, all_infos))
            for preset_id in ("default", "tags_only", "full_caption", "score_rate")
        }
        self._pipeline_stage_table.update_preset_counts(counts)

    def _refresh_pipeline_panel(self, selected_ids: list[str] | None = None) -> None:
        """ステージテーブルと推論台帳を現在の選択・ステージング件数で再描画する。

        Args:
            selected_ids: 選択中の litellm_model_id。None なら SSoT (manager 注入時は
                ModelSelectionStateManager、未注入時は ModelSelectionWidget) から現在値を
                取得する (ステージング件数変化時の再計算用、#884 P2 / #1515)。
        """
        service = getattr(self._batch_model_selection, "model_selection_service", None)
        if service is not self._cached_stage_info_service:
            self._invalidate_model_caches()

        is_implicit_refresh = selected_ids is None
        if selected_ids is None:
            selected_ids = self.selected_litellm_model_ids()
        selected_key = tuple(selected_ids)

        if not (is_implicit_refresh and self._last_composed_selected_ids == selected_key):
            self._update_preset_counts()

            # #1537: 選択が空になった、またはプリセット適用時の構成から乖離した場合は chip 強調を解除
            if not selected_ids or (
                self._active_preset_id is not None and set(selected_ids) != self._last_preset_model_ids
            ):
                self._active_preset_id = None
                self._last_preset_model_ids = set()
                if hasattr(self._pipeline_stage_table, "set_active_preset"):
                    self._pipeline_stage_table.set_active_preset(None)

            infos = self._build_stage_model_infos(selected_ids)
            self._pipeline_composition_service.compose_from_models(infos)
            self._pipeline_stage_table.display(self._pipeline_composition_service.stage_rows())
            self._last_composed_selected_ids = selected_key

        # #884 Phase 4b: dispatch_mode=batch_api のとき batch 対応モデルを別レーンへ。
        # batch-capable 判定は lib が SSoT (ADR 0038 / ADR 0005) → 都度問い合わせて消費する。
        dispatch_mode = self._pipeline_run_options.dispatch_mode
        batch_capable_ids = (
            self._resolve_batch_capable_ids(selected_ids) if dispatch_mode == "batch_api" else None
        )
        self._inference_ledger_widget.display(
            self._pipeline_composition_service.ledger(
                self._pipeline_staged_count,
                dispatch_mode=dispatch_mode,
                batch_capable_litellm_ids=batch_capable_ids,
            )
        )

    def _resolve_batch_capable_ids(self, selected_ids: list[str]) -> set[str]:
        """選択のうち Batch API へ実際に流れる litellm_model_id 集合を返す (#1136 Codex P2)。

        LEDGER レーンプレビューを controller の実振り分け (dispatch 射影) と一致させる。
        moderation を含めば ``rating_preflight``、無ければ ``annotation`` を選び、射影と同じ
        eligibility 判定 (:func:`batch_eligible_litellm_ids`) を適用する。従来は discovery 全体を
        batch レーンに出していたため、moderation+通常モデル混在時に通常モデル (実際は sync 行き)
        が batch レーンに表示される不整合があった。discovery 失敗時は空集合へ degrade する。

        Args:
            selected_ids: 現在選択中の litellm_model_id。

        Returns:
            batch レーンへ表示すべき litellm_model_id 集合。
        """
        workflow_service = getattr(self._service_container, "provider_batch_workflow_service", None)
        if workflow_service is None or self._db_manager is None:
            return set()
        try:
            raw_models = workflow_service.list_batch_capable_models()
        except (ProviderBatchError, RuntimeError, OSError) as e:
            logger.warning(f"Batch API 対応モデルの取得に失敗 (LEDGER は sync 表示に degrade): {e}")
            return set()

        resolver = self._db_manager.model_repo.get_model_by_litellm_id
        # task_type 判定は controller の _resolve_dispatch_task_type と一致させる。
        task_type = "annotation"
        for litellm_id in selected_ids:
            model = resolver(litellm_id)
            if model is not None and is_omni_moderation_model(model):
                task_type = "rating_preflight"
                break
        return set(
            batch_eligible_litellm_ids(
                selected_litellm_model_ids=selected_ids,
                batch_capable_models=raw_models,
                model_resolver=resolver,
                task_type=task_type,
            )
        )

    def _refresh_preflight_summary(self, *, invalidate_cache: bool = False) -> None:
        """送信前プリフライト card をステージング集合の既存 rating で再描画する (Issue #837, #1515)。

        ステージング集合の最新 rating を DB から引き、送信可 / 保留 / 未判定 に
        分類して表示する。moderation は実行しない (実送信時に
        :class:`ModerationPreflightService` が判定する)。
        """
        if invalidate_cache or self._cached_ratings_db_manager is not self._db_manager:
            self._cached_ratings_by_id.clear()
            self._cached_ratings_db_manager = self._db_manager

        image_ids = list(self._pipeline_staged_image_ids)
        if not image_ids or self._db_manager is None:
            self._cached_ratings_by_id.clear()
            self._preflight_summary_widget.display({}, image_ids)
            return

        active_set = set(image_ids)
        for cached_id in list(self._cached_ratings_by_id.keys()):
            if cached_id not in active_set:
                del self._cached_ratings_by_id[cached_id]

        missing_ids = [iid for iid in image_ids if iid not in self._cached_ratings_by_id]
        if missing_ids:
            fetched = self._db_manager.image_repo.get_latest_normalized_ratings_by_image_ids(missing_ids)
            fetched_map = fetched if isinstance(fetched, dict) else {}
            for iid in missing_ids:
                self._cached_ratings_by_id[iid] = fetched_map.get(iid)

        ratings_by_id: dict[int, str | None] = {
            iid: val for iid in image_ids if (val := self._cached_ratings_by_id.get(iid)) is not None
        }
        self._preflight_summary_widget.display(ratings_by_id, image_ids)

    def _build_stage_model_infos(self, selected_ids: list[str]) -> list[StageModelInfo]:
        """選択 litellm_model_id を StageModelInfo へ変換する (#1515: キャッシュ利用)。

        capabilities は DB Model の model_types 由来。API / local 判定はモデル一覧と
        同じ helper で provider と key 要否の metadata を確認する。

        Args:
            selected_ids: ModelSelectionWidget で選択中の litellm_model_id リスト。

        Returns:
            変換済み StageModelInfo リスト。DB に見つからない ID はスキップする。
        """
        service = getattr(self._batch_model_selection, "model_selection_service", None)
        if self._cached_stage_info_by_id is None or self._cached_stage_info_service is not service:
            all_models = self._load_all_models_cached()
            cost_by_id = self._build_cost_map()
            info_map: dict[str, StageModelInfo] = {}
            for model in all_models:
                litellm_id = getattr(model, "litellm_model_id", None)
                if not isinstance(litellm_id, str):
                    continue
                provider = getattr(model, "provider", None)
                is_api = is_webapi_model_id(litellm_id, provider, getattr(model, "requires_api_key", None))
                input_cost, output_cost = cost_by_id.get(litellm_id, (None, None))
                info_map[litellm_id] = StageModelInfo(
                    litellm_model_id=litellm_id,
                    display_name=getattr(model, "name", litellm_id),
                    provider=provider,
                    is_api=is_api,
                    capabilities=frozenset(str(c) for c in getattr(model, "capabilities", ())),
                    input_cost_per_token=input_cost,
                    output_cost_per_token=output_cost,
                )
            self._cached_stage_info_by_id = info_map
            self._cached_stage_info_service = service

        infos: list[StageModelInfo] = []
        for litellm_id in selected_ids:
            info = self._cached_stage_info_by_id.get(litellm_id)
            if info is None:
                logger.debug(f"選択モデルが DB モデル一覧に見つかりません: {litellm_id}")
                continue
            infos.append(info)
        return infos

    def _build_cost_map(self) -> dict[str, tuple[float | None, float | None]]:
        """litellm_model_id → (input単価, output単価) のコストマップを構築する (#1515)。

        image-annotator-lib の ``list_annotator_info()`` から実行時に pricing を取得する
        (Issue #747: litellm pricing は DB 保存せず on-demand)。取得失敗時は空マップを
        返してコスト表示なしで続行する (best-effort、アノテーション機能はブロックしない)。

        Returns:
            litellm_model_id をキーとした (input_cost_per_token, output_cost_per_token)。
        """
        if self._cached_cost_map is not None:
            return dict(self._cached_cost_map)
        adapter = getattr(self._service_container, "annotator_library", None)
        if adapter is None:
            self._cached_cost_map = {}
            return {}
        cost_map: dict[str, tuple[float | None, float | None]] = {}
        try:
            for info in adapter.list_annotator_info():
                if info.litellm_model_id is None:
                    continue
                cost_map[info.litellm_model_id] = (
                    info.input_cost_per_token,
                    info.output_cost_per_token,
                )
        except (TypeError, AttributeError, RuntimeError):
            logger.opt(exception=True).warning(
                "コスト概算用の AnnotatorInfo 取得に失敗。コスト表示なしで続行"
            )
            return {}
        self._cached_cost_map = cost_map
        return dict(cost_map)

    def _available_api_providers(self) -> set[str]:
        """config の API キー設定状況から実行可能な WebAPI provider 集合を返す (Issue #755)。

        Returns:
            非空キーが保存されている provider 名集合。config 未初期化・取得失敗時は
            空集合 (= 全 WebAPI モデルが needs key 扱い)。
        """
        config_service = getattr(self._service_container, "config_service", None)
        if config_service is None:
            return set()
        try:
            api_keys = {
                "openai": config_service.get_setting("api", "openai_key", ""),
                "anthropic": config_service.get_setting("api", "claude_key", ""),
                "google": config_service.get_setting("api", "google_key", ""),
                "openrouter": config_service.get_setting("api", "openrouter_key", ""),
            }
        except (AttributeError, KeyError, TypeError):
            logger.opt(exception=True).warning("API キー設定の取得に失敗 (全 provider を needs key 扱い)")
            return set()
        return build_available_providers(api_keys)

    def _route_preference(self) -> RoutePreference:
        """config の route_preference 設定を取得する (Issue #249, #1537, #1538)。"""
        config_service = getattr(self._service_container, "config_service", None)
        if config_service is None:
            return "auto"
        try:
            raw = config_service.get_setting("model_selection", "route_preference", "auto")
            return parse_route_preference(raw)
        except (AttributeError, KeyError, TypeError):
            logger.opt(exception=True).warning("route_preference 設定の取得に失敗 (auto fallback)")
            return "auto"

    def _build_picker_candidates(self, stage: PipelineStage) -> list[StageModelInfo]:
        """指定ステージ向けに経路重複排除・選択済み除外済みのピッカー候補を構築する (#1538, #1515)。"""
        all_models = self._load_all_models_cached()
        active_models = [model for model in all_models if getattr(model, "available", True)]
        all_ids = [model.litellm_model_id for model in active_models]
        selected_ids = set(self.selected_litellm_model_ids())
        selected_canonical_keys = {canonical_key(mid) for mid in selected_ids}
        deduped_infos = self._deduplicate_stage_model_infos(self._build_stage_model_infos(all_ids))
        return [
            info
            for info in deduped_infos
            if stage in info.fill_stages()
            and info.litellm_model_id not in selected_ids
            and (not info.is_api or canonical_key(info.litellm_model_id) not in selected_canonical_keys)
        ]

    def _on_pipeline_add_model_requested(self, stage_value: str) -> None:
        """ステージ行の「+ 追加」でピッカーを開き、選択モデル集合へ追加する (Phase 6b, #1538)。

        SSoT は ModelSelectionStateManager / ModelSelectionWidget の選択集合。ピッカーで選んだ
        モデルはチェック ON と SSoT 更新で確実に集合へ追加し、ステージ仕分けは
        compose_from_models に任せる。

        Issue #755: キー未設定 WebAPI モデルも候補に含め ``○ needs key`` で可視化。
        Issue #1538: 経路重複排除後の候補を渡し、チェックボックス未描画モデルでも確実に選択集合へ追加する。
        Issue #1570: ステージング枚数 (staged_count) とモデル一覧更新シグナルを配線する。

        Args:
            stage_value: 追加先ステージの PipelineStage value。
        """
        stage = PipelineStage(stage_value)
        candidates = self._build_picker_candidates(stage)

        dialog = StageModelPickerDialog(
            stage,
            candidates,
            available_providers=self._available_api_providers(),
            staged_count=self._pipeline_staged_count,
            parent=self,
        )
        dialog.configure_key_requested.connect(
            lambda provider, dialog=dialog, stage=stage: self._on_picker_configure_key_requested(
                provider, dialog, stage=stage
            )
        )
        if hasattr(dialog, "refresh_models_requested"):
            dialog.refresh_models_requested.connect(
                lambda dialog=dialog, stage=stage: self._on_stage_picker_refresh_models(dialog, stage)
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        picked_ids = list(dialog.selected_model_ids())
        current_selected = self.selected_litellm_model_ids()
        for litellm_model_id in picked_ids:
            checkbox_widget = self._batch_model_selection.model_checkbox_widgets.get(litellm_model_id)
            if checkbox_widget is not None:
                checkbox_widget.set_selected(True)
            else:
                if litellm_model_id not in self._extra_selected_model_ids:
                    self._extra_selected_model_ids.append(litellm_model_id)
                logger.debug(f"チェックボックス未描画モデルを offscreen 選択として追加: {litellm_model_id}")

        merged_selected: list[str] = []
        for mid in [*current_selected, *self.selected_litellm_model_ids(), *picked_ids]:
            if mid not in merged_selected:
                merged_selected.append(mid)
        self._last_composed_selected_ids = None
        self._sync_widget_selection_to_state(merged_selected)
        self._refresh_pipeline_panel()

    def _on_pipeline_remove_model_requested(self, stage_value: str, litellm_model_id: str) -> None:
        """Primary チップの × でモデルを選択集合から外す (Phase 6b, #1134, #1538)。

        実行粒度はモデル単位のため、チェック OFF = 全ステージから外れる。

        #1134: SSoT (ModelSelectionStateManager) を直接更新する。従来は checkbox
        ウィジェット経由でしか外せず、該当 checkbox が未表示 (フィルタ絞り込み中・
        一覧未構築・ID キー不一致) だと警告ログのみの silent no-op になり、チップも
        LEDGER も残っていた。SSoT を直接更新すれば checkbox 未表示でも除外が成立し、
        view (checkbox) 追従と panel/LEDGER 再描画は ``selection_changed`` →
        :meth:`_on_state_model_selection_changed` の既存配線に任せられる。

        Args:
            stage_value: × が押されたステージの value (シグナル形状の都合で受けるが未使用)。
            litellm_model_id: 集合から外すモデルの litellm_model_id。
        """
        was_offscreen = litellm_model_id in self._extra_selected_model_ids
        if was_offscreen:
            self._extra_selected_model_ids = [
                mid for mid in self._extra_selected_model_ids if mid != litellm_model_id
            ]

        if self._model_selection_state_manager is not None:
            # SSoT-first (ADR 0076)。checkbox 未表示でも除外が成立する。
            self._model_selection_state_manager.set_model_selected(litellm_model_id, False)
            return

        # 後方互換: state manager 未注入時のみ従来どおり checkbox 経由で外す。
        checkbox_widget = self._batch_model_selection.model_checkbox_widgets.get(litellm_model_id)
        if checkbox_widget is None:
            if was_offscreen:
                self._last_composed_selected_ids = None
                self._refresh_pipeline_panel()
                return
            logger.warning(f"チェックボックス未表示のため除外をスキップ: {litellm_model_id}")
            return
        checkbox_widget.set_selected(False)
        self._last_composed_selected_ids = None
        self._sync_widget_selection_to_state()
        self._refresh_pipeline_panel()

    def _on_picker_configure_key_requested(
        self,
        provider: str,
        dialog: StageModelPickerDialog,
        stage: PipelineStage | None = None,
    ) -> None:
        """ピッカーの ``○ needs key`` チップから設定の該当プロバイダ欄へ誘導する (Issue #755, #1538)。

        :data:`configure_key_requested` は MainWindow glue へ設定ダイアログ表示を委譲する。
        Qt の同一スレッド Signal は同期実行されるため、emit から戻った時点で設定保存は
        完了している。これを前提に、開いたままのピッカーとモデル一覧を再評価して
        アプリ再起動なしで ``● API ready`` に解消する。設定保存により preferred route
        (direct ↔ openrouter) が変化した場合も候補を再構築して即座に反映する。

        Args:
            provider: API キーが必要な provider 名 (例 ``"anthropic"``)。
            dialog: シグナル発火元のピッカーダイアログ (開いたまま更新する)。
            stage: ピッカーの対象ステージ (省略時は ``dialog._stage`` から取得)。
        """
        self.configure_key_requested.emit(provider)
        self._reload_model_widget_after_settings()
        available_providers = self._available_api_providers()
        dialog.refresh_key_status(available_providers)
        target_stage = stage if stage is not None else getattr(dialog, "_stage", None)
        if isinstance(target_stage, PipelineStage):
            new_candidates = self._build_picker_candidates(target_stage)
            if hasattr(dialog, "set_candidates"):
                dialog.set_candidates(new_candidates)
            elif hasattr(dialog, "replace_candidates"):
                dialog.replace_candidates(new_candidates)
        self._last_composed_selected_ids = None
        self._refresh_pipeline_panel()

    def _on_stage_picker_refresh_models(
        self,
        dialog: StageModelPickerDialog,
        stage: PipelineStage,
    ) -> None:
        """ピッカーからのモデル一覧更新要求を処理し、候補リストを再読込する (#1570)。"""
        if hasattr(self._batch_model_selection, "refresh_model_registry"):
            self._batch_model_selection.refresh_model_registry(automatic=False)
        refresh_thread = getattr(self._batch_model_selection, "_refresh_thread", None)
        if (
            refresh_thread is not None
            and hasattr(refresh_thread, "finished")
            and hasattr(refresh_thread.finished, "connect")
        ):
            refresh_thread.finished.connect(
                lambda dialog=dialog, stage=stage: self._reload_stage_picker_candidates(dialog, stage)
            )
        self._reload_stage_picker_candidates(dialog, stage)

    def _reload_stage_picker_candidates(
        self,
        dialog: StageModelPickerDialog,
        stage: PipelineStage,
    ) -> None:
        """開いているピッカーダイアログのキー状況と候補リストを更新する (#1570)。"""
        self._invalidate_model_caches()
        available_providers = self._available_api_providers()
        if hasattr(dialog, "refresh_key_status"):
            dialog.refresh_key_status(available_providers)
        candidates = self._build_picker_candidates(stage)
        if hasattr(dialog, "set_candidates"):
            dialog.set_candidates(candidates)
        elif hasattr(dialog, "replace_candidates"):
            dialog.replace_candidates(candidates)
        self._last_composed_selected_ids = None
        self._refresh_pipeline_panel()

    def _reload_model_widget_after_settings(self) -> None:
        """設定保存後にモデル選択ウィジェットへ最新のキー状況を反映する (Issue #755)。

        ServiceContainer の config_service を破棄して保存済みファイルから再読込させ、
        モデル選択ウィジェットの表示 (● API ready / ○ needs key) を更新する。
        """
        try:
            del self._service_container.config_service
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"ServiceContainer の config_service 再読込に失敗 (継続可): {e}")
        try:
            self.refresh_model_selection()
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"モデル選択ウィジェットの更新に失敗 (継続可): {e}")

    # -- 内部 UI 更新 ----------------------------------------------------------

    def _update_annotation_target_ui(self, staging_count: int) -> None:
        """アノテーション対象 UI を更新する。

        ステージング画像数に応じてラベルテキストとボタンの有効/無効を設定し、
        run bar (Issue #849) のスコープラベルと実行ボタンも同期する。

        Args:
            staging_count: ステージング画像数。
        """
        if staging_count > 0:
            self.labelAnnotationTarget.setText(f"◎ ステージング: {staging_count} 枚")
        else:
            self.labelAnnotationTarget.setText("◎ ステージング: 0 枚（画像を追加してください）")

        # .ui 由来ボタン (非表示だが互換性のため更新を維持)
        self.btnAnnotationExecute.setEnabled(staging_count > 0)

        # run bar スコープラベル / 実行ボタンを更新 (Issue #849, #1099: 2ボタン)
        self._run_bar_scope_label.setText(self._run_bar_scope_text(staging_count))
        if self._execute_in_flight:
            # #1156: 実行中は staging 変化があっても両ボタンを無効・「実行中…」のまま維持する。
            self._btn_sync_execute.setEnabled(False)
            self._btn_batch_api_execute.setEnabled(False)
            self._btn_sync_execute.setText("実行中…")
            self._btn_batch_api_execute.setText("実行中…")
        else:
            has_staging = staging_count > 0
            self._btn_sync_execute.setEnabled(has_staging)
            self._btn_sync_execute.setText(self._run_bar_sync_execute_text(staging_count))
            self._btn_batch_api_execute.setEnabled(has_staging)
            self._btn_batch_api_execute.setText(self._run_bar_batch_execute_text(staging_count))

        # ドライラン表示更新 (#1558)
        if hasattr(self, "_dry_run_indicator"):
            self._dry_run_indicator.setVisible(bool(self._pipeline_run_options.dry_run))

        # ツールチップの更新 (#1558)
        selected_models_count = len(self.selected_litellm_model_ids())
        if staging_count == 0 and selected_models_count == 0:
            tooltip = "ステージング画像とモデルを選択してください"
        elif staging_count == 0:
            tooltip = "ステージング画像がありません。画像を追加してください"
        elif selected_models_count == 0:
            tooltip = "モデルが選択されていません。モデルを選択してください"
        else:
            tooltip = ""

        if hasattr(self, "_btn_sync_execute"):
            self._btn_sync_execute.setToolTip(tooltip)
        if hasattr(self, "_btn_batch_api_execute"):
            self._btn_batch_api_execute.setToolTip(tooltip)
        if hasattr(self, "btnAnnotationExecute"):
            self.btnAnnotationExecute.setToolTip(tooltip)
