"""DBマネージャー (高レベルインターフェース)"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session

from ..storage.file_system import FileSystemManager
from ..utils.log import logger
from ..utils.tools import calculate_phash
from .db_repository import (
    AnnotationsDict,
    CaptionAnnotationData,
    ImageRepository,
    RatingAnnotationData,
    ScoreAnnotationData,
    TagAnnotationData,
)

if TYPE_CHECKING:
    from ..services.configuration_service import ConfigurationService


class ImageDatabaseManager:
    """
    画像データベース操作の高レベルインターフェースを提供するクラス。
    ImageRepositoryを使用して、画像メタデータとアノテーションの
    保存、取得、更新などの操作を行います。
    """

    def __init__(
        self,
        repository: ImageRepository,
        config_service: "ConfigurationService",
        fsm: FileSystemManager | None = None,
    ):
        """
        ImageDatabaseManagerのコンストラクタ。

        Args:
            repository (ImageRepository): 使用するImageRepositoryインスタンス。
            config_service (ConfigurationService): 設定サービスインスタンス。
            fsm (FileSystemManager): ファイルシステムマネージャー（オプション）。
        """
        self.repository = repository
        self.config_service = config_service
        self.fsm = fsm
        logger.info("ImageDatabaseManager initialized.")

    @classmethod
    def create_default(cls) -> "ImageDatabaseManager":
        """デフォルト設定でインスタンスを作成するファクトリメソッド"""
        from ..services.configuration_service import ConfigurationService

        repository = ImageRepository()
        config_service = ConfigurationService()
        return cls(repository, config_service)

    # __enter__ と __exit__ はリポジトリがセッション管理するため、ここでは不要になることが多い
    # 必要であれば、リポジトリのセッションファクトリを使う処理を追加できる

    def register_original_image(
        self, image_path: Path, fsm: FileSystemManager
    ) -> tuple[int, dict[str, Any]] | None:
        """
        オリジナル画像をストレージに保存し、メタデータをデータベースに登録します。
        重複チェック (pHash) を行い、重複があれば既存IDを返します。

        Args:
            image_path (Path): オリジナル画像のパス。
            fsm (FileSystemManager): ファイルシステム操作用マネージャー。

        Returns:
            tuple[int, dict[str, Any]] | None: 登録成功時は (image_id, original_metadata)、
                                                 重複時は (existing_image_id, existing_metadata)、
                                                 失敗時は None。

                                                 新規登録・重複時共に一貫したフォーマットで
                                                 (id, metadata) のタプルを返します。
        """
        try:
            # 1. 画像情報を取得
            original_metadata = fsm.get_image_info(image_path)
            if not original_metadata:
                logger.error(f"画像情報の取得に失敗: {image_path}")
                return None

            # 2. pHash を計算
            try:
                phash = calculate_phash(image_path)
            except Exception as e:
                logger.error(f"pHash の計算中にエラーが発生しました: {image_path}, Error: {e}")
                # pHash が計算できない場合は登録を中止する(あるいは phash=None で登録するかは要件次第)
                return None

            # 3. 重複チェック (pHash)
            existing_id = self.repository.find_duplicate_image_by_phash(phash)
            if existing_id is not None:
                logger.warning(f"重複画像を検出 (pHash): 既存ID={existing_id}, Path={image_path}")
                # 重複画像の場合、既存の512px画像があるかチェックし、なければ生成
                try:
                    existing_512px = self.check_processed_image_exists(existing_id, 512)
                    if not existing_512px:
                        logger.info(
                            f"重複画像に512px画像が存在しないため、生成を試行します: ID={existing_id}"
                        )
                        # 既存のメタデータを取得
                        existing_metadata = self.repository.get_image_metadata(existing_id)
                        if existing_metadata:
                            stored_path = Path(existing_metadata["stored_image_path"])
                            self._generate_thumbnail_512px(existing_id, stored_path, existing_metadata, fsm)
                    else:
                        logger.debug(f"重複画像に512px画像が既に存在します: ID={existing_id}")
                except Exception as e:
                    logger.warning(
                        f"重複画像の512px生成チェック中にエラー (処理続行): ID={existing_id}, Error: {e}"
                    )

                # 重複した場合、既存のメタデータを取得して返す
                existing_metadata = self.repository.get_image_metadata(existing_id)
                if existing_metadata is None:
                    logger.warning(f"既存画像のメタデータが取得できませんでした: ID={existing_id}")
                    existing_metadata = {}

                logger.debug(f"重複画像のメタデータを返します: ID={existing_id}")
                return existing_id, existing_metadata

            # 4. 画像をストレージに保存
            db_stored_original_path = fsm.save_original_image(image_path)
            if not db_stored_original_path:
                logger.error(f"オリジナル画像のストレージ保存に失敗: {image_path}")
                return None

            # 5. メタデータに情報を追加
            image_uuid = str(uuid.uuid4())
            original_metadata.update(
                {
                    "uuid": image_uuid,
                    "phash": phash,
                    "original_image_path": str(image_path),
                    "stored_image_path": str(db_stored_original_path),
                }
            )

            # 6. データベースに挿入
            image_id = self.repository.add_original_image(original_metadata)
            logger.info(f"オリジナル画像を登録しました: ID={image_id}, Path={image_path}")

            # 7. 512px サムネイル画像の自動生成
            try:
                self._generate_thumbnail_512px(image_id, db_stored_original_path, original_metadata, fsm)
            except Exception as e:
                logger.warning(
                    f"512px サムネイル生成に失敗しましたが、処理を続行します: {image_path}, Error: {e}"
                )
                # サムネイル生成の失敗はオリジナル画像登録の成功を妨げない

            return image_id, original_metadata

        except Exception as e:
            logger.error(
                f"オリジナル画像の登録処理全体でエラーが発生しました: {image_path}, Error: {e}",
                exc_info=True,
            )
            return None

    def _generate_thumbnail_512px(
        self, image_id: int, original_path: Path, original_metadata: dict[str, Any], fsm: FileSystemManager
    ) -> None:
        """
        512px サムネイル画像を生成し、データベースに登録します。

        Args:
            image_id (int): 元画像のID
            original_path (Path): 保存されたオリジナル画像のパス
            original_metadata (dict[str, Any]): 元画像のメタデータ
            fsm (FileSystemManager): ファイルシステムマネージャー
        """

        # 元画像サイズを確認（アップスケール対応のため512px以下もスキップしない）
        original_width = original_metadata.get("width", 0)
        original_height = original_metadata.get("height", 0)
        logger.debug(f"512px画像生成開始: ID={image_id}, 元サイズ={original_width}x{original_height}")

        try:
            # ImageProcessingManager を使用して512px解像度で処理（アップスケール対応）
            from ..editor.image_processor import ImageProcessingManager

            target_resolution = 512
            preferred_resolutions = [(512, 512)]  # 基本的な512x512解像度

            # 一時的なImageProcessingManagerを作成（ConfigurationService注入対応）
            ipm = ImageProcessingManager(fsm, target_resolution, preferred_resolutions, self.config_service)

            # アップスケーラー設定を取得（設定サービスから）
            image_processing_config = self.config_service.get_image_processing_config()
            upscaler = image_processing_config.get("upscaler", "RealESRGAN_x4plus")

            # 画像処理を実行（アップスケール情報付き）
            has_alpha = original_metadata.get("has_alpha", False)
            mode = original_metadata.get("mode", "RGB")
            processed_image, processing_metadata = ipm.process_image(
                original_path, has_alpha, mode, upscaler=upscaler
            )

            if processed_image:
                # 512px画像を保存
                processed_path = fsm.save_processed_image(processed_image, original_path, target_resolution)

                # 処理済み画像のメタデータを取得
                processed_metadata = fsm.get_image_info(processed_path)

                # アップスケール情報をメタデータに追加
                if processing_metadata.get("was_upscaled", False):
                    processed_metadata["upscaler_used"] = processing_metadata.get("upscaler_used")
                    logger.info(
                        f"512px生成時にアップスケールを実行: {processing_metadata.get('upscaler_used')}"
                    )

                # データベースに512px画像を登録
                processed_id = self.register_processed_image(image_id, processed_path, processed_metadata)

                if processed_id:
                    logger.info(
                        f"512px サムネイル画像を生成・登録しました: 元画像ID={image_id}, 処理済みID={processed_id}, Path={processed_path.name}"
                    )
                else:
                    logger.warning(
                        f"512px サムネイル画像の生成は成功しましたが、DB登録に失敗しました: 元画像ID={image_id}"
                    )
            else:
                logger.warning(f"512px画像の処理が失敗しました: 元画像ID={image_id}")
                raise RuntimeError(f"ImageProcessingManager returned None for image ID: {image_id}")

        except Exception as e:
            logger.error(
                f"512px サムネイル生成中にエラーが発生しました: 元画像ID={image_id}, Error: {e}",
                exc_info=True,
            )
            raise

    def register_processed_image(
        self, image_id: int, processed_path: Path, info: dict[str, Any]
    ) -> int | None:
        """
        処理済み画像を保存し、メタデータをデータベースに登録します。

        Args:
            image_id (int): 元画像のID。
            processed_path (Path): 処理済み画像の保存パス。
            info (dict[str, Any]): 処理済み画像のメタデータ (width, height などを含む)。

        Returns:
            int | None: 保存された処理済み画像のID。重複時も既存IDを返す。失敗時は None。
        """
        try:
            # ファイルシステムの保存は呼び出し元で行う想定(パスを渡すため)
            # fsm.save_processed_image(processed_path, ...)

            # メタデータに必須情報とパスを追加
            required_keys = ["width", "height", "has_alpha"]  # Repositoryでチェックされるが念のため
            if not all(key in info for key in required_keys):
                missing = [k for k in required_keys if k not in info]
                logger.error(f"処理済み画像の必須メタデータが不足: {missing}")
                return None

            info.update(
                {
                    "image_id": image_id,
                    "stored_image_path": str(processed_path),  # Path を文字列に
                }
            )

            # データベースに挿入 (Repository が重複チェックを行う)
            processed_image_id = self.repository.add_processed_image(info)
            if processed_image_id is not None:
                logger.info(
                    f"処理済み画像を登録/確認しました: ID={processed_image_id}, 元画像ID={image_id}"
                )
            # None が返るケースは Repository のエラーログで記録されるはず
            return processed_image_id

        except Exception as e:
            logger.error(
                f"処理済み画像の登録中にエラーが発生しました: 元画像ID={image_id}, Error: {e}",
                exc_info=True,
            )
            return None

    def save_tags(self, image_id: int, tags_data: list[TagAnnotationData]) -> None:
        """指定された画像のタグ情報を保存・更新します。"""
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": tags_data,
                "captions": [],
                "scores": [],
                "ratings": [],
            }
            self.repository.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のタグ {len(tags_data)} 件を保存しました。")
        except Exception as e:
            logger.error(f"画像 ID {image_id} のタグ保存中にエラー: {e}", exc_info=True)
            raise

    def save_captions(self, image_id: int, captions_data: list[CaptionAnnotationData]) -> None:
        """指定された画像のキャプション情報を保存・更新します。"""
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": captions_data,
                "scores": [],
                "ratings": [],
            }
            self.repository.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のキャプション {len(captions_data)} 件を保存しました。")
        except Exception as e:
            logger.error(f"画像 ID {image_id} のキャプション保存中にエラー: {e}", exc_info=True)
            raise

    def save_scores(self, image_id: int, scores_data: list[ScoreAnnotationData]) -> None:
        """指定された画像のスコア情報を保存・更新します。"""
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": [],
                "scores": scores_data,
                "ratings": [],
            }
            self.repository.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のスコア {len(scores_data)} 件を保存しました。")
        except Exception as e:
            logger.error(f"画像 ID {image_id} のスコア保存中にエラー: {e}", exc_info=True)
            raise

    def save_ratings(self, image_id: int, ratings_data: list[RatingAnnotationData]) -> None:
        """指定された画像のレーティング情報を保存・更新します。"""
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": [],
                "scores": [],
                "ratings": ratings_data,
            }
            self.repository.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のレーティング {len(ratings_data)} 件を保存しました。")
        except Exception as e:
            logger.error(f"画像 ID {image_id} のレーティング保存中にエラー: {e}", exc_info=True)
            raise

    def register_prompt_tags(self, image_id: int, tags: list[str]) -> None:
        """プロンプトなど、元ファイル由来のタグを登録します。"""
        if not tags:
            return
        tags_data: list[TagAnnotationData] = [
            {
                "tag": tag,
                "model_id": None,
                "confidence_score": None,
                "existing": True,
                "is_edited_manually": False,
                "tag_id": None,
            }
            for tag in tags
        ]
        try:
            self.save_tags(image_id, tags_data)
            logger.info(f"画像 ID {image_id} のプロンプトタグ {len(tags)} 件を登録しました。")
        except Exception as e:
            # save_tags 内でログが出るのでここでは再ログしないか、レベルを変える
            logger.warning(f"画像 ID {image_id} のプロンプトタグ登録に失敗: {e}")
            # raise はしない(上位処理を止めない場合)

    # 旧 save_score を save_scores を使うように変更
    def save_score(self, image_id: int, score_dict: dict[str, Any]) -> None:
        """単一のスコア情報を保存します (下位互換性のため)。"""
        score_float = score_dict.get("score")
        model_id = score_dict.get("model_id")
        if score_float is None or model_id is None:
            logger.error(f"スコア情報が不正です: {score_dict}")
            return

        score_data: ScoreAnnotationData = {
            "score": score_float,
            "model_id": model_id,
            "is_edited_manually": False,
        }
        try:
            self.save_scores(image_id, [score_data])
            # logger info は save_scores 内で出力される
        except Exception as e:
            logger.warning(f"画像 ID {image_id} のスコア保存に失敗: {e}")

    def get_low_res_image_path(self, image_id: int) -> str | None:
        """
        指定されたIDで最も解像度が低い処理済み画像のパスを取得します。

        Args:
            image_id (int): 取得する元画像のID。

        Returns:
            str | None: 最も解像度が低い処理済み画像のパス。見つからない場合はNone。
        """
        try:
            # resolution=0 で最低解像度を取得
            metadata = self.repository.get_processed_image(image_id, resolution=0, all_data=False)
            if isinstance(metadata, dict):  # None でなく dict であることを確認
                path = metadata.get("stored_image_path")
                if path:
                    logger.debug(f"画像ID {image_id} の低解像度画像パスを取得しました。")
                    return path  # type: ignore[no-any-return]
                else:
                    logger.warning(
                        f"画像ID {image_id} の低解像度画像のパスが見つかりません。 Metadata: {metadata}"
                    )
            else:
                logger.warning(f"画像ID {image_id} の低解像度画像メタデータが見つかりません。")
            return None
        except Exception as e:
            logger.error(f"低解像度画像のパス取得中にエラーが発生しました: {e}", exc_info=True)
            return None

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """
        指定されたIDのオリジナル画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            dict[str, Any] | None: 画像メタデータを含む辞書。画像が見つからない場合はNone。
        """
        try:
            metadata = self.repository.get_image_metadata(image_id)
            if metadata is None:
                logger.info(f"ID {image_id} の画像メタデータが見つかりません。")
            return metadata
        except Exception as e:
            logger.error(f"画像メタデータ取得中にエラーが発生しました: {e}", exc_info=True)
            raise  # Repositoryでエラーが発生したら上に伝える

    def get_processed_metadata(self, image_id: int) -> list[dict[str, Any]] | None:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            image_id (int): 元画像のID。

        Returns:
            list[dict[str, Any]] | None: 処理済み画像のメタデータのリスト。見つからない場合は空リスト。
        """
        try:
            # all_data=True でリストが返る
            metadata_list = self.repository.get_processed_image(image_id, all_data=True)
            if isinstance(metadata_list, list):
                if not metadata_list:
                    logger.info(f"ID {image_id} の元画像に関連する処理済み画像が見つかりません。")
                return metadata_list
            else:
                # Repository が予期せず None や dict を返した場合 (通常はないはず)
                logger.error(
                    f"get_processed_image(all_data=True) がリストを返しませんでした: {type(metadata_list)}"
                )
                return []
        except Exception as e:
            logger.error(f"処理済み画像メタデータ取得中にエラーが発生しました: {e}", exc_info=True)
            raise

    def get_image_annotations(self, image_id: int) -> dict[str, list[dict[str, Any]]]:
        """指定された画像のアノテーション(タグ、キャプション、スコア、レーティング)を取得します。"""
        try:
            return self.repository.get_image_annotations(image_id)
        except Exception as e:
            logger.error(f"画像ID {image_id} のアノテーション取得中にエラー: {e}", exc_info=True)
            return {"tags": [], "captions": [], "scores": [], "ratings": []}

    def get_models(self) -> list[dict[str, Any]]:
        """データベースに登録されている全てのモデル情報を取得します。"""
        try:
            return self.repository.get_models()
        except Exception as e:
            logger.error(f"全モデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_tagger_models(self) -> list[dict[str, Any]]:
        """Taggerタイプのモデル情報を取得します。"""
        try:
            return self.repository.get_models_by_type("tagger")
        except Exception as e:
            logger.error(f"Taggerモデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_score_models(self) -> list[dict[str, Any]]:
        """Scoreタイプのモデル情報を取得します。"""
        try:
            return self.repository.get_models_by_type("score")
        except Exception as e:
            logger.error(f"Scoreモデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_captioner_models(self) -> list[dict[str, Any]]:
        """Captionerタイプのモデル情報を取得します。"""
        try:
            return self.repository.get_models_by_type("captioner")
        except Exception as e:
            logger.error(f"Captionerモデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_upscaler_models(self) -> list[dict[str, Any]]:
        """Upscalerタイプのモデル情報を取得します。"""
        try:
            return self.repository.get_models_by_type("upscaler")
        except Exception as e:
            logger.error(f"Upscalerモデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_llm_models(self) -> list[dict[str, Any]]:
        """LLMタイプのモデル情報を取得します。"""
        try:
            return self.repository.get_models_by_type("llm")
        except Exception as e:
            logger.error(f"LLMモデル情報の取得中にエラー: {e}", exc_info=True)
            return []

    def get_manual_edit_model_id(self) -> int:
        """
        手動編集用のモデルIDを取得します（キャッシュ機能付き）。

        MANUAL_EDITという名前のモデルが存在しない場合は新規作成します。
        初回呼び出し時にのみデータベースアクセスを行い、2回目以降はキャッシュされた値を返します。

        Returns:
            int: MANUAL_EDITモデルのID

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合
        """
        if not hasattr(self, "_manual_edit_model_id"):
            with self.repository.session_factory() as session:
                self._manual_edit_model_id = self.repository._get_or_create_manual_edit_model(
                    session
                )
                session.commit()
            logger.debug(f"MANUAL_EDITモデルIDをキャッシュ: {self._manual_edit_model_id}")
        return self._manual_edit_model_id

    def get_images_by_filter(
        self,
        tags: list[str] | None = None,
        caption: str | None = None,
        resolution: int = 0,
        use_and: bool = True,
        start_date: str | None = None,
        end_date: str | None = None,
        include_untagged: bool = False,
        include_nsfw: bool = False,
        include_unrated: bool = True,
        manual_rating_filter: str | None = None,
        ai_rating_filter: str | None = None,
        manual_edit_filter: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        指定された条件に基づいて画像をフィルタリングし、メタデータと件数を返します。

        Args:
            tags: 検索するタグのリスト
            caption: 検索するキャプション文字列
            resolution: 検索対象の解像度(長辺)、0の場合はオリジナル画像
            use_and: 複数タグ指定時の検索方法 (True: AND, False: OR)
            start_date: 検索開始日時 (ISO 8601形式)
            end_date: 検索終了日時 (ISO 8601形式)
            include_untagged: タグが付いていない画像のみを対象とするか
            include_nsfw: NSFWコンテンツを含む画像を除外しないか
            include_unrated: 未評価画像を含めるか (False: 手動またはAI評価のいずれか1つ以上を持つ画像のみ)
            manual_rating_filter: 指定した手動レーティングを持つ画像のみを対象とするか
            ai_rating_filter: 指定したAI評価レーティングを持つ画像のみを対象とするか (多数決ロジック)
            manual_edit_filter: アノテーションが手動編集されたかでフィルタするか

        Returns:
            tuple: (画像メタデータのリスト, 総数)
        """
        try:
            # 引数をそのままリポジトリに渡す
            return self.repository.get_images_by_filter(
                tags=tags,
                caption=caption,
                resolution=resolution,
                use_and=use_and,
                start_date=start_date,
                end_date=end_date,
                include_untagged=include_untagged,
                include_nsfw=include_nsfw,
                include_unrated=include_unrated,
                manual_rating_filter=manual_rating_filter,
                ai_rating_filter=ai_rating_filter,
                manual_edit_filter=manual_edit_filter,
            )
        except Exception as e:
            logger.error(f"画像フィルタリング検索中にエラーが発生しました: {e}", exc_info=True)
            raise

    def detect_duplicate_image(self, image_path: Path) -> int | None:
        """
        画像の重複を検出し、重複する場合はその画像のIDを返す。
        pHashベースの視覚的重複検出を使用します。

        Args:
            image_path (Path): 検査する画像ファイルのパス

        Returns:
            int | None: 重複する画像が見つかった場合はそのimage_id、見つからない場合はNone
        """
        image_name = image_path.name

        try:
            # pHash で視覚的重複検出
            try:
                phash = calculate_phash(image_path)
            except Exception as e:
                logger.error(f"重複検出のための pHash 計算中にエラー: {image_path}, Error: {e}")
                return None  # pHash 計算失敗時は重複なしとして扱う

            image_id = self.repository.find_duplicate_image_by_phash(phash)
            if image_id is not None:
                logger.info(f"重複検出: pHash 一致 ID={image_id}, Name={image_name}, pHash={phash}")
            else:
                logger.debug(f"重複なし: Name={image_name}, pHash={phash}")
            return image_id

        except Exception as e:
            logger.error(
                f"重複画像検出プロセス中にエラーが発生しました: {image_path}, Error: {e}", exc_info=True
            )
            return None

    def get_total_image_count(self) -> int:
        """データベース内に登録されたオリジナル画像の総数を取得します。"""
        try:
            count = self.repository.get_total_image_count()
            return count
        except Exception as e:
            logger.error(f"総画像数の取得中にエラーが発生しました: {e}", exc_info=True)
            return 0  # エラー時は0を返す

    def get_image_ids_from_directory(self, directory_path: Path) -> list[int]:
        """
        指定されたディレクトリに含まれる画像のIDリストを取得します。

        Args:
            directory_path (Path): 検索対象のディレクトリパス

        Returns:
            list[int]: 該当する画像のIDリスト
        """
        try:
            # ディレクトリ内の画像ファイルを取得
            if not self.fsm:
                from ..storage.file_system import FileSystemManager

                temp_fsm = FileSystemManager()
                image_files = temp_fsm.get_image_files(directory_path)
            else:
                image_files = self.fsm.get_image_files(directory_path)
            image_ids = []

            for image_file in image_files:
                # pHashで重複検出（既存画像のID取得）
                image_id = self.detect_duplicate_image(image_file)
                if image_id:
                    image_ids.append(image_id)

            logger.info(f"ディレクトリ {directory_path} から {len(image_ids)} 件の画像IDを取得しました")
            return image_ids

        except Exception as e:
            logger.error(
                f"ディレクトリからの画像ID取得中にエラー: {directory_path}, Error: {e}", exc_info=True
            )
            return []

    def get_dataset_status(self) -> dict[str, Any]:
        """
        データセット状態の取得（軽量な読み取り操作）

        Returns:
            dict: データセット状態情報 {"total_images": int, "status": str}
        """
        try:
            total_count = self.get_total_image_count()
            return {"total_images": total_count, "status": "ready" if total_count > 0 else "empty"}
        except Exception as e:
            logger.error(f"データセット状態取得エラー: {e}")
            return {"total_images": 0, "status": "error"}

    def get_annotation_status_counts(self) -> dict[str, int | float]:
        """
        アノテーション状態カウントを取得

        Returns:
            dict: アノテーション状態統計 {"total": int, "completed": int, "error": int, "completion_rate": float}
        """
        try:
            # 総画像数取得
            total_images = self.get_total_image_count()

            if total_images == 0:
                return {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}

            # 完了画像数取得 (タグまたはキャプションが存在)
            session: Session = self.repository.get_session()
            with session:
                completed_query = text("""
                    SELECT COUNT(DISTINCT i.id) FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                """)
                result: Result[Any] = session.execute(completed_query)
                completed_images: int = result.scalar() or 0

                # エラー画像数取得 (未解決のアノテーションエラーのみ)
                error_images = self.repository.get_error_count_unresolved(operation_type="annotation")

                completion_rate = (completed_images / total_images) * 100.0 if total_images > 0 else 0.0

                return {
                    "total": total_images,
                    "completed": completed_images,
                    "error": error_images,
                    "completion_rate": completion_rate,
                }

        except Exception as e:
            logger.error(f"アノテーション状態カウント取得エラー: {e}", exc_info=True)
            return {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}

    def filter_by_annotation_status(
        self, completed: bool = False, error: bool = False
    ) -> list[dict[str, Any]]:
        """
        アノテーション状態でフィルタリング

        Args:
            completed: 完了画像のみ
            error: エラー画像のみ

        Returns:
            list: フィルター後の画像リスト
        """
        try:
            session: Session = self.repository.get_session()

            with session:
                if completed:
                    # 完了画像（タグまたはキャプション有り）
                    query = text("""
                        SELECT DISTINCT i.* FROM images i
                        LEFT JOIN tags t ON i.id = t.image_id
                        LEFT JOIN captions c ON i.id = c.image_id
                        WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                    """)
                elif error:
                    # エラー画像（未解決のアノテーションエラーのみ）
                    error_image_ids = self.repository.get_error_image_ids(
                        operation_type="annotation", resolved=False
                    )
                    if not error_image_ids:
                        return []
                    return self.repository.get_images_by_ids(error_image_ids)
                else:
                    # 全ての画像
                    query = text("SELECT * FROM images")

                result: Result[Any] = session.execute(query)
                return [dict(row._mapping) for row in result.fetchall()]

        except Exception as e:
            logger.error(f"アノテーション状態フィルタリングエラー: {e}", exc_info=True)
            return []

    def get_directory_images_metadata(self, directory_path: Path) -> list[dict[str, Any]]:
        """
        ディレクトリ内画像のメタデータ取得（軽量な読み取り操作）

        Args:
            directory_path: 検索対象ディレクトリのパス

        Returns:
            list: ディレクトリ内の画像メタデータリスト
        """
        try:
            image_ids = self.get_image_ids_from_directory(directory_path)
            if not image_ids:
                return []

            # 画像IDリストからメタデータを取得
            images = []
            for image_id in image_ids:
                metadata = self.get_image_metadata(image_id)
                if metadata:
                    images.append(metadata)

            logger.info(
                f"ディレクトリ {directory_path} から {len(images)} 件の画像メタデータを取得しました"
            )
            return images

        except Exception as e:
            logger.error(f"ディレクトリ画像メタデータ取得エラー: {directory_path}, {e}", exc_info=True)
            return []

    def check_processed_image_exists(self, image_id: int, target_resolution: int) -> dict[str, Any] | None:
        """
        指定された画像IDと目標解像度に一致する処理済み画像が存在するかチェックします。

        Args:
            image_id (int): 元画像のID
            target_resolution (int): 目標解像度

        Returns:
            dict[str, Any] | None: 処理済み画像が存在する場合はそのメタデータ、存在しない場合はNone
        """
        try:
            # get_processed_image は resolution=0 以外の場合、dict | None を返す
            processed_image_metadata = self.repository.get_processed_image(
                image_id, resolution=target_resolution, all_data=False
            )

            if isinstance(processed_image_metadata, dict):
                logger.debug(
                    f"解像度 {target_resolution} の処理済み画像が既に存在します: 元画像ID={image_id}, 処理済ID={processed_image_metadata.get('id')}"
                )
                return processed_image_metadata
            else:
                logger.info(
                    f"解像度 {target_resolution} に一致する処理済み画像は見つかりませんでした: 元画像ID={image_id}"
                )
                return None
        except Exception as e:
            logger.error(
                f"処理済み画像の存在チェック中にエラーが発生しました: 元画像ID={image_id}, 解像度={target_resolution}, Error: {e}",
                exc_info=True,
            )
            return None

    def filter_recent_annotations(
        self, annotations: dict[str, list[dict[str, Any]]], minutes_threshold: int = 5
    ) -> dict[str, list[dict[str, Any]]]:
        """
        与えられたアノテーションデータから、指定時間内に更新されたものだけをフィルタリングします。
        'updated_at' フィールドが存在しないアノテーションは無視されます。

        Args:
            annotations (dict): 'tags', 'captions', 'scores', 'ratings' キーを持つアノテーション辞書。
                                各値はアノテーション情報の辞書のリスト。
            minutes_threshold (int): 最新の更新時刻から遡る時間(分)。デフォルトは5分。

        Returns:
            dict: フィルタリングされたアノテーション辞書。
        """
        filtered_annotations: dict[str, list[dict[str, Any]]] = {
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }  # 型ヒントを追加

        # 1. 全アノテーションから最新の更新日時を見つける
        all_updates = []
        for key in annotations:
            for item in annotations[key]:
                if isinstance(item, dict) and "updated_at" in item:
                    # SQLAlchemy は datetime オブジェクトを返すはず
                    update_time = item["updated_at"]
                    if isinstance(update_time, datetime):
                        all_updates.append(update_time)
                    elif isinstance(update_time, str):  # 文字列の場合も考慮 (念のため)
                        try:
                            dt = datetime.fromisoformat(
                                update_time.replace("Z", "+00:00")
                            )  # ISO形式をパース
                            all_updates.append(dt)
                        except ValueError:
                            logger.warning(f"不正な updated_at 文字列: {update_time}")

        if not all_updates:
            logger.info(
                "アノテーションに有効な更新日時が見つかりませんでした。フィルタリングをスキップします。"
            )
            return filtered_annotations  # または元の annotations を返すか

        latest_update_dt = max(all_updates)
        # タイムゾーン対応: aware datetime 同士で比較
        if latest_update_dt.tzinfo is None:
            # naive datetime の場合、UTC とみなすかローカルタイムとみなすか要検討
            # ここでは UTC と仮定 (DB保存時に timezone=True を想定)
            latest_update_dt = latest_update_dt.replace(tzinfo=UTC)
            logger.warning("naive な updated_at を UTC として扱います。")

        time_threshold = latest_update_dt - timedelta(minutes=minutes_threshold)
        logger.debug(f"最新更新日時: {latest_update_dt}, 閾値: {time_threshold}")

        # 2. 閾値でフィルタリング
        for key in annotations:
            for item in annotations[key]:
                if isinstance(item, dict) and "updated_at" in item:
                    update_time = item["updated_at"]
                    item_dt: datetime | None = None
                    if isinstance(update_time, datetime):
                        item_dt = update_time
                    elif isinstance(update_time, str):
                        try:
                            item_dt = datetime.fromisoformat(update_time.replace("Z", "+00:00"))
                        except ValueError:
                            continue  # 不正な形式はスキップ

                    if item_dt:
                        # タイムゾーンを合わせる
                        if item_dt.tzinfo is None:
                            item_dt = item_dt.replace(tzinfo=UTC)  # UTC と仮定

                        if item_dt >= time_threshold:
                            filtered_annotations[key].append(item)

        logger.info(f"最近更新されたアノテーションをフィルタリングしました (閾値: {minutes_threshold}分)。")
        return filtered_annotations

    def check_image_has_annotation(self, image_id: int) -> bool:
        """
        画像にアノテーション（タグまたはキャプション）が存在するかチェック

        Args:
            image_id: 画像ID

        Returns:
            bool: アノテーションが存在するかどうか
        """
        try:
            session = self.repository.get_session()
            with session:
                # タグまたはキャプションの存在確認
                query = """
                    SELECT 1 FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE i.id = :image_id AND (t.id IS NOT NULL OR c.id IS NOT NULL)
                    LIMIT 1
                """
                result = session.execute(text(query), {"image_id": image_id})
                has_annotation = result.scalar() is not None

                logger.debug(
                    f"アノテーション存在確認: image_id={image_id}, has_annotation={has_annotation}"
                )
                return has_annotation

        except Exception as e:
            logger.error(f"アノテーション存在確認エラー: image_id={image_id}, error={e}", exc_info=True)
            return False

    def execute_filtered_search(self, conditions: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        """
        フィルタリング検索実行（データ層の適切な責任）

        検索条件に基づいてデータベース検索を実行し、結果を返します。

        Args:
            conditions: 検索条件辞書

        Returns:
            tuple: (検索結果リスト, 総件数)
        """
        try:
            # 既存のget_images_by_filterメソッドを活用
            images, total_count = self.get_images_by_filter(**conditions)

            logger.info(f"フィルタリング検索実行完了: 条件={len(conditions)}項目, 結果={len(images)}件")
            return images, total_count

        except Exception as e:
            logger.error(f"フィルタリング検索実行エラー: {e}", exc_info=True)
            return [], 0

    def save_error_record(
        self,
        operation_type: str,
        error_type: str,
        error_message: str,
        image_id: int | None = None,
        stack_trace: str | None = None,
        file_path: str | None = None,
        model_name: str | None = None,
    ) -> int:
        """
        エラーレコードを保存（Manager層Facade）

        Worker層から呼び出されるFacadeメソッド。
        二次エラー（エラー保存中のエラー）を防ぐため、try-exceptで保護されています。

        Args:
            operation_type: 操作種別 ("registration" | "annotation" | "processing")
            error_type: エラー種別（例: "FileNotFoundError", "APIError"）
            error_message: エラーメッセージ
            image_id: 画像ID (Optional)
            stack_trace: スタックトレース (Optional)
            file_path: ファイルパス (Optional)
            model_name: モデル名 (Optional)

        Returns:
            int: 作成された error_record_id（二次エラー時は -1）
        """
        try:
            error_id = self.repository.save_error_record(
                operation_type=operation_type,
                error_type=error_type,
                error_message=error_message,
                image_id=image_id,
                stack_trace=stack_trace,
                file_path=file_path,
                model_name=model_name,
            )
            logger.debug(
                f"エラーレコード保存完了: error_id={error_id}, "
                f"operation_type={operation_type}, error_type={error_type}"
            )
            return error_id

        except Exception as e:
            # 二次エラーは致命的ではないので、ログだけ出力して処理続行
            logger.error(f"エラーレコード保存中にエラー（二次エラー）: {e}", exc_info=True)
            return -1

    def get_image_id_by_filepath(self, filepath: str) -> int | None:
        """
        ファイルパスから画像IDを取得（Manager層Facade）

        Args:
            filepath: 画像ファイルパス

        Returns:
            int | None: 画像ID（見つからない場合は None）
        """
        try:
            return self.repository.get_image_id_by_filepath(filepath)
        except Exception as e:
            logger.error(f"ファイルパスからの画像ID取得エラー: {e}", exc_info=True)
            return None


# --- 初期化チェック ---
# try:
#     # 設定ファイル等からDBディレクトリパスを取得する想定
#     # db_dir = Path("path/to/your/database/directory")
#     manager = ImageDatabaseManager()
#     print("ImageDatabaseManager initialized successfully.")
# except Exception as e:
#     print(f"Failed to initialize ImageDatabaseManager: {e}")
#     traceback.print_exc()
