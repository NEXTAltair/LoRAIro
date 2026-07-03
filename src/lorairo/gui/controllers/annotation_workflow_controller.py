"""アノテーションワークフロー制御Controller

MainWindow.start_annotation()から抽出したアノテーションワークフロー制御ロジック。
DatasetControllerパターンに従い、依存性注入とcallbackパターンを使用。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QMessageBox, QWidget

from lorairo.database.db_core import resolve_stored_path
from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.widgets.preflight_summary_widget import classify_preflight_counts
from lorairo.gui.workers.async_batch_dispatch_worker import AsyncBatchDispatchWorker
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.dispatch_projection_service import (
    DispatchProjection,
    DispatchProjectionError,
    project_async_batch_dispatch,
)
from lorairo.services.model_route_service import validate_api_keys_for_models
from lorairo.services.provider_batch_capability import (
    MixedBatchTaskTypeError,
    resolve_batch_task_type,
)
from lorairo.services.provider_batch_service import ProviderBatchError
from lorairo.services.selection_state_service import SelectionStateService
from lorairo.services.service_container import get_service_container

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.gui.state.staging_state import StagingStateManager
    from lorairo.gui.tab.annotate_tab import AnnotateTabWidget
    from lorairo.gui.widgets.run_settings_dialog import RunOptions
    from lorairo.services.service_container import ServiceContainer

# async batch dispatch worker thread の GC 防止用 (ProviderBatchJobWidget と同方式)。
# 受け手 (controller) は QObject なので worker → slot は queued 接続でメインスレッド実行。
_ACTIVE_DISPATCH_THREADS: set[QThread] = set()


def _resolve_dispatch_task_type(
    parent_widget: QWidget | None,
    selected_litellm_model_ids: list[str],
    db_manager: "ImageDatabaseManager",
) -> str | None:
    """選択モデル種別から async batch dispatch の task_type を決める (#1098)。

    全モデルが moderation (omni-moderation-*) なら ``"rating_preflight"``、
    通常モデルのみなら ``"annotation"``。moderation + 通常モデルの混在は
    「非 batch 混在拒否」原則 (ADR 0076 §2) で拒否し、warning を表示して None を返す。

    Args:
        parent_widget: warning ダイアログの親ウィジェット。
        selected_litellm_model_ids: Annotate の選択モデル集合 (SSoT)。
        db_manager: litellm_model_id → DB Model 解決に使う。

    Returns:
        "annotation" / "rating_preflight"。混在で拒否した場合は None。
    """
    selected_models = [
        model
        for litellm_id in selected_litellm_model_ids
        if (model := db_manager.model_repo.get_model_by_litellm_id(litellm_id)) is not None
    ]
    try:
        return resolve_batch_task_type(selected_models)
    except MixedBatchTaskTypeError as e:
        QMessageBox.warning(parent_widget, "Batch API 送信", str(e))
        return None


def _moderation_gate_blocks(
    parent_widget: QWidget | None,
    task_type: str,
    image_ids: list[int],
    db_manager: "ImageDatabaseManager",
) -> bool:
    """fail-closed moderation gate。送信不可なら warning を出して True を返す (ADR 0070)。

    送信可 (sendable) でない rating (保留 / 未判定) を含む画像があれば dispatch を
    拒否する。#1098: rating_preflight (moderation モデル自体で rating を確定する送信)
    は gate の対象外。まさに rating を付ける操作なので「先に rating 確定を」は本末転倒。

    Args:
        parent_widget: warning ダイアログの親ウィジェット。
        task_type: :func:`_resolve_dispatch_task_type` が決めた task_type。
        image_ids: 送信対象の image_id。
        db_manager: rating 取得に使う。

    Returns:
        gate がブロックしたら True (warning 表示済み)、送信可なら False。
    """
    if task_type == "rating_preflight":
        return False
    ratings_by_id = db_manager.image_repo.get_latest_normalized_ratings_by_image_ids(image_ids)
    preflight = classify_preflight_counts(ratings_by_id, image_ids)
    if preflight.held > 0 or preflight.unrated > 0:
        QMessageBox.warning(
            parent_widget,
            "Batch API 送信",
            "送信前 moderation が未完了の画像があります "
            f"(保留 {preflight.held} 件 / 未判定 {preflight.unrated} 件)。\n"
            "Batch API の自動 preflight は未対応のため、先に rating を確定してください。",
        )
        return True
    return False


def _build_batch_projection(
    parent_widget: QWidget | None,
    *,
    workflow_service: Any,
    db_manager: "ImageDatabaseManager",
    selected_litellm_model_ids: list[str],
    image_ids: list[int],
    prompt_profile: str,
    description: str | None,
    processed_paths: dict[int, str],
    task_type: str,
) -> "DispatchProjection | None":
    """batch-capable discovery → dispatch 射影を行う。失敗時は warning を出し None を返す。

    discovery / 射影の recoverable な失敗 (ProviderBatchError / DispatchProjectionError 等)
    は warning を表示して None を返し、呼び出し側の dispatch を中止させる。

    Returns:
        成功時は :class:`DispatchProjection`、失敗時は None (warning 表示済み)。
    """
    try:
        batch_capable_models = workflow_service.list_batch_capable_models()
    except (ProviderBatchError, RuntimeError, OSError) as e:
        logger.error(f"Batch API モデル discovery 失敗: {e}", exc_info=True)
        QMessageBox.warning(
            parent_widget, "Batch API 送信", f"Batch API 対応モデルの取得に失敗しました:\n{e}"
        )
        return None

    try:
        return project_async_batch_dispatch(
            selected_litellm_model_ids=selected_litellm_model_ids,
            batch_capable_models=batch_capable_models,
            model_resolver=db_manager.model_repo.get_model_by_litellm_id,
            image_ids=image_ids,
            prompt_profile=prompt_profile,
            description=description,
            image_paths=processed_paths,
            task_type=task_type,
        )
    except DispatchProjectionError as e:
        QMessageBox.warning(parent_widget, "Batch API 送信", str(e))
        return None


class AnnotationWorkflowController(QObject):
    """アノテーション処理ワークフロー制御Controller

    MainWindow.start_annotation()から抽出。
    画像選択→モデル選択→アノテーション実行のワークフロー全体を制御。

    DatasetControllerパターン準拠:
    - 依存性注入（constructor injection）
    - Callbackパターン（GUI操作はMainWindowに委譲）
    - サービス層へのビジネスロジック委譲

    QObject を継承する理由 (#896 PR4b): async batch dispatch の worker は専用
    QThread 上で動くため、``worker.succeeded`` 等を本 controller の slot へ
    connect する際、受け手が QObject (メインスレッド affinity) であることで
    queued 接続となりメインスレッドで slot が実行される。非 QObject だと
    direct 接続になり worker スレッドから GUI/state を触りクラッシュする。
    """

    def __init__(
        self,
        worker_service: WorkerService,
        selection_state_service: SelectionStateService,
        config_service: ConfigurationService,
        parent: QWidget | None = None,
    ):
        """初期化

        Args:
            worker_service: Worker管理サービス（必須）
            selection_state_service: 画像選択状態管理サービス
            config_service: 設定管理サービス
            parent: 親ウィジェット（QMessageBox用、Noneも可）
        """
        # QObject の Qt 親は設定しない (テストは Mock parent を渡すため)。生存期間は
        # MainWindow の Python 参照で管理し、thread affinity はメインスレッドに固定する。
        super().__init__()
        self.worker_service = worker_service
        self.selection_state_service = selection_state_service
        self.config_service = config_service
        self._parent_widget = parent

        # -- async batch dispatch (#896 PR4b: MainWindow から移送, ADR 0076 §2) --
        # 再入/busy ガード (#884 Phase 2c, ADR 0044)
        self._async_dispatch_in_progress = False
        self._async_dispatch_thread: QThread | None = None
        self._async_dispatch_worker: AsyncBatchDispatchWorker | None = None
        # 送信済み画像 (成功/部分失敗時に staging から外し二重送信を防ぐ)
        self._async_dispatch_image_ids: list[int] = []
        # configure_async_dispatch() で注入される協調オブジェクト (未注入時は no-op)
        self._service_container: ServiceContainer | None = None
        self._db_manager: ImageDatabaseManager | None = None
        self._staging_state_manager: StagingStateManager | None = None
        self._annotate_tab: AnnotateTabWidget | None = None
        self._jobs_refresh: Callable[[], None] = lambda: None
        self._status_callback: Callable[[str, int], None] = lambda message, timeout: None
        # アノテーションタブが現在アクティブか (= ステージング画像を override に使うか)
        self._is_annotate_tab_active: Callable[[], bool] = lambda: False

    def configure_async_dispatch(
        self,
        *,
        service_container: "ServiceContainer",
        db_manager: "ImageDatabaseManager | None",
        staging_state_manager: "StagingStateManager | None",
        annotate_tab: "AnnotateTabWidget | None",
        jobs_refresh: Callable[[], None],
        status_callback: Callable[[str, int], None],
        is_annotate_tab_active: Callable[[], bool],
    ) -> None:
        """アノテーション実行フローに必要な協調オブジェクトを注入する (#896 PR4b/PR4c)。

        MainWindow が全タブ構築後に呼ぶ。controller 生成時点では annotate_tab /
        jobs_tab が未生成のため、constructor injection でなく setter injection で
        受ける。

        Args:
            service_container: provider batch workflow / annotator library の取得元。
            db_manager: rating 取得・モデル解決・processed パス解決に使う。
            staging_state_manager: 送信済み画像を staging から外す SSoT。
            annotate_tab: run options / staging 集合 / 選択モデルの読み出し元。
            jobs_refresh: 送信後に Jobs 台帳を再読込する callback。
            status_callback: statusBar への ``(message, timeout_ms)`` 表示 callback。
            is_annotate_tab_active: アノテーションタブが現在アクティブかを返す callback
                (#896 PR4c)。True のとき同期アノテはステージング画像を override に使う。
        """
        self._service_container = service_container
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager
        self._annotate_tab = annotate_tab
        self._jobs_refresh = jobs_refresh
        self._status_callback = status_callback
        self._is_annotate_tab_active = is_annotate_tab_active

    def start_annotation(self, dispatch_mode: str | None = None) -> None:
        """アノテーション実行エントリ。dispatch mode で分岐する (#896 PR4c, #1099)。

        AnnotateTabWidget の run bar 実行ボタン (``annotation_execute_requested``)
        から呼ばれる。``dispatch_mode`` (ADR 0076 §1) が ``batch_api`` なら async
        Provider Batch dispatch へ、それ以外は同期バッチアノテーション
        (:meth:`start_annotation_workflow`) へ分岐する。

        Args:
            dispatch_mode: 実行ボタンが指定した送信方式 ("sync" / "batch_api"、#1099)。
                None の場合は ``run_options().dispatch_mode`` を使う (後方互換)。
        """
        annotate_tab = self._annotate_tab

        # 送信方式 (dispatch mode) 判定 (#884 Phase 2c, ADR 0076 §1, #1099)。
        # 実行ボタン (#1099) が明示指定する dispatch_mode を優先し、無ければ RunOptions を読む。
        effective_mode = dispatch_mode
        if effective_mode is None and annotate_tab is not None:
            effective_mode = annotate_tab.run_options().dispatch_mode
        # batch_api (async) は dispatch 射影 → worker thread へ分岐する。
        if effective_mode == "batch_api":
            self.dispatch_async_batch()
            return

        # アノテーションタブの選択モデルを取得 (Issue #245: litellm_model_id ベース、#868)
        selected_litellm_model_ids: list[str] = []
        if annotate_tab is not None:
            selected_litellm_model_ids = annotate_tab.selected_litellm_model_ids()
            logger.debug(
                f"アノテタブから選択されたモデル (litellm_model_ids): {selected_litellm_model_ids}"
            )

        # アノテーションタブがアクティブな場合はステージング画像を override に使う
        override_image_paths: list[str] | None = None
        if self._is_annotate_tab_active():
            override_image_paths = annotate_tab.staged_image_paths() if annotate_tab is not None else []
            if not override_image_paths:
                QMessageBox.information(
                    self._parent_widget,
                    "ステージング画像なし",
                    "ステージングリストに画像がありません。\n"
                    "画像を選択してからアノテーションを実行してください。",
                )
                return

        # 実行詳細設定 (RunOptions) を同期アノテフローへ伝搬する (Issue #803)。
        run_options = annotate_tab.run_options() if annotate_tab is not None else None

        # チェックボックスから選択されたモデルを優先し、無ければダイアログ callback へ
        self.start_annotation_workflow(
            selected_litellm_model_ids=selected_litellm_model_ids if selected_litellm_model_ids else None,
            model_selection_callback=annotate_tab.show_model_selection_dialog
            if not selected_litellm_model_ids and annotate_tab is not None
            else None,
            image_paths=override_image_paths,
            run_options=run_options,
        )

    def start_annotation_workflow(
        self,
        selected_litellm_model_ids: list[str] | None = None,
        model_selection_callback: Callable[[list[str]], str | None] | None = None,
        image_paths: list[str] | None = None,
        run_options: "RunOptions | None" = None,
    ) -> None:
        """アノテーションワークフロー実行

        ワークフロー:
        1. サービス検証
        2. 選択画像取得（image_paths指定時はそれを使用、なければSelectionStateService経由）
        3. モデル選択（selected_litellm_model_ids優先、なければcallback呼び出し）
        4. バッチアノテーション開始（WorkerService経由）

        Issue #245 / ADR 0023 Phase 1.11: モデル指定は `Model.litellm_model_id`
        (registry key SSoT) で受け取る。

        Args:
            selected_litellm_model_ids: 事前選択されたモデルの `litellm_model_id`
                リスト（チェックボックスから）
            model_selection_callback: モデル選択ダイアログ表示callback（フォールバック用）
                利用可能モデルリストを受け取り、選択された `litellm_model_id` を返す。
                キャンセル時はNone。
            image_paths: 明示的に指定する画像パスリスト（バッチタグタブから使用）
                指定時はSelectionStateServiceをバイパスしてこのリストを使用。
            run_options: 実行詳細設定 (Issue #803)。``dry_run`` / ``rating_gate`` を
                worker_service 経由で AnnotationWorker に伝搬する。``None`` の場合は従来挙動。
        """
        try:
            # Step 1: サービス検証（image_paths指定時はSelectionStateService不要）
            if not image_paths and not self._validate_services():
                return

            # Step 2: 選択画像取得（image_paths指定時はそれを使用）
            if image_paths:
                logger.debug(f"明示指定された画像パスを使用: {len(image_paths)}件")
                paths_to_use = image_paths
            else:
                paths_to_use = self._get_selected_image_paths()
                if not paths_to_use:
                    return
            image_paths = paths_to_use

            # Step 3: モデル選択（selected_litellm_model_ids優先）
            models_to_use = self._resolve_models_to_use(
                selected_litellm_model_ids, model_selection_callback
            )
            if not models_to_use:
                return

            if self._warn_deprecated_models(models_to_use) is False:
                return

            # Issue #241: 実行直前に API key 不足を検出する。
            # 旧実装は WorkerService 内で library 呼び出し時に MissingApiKeyError が
            # 出るまで失敗を検出できなかった。直接プロバイダー key のみ持つ環境で
            # `openrouter/...` モデルを誤選択した場合などをここで止める。
            if self._validate_api_keys_for_models(models_to_use) is False:
                return

            # Step 4: バッチアノテーション開始
            self._start_batch_annotation(image_paths, models_to_use, run_options=run_options)

        except Exception as e:
            error_msg = f"アノテーション処理の開始に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            if self._parent_widget:
                QMessageBox.critical(
                    self._parent_widget,
                    "アノテーション開始エラー",
                    error_msg,
                )

    def _resolve_models_to_use(
        self,
        selected_litellm_model_ids: list[str] | None,
        model_selection_callback: Callable[[list[str]], str | None] | None,
    ) -> list[str]:
        """アノテーションに使用するモデルを決定する (戻り値は `litellm_model_id` リスト)。"""
        if selected_litellm_model_ids:
            logger.info(
                f"チェックボックスから選択されたモデル (litellm_model_ids): {selected_litellm_model_ids}"
            )
            return selected_litellm_model_ids

        if model_selection_callback:
            available_models = self._get_available_models()
            selected_model = model_selection_callback(available_models)
            if not selected_model:
                logger.info("モデル選択がキャンセルされました")
                return []
            logger.info(f"ダイアログから選択されたモデル: {selected_model}")
            return [selected_model]

        logger.warning("モデルが選択されていません")
        if self._parent_widget:
            QMessageBox.warning(
                self._parent_widget,
                "モデル未選択",
                "アノテーションに使用するモデルを選択してください。",
            )
        return []

    def _validate_services(self) -> bool:
        """必須サービスの検証

        Returns:
            bool: 全サービスが有効な場合True
        """
        if not self.worker_service:
            logger.warning("WorkerServiceが初期化されていません")
            if self._parent_widget:
                QMessageBox.warning(
                    self._parent_widget,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、アノテーション処理を実行できません。",
                )
            return False

        if not self.selection_state_service:
            logger.warning("SelectionStateServiceが初期化されていません")
            if self._parent_widget:
                QMessageBox.warning(
                    self._parent_widget,
                    "サービス未初期化",
                    "SelectionStateServiceが初期化されていないため、画像を選択できません。",
                )
            return False

        return True

    def _get_selected_image_paths(self) -> list[str]:
        """選択画像パスリスト取得

        Returns:
            list[str]: 画像パスリスト。エラー時は空リスト。
        """
        try:
            image_paths = self.selection_state_service.get_selected_image_paths()
            logger.debug(f"選択画像を取得: {len(image_paths)}件")

            if not image_paths:
                logger.warning("画像パスリストが空です")
                if self._parent_widget:
                    QMessageBox.information(
                        self._parent_widget,
                        "画像データ取得エラー",
                        "選択された画像のパスを取得できませんでした。\n"
                        "データベースの状態を確認してください。",
                    )
                return []

            return image_paths

        except ValueError as e:
            # SelectionStateService.get_selected_image_paths()からのエラー
            logger.info(f"画像選択エラー: {e}")
            if self._parent_widget:
                QMessageBox.information(
                    self._parent_widget,
                    "画像未選択",
                    str(e),
                )
            return []

        except Exception as e:
            logger.error(f"画像パス取得中にエラー: {e}", exc_info=True)
            if self._parent_widget:
                QMessageBox.warning(
                    self._parent_widget,
                    "画像データ取得エラー",
                    f"画像パスの取得中にエラーが発生しました: {e}",
                )
            return []

    def _get_available_models(self) -> list[str]:
        """利用可能なモデルリスト取得

        ConfigurationServiceから動的にモデルリストを取得します。

        Returns:
            list[str]: 利用可能なモデル名リスト
        """
        if not self.config_service:
            logger.warning("ConfigurationServiceが未設定")
            return []

        return self.config_service.get_available_annotation_models()

    def _warn_deprecated_models(self, litellm_model_ids: list[str]) -> bool:
        """廃止済みモデルが選択されている場合に警告する。

        Issue #245: 入力は `litellm_model_id` (registry key)。
        `is_model_deprecated()` は registry key を受け取る前提のためそのまま渡せる。

        Returns:
            bool: 処理継続する場合True。
        """
        try:
            annotator = get_service_container().annotator_library
            deprecated_models = [
                key for key in litellm_model_ids if annotator.is_model_deprecated(key) is True
            ]
        except Exception as e:
            logger.warning(f"廃止モデル判定をスキップ: {e}")
            return True

        if not deprecated_models:
            return True

        message = (
            "選択されたモデルは廃止済みです。\n"
            f"{', '.join(deprecated_models)}\n\n"
            "再現性のため実行は可能ですが、新しいモデルへの切り替えを推奨します。"
        )
        logger.warning(f"廃止済みモデルが選択されています: {deprecated_models}")

        if not self._parent_widget:
            return True

        reply = QMessageBox.warning(
            self._parent_widget,
            "廃止済みモデル",
            message,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        return reply == QMessageBox.StandardButton.Ok

    def _validate_api_keys_for_models(self, litellm_model_ids: list[str]) -> bool:
        """Issue #241: 実行直前に API key 不足を検出し、不足時は QMessageBox.warning を表示。

        ``selection_includes_webapi_model`` のような registry 経由判定とは異なり、
        provider 単位の不足を ``(litellm_model_id, missing_provider)`` ペアで列挙する。
        DB から ``Model.provider`` を hint として取得して判定精度を上げる。

        Args:
            litellm_model_ids: 実行直前に検証するモデルの ``litellm_model_id`` リスト。

        Returns:
            bool: 不足なしの場合 True、不足ありで abort する場合 False。
        """
        try:
            api_keys = {
                "openai": self.config_service.get_setting("api", "openai_key", ""),
                "anthropic": self.config_service.get_setting("api", "claude_key", ""),
                "google": self.config_service.get_setting("api", "google_key", ""),
                "openrouter": self.config_service.get_setting("api", "openrouter_key", ""),
            }

            repository = get_service_container().db_manager.model_repo
            provider_hints: dict[str, str] = {}
            for litellm_id in litellm_model_ids:
                model = repository.get_model_by_litellm_id(litellm_id)
                if model is not None and model.provider:
                    provider_hints[litellm_id] = model.provider

            missing = validate_api_keys_for_models(litellm_model_ids, api_keys, provider_hints)
        except Exception as e:
            logger.warning(f"API key validation 中にエラー発生、検証 skip して続行: {e}")
            return True

        if not missing:
            return True

        lines = "\n".join(f"  - {provider}: {litellm_id}" for litellm_id, provider in missing)
        message = (
            "選択されたモデルに必要な API キーが設定されていません。\n\n"
            f"{lines}\n\n"
            "config/lorairo.toml の [api] セクションに該当プロバイダーのキーを設定するか、"
            "別の route のモデル (例: openrouter/... の代わりに直接プロバイダーのモデル) を選択してください。"
        )
        logger.warning(f"API key 不足 (実行中止): {missing}")

        if self._parent_widget is not None:
            QMessageBox.warning(
                self._parent_widget,
                "API キー未設定",
                message,
            )
        return False

    def _start_batch_annotation(
        self,
        image_paths: list[str],
        litellm_model_ids: list[str],
        run_options: "RunOptions | None" = None,
    ) -> None:
        """バッチアノテーション開始

        Args:
            image_paths: 画像パスリスト
            litellm_model_ids: モデルの `litellm_model_id` リスト
            run_options: 実行詳細設定 (Issue #803)。worker_service へ伝搬する。
        """
        try:
            logger.info(
                f"バッチアノテーション処理開始: {len(image_paths)}画像, {len(litellm_model_ids)}モデル"
            )

            # WorkerService.start_enhanced_batch_annotation()を呼び出し
            # Signal経由で進捗・完了・エラーがハンドラに通知される
            self.worker_service.start_enhanced_batch_annotation(
                image_paths=image_paths,
                litellm_model_ids=litellm_model_ids,
                run_options=run_options,
            )

            # 非ブロッキング通知
            status_msg = f"アノテーション処理を開始: {len(image_paths)}画像, モデル: {litellm_model_ids[0]}"
            logger.info(status_msg)

        except Exception as e:
            error_msg = f"バッチアノテーション開始に失敗: {e}"
            logger.error(error_msg, exc_info=True)
            if self._parent_widget:
                QMessageBox.critical(
                    self._parent_widget,
                    "アノテーション実行エラー",
                    error_msg,
                )
            raise

    # == async Provider Batch dispatch (#896 PR4b, ADR 0076 §2) ================

    def dispatch_async_batch(self) -> None:
        """選択モデル集合を async Provider Batch dispatch へ射影して送信する。

        ADR 0076 §2: 選択モデル集合 → dispatch 射影 (batch-capable ∩ discovery) →
        worker thread で ``submit_images`` をモデルごとにループ呼び出しする。
        非 batch-capable 混在は射影が拒否する ((a))。送信前 moderation が未完了の
        画像 (保留 / 未判定) がある場合は fail-closed で拒否する (ADR 0070、自動2段は
        deferral)。

        #1098: 選択モデルが全て omni-moderation-* (rating確定用途) なら
        ``task_type="rating_preflight"`` で射影し (OpenAI 公式 Batch API の
        ``/v1/moderations`` へ送信)、fail-closed moderation gate は適用しない
        (rating を付ける操作自体なので「先に rating 確定を」は本末転倒)。
        moderation モデルと通常モデルの混在は「非 batch 混在拒否」原則で弾く。
        """
        if self._annotate_tab is None:
            return
        if self._async_dispatch_in_progress:
            return

        container = self._service_container
        workflow_service = getattr(container, "provider_batch_workflow_service", None)
        model_source = getattr(container, "annotator_library", None)
        db_manager = self._db_manager
        if workflow_service is None or model_source is None or db_manager is None:
            QMessageBox.warning(
                self._parent_widget, "Batch API 送信", "Batch API サービスを利用できません。"
            )
            return

        run_options = self._annotate_tab.run_options()
        image_ids = list(self._annotate_tab.get_staged_items().keys())
        if not image_ids:
            QMessageBox.information(
                self._parent_widget,
                "ステージング画像なし",
                "ステージングリストに画像がありません。\n"
                "画像を選択してからアノテーションを実行してください。",
            )
            return

        # dry-run: 実送信せず件数プレビューのみ (RunSettings の dry-run 契約)
        if run_options.dry_run:
            QMessageBox.information(
                self._parent_widget,
                "Batch API 送信 (dry-run)",
                f"dry-run: {len(image_ids)} 枚を Batch API へ送信予定です。\n実際の送信・推論は行いません。",
            )
            return

        # #1098: 選択モデル種別から task_type を決定する。混在は helper 内で弾く。
        selected_litellm_model_ids = self._annotate_tab.selected_litellm_model_ids()
        task_type = _resolve_dispatch_task_type(self._parent_widget, selected_litellm_model_ids, db_manager)
        if task_type is None:
            return  # moderation + 通常モデル混在で拒否 (warning は helper 内で表示済み)

        # fail-closed moderation gate (ADR 0070)。rating_preflight は対象外 (#1098)。
        if _moderation_gate_blocks(self._parent_widget, task_type, image_ids, db_manager):
            return  # warning は helper 内で表示済み

        # ADR 0064: original でなく processed/resized パスを送信する。staging の
        # stored_path は original を指し得るため、低解像度 processed 版を解決する。
        processed_paths = self._resolve_processed_paths_for_batch(image_ids)
        if processed_paths is None:
            return  # 解決失敗 (warning は helper 内で表示済み)

        projection = _build_batch_projection(
            self._parent_widget,
            workflow_service=workflow_service,
            db_manager=db_manager,
            selected_litellm_model_ids=selected_litellm_model_ids,
            image_ids=image_ids,
            prompt_profile=run_options.prompt_profile,
            description=run_options.description,
            processed_paths=processed_paths,
            task_type=task_type,
        )
        if projection is None:
            return  # discovery / 射影の失敗 (warning は helper 内で表示済み)

        logger.info(
            f"Batch API dispatch 開始: {projection.job_count} ジョブ / {len(image_ids)} 枚 "
            f"(dispatch_mode={run_options.dispatch_mode}, task_type={task_type})"
        )
        self._async_dispatch_in_progress = True
        self._async_dispatch_image_ids = image_ids
        self._start_async_dispatch_worker(workflow_service, projection)

    def _resolve_processed_paths_for_batch(self, image_ids: list[int]) -> dict[int, str] | None:
        """各 image_id の低解像度 processed パスを解決する (ADR 0064)。

        original 送信を避けるため processed/resized 版のみを使う。processed 版が無い
        画像が 1 枚でもあれば warning を出して None を返す (fail-closed)。

        Args:
            image_ids: 送信対象の image_id。

        Returns:
            {image_id: 解決済み processed パス}。解決できない画像があれば None。
        """
        if self._db_manager is None:
            return None
        processed_paths: dict[int, str] = {}
        missing: list[int] = []
        for image_id in image_ids:
            stored = self._db_manager.get_low_res_image_path(image_id)
            resolved = resolve_stored_path(stored) if stored else None
            if resolved is not None and resolved.exists():
                processed_paths[image_id] = str(resolved)
            else:
                missing.append(image_id)
        if missing:
            QMessageBox.warning(
                self._parent_widget,
                "Batch API 送信",
                f"processed 版が無い画像が {len(missing)} 件あります。\n"
                "Batch API は processed/resized 画像のみ送信できます (ADR 0064)。\n"
                "先に画像処理を実行してください。",
            )
            return None
        return processed_paths

    def _start_async_dispatch_worker(self, workflow_service: Any, projection: DispatchProjection) -> None:
        """射影結果を専用 QThread で submit する (ADR 0044)。

        worker → slot の connect は受け手 (本 controller = QObject、メインスレッド
        affinity) と worker (専用 QThread) が別スレッドのため queued 接続となり、
        slot はメインスレッドで実行される。``_ACTIVE_DISPATCH_THREADS`` で thread を
        GC から守り、終了時に discard する (忘れると worker 即 GC でクラッシュ)。
        """
        thread = QThread()
        worker = AsyncBatchDispatchWorker(workflow_service, projection.entries)
        worker.moveToThread(thread)
        _ACTIVE_DISPATCH_THREADS.add(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_async_dispatch_succeeded)
        worker.failed.connect(self._on_async_dispatch_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_async_dispatch_thread_finished)
        thread.finished.connect(lambda: _ACTIVE_DISPATCH_THREADS.discard(thread))
        thread.finished.connect(thread.deleteLater)

        self._async_dispatch_thread = thread
        self._async_dispatch_worker = worker
        thread.start()

    def _finalize_submitted_jobs(self, job_ids: list[int]) -> None:
        """送信済みジョブを台帳へ反映し、対象画像を staging から外す。

        成功・部分失敗の双方で呼ぶ。1 つでもジョブが作成されていれば対象画像は
        dispatch 済みなので staging から除去し、再クリックによる二重送信を防ぐ
        (ProviderBatchJobWidget と同方針)。

        Args:
            job_ids: 作成済みの provider batch job_id。
        """
        if not job_ids:
            return
        if self._staging_state_manager is not None and self._async_dispatch_image_ids:
            self._staging_state_manager.remove_image_ids(self._async_dispatch_image_ids)
        self._jobs_refresh()

    def _on_async_dispatch_succeeded(self, job_ids: list[int]) -> None:
        """全ジョブ送信成功時に Jobs 台帳を更新しサマリーを表示する。"""
        logger.info(f"Batch API dispatch 完了: {len(job_ids)} ジョブを送信しました")
        self._finalize_submitted_jobs(job_ids)
        self._status_callback(f"Batch API: {len(job_ids)} ジョブを送信しました", 5000)

    def _on_async_dispatch_failed(self, error: object, job_ids: list[int]) -> None:
        """dispatch 失敗時にエラーを通知する。部分送信済みジョブは台帳へ反映する。

        Args:
            error: 送信中に発生した例外。
            job_ids: 失敗前に作成済みの provider batch job_id (部分成功)。
        """
        if job_ids:
            # 部分送信: 作成済みジョブを台帳へ反映 + staging 除去で二重送信を防ぐ。
            logger.warning(
                f"Batch API dispatch 部分失敗: {len(job_ids)} ジョブ送信済み、以降で失敗: {error}"
            )
            self._finalize_submitted_jobs(job_ids)
            message = f"Batch API 送信が途中で失敗しました ({len(job_ids)} ジョブ送信済み):\n{error}"
        else:
            logger.error(f"Batch API dispatch 失敗: {error}", exc_info=isinstance(error, Exception))
            message = f"Batch API 送信に失敗しました:\n{error}"
        QMessageBox.critical(self._parent_widget, "Batch API 送信", message)

    def _on_async_dispatch_thread_finished(self) -> None:
        """worker thread 終了時に busy/再入ガードを解除する。"""
        self._async_dispatch_in_progress = False
        self._async_dispatch_worker = None
        self._async_dispatch_thread = None
