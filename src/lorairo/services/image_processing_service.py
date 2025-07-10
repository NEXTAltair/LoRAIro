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
        # ImageProcessingManager は処理時に一時的に作成（永続インスタンスは削除）

    def create_processing_manager(self, target_resolution: int) -> ImageProcessingManager:
        """処理時に一時的な ImageProcessingManager インスタンスを作成します。

        Args:
            target_resolution (int): 処理で使用する目標解像度（GUI で指定された現在の値）

        Returns:
            ImageProcessingManager: 処理用の一時的インスタンス

        Raises:
            ValueError: ImageProcessingManager の初期化に失敗した場合
        """
        try:
            preferred_resolutions_int = self.config_service.get_preferred_resolutions()
            # list[int] を list[tuple[int, int]] に変換
            preferred_resolutions = [(res, res) for res in preferred_resolutions_int]

            ipm = ImageProcessingManager(self.fsm, target_resolution, preferred_resolutions)
            logger.info(
                f"一時的な ImageProcessingManager を作成しました。target_resolution={target_resolution}"
            )
            return ipm
        except Exception as e:
            logger.error(f"ImageProcessingManager の作成に失敗しました: {e}", exc_info=True)
            raise ValueError(f"ImageProcessingManager の作成に失敗しました: {e}") from e

    def process_images_in_list(
        self,
        image_paths: list[Path],
        target_resolution: int,
        progress_callback: Callable[[int], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        is_canceled: Callable[[], bool] | None = None,
        upscaler_override: str | None = None,  # GUIから選択されたアップスケーラを渡す想定
    ) -> None:
        """指定された画像パスのリストに対して処理を実行します。

        Args:
            image_paths: 処理対象の画像ファイルパスのリスト。
            target_resolution: 処理で使用する目標解像度（GUI で指定された現在の値）。
            progress_callback: 進捗を通知するコールバック関数 (0-100のintを受け取る)。
            status_callback: ステータスメッセージを通知するコールバック関数 (strを受け取る)。
            is_canceled: キャンセルされたかどうかを返すコールバック関数。
            upscaler_override: GUI で選択されたアップスケーラ名 (設定より優先)。
        """
        # 処理時に一時的な ImageProcessingManager を作成
        ipm = self.create_processing_manager(target_resolution)

        logger.info(
            f"一時的な ImageProcessingManager を使用して処理を開始します。target_resolution={target_resolution}"
        )

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
                self._process_single_image(image_path, upscaler_override, ipm)
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

    def _process_single_image(
        self, image_file: Path, upscaler: str | None = None, ipm: ImageProcessingManager | None = None
    ) -> None:
        """単一の画像ファイルに対して処理を実行します。
           (元 ImageEditWidget.process_image + handle_processing_result)

        Args:
            image_file: 処理対象の画像ファイルパス。
            upscaler: 使用するアップスケーラ名 (Noneの場合は設定を使用)。
            ipm: 使用する ImageProcessingManager インスタンス。
        """
        if not ipm:
            logger.error("ImageProcessingManager が提供されていないため、処理を実行できません。")
            raise RuntimeError("ImageProcessingManager is not provided.")

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
        # 設定から最新の解像度を取得 (edit.pyで変更された可能性があるため)
        image_processing_config = self.config_service.get_image_processing_config()
        target_resolution = image_processing_config.get("target_resolution", 512)
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
        processed_image, processing_metadata = ipm.process_image(
            image_file,
            original_image_metadata.get("has_alpha", False),  # .get でキー存在確認
            original_image_metadata.get("mode", "RGB"),
            upscaler=final_upscaler,  # 修正後のアップスケーラ名を渡す
        )

        # --- 5. 処理結果の保存とDB登録 (元 handle_processing_result) ---
        if processed_image:
            # アップスケールが実行された場合はタグを追加
            if processing_metadata.get("was_upscaled", False):
                logger.info(f"{image_file.name}: アップスケールが実行されたため、upscaledタグを追加します")
                self._add_upscaled_tag(image_id, processing_metadata.get("upscaler_used"))

        if processed_image:
            logger.debug(f"{image_file.name}: 処理結果を保存・登録します。")
            processed_path = self.fsm.save_processed_image(processed_image, image_file, target_resolution)
            processed_metadata = self.fsm.get_image_info(processed_path)

            # アップスケール情報をメタデータに追加
            if processing_metadata.get("was_upscaled", False):
                processed_metadata["upscaler_used"] = processing_metadata.get("upscaler_used")
                logger.debug(
                    f"{image_file.name}: アップスケーラー情報をメタデータに追加: {processed_metadata['upscaler_used']}"
                )

            self.idm.register_processed_image(image_id, processed_path, processed_metadata)
            logger.info(f"画像処理完了: {image_file.name} -> {processed_path.name}")
        else:
            logger.warning(f"画像処理スキップ (ipm.process_image が None を返しました): {image_file.name}")

    def ensure_512px_image(self, image_id: int, original_path: Path) -> Path | None:
        """
        512px画像が存在することを保証し、なければ既存パイプラインで作成します。
        サムネイル表示や学習データセット用の512px画像を提供します。

        Args:
            image_id (int): データベース内の画像ID
            original_path (Path): 元画像のパス

        Returns:
            Path | None: 512px画像のパス、作成に失敗した場合はNone
        """
        try:
            # 1. 既存の512px画像をチェック
            existing_512px = self.idm.check_processed_image_exists(image_id, 512)
            if existing_512px and "stored_image_path" in existing_512px:
                path = Path(existing_512px["stored_image_path"])
                if path.exists():
                    logger.debug(f"既存の512px画像を使用: image_id={image_id}, path={path}")
                    return path
                else:
                    logger.warning(f"512px画像がファイルシステムに存在しません: {path}")

            # 2. 512px画像が存在しない場合は作成
            logger.info(f"512px画像を作成します: image_id={image_id}, original_path={original_path}")
            self._process_single_image_for_resolution(original_path, image_id, 512)

            # 3. 作成後に再取得
            new_512px = self.idm.check_processed_image_exists(image_id, 512)
            if new_512px and "stored_image_path" in new_512px:
                path = Path(new_512px["stored_image_path"])
                logger.info(f"512px画像の作成完了: image_id={image_id}, path={path}")
                return path
            else:
                logger.error(f"512px画像の作成後にDBから取得できませんでした: image_id={image_id}")

        except Exception as e:
            logger.warning(
                f"512px画像作成中にエラー: image_id={image_id}, original_path={original_path}, Error: {e}"
            )

        return None

    def _add_upscaled_tag(self, image_id: int, upscaler_used: str | None) -> None:
        """
        アップスケールされた画像にupscaledタグを追加します。

        Args:
            image_id (int): 対象画像のID
            upscaler_used (str | None): 使用されたアップスケーラー名
        """
        try:
            from ..database.db_repository import TagAnnotationData

            # upscaledタグを追加
            upscaled_tag: TagAnnotationData = {
                "tag": "upscaled",
                "tag_id": 33138,  # データベースにある既存のupscaledタグID
                "model_id": None,  # アップスケーラーはAIモデルではないためNone
                "existing": False,  # 処理によって追加されたタグ
                "is_edited_manually": False,
                "confidence_score": None,
            }

            self.idm.save_tags(image_id, [upscaled_tag])
            logger.info(f"upscaledタグを追加しました: image_id={image_id}, upscaler={upscaler_used}")

        except Exception as e:
            logger.warning(f"upscaledタグの追加に失敗しました: image_id={image_id}, Error: {e}")

    def _process_single_image_for_resolution(
        self, image_file: Path, image_id: int, target_resolution: int
    ) -> None:
        """
        指定解像度で単一画像を処理します（既存パイプライン活用）。

        Args:
            image_file (Path): 処理対象の画像ファイルパス
            image_id (int): データベース内の画像ID
            target_resolution (int): 目標解像度
        """
        # 既存の処理済み画像をチェック
        existing_processed_image = self.idm.check_processed_image_exists(image_id, target_resolution)
        if existing_processed_image:
            logger.debug(
                f"解像度 {target_resolution} の処理済み画像が既に存在するためスキップ: {image_file}"
            )
            return

        # 元画像のメタデータを取得
        original_metadata = self.idm.get_image_metadata(image_id)
        if not original_metadata:
            logger.error(f"画像ID {image_id} のメタデータが取得できません")
            raise RuntimeError(f"Failed to get metadata for image ID: {image_id}")

        # 処理用の一時的なImageProcessingManagerを作成
        ipm = self.create_processing_manager(target_resolution)

        # アップスケーラー設定を取得（設定ファイルから）
        image_processing_config = self.config_service.get_image_processing_config()
        upscaler = image_processing_config.get("upscaler")

        # 元画像のパスを取得（DBに保存されているパス）
        stored_original_path = Path(original_metadata["stored_image_path"])

        logger.debug(f"画像処理を実行: {image_file} -> 解像度 {target_resolution}")
        processed_image, processing_metadata = ipm.process_image(
            stored_original_path,
            original_metadata.get("has_alpha", False),
            original_metadata.get("mode", "RGB"),
            upscaler=upscaler,
        )

        # アップスケールが実行された場合はタグを追加
        if processing_metadata.get("was_upscaled", False):
            logger.info(f"{image_file}: アップスケールが実行されたため、upscaledタグを追加します")
            self._add_upscaled_tag(image_id, processing_metadata.get("upscaler_used"))

        if processed_image:
            logger.debug(f"処理結果を保存・登録: {image_file}")
            processed_path = self.fsm.save_processed_image(processed_image, image_file, target_resolution)
            processed_metadata = self.fsm.get_image_info(processed_path)

            # アップスケール情報をメタデータに追加
            if processing_metadata.get("was_upscaled", False):
                processed_metadata["upscaler_used"] = processing_metadata.get("upscaler_used")
                logger.debug(
                    f"{image_file}: アップスケーラー情報をメタデータに追加: {processed_metadata['upscaler_used']}"
                )

            self.idm.register_processed_image(image_id, processed_path, processed_metadata)
            logger.info(f"解像度 {target_resolution} 画像処理完了: {image_file} -> {processed_path.name}")
        else:
            logger.warning(f"画像処理結果がNone: {image_file}")
            raise RuntimeError(f"Image processing returned None for {image_file}")
