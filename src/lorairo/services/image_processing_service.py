"""画像処理関連のビジネスロジックを担当するサービスモジュール。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..database.db_manager import ImageDatabaseManager
from ..editor.image_processor import ImageProcessingManager  # ImageEditWidget から移動
from ..storage.file_system import FileSystemManager
from ..utils.log import logger
from .configuration_service import ConfigurationService

# ImageAnalyzer はアノテーション関連なので、ここでは直接使わない想定 (必要なら別サービス経由)
# from ..annotations.caption_tags import ImageAnalyzer


class ImageProcessingService:
    """画像のリサイズ、アップスケールなどの処理と、関連するDB操作を担当する。"""

    def __init__(
        self,
        config_service: ConfigurationService,
        fsm: FileSystemManager,
        idm: ImageDatabaseManager,
    ) -> None:
        """ImageProcessingService を初期化します。

        Args:
            config_service: 設定サービス。
            fsm: ファイルシステムマネージャー。
            idm: イメージデータベースマネージャー。
        """
        self.config_service = config_service
        self.fsm = fsm
        self.idm = idm
        # ImageProcessingManager はここで初期化するか、処理実行時に初期化するか検討
        self.ipm: ImageProcessingManager | None = None
        self._initialize_internal_processor()  # 内部で初期化を試みる

    def _initialize_internal_processor(self) -> None:
        """内部で使用する ImageProcessingManager を初期化します。"""
        try:
            # 設定値を取得して ImageProcessingManager を初期化
            image_processing_config = self.config_service.get_image_processing_config()
            target_resolution = image_processing_config.get("target_resolution", 512)
            preferred_resolutions_int = self.config_service.get_preferred_resolutions()
            # list[int] を list[tuple[int, int]] に変換
            preferred_resolutions = [(res, res) for res in preferred_resolutions_int]
            output_dir = self.config_service.get_export_directory()

            # FileSystemManager の初期化もここで行うか確認 (現状は外部で初期化想定)
            # self.fsm.initialize(output_dir, target_resolution) # 必要なら実行

            self.ipm = ImageProcessingManager(self.fsm, target_resolution, preferred_resolutions)
            logger.info("ImageProcessingManager を初期化しました。")
        except Exception as e:
            logger.error(f"ImageProcessingManager の初期化に失敗しました: {e}", exc_info=True)
            self.ipm = None  # 初期化失敗時は None のまま

    def process_images_in_list(
        self,
        image_paths: list[Path],
        progress_callback: Callable[[int], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        is_canceled: Callable[[], bool] | None = None,
        upscaler_override: str | None = None,  # GUIから選択されたアップスケーラを渡す想定
    ) -> None:
        """指定された画像パスのリストに対して処理を実行します。

        Args:
            image_paths: 処理対象の画像ファイルパスのリスト。
            progress_callback: 進捗を通知するコールバック関数 (0-100のintを受け取る)。
            status_callback: ステータスメッセージを通知するコールバック関数 (strを受け取る)。
            is_canceled: キャンセルされたかどうかを返すコールバック関数。
            upscaler_override: GUI で選択されたアップスケーラ名 (設定より優先)。
        """
        if not self.ipm:
            logger.error("ImageProcessingManager が初期化されていないため、処理を実行できません。")
            # TODO: エラーを呼び出し元に通知する仕組みが必要
            raise RuntimeError("ImageProcessingManager is not initialized.")

        total_images = len(image_paths)
        logger.info(f"{total_images} 件の画像処理を開始します。")

        for index, image_path in enumerate(image_paths):
            if is_canceled and is_canceled():
                logger.info("画像処理がキャンセルされました。")
                if status_callback:
                    status_callback("処理がキャンセルされました。")
                break  # ループ中断

            logger.debug(f"画像処理中: {index + 1}/{total_images} - {image_path.name}")
            if status_callback:
                status_callback(f"画像 {index + 1}/{total_images} ({image_path.name}) を処理中...")

            try:
                # 個別画像の処理を実行
                self._process_single_image(image_path, upscaler_override)
            except Exception as e:
                logger.error(f"{image_path.name} の処理中にエラーが発生しました: {e}", exc_info=True)
                # TODO: エラーが発生しても処理を継続するか、中断するか?
                # とりあえずログに残して継続
                if status_callback:
                    status_callback(f"エラー: {image_path.name} の処理に失敗しました。")

            if progress_callback:
                progress = int((index + 1) / total_images * 100)
                progress_callback(progress)

        logger.info("画像処理が完了しました。")
        if status_callback:
            status_callback("画像処理が完了しました。")

    def _process_single_image(self, image_file: Path, upscaler: str | None = None) -> None:
        """単一の画像ファイルに対して処理を実行します。
           (元 ImageEditWidget.process_image + handle_processing_result)

        Args:
            image_file: 処理対象の画像ファイルパス。
            upscaler: 使用するアップスケーラ名 (Noneの場合は設定を使用)。
        """
        if not self.ipm:
            # このケースは process_images_in_list でチェック済みのはずだが念のため
            raise RuntimeError("ImageProcessingManager is not initialized.")

        # --- 1. DBチェックとオリジナル画像登録 (元 process_image の前半) ---
        image_id = self.idm.detect_duplicate_image(image_file)
        if not image_id:
            logger.debug(f"{image_file.name}: DBに未登録。新規登録します。")
            # register_original_image の戻り値をチェック
            registration_result = self.idm.register_original_image(image_file, self.fsm)
            if registration_result is None:
                logger.error(f"{image_file.name}: DBへの新規登録に失敗しました。")
                # エラー処理: ここで処理を中断するかどうか
                raise RuntimeError(f"Failed to register original image: {image_file.name}")
            image_id, original_image_metadata_maybe = registration_result
            # 戻り値が None でないことを確認してから代入
            if image_id is None or original_image_metadata_maybe is None:
                logger.error(
                    f"{image_file.name}: DBへの新規登録後、有効なIDまたはメタデータが取得できませんでした。"
                )
                raise RuntimeError(f"Failed to get valid data after registering: {image_file.name}")
            original_image_metadata: dict[str, Any] = original_image_metadata_maybe
        else:
            logger.debug(f"{image_file.name}: DBに登録済み (ID: {image_id})。メタデータを取得します。")
            # get_image_metadata の戻り値が None の可能性を考慮
            metadata_maybe = self.idm.get_image_metadata(image_id)
            if metadata_maybe is None:
                logger.error(f"{image_file.name} (ID: {image_id}): DBからメタデータの取得に失敗しました。")
                # エラー処理: ここで処理を中断するかどうか
                raise RuntimeError(f"Failed to get metadata from DB for image ID: {image_id}")
            original_image_metadata: dict[str, Any] = metadata_maybe

        # --- 2. 既存アノテーションの処理 (元 process_image の中盤) ---
        # アノテーション処理は ImageAnalyzer サービス等に分離するのが望ましいが、
        # 元コードに合わせて一旦ここに含めるか、コメントアウトして責務外とする。
        # ※ 元コードでは ImageAnalyzer.get_existing_annotations を呼び出していたが、
        #   それはファイルベースの .txt/.json を見る実装だった可能性。
        #   DBから取得するロジックに修正が必要かも。
        # existing_annotations = ImageAnalyzer.get_existing_annotations(image_file) # ファイルベース想定?
        # logger.warning("_process_single_image 内のアノテーション処理は未実装です。")

        # --- 3. 処理済み画像の存在チェック (元 process_image の後半) ---
        target_resolution = self.ipm.target_resolution  # ipm から取得
        existing_processed_image = self.idm.check_processed_image_exists(image_id, target_resolution)
        if existing_processed_image:
            logger.info(
                f"{image_file.name}: Target resolution ({target_resolution}) の処理済み画像が既に存在するためスキップします。"
            )
            return

        # --- 4. 画像処理の実行 (元 process_image の後半) ---
        # upscaler が None の場合は設定から取得
        final_upscaler = upscaler
        if final_upscaler is None:
            image_processing_config = self.config_service.get_image_processing_config()
            final_upscaler = image_processing_config.get(
                "upscaler"
            )  # 設定にもなければ None のまま (process_image 側で対応想定)
            if final_upscaler:
                logger.debug(
                    f"{image_file.name}: Upscaler override is None. Using default from config: {final_upscaler}"
                )
            else:
                logger.debug(
                    f"{image_file.name}: Upscaler override is None and no default found in config."
                )

        # final_upscaler が決定できなかった場合は処理をスキップ
        if final_upscaler is None:
            logger.warning(
                f"{image_file.name}: Upscaler が決定できなかったため、画像処理をスキップします。"
            )
            return

        logger.debug(f"{image_file.name}: 画像処理を実行します。Upscaler: {final_upscaler}")
        processed_image = self.ipm.process_image(
            image_file,
            original_image_metadata.get("has_alpha", False),  # .get でキー存在確認
            original_image_metadata.get("mode", "RGB"),
            upscaler=final_upscaler,  # 修正後のアップスケーラ名を渡す
        )

        # --- 5. 処理結果の保存とDB登録 (元 handle_processing_result) ---
        if processed_image:
            logger.debug(f"{image_file.name}: 処理結果を保存・登録します。")
            processed_path = self.fsm.save_processed_image(processed_image, image_file)
            processed_metadata = self.fsm.get_image_info(processed_path)
            self.idm.register_processed_image(image_id, processed_path, processed_metadata)
            logger.info(f"画像処理完了: {image_file.name} -> {processed_path.name}")
        else:
            logger.warning(f"画像処理スキップ (ipm.process_image が None を返しました): {image_file.name}")
