"""アノテーションワークフロー制御Controller

MainWindow.start_annotation()から抽出したアノテーションワークフロー制御ロジック。
DatasetControllerパターンに従い、依存性注入とcallbackパターンを使用。
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
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
    DispatchEntry,
    DispatchProjection,
    DispatchProjectionError,
    project_async_batch_dispatch,
)
from lorairo.services.model_route_service import validate_api_keys_for_models
from lorairo.services.provider_batch_capability import (
    direct_provider_for_model,
    is_omni_moderation_model,
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
    selected_litellm_model_ids: list[str],
    db_manager: "ImageDatabaseManager",
) -> str:
    """Batch API 側の task_type を決める (#1098 + #1133)。

    選択に omni-moderation-* が 1 つでも含まれれば ``"rating_preflight"``、無ければ
    ``"annotation"``。#1133 で混在は拒否しない: 選んだ task_type に対応しないモデル
    (例: rating_preflight での通常モデル、annotation での moderation モデル) は射影で
    ineligible になり、呼び出し側が同期ワークフローへ振り分ける。moderation は
    ``rating_preflight`` で batch へ流し、混在する通常モデルは同期へ回る (仕様例)。

    Args:
        selected_litellm_model_ids: Annotate の選択モデル集合 (SSoT)。
        db_manager: litellm_model_id → DB Model 解決に使う。

    Returns:
        "annotation" または "rating_preflight" (拒否・None は返さない)。
    """
    for litellm_id in selected_litellm_model_ids:
        model = db_manager.model_repo.get_model_by_litellm_id(litellm_id)
        if model is not None and is_omni_moderation_model(model):
            return "rating_preflight"
    return "annotation"


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
    processed_paths: dict[int, str] | None,
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
        logger.opt(exception=True).error(f"Batch API モデル discovery 失敗: {e}")
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


def _partition_moderation_from_sync(
    ineligible_ids: Sequence[str], db_manager: "ImageDatabaseManager"
) -> tuple[list[str], list[str]]:
    """ineligible を「同期対象 (通常モデル)」と「unsupported (moderation)」へ分離する (#1136 Codex P2)。

    omni-moderation-* は moderation 専用で同期アノテーションワークフローでは実行できない。
    同期フォールバックへ渡すと必ず失敗するため、sync 対象から除外し unsupported として返す。
    呼び出し側がユーザーへ「moderation は Batch API のみ対応」と明示する。

    Args:
        ineligible_ids: batch 非対応で振り分け対象の litellm_model_id (順序保持)。
        db_manager: litellm_model_id → DB Model 解決に使う。

    Returns:
        (sync_ids, unsupported_moderation_ids)。
    """
    sync_ids: list[str] = []
    unsupported_ids: list[str] = []
    for litellm_id in ineligible_ids:
        model = db_manager.model_repo.get_model_by_litellm_id(litellm_id)
        if model is not None and is_omni_moderation_model(model):
            unsupported_ids.append(litellm_id)
        else:
            sync_ids.append(litellm_id)
    return sync_ids, unsupported_ids


def _partition_batch_unavailable(
    selected_ids: Sequence[str], db_manager: "ImageDatabaseManager"
) -> tuple[list[str], list[str], list[str]]:
    """Batch が使えないとき選択を「同期 / batch のみ(実行不可) / unsupported」へ 3 分割する (#1136 2巡目)。

    Batch サービス不在・discovery 失敗で batch 射影ができないケース。API モデル
    (direct openai/anthropic) はユーザーが Batch API を選んだ対象なので黙って同期実行せず
    「実行されない」ものとして分ける。moderation は Batch 専用で unsupported。
    local などの同期専用モデルだけを同期起動対象にする。

    Args:
        selected_ids: 選択モデル集合。
        db_manager: litellm_model_id → DB Model 解決に使う。

    Returns:
        (sync_ids, blocked_api_ids, unsupported_moderation_ids)。
    """
    sync_ids: list[str] = []
    blocked_api_ids: list[str] = []
    unsupported_ids: list[str] = []
    for litellm_id in selected_ids:
        model = db_manager.model_repo.get_model_by_litellm_id(litellm_id)
        if model is not None and is_omni_moderation_model(model):
            unsupported_ids.append(litellm_id)
        elif model is not None and direct_provider_for_model(model) is not None:
            # direct API モデル = batch 候補。batch 不可時は同期へ流さず実行しない。
            blocked_api_ids.append(litellm_id)
        else:
            sync_ids.append(litellm_id)
    return sync_ids, blocked_api_ids, unsupported_ids


def _start_sync_workflow(
    controller: "AnnotationWorkflowController",
    sync_ids: list[str],
    run_options: "RunOptions",
) -> bool:
    """同期対象モデルを ステージング画像で同期ワークフロー起動する (空パスガード付き、#1136 2巡目 P2)。

    staged 画像はあってもパスが 1 件も解決できない (ファイル削除等) 場合、空リストを渡すと
    ``start_annotation_workflow`` が「override なし」とみなし SelectionStateService の別集合へ
    フォールバックしてしまう。空パスは明示エラーにして同期を起動しない。

    Returns:
        同期ワークフローを開始できたら True。
    """
    if not sync_ids or controller._annotate_tab is None:
        return False
    staged_paths = controller._annotate_tab.staged_image_paths()
    if not staged_paths:
        QMessageBox.information(
            controller._parent_widget,
            "ステージング画像なし",
            "ステージング画像のパスを解決できませんでした。\n"
            "画像ファイルが存在するか確認してから再実行してください。",
        )
        return False
    logger.info(f"同期専用モデルを起動: {len(sync_ids)} モデル")
    return controller.start_annotation_workflow(
        selected_litellm_model_ids=sync_ids,
        image_paths=staged_paths,
        run_options=run_options,
    )


def _notify_batch_unavailable(
    controller: "AnnotationWorkflowController",
    sync_count: int,
    blocked_api_count: int,
    unsupported_count: int,
) -> None:
    """Batch 不可時の振り分け結果 (API モデルは実行されない旨) を明示する (#1136 2巡目 P2)。"""
    parts: list[str] = []
    if blocked_api_count:
        parts.append(f"Batch API が利用できないため API モデル {blocked_api_count} 件は実行されません")
    if sync_count:
        parts.append(f"同期専用 {sync_count} 件を同期実行します")
    message = "。".join(parts) if parts else "実行できるモデルがありません"
    if unsupported_count:
        message += f" (moderation {unsupported_count} 件は Batch API のみ対応のため実行対象外)"
    logger.info(message)
    controller._status_callback(message, 5000)


def _dispatch_batch_unavailable(
    controller: "AnnotationWorkflowController",
    selected_ids: list[str],
    run_options: "RunOptions",
    db_manager: "ImageDatabaseManager",
) -> bool:
    """Batch サービス不在 / discovery 失敗時の同期フォールバック (#1136 2巡目 P2 #1/#3)。

    batch 射影が一切できないため、API モデルは実行せず (Batch API 前提)、同期専用モデル
    (local 等) だけを同期起動する。moderation は unsupported。振り分けはステータスへ明示。

    Returns:
        同期を開始できたら True。
    """
    sync_ids, blocked_api_ids, unsupported_ids = _partition_batch_unavailable(selected_ids, db_manager)
    _notify_batch_unavailable(controller, len(sync_ids), len(blocked_api_ids), len(unsupported_ids))
    return _start_sync_workflow(controller, sync_ids, run_options)


def _resolve_batch_entries(
    controller: "AnnotationWorkflowController",
    projection: "DispatchProjection",
    task_type: str,
    image_ids: list[int],
    db_manager: "ImageDatabaseManager",
) -> tuple[DispatchEntry, ...]:
    """batch entry を最終確定する (gate / processed パスを満たすときのみ、#1136 Codex P2)。

    annotation batch entry がある場合のみ moderation gate を適用し、通過したら processed
    パス (ADR 0064) を解決して各 entry へ差し込む。gate ブロックやパス解決失敗なら空を返し、
    batch は起動しない (同期対象は呼び出し側で独立起動する)。module-level 関数にしているのは
    Mock-self の unbound-call 統合テスト互換のため。

    Returns:
        処理済みパス差込済みの batch entry。起動不可なら空タプル。
    """
    if not projection.entries:
        return ()
    # fail-closed moderation gate (ADR 0070)。rating_preflight は gate 内で自動スキップ。
    if _moderation_gate_blocks(controller._parent_widget, task_type, image_ids, db_manager):
        return ()
    processed_paths = controller._resolve_processed_paths_for_batch(image_ids)
    if processed_paths is None:
        return ()  # 解決失敗 (warning は helper 内で表示済み)、batch のみ中止
    return tuple(replace(entry, image_paths=processed_paths) for entry in projection.entries)


def _notify_dispatch_split(
    controller: "AnnotationWorkflowController",
    batch_count: int,
    sync_count: int,
    unsupported_count: int = 0,
) -> None:
    """振り分け結果をステータスへ明示する (#1133 / #1136)。

    Args:
        controller: status callback を持つ AnnotationWorkflowController。
        batch_count: Batch API へ射影したモデル数。
        sync_count: 同期へ振り分けたモデル数。
        unsupported_count: moderation で同期不可・batch にも乗らずスキップしたモデル数。
    """
    if batch_count and sync_count:
        message = f"{batch_count} モデルを Batch API へ、{sync_count} モデルを同期で実行します"
    elif batch_count:
        message = f"{batch_count} モデルを Batch API へ送信します"
    elif sync_count:
        message = f"{sync_count} モデルを同期で実行します"
    else:
        message = "実行できるモデルがありません"
    if unsupported_count:
        message += f" (moderation {unsupported_count} 件は Batch API のみ対応のため実行対象外)"
    logger.info(message)
    controller._status_callback(message, 5000)


def _run_dispatch_split(
    controller: "AnnotationWorkflowController",
    workflow_service: Any,
    batch_entries: tuple[DispatchEntry, ...],
    sync_ids: list[str],
    unsupported_ids: list[str],
    image_ids: list[int],
    run_options: "RunOptions",
) -> bool:
    """batch 対応モデルを Batch API へ、同期対象を同期ワークフローへ並行起動する (#1133 / #1136)。

    batch と同期は互いに独立に判定・起動する: Batch サービス不在や processed パス解決失敗で
    batch が起動できなくても、同期対象 (sync_ids) は独立して起動する (Codex P2 #1/#2)。
    module-level 関数にしているのは Mock-self の unbound-call 統合テスト互換のため。

    Args:
        controller: dispatch を所有する AnnotationWorkflowController。
        workflow_service: Provider Batch workflow service (None なら batch は起動しない)。
        batch_entries: Batch API へ送る dispatch entry (空なら batch なし)。
        sync_ids: 同期ワークフローで実行する litellm_model_id。
        unsupported_ids: moderation で実行対象外のモデル (通知のみ)。
        image_ids: 送信対象の image_id。
        run_options: 実行詳細設定 (同期側へ伝搬)。

    Returns:
        batch / 同期のいずれか一方でも開始できたら True。
    """
    # #1133/#1136: 振り分け結果を明示する (黙って振り分けない)
    _notify_dispatch_split(controller, len(batch_entries), len(sync_ids), len(unsupported_ids))

    started_batch = False
    if batch_entries and workflow_service is not None:
        projection = DispatchProjection(entries=batch_entries, ineligible_litellm_model_ids=tuple(sync_ids))
        logger.info(
            f"Batch API dispatch 開始: {projection.job_count} ジョブ / {len(image_ids)} 枚 "
            f"(dispatch_mode={run_options.dispatch_mode}, sync_fallback={len(sync_ids)} モデル)"
        )
        controller._async_dispatch_in_progress = True
        controller._async_dispatch_image_ids = image_ids
        controller._start_async_dispatch_worker(workflow_service, projection)
        started_batch = True

    # 同期は空パスガード付き helper へ委譲 (#1136 2巡目 P2)
    started_sync = _start_sync_workflow(controller, sync_ids, run_options)

    return started_batch or started_sync


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

    def start_annotation(self, dispatch_mode: str | None = None) -> bool:
        """アノテーション実行エントリ。dispatch mode で分岐する (#896 PR4c, #1099)。

        AnnotateTabWidget の run bar 実行ボタン (``annotation_execute_requested``)
        から呼ばれる。``dispatch_mode`` (ADR 0076 §1) が ``batch_api`` なら async
        Provider Batch dispatch へ、それ以外は同期バッチアノテーション
        (:meth:`start_annotation_workflow`) へ分岐する。

        Args:
            dispatch_mode: 実行ボタンが指定した送信方式 ("sync" / "batch_api"、#1099)。
                None の場合は ``run_options().dispatch_mode`` を使う (後方互換)。

        Returns:
            実行が実際に開始できたら True、開始前に拒否した場合 (ステージング空 /
            モデル未選択 / 射影・preflight 失敗等) は False (#1102: 遷移可否の判定に使う)。
        """
        annotate_tab = self._annotate_tab

        # 送信方式 (dispatch mode) 判定 (#884 Phase 2c, ADR 0076 §1, #1099)。
        # 実行ボタン (#1099) が明示指定する dispatch_mode を優先し、無ければ RunOptions を読む。
        effective_mode = dispatch_mode
        if effective_mode is None and annotate_tab is not None:
            effective_mode = annotate_tab.run_options().dispatch_mode
        # batch_api (async) は dispatch 射影 → worker thread へ分岐する。
        if effective_mode == "batch_api":
            return self.dispatch_async_batch()

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
                return False

        # 実行詳細設定 (RunOptions) を同期アノテフローへ伝搬する (Issue #803)。
        run_options = annotate_tab.run_options() if annotate_tab is not None else None

        # チェックボックスから選択されたモデルを優先し、無ければダイアログ callback へ
        return self.start_annotation_workflow(
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
    ) -> bool:
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

        Returns:
            バッチアノテーションを実際に開始できたら True、開始前に拒否した場合
            (画像/モデル未選択、API key 不足、例外等) は False (#1102)。
        """
        try:
            # Step 1: サービス検証（image_paths指定時はSelectionStateService不要）
            if not image_paths and not self._validate_services():
                return False

            # Step 2: 選択画像取得（image_paths指定時はそれを使用）
            if image_paths:
                logger.debug(f"明示指定された画像パスを使用: {len(image_paths)}件")
                paths_to_use = image_paths
            else:
                paths_to_use = self._get_selected_image_paths()
                if not paths_to_use:
                    return False
            image_paths = paths_to_use

            # Step 3: モデル選択（selected_litellm_model_ids優先）
            models_to_use = self._resolve_models_to_use(
                selected_litellm_model_ids, model_selection_callback
            )
            if not models_to_use:
                return False

            if self._warn_deprecated_models(models_to_use) is False:
                return False

            # Issue #241: 実行直前に API key 不足を検出する。
            # 旧実装は WorkerService 内で library 呼び出し時に MissingApiKeyError が
            # 出るまで失敗を検出できなかった。直接プロバイダー key のみ持つ環境で
            # `openrouter/...` モデルを誤選択した場合などをここで止める。
            if self._validate_api_keys_for_models(models_to_use) is False:
                return False

            # Step 4: バッチアノテーション開始
            return self._start_batch_annotation(image_paths, models_to_use, run_options=run_options)

        except Exception as e:
            error_msg = f"アノテーション処理の開始に失敗しました: {e}"
            logger.opt(exception=True).error(error_msg)
            if self._parent_widget:
                QMessageBox.critical(
                    self._parent_widget,
                    "アノテーション開始エラー",
                    error_msg,
                )
            return False

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
            logger.opt(exception=True).error(f"画像パス取得中にエラー: {e}")
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
    ) -> bool:
        """バッチアノテーション開始

        Args:
            image_paths: 画像パスリスト
            litellm_model_ids: モデルの `litellm_model_id` リスト
            run_options: 実行詳細設定 (Issue #803)。worker_service へ伝搬する。

        Returns:
            worker を起動できたら True (#1102)。例外時は False を返さず re-raise する
            (呼び出し元 :meth:`start_annotation_workflow` の except が集約処理する)。
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
            return True

        except Exception as e:
            error_msg = f"バッチアノテーション開始に失敗: {e}"
            logger.opt(exception=True).error(error_msg)
            if self._parent_widget:
                QMessageBox.critical(
                    self._parent_widget,
                    "アノテーション実行エラー",
                    error_msg,
                )
            raise

    # == async Provider Batch dispatch (#896 PR4b, ADR 0076 §2) ================

    def dispatch_async_batch(self) -> bool:
        """「Batch API 実行」を batch 対応 / 同期専用へ自動振り分けして起動する (#1133)。

        ADR 0076 §2: 選択モデル集合 → dispatch 射影 (batch-capable ∩ discovery) →
        worker thread で ``submit_images`` をモデルごとにループ呼び出しする。

        #1133 (2026-07-04 ユーザー決定で #884 の混在拒否を上書き): batch 非対応モデルが
        混在しても拒否せず、batch 対応モデルは Batch API へ射影・送信し、同期専用モデルは
        同期ワークフロー (:meth:`start_annotation_workflow`) へ並行起動する。batch と同期は
        互いに独立に判定・起動する (#1136 Codex P2): Batch サービス不在や processed パス
        解決失敗で batch が起動できなくても、同期対象は独立して起動する。

        #1098/#1136: moderation (omni-moderation-*) を含む選択は ``task_type="rating_preflight"``
        で射影 (OpenAI 公式 Batch API の ``/v1/moderations``)。moderation は同期実行できない
        ため、batch に乗らなかった moderation モデルは同期へは流さず実行対象外として明示する
        (#1136 Codex P2)。annotation batch entry がある場合のみ送信前 moderation 未完了の
        画像を gate で拒否する (ADR 0070)。

        Returns:
            batch / 同期のいずれか一方でも開始できたら True、開始前に全て拒否/対象外だった
            場合は False (#1102: どちらか開始成功で Jobs 遷移)。
        """
        if self._annotate_tab is None:
            return False
        if self._async_dispatch_in_progress:
            return False

        db_manager = self._db_manager
        if db_manager is None:
            QMessageBox.warning(self._parent_widget, "Batch API 送信", "サービスを利用できません。")
            return False

        run_options = self._annotate_tab.run_options()
        image_ids = list(self._annotate_tab.get_staged_items().keys())
        if not image_ids:
            QMessageBox.information(
                self._parent_widget,
                "ステージング画像なし",
                "ステージングリストに画像がありません。\n"
                "画像を選択してからアノテーションを実行してください。",
            )
            return False

        # dry-run: 実送信せず件数プレビューのみ (RunSettings の dry-run 契約)
        if run_options.dry_run:
            QMessageBox.information(
                self._parent_widget,
                "Batch API 送信 (dry-run)",
                f"dry-run: {len(image_ids)} 枚を Batch API へ送信予定です。\n実際の送信・推論は行いません。",
            )
            return False

        # #1098/#1133: moderation を含めば rating_preflight、無ければ annotation。
        selected_litellm_model_ids = self._annotate_tab.selected_litellm_model_ids()
        task_type = _resolve_dispatch_task_type(selected_litellm_model_ids, db_manager)

        container = self._service_container
        workflow_service = getattr(container, "provider_batch_workflow_service", None)
        model_source = getattr(container, "annotator_library", None)

        # #1136 2巡目 P2: Batch サービス不在なら batch 射影不能。API モデルは同期へ流さず、
        # 同期専用モデルだけを同期起動する (batch 前処理から独立)。
        if workflow_service is None or model_source is None:
            return _dispatch_batch_unavailable(self, selected_litellm_model_ids, run_options, db_manager)

        # 射影で eligible / ineligible を確定 (processed パスは実 batch 起動時のみ解決)。
        projection = _build_batch_projection(
            self._parent_widget,
            workflow_service=workflow_service,
            db_manager=db_manager,
            selected_litellm_model_ids=selected_litellm_model_ids,
            image_ids=image_ids,
            prompt_profile=run_options.prompt_profile,
            description=run_options.description,
            processed_paths=None,
            task_type=task_type,
        )
        if projection is None:
            # #1136 2巡目 P2 #1: discovery 失敗でも同期は discovery 不要 → 同期専用へフォールバック。
            return _dispatch_batch_unavailable(self, selected_litellm_model_ids, run_options, db_manager)

        # #1136 Codex P2: ineligible を「同期対象 (通常)」と「実行対象外 (moderation)」へ分離。
        sync_ids, unsupported_ids = _partition_moderation_from_sync(
            projection.ineligible_litellm_model_ids, db_manager
        )

        # batch entry があるときだけ moderation gate + processed パス解決。gate ブロック /
        # パス解決失敗なら batch は起動せず、同期対象は独立して起動する (#1136 Codex P2)。
        batch_entries = _resolve_batch_entries(self, projection, task_type, image_ids, db_manager)

        return _run_dispatch_split(
            self, workflow_service, batch_entries, sync_ids, unsupported_ids, image_ids, run_options
        )

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
            # slot は except 節外で後から実行されるため sys.exc_info() は空。emit された例外
            # オブジェクトを exception= に直接渡して traceback を記録する (#1153 Codex P2)。
            logger.opt(exception=error if isinstance(error, Exception) else None).error(
                f"Batch API dispatch 失敗: {error}"
            )
            message = f"Batch API 送信に失敗しました:\n{error}"
        QMessageBox.critical(self._parent_widget, "Batch API 送信", message)

    def _on_async_dispatch_thread_finished(self) -> None:
        """worker thread 終了時に busy/再入ガードを解除する。"""
        self._async_dispatch_in_progress = False
        self._async_dispatch_worker = None
        self._async_dispatch_thread = None
        # #1156: Batch API dispatch (submit) 完了で実行ボタンを再有効化する (連打ガード解除)。
        if self._annotate_tab is not None:
            self._annotate_tab.set_execution_running(False)
