"""DBリポジトリ"""

import datetime
from typing import Any, TypedDict, cast

from sqlalchemy import Select, and_, exists, func, not_, or_, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from ..utils.log import logger
from .db_core import DefaultSessionLocal, get_tag_db_path
from .schema import Caption, Image, Model, ModelType, ProcessedImage, Rating, Score, Tag


# --- データ構造の型定義 (例) ---
# 呼び出し側はこの構造に合わせてデータを用意する想定
class TagAnnotationData(TypedDict):
    tag: str
    model_id: int | None
    confidence_score: float | None
    existing: bool
    is_edited_manually: bool | None
    tag_id: int | None


class CaptionAnnotationData(TypedDict):
    caption: str
    model_id: int | None
    existing: bool
    is_edited_manually: bool | None


class ScoreAnnotationData(TypedDict):
    score: float
    model_id: int
    is_edited_manually: bool


class RatingAnnotationData(TypedDict):
    raw_rating_value: str
    normalized_rating: str
    model_id: int  # Rating must have a model
    confidence_score: float | None


class AnnotationsDict(TypedDict):
    tags: list[TagAnnotationData]
    captions: list[CaptionAnnotationData]
    scores: list[ScoreAnnotationData]
    ratings: list[RatingAnnotationData]


class ImageRepository:
    """
    画像関連エンティティのデータベース永続化を担当するクラス (SQLAlchemyベース)。
    CRUD操作と基本的な検索機能を提供します。
    """

    def __init__(self, session_factory: sessionmaker[Session] = DefaultSessionLocal):
        """
        ImageRepositoryのコンストラクタ。

        Args:
            session_factory (Callable[[], Session]): SQLAlchemyセッションを生成するファクトリ関数。
                                                    デフォルトはdb_core.SessionLocalを使用。
                                                    テスト時にモック化可能。
        """
        self.session_factory = session_factory
        logger.info("ImageRepository initialized.")
        self.tag_db_path = get_tag_db_path()

    def _get_model_id(self, model_name: str) -> int | None:
        """
        モデル名からモデルIDを取得します。

        Args:
            model_name (str): 検索するモデル名。

        Returns:
            int | None: 見つかったモデルのID。見つからない場合はNone。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Model.id).where(Model.name == model_name)
                result = session.execute(stmt).scalar_one_or_none()
                if result is None:
                    logger.warning(f"モデル名 '{model_name}' がデータベースに見つかりません。")
                return cast(int | None, result)
            except SQLAlchemyError as e:
                logger.error(f"モデルIDの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def _image_exists(self, image_id: int) -> bool:
        """
        指定された画像IDが images テーブルに存在するかを確認します。

        Args:
            image_id (int): 確認する画像のID。

        Returns:
            bool: 画像が存在する場合はTrue、存在しない場合はFalse。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Image.id).where(Image.id == image_id)
                # exists() など、より効率的な方法も検討できるが、まずはシンプルに
                result = session.execute(stmt).scalar_one_or_none()
                return result is not None
            except SQLAlchemyError as e:
                logger.error(
                    f"画像存在チェック中にエラーが発生しました (ID: {image_id}): {e}", exc_info=True
                )
                raise

    def find_duplicate_image_by_phash(self, phash: str) -> int | None:
        """
        指定されたpHashに一致する画像をデータベースから検索し、Image IDを返します。
        pHashはNULL不可のため、完全一致で検索します。

        Args:
            phash (str): 検索するpHash。

        Returns:
            int | None: 重複する画像のID。見つからない場合はNone。
        """
        if not phash:  # pHashが空文字列やNoneの場合は検索しない
            return None
        with self.session_factory() as session:
            try:
                # ID を返す必要があるので、ID を SELECT するように修正
                stmt_id = select(Image.id).where(Image.phash == phash).limit(1)
                image_id = session.execute(stmt_id).scalar_one_or_none()
                if image_id:
                    logger.info(f"pHashによる重複画像が見つかりました: ID {image_id}, pHash {phash}")
                return image_id
            except SQLAlchemyError as e:
                logger.error(f"pHashによる重複画像の検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    def add_original_image(self, info: dict[str, Any]) -> int:
        """
        オリジナル画像のメタデータを images テーブルに追加します。
        pHashによる重複チェックを行い、重複がある場合は既存IDを返します。
        pHash計算失敗時は例外を送出します。

        Args:
            info (dict[str, Any]): 画像情報を含む辞書。
                                   `calculate_phash` が成功した前提で `phash` キーも含まれる想定。
                                   以下のキーが必須: uuid, phash, original_image_path,
                                   stored_image_path, width, height, format, extension。
                                   その他は Optional。

        Returns:
            int: 挿入された画像のID、または重複していた既存画像のID。

        Raises:
            ValueError: 必須情報が不足している場合、またはpHash計算済みでない場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        required_keys = {
            "uuid",
            "phash",
            "original_image_path",
            "stored_image_path",
            "width",
            "height",
            "format",
            "extension",
        }
        if not required_keys.issubset(info.keys()):
            missing_keys = required_keys - info.keys()
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        phash = info["phash"]

        # pHashで重複チェック
        existing_id = self.find_duplicate_image_by_phash(phash)
        if existing_id is not None:
            logger.warning(f"pHashが一致する画像が既に存在します: ID {existing_id} (pHash: {phash})")
            return existing_id

        # 新しい Image オブジェクトを作成
        new_image = Image(
            uuid=info["uuid"],
            phash=phash,
            original_image_path=str(info["original_image_path"]),  # Pathオブジェクトを文字列に
            stored_image_path=str(info["stored_image_path"]),  # Pathオブジェクトを文字列に
            width=info["width"],
            height=info["height"],
            format=info["format"],
            mode=info.get("mode"),
            has_alpha=info.get("has_alpha"),
            filename=info.get("filename"),
            extension=info["extension"],
            color_space=info.get("color_space"),
            icc_profile=info.get("icc_profile"),
            manual_rating=info.get("manual_rating"),  # 初期値はNoneのはず
            # created_at, updated_at は server_default で設定される
        )

        with self.session_factory() as session:
            try:
                session.add(new_image)
                session.flush()  # ID を取得するために flush
                image_id = new_image.id
                session.commit()  # コミットは flush 後でもOK
                logger.info(f"オリジナル画像をDBに追加しました: ID={image_id}, UUID={new_image.uuid}")
                return image_id
            except IntegrityError as e:
                # uuid の UNIQUE 制約違反など
                session.rollback()
                logger.error(f"オリジナル画像の追加中に整合性エラーが発生しました: {e}", exc_info=True)
                # uuid重複の場合、既存IDを探して返すか、あるいは単にエラーとするか?
                # ここではエラーを再発生させる
                raise
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"オリジナル画像の追加中にデータベースエラーが発生しました: {e}", exc_info=True
                )
                raise

    def _find_existing_processed_image_id(
        self, image_id: int, width: int, height: int, filename: str | None
    ) -> int | None:
        """
        指定された条件に一致する既存の processed_image の ID を検索します。
        add_processed_image で IntegrityError が発生した場合に使用します。

        Args:
            image_id (int): 元画像の ID。
            width (int): 幅。
            height (int): 高さ。
            filename (Optional[str]): ファイル名。

        Returns:
            Optional[int]: 既存レコードの ID。見つからない場合は None。
        """
        with self.session_factory() as session:
            try:
                stmt = select(ProcessedImage.id).where(
                    ProcessedImage.image_id == image_id,
                    ProcessedImage.width == width,
                    ProcessedImage.height == height,
                    # filename が None の場合も考慮して比較
                    (ProcessedImage.filename == filename)
                    if filename is not None
                    else (ProcessedImage.filename.is_(None)),
                )
                existing_id = session.execute(stmt).scalar_one_or_none()
                return existing_id
            except SQLAlchemyError as e:
                logger.error(f"既存の処理済み画像ID検索中にエラー: {e}", exc_info=True)
                # この検索自体が失敗した場合は None を返すか、エラーを再発生させるか検討
                return None  # ここでは None を返す

    def add_processed_image(self, info: dict[str, Any]) -> int | None:
        """
        処理済み画像のメタデータを processed_images テーブルに追加します。
        重複する場合は既存の ID を返します。

        Args:
            info (dict[str, Any]): 処理済み画像情報を含む辞書。
                                   必須キー: image_id, stored_image_path, width, height, has_alpha。
                                   その他は Optional。

        Returns:
            int | None: 挿入された処理済み画像のID、または重複していた既存画像のID。
                        検索に失敗した場合は None を返す可能性あり。

        Raises:
            ValueError: 必須情報が不足している場合、または関連する Image が存在しない場合。
            SQLAlchemyError: 予期せぬデータベース操作でエラーが発生した場合 (IntegrityError 以外)。
        """
        required_keys = {"image_id", "stored_image_path", "width", "height", "has_alpha"}
        if not required_keys.issubset(info.keys()):
            missing_keys = required_keys - info.keys()
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        image_id = info["image_id"]
        width = info["width"]
        height = info["height"]
        filename = info.get("filename")  # filename は Optional

        # 関連する Image レコードが存在するか確認 (FK制約のため)
        if not self._image_exists(image_id):
            raise ValueError(f"関連するオリジナル画像が見つかりません: image_id={image_id}")

        # 新しい ProcessedImage オブジェクトを作成
        new_processed_image = ProcessedImage(
            image_id=image_id,
            stored_image_path=str(info["stored_image_path"]),  # Pathオブジェクトを文字列に
            width=width,
            height=height,
            mode=info.get("mode"),
            has_alpha=info["has_alpha"],
            filename=filename,
            color_space=info.get("color_space"),
            icc_profile=info.get("icc_profile"),
            upscaler_used=info.get("upscaler_used"),  # アップスケーラー情報を追加
            # created_at, updated_at は server_default で設定される
        )

        with self.session_factory() as session:
            try:
                session.add(new_processed_image)
                session.flush()  # ID を取得するために flush
                processed_image_id = new_processed_image.id
                session.commit()
                logger.info(f"処理済み画像をDBに追加しました: ID={processed_image_id}, 親画像ID={image_id}")
                return processed_image_id
            except IntegrityError:
                # UNIQUE 制約違反 (image_id, width, height, filename)
                session.rollback()
                logger.warning(
                    f"処理済み画像の追加中に整合性エラーが発生しました。"
                    f" (おそらく重複: image_id={image_id}, width={width}, height={height}, filename={filename})."
                    f" 既存のIDを検索します。"
                )
                # 既存のIDを検索して返す
                existing_id = self._find_existing_processed_image_id(image_id, width, height, filename)
                if existing_id:
                    logger.info(f"既存の処理済み画像IDが見つかりました: {existing_id}")
                else:
                    # 通常ここには来ないはずだが、もし検索でも見つからなければ警告
                    logger.error(
                        f"整合性エラー後、既存の処理済み画像が見つかりませんでした。"
                        f" 条件: image_id={image_id}, width={width}, height={height}, filename={filename}"
                    )
                return existing_id  # None の可能性もある
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"処理済み画像の追加中に予期せぬデータベースエラーが発生しました: {e}", exc_info=True
                )
                raise  # IntegrityError 以外の DB エラーは再発生させる

    # --- Annotation Saving Methods ---

    def save_annotations(self, image_id: int, annotations: AnnotationsDict) -> None:
        """
        指定された画像IDに対して、複数のアノテーションを一括で保存・更新します。
        各アノテーションタイプごとにUpsert処理を行います。

        Args:
            image_id (int): アノテーションを追加/更新する画像のID。
            annotations (AnnotationsDict): 保存するアノテーションデータを含む辞書。
                                           キー: 'tags', 'captions', 'scores', 'ratings'
                                           値: 各アノテーションデータのリスト。

        Raises:
            ValueError: 指定された image_id が存在しない場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定された画像ID {image_id} は存在しません。")

        with self.session_factory() as session:
            try:
                # 各アノテーションタイプを処理
                if annotations.get("tags"):
                    self._save_tags(session, image_id, annotations["tags"])
                if annotations.get("captions"):
                    self._save_captions(session, image_id, annotations["captions"])
                if annotations.get("scores"):
                    self._save_scores(session, image_id, annotations["scores"])
                if annotations.get("ratings"):
                    self._save_ratings(session, image_id, annotations["ratings"])

                session.commit()
                logger.info(f"画像ID {image_id} のアノテーションを保存・更新しました。")

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"画像ID {image_id} のアノテーション保存中にエラーが発生しました: {e}", exc_info=True
                )
                raise

    def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
        """
        アタッチされた tag_db から tag 文字列に一致する tag_id を検索して返します。

        注意: このメソッドは外部DBへの書き込み（新規タグ登録）は行いません。
              タグが見つからない場合は None を返します。
              新規タグ登録は genai-tag-db-tools を直接使用する上位のサービス等で行う想定です。

        Args:
            session (Session): SQLAlchemy セッション (Raw SQL 実行に使用)。
            tag_string (str): 検索するタグ文字列。

        Returns:
            int | None: 見つかったタグの tag_id。見つからない場合は None。

        Raises:
            SQLAlchemyError: データベース検索中にエラーが発生した場合。
        """

        logger.debug(f"Searching for tag_id in tag_db for tag: '{tag_string}'")
        try:
            # tag_db.TAGS テーブルを検索
            stmt = text("SELECT tag_id FROM tag_db.TAGS WHERE tag = :tag_name")
            result = session.execute(stmt, {"tag_name": tag_string}).scalar_one_or_none()

            if result:
                logger.debug(f"Found tag_id {result} for tag '{tag_string}' in tag_db.")
                return result
            else:
                # 見つからなかった場合 (新規作成はここでは行わない)
                logger.info(
                    f"Tag '{tag_string}' not found in tag_db. Returning None. (Registration should be handled elsewhere)"
                )
                return None

        except SQLAlchemyError as e:
            logger.error(f"Error searching tag_id in tag_db for tag '{tag_string}': {e}", exc_info=True)
            # エラー発生時も None を返す (呼び出し元で処理を継続できるように)
            # 必要であれば raise するように変更も可能
            return None

    def _save_tags(self, session: Session, image_id: int, tags_data: list[TagAnnotationData]) -> None:
        """タグ情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(tags_data)} tags for image_id {image_id}")

        # 既存のタグを image_id と tag 文字列で取得 (効率化のため)
        existing_tags_stmt = select(Tag).where(Tag.image_id == image_id)
        existing_tags_result = session.execute(existing_tags_stmt).scalars().all()
        # (tag_string, model_id) をキーとする辞書を作成
        existing_tags_map = {(t.tag, t.model_id): t for t in existing_tags_result}

        for tag_info in tags_data:
            tag_string = tag_info["tag"]
            model_id = tag_info.get("model_id")  # Optional
            confidence = tag_info.get("confidence_score")  # Optional
            is_existing_tag = tag_info.get("existing", False)  # 元ファイル由来か

            # 外部DBから tag_id を取得/作成 (TODO: 実際の連携処理に置き換える)
            external_tag_id = self._get_or_create_tag_id_external(session, tag_string)

            # 既存レコードを検索
            existing_record = existing_tags_map.get((tag_string, model_id))

            if existing_record:
                # 更新
                logger.debug(f"Updating existing tag: id={existing_record.id}, tag='{tag_string}'")
                existing_record.tag_id = external_tag_id
                existing_record.confidence_score = confidence
                existing_record.existing = is_existing_tag
                existing_record.is_edited_manually = tag_info.get("is_edited_manually")
            else:
                # 新規作成
                logger.debug(f"Adding new tag: tag='{tag_string}'")
                new_tag = Tag(
                    image_id=image_id,
                    model_id=model_id,
                    tag=tag_string,
                    tag_id=external_tag_id,
                    confidence_score=confidence,
                    existing=is_existing_tag,
                    is_edited_manually=tag_info.get("is_edited_manually"),
                )
                session.add(new_tag)
                existing_tags_map[(tag_string, model_id)] = new_tag

    def _save_captions(
        self, session: Session, image_id: int, captions_data: list[CaptionAnnotationData]
    ) -> None:
        """キャプション情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(captions_data)} captions for image_id {image_id}")

        # 既存キャプションを image_id で取得
        existing_captions_stmt = select(Caption).where(Caption.image_id == image_id)
        existing_captions_result = session.execute(existing_captions_stmt).scalars().all()
        # (caption_string, model_id) をキーとする辞書を作成
        existing_captions_map = {(c.caption, c.model_id): c for c in existing_captions_result}

        for caption_info in captions_data:
            caption_string = caption_info["caption"]
            model_id = caption_info.get("model_id")
            is_existing_caption = caption_info.get("existing", False)

            existing_record = existing_captions_map.get((caption_string, model_id))

            if existing_record:
                # 更新
                logger.debug(f"Updating existing caption: id={existing_record.id}")
                existing_record.existing = is_existing_caption
                existing_record.is_edited_manually = caption_info.get(
                    "is_edited_manually"
                )  # 渡された値を使用 (Nullable)
            else:
                # 新規作成
                logger.debug(f"Adding new caption: caption='{caption_string[:20]}...'")
                new_caption = Caption(
                    image_id=image_id,
                    model_id=model_id,
                    caption=caption_string,
                    existing=is_existing_caption,
                    is_edited_manually=caption_info.get("is_edited_manually"),
                )
                session.add(new_caption)
                existing_captions_map[(caption_string, model_id)] = new_caption

    def _save_scores(self, session: Session, image_id: int, scores_data: list[ScoreAnnotationData]) -> None:
        """スコア情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(scores_data)} scores for image_id {image_id}")

        # 既存スコアを image_id で取得
        existing_scores_stmt = select(Score).where(Score.image_id == image_id)
        existing_scores_result = session.execute(existing_scores_stmt).scalars().all()
        # model_id をキーとする辞書を作成 (同じ画像・モデルのスコアは1つのはず)
        existing_scores_map = {s.model_id: s for s in existing_scores_result}

        for score_info in scores_data:
            model_id = score_info["model_id"]
            score_value = score_info["score"]
            is_edited = score_info.get("is_edited_manually", False)

            existing_record = existing_scores_map.get(model_id)

            if existing_record:
                # 更新
                logger.debug(f"Updating existing score: id={existing_record.id}")
                existing_record.score = score_value
                existing_record.is_edited_manually = is_edited  # 渡された値を使用
            else:
                # 新規作成
                logger.debug(f"Adding new score: model_id={model_id}, score={score_value}")
                new_score = Score(
                    image_id=image_id,
                    model_id=model_id,
                    score=score_value,
                    is_edited_manually=is_edited,  # 渡された値を使用
                )
                session.add(new_score)
                existing_scores_map[model_id] = new_score

    def _save_ratings(
        self, session: Session, image_id: int, ratings_data: list[RatingAnnotationData]
    ) -> None:
        """レーティング情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(ratings_data)} ratings for image_id {image_id}")

        # 既存レーティングを image_id で取得
        existing_ratings_stmt = select(Rating).where(Rating.image_id == image_id)
        existing_ratings_result = session.execute(existing_ratings_stmt).scalars().all()
        # model_id をキーとする辞書を作成 (同じ画像・モデルのレーティングは1つのはず)
        existing_ratings_map = {r.model_id: r for r in existing_ratings_result}

        for rating_info in ratings_data:
            model_id = rating_info["model_id"]  # 必須
            raw_value = rating_info["raw_rating_value"]
            norm_value = rating_info["normalized_rating"]
            confidence = rating_info.get("confidence_score")

            existing_record = existing_ratings_map.get(model_id)

            if existing_record:
                # 更新
                logger.debug(f"Updating existing rating: id={existing_record.id}")
                existing_record.raw_rating_value = raw_value
                existing_record.normalized_rating = norm_value
                existing_record.confidence_score = confidence
                # Rating には is_edited_manually はない
            else:
                # 新規作成
                logger.debug(f"Adding new rating: model_id={model_id}, rating={norm_value}")
                new_rating = Rating(
                    image_id=image_id,
                    model_id=model_id,
                    raw_rating_value=raw_value,
                    normalized_rating=norm_value,
                    confidence_score=confidence,
                )
                session.add(new_rating)
                existing_ratings_map[model_id] = new_rating

    # --- Data Retrieval Methods ---

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """
        指定されたIDのオリジナル画像メタデータを辞書形式で取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                # 主キー検索には session.get が効率的
                image: Image | None = session.get(Image, image_id)
                if image is None:
                    logger.warning(f"画像メタデータが見つかりません: image_id={image_id}")
                    return None

                # SQLAlchemy オブジェクトを辞書に変換して返す
                # (必要に応じて __dict__ 以外の方法も検討)
                # relationship でロードされたオブジェクトは除外するなど、調整が必要な場合がある
                metadata = {c.name: getattr(image, c.name) for c in image.__table__.columns}
                logger.debug(f"画像メタデータを取得しました: image_id={image_id}")
                return metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"画像メタデータの取得中にエラーが発生しました (ID: {image_id}): {e}", exc_info=True
                )
                raise

    def get_processed_image(
        self, image_id: int, resolution: int = 0, all_data: bool = False
    ) -> dict[str, Any] | list[dict[str, Any]] | None:  # 戻り値の型を調整
        """
        指定された image_id に関連する処理済み画像のメタデータを取得します。
        resolution に基づいてフィルタリングするか、all_data=True で全て取得します。

        Args:
            image_id (int): 元画像のID。
            resolution (int): フィルタリングの基準となる解像度 (長辺)。
                              0 の場合は最も解像度が低いものを返します。
            all_data (bool): True の場合はフィルタリングせず、関連する全ての
                             処理済み画像メタデータをリストで返します。

        Returns:
            Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
                - all_data=True: 処理済み画像メタデータの辞書のリスト。見つからない場合は空リスト。
                - all_data=False: 条件に一致した処理済み画像メタデータの辞書。見つからない場合は None。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                # image_id に紐づく全ての処理済み画像を取得
                stmt = select(ProcessedImage).where(ProcessedImage.image_id == image_id)
                results: list[ProcessedImage] = list(session.execute(stmt).scalars().all())

                if not results:
                    logger.warning(f"処理済み画像が見つかりません: image_id={image_id}")
                    return [] if all_data else None

                # モデルオブジェクトを辞書のリストに変換
                metadata_list = [
                    {c.name: getattr(img, c.name) for c in img.__table__.columns} for img in results
                ]

                if all_data:
                    logger.debug(
                        f"全 {len(metadata_list)} 件の処理済み画像メタデータを取得しました: image_id={image_id}"
                    )
                    return metadata_list

                # 解像度に基づいてフィルタリング
                selected_metadata: dict[str, Any] | None = None
                if resolution == 0:
                    # 最も解像度が低いもの (面積で比較)
                    selected_metadata = min(metadata_list, key=lambda x: x["width"] * x["height"])
                    logger.debug(
                        f"最低解像度の処理済み画像を選択しました: image_id={image_id}, id={selected_metadata['id']}"
                    )
                else:
                    # 指定解像度に最も近いものを選択
                    selected_metadata = self._filter_by_resolution(metadata_list, resolution)

                # all_data=False の場合、ここで選択されたメタデータ (またはNone) を返す
                if not all_data:
                    if selected_metadata:
                        logger.debug(
                            f"解像度 {resolution} に一致する処理済み画像を選択しました: image_id={image_id}, id={selected_metadata.get('id')}"
                        )
                    else:
                        logger.warning(
                            f"解像度 {resolution} に一致する処理済み画像が見つかりませんでした: image_id={image_id}"
                        )
                    return selected_metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"処理済み画像の取得中にエラーが発生しました (ID: {image_id}): {e}", exc_info=True
                )
                raise

    def _filter_by_resolution(
        self, metadata_list: list[dict[str, Any]], resolution: int
    ) -> dict[str, Any] | None:
        """
        解像度に基づいてメタデータをフィルタリングします。
        指定された解像度に最も近いもの (面積比で許容誤差20%以内) を返します。

        Args:
            metadata_list (list[dict[str, Any]]): ProcessedImageのメタデータの辞書のリスト。
            resolution (int): 目標解像度 (長辺)。

        Returns:
            dict[str, Any] | None: フィルタリングされたメタデータの辞書。見つからない場合はNone。
        """
        # 型安全性チェック: resolution が文字列の場合は int に変換
        if isinstance(resolution, str):
            try:
                resolution = int(resolution)
                logger.warning(
                    f"解像度パラメータが文字列として渡されました: '{resolution}' -> {resolution}"
                )
            except ValueError:
                logger.error(f"解像度パラメータの変換に失敗しました: '{resolution}'")
                return None

        best_match: dict[str, Any] | None = None
        min_error_ratio = float("inf")

        target_area = resolution * resolution  # Target area based on square of the long side

        for metadata in metadata_list:
            width = metadata.get("width", 0)
            height = metadata.get("height", 0)
            if not width or not height:
                continue

            # 1. Check for exact match on the longer side
            long_side = max(width, height)
            if long_side == resolution:
                logger.debug(f"Exact resolution match found: {metadata['id']}")
                return metadata  # Exact match found, return immediately

            # 2. Calculate area ratio difference if no exact match yet
            short_side = min(width, height)
            actual_area = long_side * short_side

            # Avoid division by zero if target_area is 0 (resolution is 0)
            # Though resolution=0 should be handled before calling this function
            if target_area == 0:
                error_ratio = float("inf")  # Or handle as a special case if needed
            else:
                error_ratio = abs(target_area - actual_area) / target_area

            # Check if within 20% tolerance and better than the current best match
            if error_ratio <= 0.2 and error_ratio < min_error_ratio:
                min_error_ratio = error_ratio
                best_match = metadata

        if best_match:
            logger.debug(
                f"Closest resolution match found (error: {min_error_ratio:.2f}): {best_match['id']}"
            )
        else:
            logger.debug(f"No suitable processed image found for resolution {resolution}")

        return best_match  # Return the best match found within tolerance, or None

    def get_image_annotations(self, image_id: int) -> dict[str, list[dict[str, Any]]]:
        """
        指定された画像IDのアノテーション(タグ、キャプション、スコア、レーティング)を取得します。
        Eager Loading を使用して関連データを効率的に取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            dict[str, list[dict[str, Any]]]: アノテーションデータを含む辞書。
                キー: 'tags', 'captions', 'scores', 'ratings'
                値: 各アノテーション情報の辞書のリスト。
                画像が存在しない場合は空のリストを持つ辞書を返します。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        from sqlalchemy.orm import joinedload

        logger.debug(f"Getting annotations for image_id: {image_id}")
        annotations: dict[str, list[dict[str, Any]]] = {
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Image)
                    .where(Image.id == image_id)
                    .options(
                        joinedload(Image.tags),
                        joinedload(Image.captions),
                        joinedload(Image.scores),
                        joinedload(Image.ratings),
                        joinedload(Image.processed_images),
                    )
                )
                image = session.execute(stmt).unique().scalar_one_or_none()

                if image is None:
                    logger.warning(f"画像が見つかりません: image_id={image_id}")
                    return annotations  # Return empty structure

                # Extract and format annotations
                if image.tags:
                    annotations["tags"] = [
                        {
                            "id": tag.id,
                            "tag": tag.tag,
                            "tag_id": tag.tag_id,
                            "model_id": tag.model_id,
                            "existing": tag.existing,
                            "is_edited_manually": tag.is_edited_manually,
                            "confidence_score": tag.confidence_score,
                            "created_at": tag.created_at,
                            "updated_at": tag.updated_at,
                        }
                        for tag in image.tags
                    ]
                if image.captions:
                    annotations["captions"] = [
                        {
                            "id": caption.id,
                            "caption": caption.caption,
                            "model_id": caption.model_id,
                            "existing": caption.existing,
                            "is_edited_manually": caption.is_edited_manually,
                            "created_at": caption.created_at,
                            "updated_at": caption.updated_at,
                        }
                        for caption in image.captions
                    ]
                if image.scores:
                    annotations["scores"] = [
                        {
                            "id": score.id,
                            "score": score.score,
                            "model_id": score.model_id,
                            "is_edited_manually": score.is_edited_manually,
                            "created_at": score.created_at,
                            "updated_at": score.updated_at,
                        }
                        for score in image.scores
                    ]
                if image.ratings:
                    annotations["ratings"] = [
                        {
                            "id": rating.id,
                            "raw_rating_value": rating.raw_rating_value,
                            "normalized_rating": rating.normalized_rating,
                            "model_id": rating.model_id,
                            "confidence_score": rating.confidence_score,
                            "created_at": rating.created_at,
                            "updated_at": rating.updated_at,
                        }
                        for rating in image.ratings
                    ]

                logger.info(
                    f"取得したアノテーション数: tags={len(annotations['tags'])}, captions={len(annotations['captions'])}, scores={len(annotations['scores'])}, ratings={len(annotations['ratings'])} for image_id={image_id}"
                )
                return annotations

            except SQLAlchemyError as e:
                logger.error(
                    f"画像ID {image_id} のアノテーション取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def _parse_datetime_str(self, date_str: str | None) -> datetime.datetime | None:
        """
        日付文字列を UTC timezone-aware datetime オブジェクトに変換。

        アプリケーション全体でUTC統一方針に従い、入力文字列をUTCとして解釈します。
        データベースは TIMESTAMP(timezone=True) でUTC保存されているため、
        フィルタリング時の比較もUTC基準で行います。

        Args:
            date_str: ISO 8601形式の日付文字列 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS)

        Returns:
            datetime.datetime | None: UTC timezone-aware datetime オブジェクト、無効な場合は None
        """
        if not date_str:
            return None
        try:
            # ISO 8601形式 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS) を想定
            # スペース区切りも考慮
            date_str = date_str.replace(" ", "T")
            # マイクロ秒以下を削除 (存在する場合)
            if "." in date_str:
                date_str = date_str.split(".")[0]

            # naive datetime としてパースしてからUTCタイムゾーンを設定
            # 入力文字列はUTC時刻として解釈する（アプリケーション統一方針）
            parsed_dt = datetime.datetime.fromisoformat(date_str)

            # タイムゾーン情報がない場合はUTCとして扱う
            if parsed_dt.tzinfo is None:
                from datetime import UTC

                parsed_dt = parsed_dt.replace(tzinfo=UTC)

            return parsed_dt
        except ValueError:
            logger.warning(f"無効な日付形式です: {date_str}。無視されます。")
            return None

    def _prepare_like_pattern(self, term: str) -> tuple[str, bool]:
        """検索語からLIKEパターンと完全一致フラグを準備します。"""
        is_exact = False
        pattern = term.strip()  # 前後の空白を除去

        if pattern.startswith('"') and pattern.endswith('"') and len(pattern) > 1:
            # ダブルクォートで囲まれている場合は完全一致
            is_exact = True
            pattern = pattern[1:-1]  # クォートを除去
            # クォート内のワイルドカードはリテラルとして扱う
            pattern = pattern.replace("%", "\\%").replace("_", "\\_").replace("*", "*")
        elif "*" in pattern:
            # アスタリスクがあれば LIKE 検索 (部分一致)
            # アスタリスクを SQL の % に置換
            pattern = pattern.replace("%", "\\%").replace("_", "\\_").replace("*", "%")
            is_exact = False
        else:
            # デフォルトは部分一致 (LIKE)
            is_exact = False
            # 前後に % を追加
            pattern = f"%{pattern.replace('%', '\\%').replace('_', '\\_')}%"

        # logger.debug(f"Prepared pattern: '{pattern}', is_exact: {is_exact} for term: '{term}'")
        return pattern, is_exact

    # --- Filtering Helper Methods ---

    def _apply_date_filter(
        self,
        query: Select,
        start_dt: datetime.datetime | None,
        end_dt: datetime.datetime | None,
    ) -> Select:
        """クエリに日付フィルタを適用します (画像またはアノテーションの更新日時)。"""
        if not start_dt and not end_dt:
            return query

        # 画像自体の作成/更新日時のみを考慮
        img_date_conds = []
        if start_dt:
            img_date_conds.append(Image.updated_at >= start_dt)
        if end_dt:
            img_date_conds.append(Image.updated_at <= end_dt)
        if img_date_conds:
            query = query.where(and_(*img_date_conds))

        return query

    def _apply_tag_filter(
        self,
        query: Select,
        tags: list[str] | None,
        use_and: bool,
        include_untagged: bool,
    ) -> Select:
        """クエリにタグフィルタを適用します。"""
        if include_untagged:
            # タグが存在しない画像 (outerjoinしてTag.idがNULL)
            # 注: この条件は他のタグ/キャプション条件と併用されない前提 (Manager側で制御想定)
            query = query.outerjoin(Tag, Image.id == Tag.image_id).where(Tag.id.is_(None))
        elif tags:
            # use_and (AND検索) の場合、タグごとにJOIN条件を追加する
            if use_and:
                logger.debug(f"Applying AND tag filter (EXISTS) for tags: {tags}")
                for _i, tag_term in enumerate(tags):
                    pattern, is_exact = self._prepare_like_pattern(tag_term)
                    # is_exact フラグに基づいて条件を選択
                    subquery_condition = (Tag.tag == pattern) if is_exact else Tag.tag.like(pattern)
                    # EXISTS サブクエリを作成
                    exists_subquery = (
                        select(Tag.id)  # SELECT句は何でもよい (通常は 1 や PK)
                        .where(
                            Tag.image_id == Image.id,  # WHERE句に明示的な相関条件は残す
                            subquery_condition,
                        )
                        .correlate(Image)  # 明示的に相関させる
                        .exists()
                    )
                    # メインクエリに EXISTS 条件を追加
                    query = query.where(exists_subquery)
            else:
                # use_and=False (OR検索) の場合、単一のJOINとOR条件
                logger.debug(f"Applying OR tag filter for tags: {tags}")
                tag_criteria = []
                for t in tags:
                    pattern, is_exact = self._prepare_like_pattern(t)
                    if is_exact:
                        tag_criteria.append(Tag.tag == pattern)
                    else:
                        tag_criteria.append(Tag.tag.like(pattern))
                if tag_criteria:
                    query = query.join(Tag, Image.id == Tag.image_id).where(or_(*tag_criteria))
                    # logger.debug(f"Query after OR tag join: {query}") # クエリ確認用

        return query

    def _apply_caption_filter(self, query: Select, caption: str | None) -> Select:
        """クエリにキャプションフィルタを適用します (EXISTSを使用)。"""
        if caption:
            logger.debug(f"Applying caption filter (EXISTS) for caption: '{caption}'")
            pattern, is_exact = self._prepare_like_pattern(caption)

            caption_filter = (Caption.caption == pattern) if is_exact else (Caption.caption.like(pattern))

            # EXISTS サブクエリを作成
            exists_subquery = (
                select(Caption.id)
                .where(
                    Caption.image_id == Image.id,  # メインクエリの Image と相関させる
                    caption_filter,
                )
                .correlate(Image)  # 明示的に相関させる
                .exists()
            )
            # メインクエリに EXISTS 条件を追加
            query = query.where(exists_subquery)
        return query

    def _apply_nsfw_filter(self, query: Select, include_nsfw: bool) -> Select:
        """クエリにNSFWフィルタを適用します。"""
        if not include_nsfw:
            # NSFWとみなすレーティング値 (小文字にして比較)
            nsfw_ratings = ["r", "x", "xxx"]

            # AIによるレーティングに基づく除外条件
            # Rating テーブルを LEFT JOIN する (なければ Rating.id is NULL)
            # query = query.outerjoin(Rating, Image.id == Rating.image_id)
            # 条件: Rating が存在し、かつ normalized_rating が NSFW リストに含まれる
            ai_nsfw_condition = (
                exists()
                .where(Rating.image_id == Image.id, func.lower(Rating.normalized_rating).in_(nsfw_ratings))
                .correlate(Image)
            )

            # 手動レーティングに基づく除外条件
            manual_nsfw_condition = func.lower(func.coalesce(Image.manual_rating, "")).in_(nsfw_ratings)

            # AIレーティングまたは手動レーティングがNSFWである画像を除外
            query = query.where(not_(or_(ai_nsfw_condition, manual_nsfw_condition)))
            # レーティング情報がない (NULL) 画像は除外しない
        return query

    def _apply_manual_filters(
        self,
        query: Select,
        manual_rating_filter: str | None,
        manual_edit_filter: bool | None,
    ) -> Select:
        """クエリに手動評価と手動編集フラグのフィルタを適用します。"""
        if manual_rating_filter:
            query = query.where(Image.manual_rating == manual_rating_filter)

        if manual_edit_filter is not None:
            has_manual_edit = or_(
                exists().where(Tag.image_id == Image.id, Tag.is_edited_manually).correlate(Image),
                exists().where(Caption.image_id == Image.id, Caption.is_edited_manually).correlate(Image),
                exists().where(Score.image_id == Image.id, Score.is_edited_manually).correlate(Image),
            )

            if manual_edit_filter:
                query = query.where(has_manual_edit)
            else:
                query = query.where(not_(has_manual_edit))

        return query

    def _fetch_filtered_metadata(
        self, session: Session, image_ids: list[int], resolution: int
    ) -> list[dict[str, Any]]:
        """フィルタリングされたIDリストに基づき、指定解像度のメタデータを取得します。"""
        final_metadata_list = []
        if not image_ids:
            return []

        if resolution == 0:
            orig_stmt = select(Image).where(Image.id.in_(image_ids))
            orig_results: list[Image] = list(session.execute(orig_stmt).scalars().all())
            final_metadata_list = [
                {c.name: getattr(img, c.name) for c in img.__table__.columns} for img in orig_results
            ]
        else:
            # ProcessedImage を image_id で一括ロード
            proc_stmt = select(ProcessedImage).where(ProcessedImage.image_id.in_(image_ids))
            all_proc_images = session.execute(proc_stmt).scalars().all()

            # image_id ごとにグループ化
            proc_images_by_id: dict[int, list[dict[str, Any]]] = {}
            for img in all_proc_images:
                if img.image_id not in proc_images_by_id:
                    proc_images_by_id[img.image_id] = []
                proc_images_by_id[img.image_id].append(
                    {c.name: getattr(img, c.name) for c in img.__table__.columns}
                )

            # 各 image_id グループ内で解像度フィルタを適用
            for image_id in image_ids:
                metadata_list = proc_images_by_id.get(image_id, [])
                if metadata_list:
                    selected_metadata = self._filter_by_resolution(metadata_list, resolution)
                    if selected_metadata:
                        final_metadata_list.append(selected_metadata)

        return final_metadata_list

    # --- Main Filter Method ---

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
        manual_rating_filter: str | None = None,  # 手動レーティングでフィルタ
        manual_edit_filter: bool
        | None = None,  # 手動編集フラグでフィルタ (True:編集済, False:未編集, None:フィルタ無)
        # TODO: rating (AIによる評価) でのフィルタも追加検討
    ) -> tuple[list[dict[str, Any]], int]:
        """
        指定された条件に基づいて画像をフィルタリングし、メタデータと件数を返します。

        Args:
            tags (Optional[list[str]]): 検索するタグのリスト。
            caption (Optional[str]): 検索するキャプション文字列。
            resolution (int): 検索対象の解像度(長辺)。0の場合はオリジナル画像。
            use_and (bool): 複数タグ指定時の検索方法 (True: AND, False: OR)。
            start_date (Optional[str]): 検索開始日時 (ISO 8601形式)。
            end_date (Optional[str]): 検索終了日時 (ISO 8601形式)。
            include_untagged (bool): タグが付いていない画像のみを対象とするか。
            include_nsfw (bool): NSFWコンテンツを含む画像を除外しないか。
            manual_rating_filter (Optional[str]): 指定した手動レーティングを持つ画像のみを対象とするか。
            manual_edit_filter (Optional[bool]): アノテーションが手動編集されたかでフィルタするか。
                                                 True: 編集済のみ, False: 未編集のみ, None: フィルタしない。

        Returns:
            tuple[list[dict[str, Any]], int]:
                条件にマッチした画像メタデータのリストとその総数。
        """
        # 型安全性チェック: resolution が文字列の場合は int に変換
        if isinstance(resolution, str):
            try:
                resolution = int(resolution)
                logger.warning(
                    f"解像度パラメータが文字列として渡されました: '{resolution}' -> {resolution}"
                )
            except ValueError:
                logger.error(f"解像度パラメータの変換に失敗しました: '{resolution}'")
                return [], 0

        with self.session_factory() as session:
            try:
                # --- 1. 基本クエリと日付フィルタ ---
                query = select(Image.id)  # まずは ID のみ取得

                start_dt = self._parse_datetime_str(start_date)
                end_dt = self._parse_datetime_str(end_date)

                # --- フィルタ適用 --- (ヘルパーメソッド呼び出し)
                query = self._apply_date_filter(query, start_dt, end_dt)  # 日付フィルタを最初に適用

                if include_untagged and (tags or caption):
                    logger.warning(
                        "検索語句と include_untagged が同時に指定されたため、検索語句は無視されます。"
                    )

                # タグフィルタ適用
                query = self._apply_tag_filter(query, tags, use_and, include_untagged)

                # キャプション、NSFW、手動編集フィルタ適用
                query = self._apply_caption_filter(query, caption)

                # ★★★ フィルター順序変更: Manual Filters を先に適用 ★★★
                query = self._apply_manual_filters(query, manual_rating_filter, manual_edit_filter)

                # ★★★ NSFW Filter は Manual Filters の後に適用 ★★★
                # Apply NSFW filter only if include_nsfw is False and the user is NOT explicitly asking for an NSFW manual rating
                nsfw_values_to_exclude = {"r", "x", "xxx"}
                apply_nsfw_exclusion = not include_nsfw and (
                    manual_rating_filter is None
                    or manual_rating_filter.lower() not in nsfw_values_to_exclude
                )
                if apply_nsfw_exclusion:
                    query = self._apply_nsfw_filter(query, include_nsfw=False)  # Pass False explicitly
                elif include_nsfw:  # If include_nsfw is True, apply the filter logic (which essentially does nothing if include_nsfw=True)
                    query = self._apply_nsfw_filter(query, include_nsfw=True)

                # --- 5. クエリ実行と ID 取得 --- #
                query = query.distinct()

                filtered_image_ids: list[int] = list(session.execute(query).scalars().all())

                if not filtered_image_ids:
                    logger.info("指定された条件に一致する画像が見つかりませんでした。")
                    return [], 0

                logger.info(f"フィルタリングで {len(filtered_image_ids)} 件の候補画像IDを取得しました。")

                # --- 6. メタデータ取得 --- (ヘルパーメソッド呼び出し)
                final_metadata_list = self._fetch_filtered_metadata(session, filtered_image_ids, resolution)

                list_count = len(final_metadata_list)
                logger.info(f"最終的な検索結果: {list_count} 件")

                return final_metadata_list, list_count

            except SQLAlchemyError as e:
                logger.error(f"画像フィルタリング検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    # --- Model Information Retrieval ---

    def get_models(self) -> list[dict[str, Any]]:
        """
        データベースに登録されている全てのモデルの情報を取得します。
        各モデルに関連付けられたタイプ名も含まれます。

        Returns:
            list[dict[str, Any]]: モデル情報の辞書のリスト。
                各辞書には 'id', 'name', 'provider', 'discontinued_at',
                'created_at', 'updated_at', 'model_types' (タイプ名のリスト) が含まれます。

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Model).options(selectinload(Model.model_types)).order_by(Model.name)

                models_result: list[Model] = list(session.execute(stmt).scalars().unique().all())

                model_list = [
                    {
                        "id": model.id,
                        "name": model.name,
                        "provider": model.provider,
                        "discontinued_at": model.discontinued_at,
                        "created_at": model.created_at,
                        "updated_at": model.updated_at,
                        "model_types": sorted([mt.name for mt in model.model_types]),  # タイプ名のリスト
                    }
                    for model in models_result
                ]

                logger.info(f"全モデル情報を取得しました。 件数: {len(model_list)}")
                return model_list

            except SQLAlchemyError as e:
                logger.error(f"全モデル情報の取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_model_objects(self) -> list[Model]:
        """
        データベースから実際のModelオブジェクトを直接取得します（DB中心アーキテクチャ用）

        Returns:
            list[Model]: Modelオブジェクトのリスト（関連するmodel_types含む）
        """
        try:
            with self.session_factory() as session:
                stmt = select(Model).options(selectinload(Model.model_types)).order_by(Model.name)
                models_result = session.execute(stmt).scalars().unique().all()

                model_list = list(models_result)
                logger.info(f"DB Modelオブジェクトを取得しました。 件数: {len(model_list)}")
                return model_list

        except SQLAlchemyError as e:
            logger.error(f"DB Modelオブジェクトの取得中にエラーが発生しました: {e}", exc_info=True)
            raise

    def get_models_by_type(self, model_type_name: str) -> list[dict[str, Any]]:
        """
        指定されたタイプ名を持つモデルの情報を取得します。

        Args:
            model_type_name (str): フィルタリングするモデルのタイプ名 (例: 'tagger')。

        Returns:
            list[dict[str, Any]]: 条件に一致したモデル情報の辞書のリスト。
                形式は get_models と同じです。

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合。
        """
        from sqlalchemy.orm import selectinload

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Model)
                    .join(Model.model_types)
                    .where(ModelType.name == model_type_name)
                    .options(selectinload(Model.model_types))
                    .order_by(Model.name)
                    .distinct()
                )

                models_result: list[Model] = list(session.execute(stmt).scalars().all())

                model_list = [
                    {
                        "id": model.id,
                        "name": model.name,
                        "provider": model.provider,
                        "discontinued_at": model.discontinued_at,
                        "created_at": model.created_at,
                        "updated_at": model.updated_at,
                        "model_types": sorted([mt.name for mt in model.model_types]),
                    }
                    for model in models_result
                ]

                logger.info(
                    f"タイプ '{model_type_name}' のモデル情報を取得しました。 件数: {len(model_list)}"
                )
                return model_list

            except SQLAlchemyError as e:
                logger.error(
                    f"タイプ '{model_type_name}' のモデル情報取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    # --- Count Methods ---

    def get_total_image_count(self) -> int:
        """データベース内のオリジナル画像の総数を取得します。"""
        with self.session_factory() as session:
            try:
                stmt = select(func.count(Image.id))
                count = session.execute(stmt).scalar_one()
                return count
            except SQLAlchemyError as e:
                logger.error(f"総画像数の取得中にエラーが発生しました: {e}", exc_info=True)
                raise  # または、目的のエラー処理に応じて0を返します

    # --- Update Methods (Manual Edits) ---

    def update_manual_rating(self, image_id: int, rating: str | None) -> bool:
        """
        指定された画像IDの manual_rating を更新します。

        Args:
            image_id (int): 更新する画像のID。
            rating (Optional[str]): 新しいレーティング値 ('PG', 'R' など)。NoneでNULLに設定。

        Returns:
            bool: 更新が成功した場合はTrue、画像が見つからない場合はFalse。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                stmt = update(Image).where(Image.id == image_id).values(manual_rating=rating)
                result = session.execute(stmt)
                if result.rowcount == 0:
                    logger.warning(f"Manual rating の更新対象画像が見つかりません: image_id={image_id}")
                    return False
                session.commit()
                logger.info(f"画像ID {image_id} の manual_rating を '{rating}' に更新しました。")
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Manual rating の更新中にエラーが発生しました (ID: {image_id}): {e}", exc_info=True
                )
                raise

    def update_annotation_manual_edit_flag(
        self, annotation_type: str, annotation_id: int, is_edited: bool
    ) -> bool:
        """
        指定されたアノテーションの is_edited_manually フラグを更新します。

        Args:
            annotation_type (str): アノテーションのタイプ ('tags', 'captions', 'scores')。
            annotation_id (int): 更新するアノテーションのID。
            is_edited (bool): 設定する手動編集フラグの値。

        Returns:
            bool: 更新が成功した場合はTrue、アノテーションが見つからない場合はFalse。

        Raises:
            ValueError: サポートされていない annotation_type が指定された場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        model_map = {"tags": Tag, "captions": Caption, "scores": Score}
        if annotation_type not in model_map:
            raise ValueError(f"サポートされていないアノテーションタイプです: {annotation_type}")

        target_model = model_map[annotation_type]

        with self.session_factory() as session:
            try:
                stmt = (
                    update(target_model)
                    .where(target_model.__table__.c.id == annotation_id)
                    .values(is_edited_manually=is_edited)
                )
                result = session.execute(stmt)
                if result.rowcount == 0:
                    logger.warning(
                        f"手動編集フラグの更新対象アノテーションが見つかりません: "
                        f"type={annotation_type}, id={annotation_id}"
                    )
                    return False
                session.commit()
                logger.info(
                    f"{annotation_type} ID {annotation_id} の is_edited_manually を {is_edited} に更新しました。"
                )
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"手動編集フラグの更新中にエラーが発生しました (Type: {annotation_type}, ID: {annotation_id}): {e}",
                    exc_info=True,
                )
                raise
