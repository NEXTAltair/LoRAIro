"""アノテーションワークフロー制御Controller

MainWindow.start_annotation()から抽出したアノテーションワークフロー制御ロジック。
DatasetControllerパターンに従い、依存性注入とcallbackパターンを使用。
"""

from collections.abc import Callable

from loguru import logger
from PySide6.QtWidgets import QMessageBox, QWidget

from lorairo.gui.services.worker_service import WorkerService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.model_route_service import validate_api_keys_for_models
from lorairo.services.selection_state_service import SelectionStateService
from lorairo.services.service_container import get_service_container


class AnnotationWorkflowController:
    """アノテーション処理ワークフロー制御Controller

    MainWindow.start_annotation()から抽出。
    画像選択→モデル選択→アノテーション実行のワークフロー全体を制御。

    DatasetControllerパターン準拠:
    - 依存性注入（constructor injection）
    - Callbackパターン（GUI操作はMainWindowに委譲）
    - サービス層へのビジネスロジック委譲
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
        self.worker_service = worker_service
        self.selection_state_service = selection_state_service
        self.config_service = config_service
        self.parent = parent

    def start_annotation_workflow(
        self,
        selected_litellm_model_ids: list[str] | None = None,
        model_selection_callback: Callable[[list[str]], str | None] | None = None,
        image_paths: list[str] | None = None,
        confidence_thresholds: dict[str, float] | None = None,
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
            confidence_thresholds: stage ピッカーで設定された conf-min 閾値
                (`litellm_model_id` → 閾値)。RunOptions とは別経路で worker へ伝播する
                (#851)。None または空 dict の場合は閾値フィルタなし。
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
            self._start_batch_annotation(image_paths, models_to_use, confidence_thresholds)

        except Exception as e:
            error_msg = f"アノテーション処理の開始に失敗しました: {e}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(
                    self.parent,
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
        if self.parent:
            QMessageBox.warning(
                self.parent,
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
            if self.parent:
                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "WorkerServiceが初期化されていないため、アノテーション処理を実行できません。",
                )
            return False

        if not self.selection_state_service:
            logger.warning("SelectionStateServiceが初期化されていません")
            if self.parent:
                QMessageBox.warning(
                    self.parent,
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
                if self.parent:
                    QMessageBox.information(
                        self.parent,
                        "画像データ取得エラー",
                        "選択された画像のパスを取得できませんでした。\n"
                        "データベースの状態を確認してください。",
                    )
                return []

            return image_paths

        except ValueError as e:
            # SelectionStateService.get_selected_image_paths()からのエラー
            logger.info(f"画像選択エラー: {e}")
            if self.parent:
                QMessageBox.information(
                    self.parent,
                    "画像未選択",
                    str(e),
                )
            return []

        except Exception as e:
            logger.error(f"画像パス取得中にエラー: {e}", exc_info=True)
            if self.parent:
                QMessageBox.warning(
                    self.parent,
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

        if not self.parent:
            return True

        reply = QMessageBox.warning(
            self.parent,
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

        if self.parent is not None:
            QMessageBox.warning(
                self.parent,
                "API キー未設定",
                message,
            )
        return False

    def _start_batch_annotation(
        self,
        image_paths: list[str],
        litellm_model_ids: list[str],
        confidence_thresholds: dict[str, float] | None = None,
    ) -> None:
        """バッチアノテーション開始

        Args:
            image_paths: 画像パスリスト
            litellm_model_ids: モデルの `litellm_model_id` リスト
            confidence_thresholds: stage ピッカー由来の conf-min 閾値
                (`litellm_model_id` → 閾値)。worker へ伝播する (#851)。
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
                confidence_thresholds=confidence_thresholds,
            )

            # 非ブロッキング通知
            status_msg = f"アノテーション処理を開始: {len(image_paths)}画像, モデル: {litellm_model_ids[0]}"
            logger.info(status_msg)

        except Exception as e:
            error_msg = f"バッチアノテーション開始に失敗: {e}"
            logger.error(error_msg, exc_info=True)
            if self.parent:
                QMessageBox.critical(
                    self.parent,
                    "アノテーション実行エラー",
                    error_msg,
                )
            raise
