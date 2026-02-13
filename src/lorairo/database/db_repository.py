"""DBリポジトリ"""

import datetime
from typing import Any, TypedDict, cast

from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from sqlalchemy import Select, and_, exists, func, not_, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from ..utils.log import logger
from .db_core import DefaultSessionLocal
from .filter_criteria import ImageFilterCriteria
from .schema import (
    Caption,
    ErrorRecord,
    Image,
    Model,
    ModelType,
    ProcessedImage,
    Rating,
    Score,
    Tag,
)


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
    """画像関連エンティティのデータベース永続化を担当するクラス (SQLAlchemyベース)。
    CRUD操作と基本的な検索機能を提供します。
    """

    # SQLite バインド変数上限の安全マージン（32,766の約半分）
    # IN句以外にもクエリ内で変数を使うため余裕を持たせる
    BATCH_CHUNK_SIZE = 15000

    def __init__(self, session_factory: sessionmaker[Session] = DefaultSessionLocal):
        """ImageRepositoryのコンストラクタ。

        Args:
            session_factory (Callable[[], Session]): SQLAlchemyセッションを生成するファクトリ関数。
                                                    デフォルトはdb_core.SessionLocalを使用。
                                                    テスト時にモック化可能。

        """
        self.session_factory = session_factory
        logger.info("ImageRepository initialized.")

        # 外部tag_db統合（公開API経由、グレースフルデグラデーション対応）
        # TagCleaner.clean_format()は静的メソッドなのでインスタンス化不要
        self.merged_reader = self._initialize_merged_reader()  # 失敗時はNoneで継続
        # TagRegisterServiceは遅延初期化（登録時のみ必要）
        self.tag_register_service: TagRegisterService | None = None

    def _initialize_merged_reader(self) -> MergedTagReader | None:
        """外部タグDBリーダーを初期化（遅延初期化対応）。

        Returns:
            MergedTagReader | None: 初期化成功時はMergedTagReader、失敗時はNone。
                                   Noneの場合、外部タグDB機能は無効化され、tag_id=Noneで動作継続。

        Note:
            - 初期化失敗時はグレースフルデグラデーション（警告ログのみ、システム継続）
            - get_default_reader() はベースDBとユーザーDBの両方が無い場合にエラー
            - LoRAIroは外部タグDB無しでも動作可能（tag_id=None許容設計）

        """
        try:
            return get_default_reader()
        except Exception as e:
            logger.warning(
                f"Failed to initialize MergedTagReader (external tag DB unavailable): {e}. "
                "Tag operations will continue without external tag_id.",
            )
            return None

    def _initialize_tag_register_service(self) -> TagRegisterService | None:
        """タグ登録サービスを初期化（遅延初期化、Qt非依存）。

        Returns:
            TagRegisterService | None: 初期化成功時はTagRegisterService、失敗時はNone。
                                      Noneの場合、タグ登録機能は無効化され、検索のみ動作。

        Note:
            - MergedTagReaderが利用可能な場合のみ初期化
            - TagRegisterServiceはQt非依存で、CLI/ライブラリ/GUIで使用可能
            - 初期化失敗時はグレースフルデグラデーション（警告ログのみ、システム継続）

        """
        if self.merged_reader is None:
            logger.warning("MergedTagReader unavailable, cannot initialize TagRegisterService")
            return None

        try:
            return TagRegisterService(reader=self.merged_reader)
        except Exception as e:
            logger.warning(f"Failed to initialize TagRegisterService: {e}", exc_info=True)
            return None  # エラー時はNoneで継続

    def _get_model_id(self, model_name: str) -> int | None:
        """モデル名からモデルIDを取得します。

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
                return cast("int | None", result)
            except SQLAlchemyError as e:
                logger.error(f"モデルIDの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_model_by_name(self, name: str) -> Model | None:
        """モデル名からModelオブジェクトを取得（公開API）

        Args:
            name: モデル名

        Returns:
            Model | None: 見つかった場合はModelオブジェクト（model_types eager load済み）、なければNone

        Raises:
            SQLAlchemyError: DB操作エラー

        """
        with self.session_factory() as session:
            try:
                # model_typesを eager loadingで取得（N+1クエリ回避）
                stmt = select(Model).options(selectinload(Model.model_types)).where(Model.name == name)
                result = session.execute(stmt).scalar_one_or_none()
                if result is None:
                    logger.debug(f"モデル '{name}' は登録されていません")
                return result
            except SQLAlchemyError as e:
                logger.error(f"モデル取得エラー (name={name}): {e}", exc_info=True)
                raise

    def get_models_by_names(self, names: set[str]) -> dict[str, Model]:
        """複数モデル名からModelオブジェクトを一括取得する。

        Args:
            names: 取得するモデル名のセット。

        Returns:
            モデル名 → Model のマッピング。見つからなかった名前は含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not names:
            return {}

        with self.session_factory() as session:
            try:
                stmt = select(Model).options(selectinload(Model.model_types)).where(Model.name.in_(names))
                results = session.execute(stmt).scalars().all()
                models_map = {model.name: model for model in results}
                logger.debug(f"モデル一括取得: {len(models_map)}/{len(names)}件見つかりました")
                return models_map
            except SQLAlchemyError as e:
                logger.error(f"モデル一括取得エラー: {e}", exc_info=True)
                raise

    def _get_or_create_manual_edit_model(self, session: Session) -> int:
        """手動編集用のモデルIDを取得または作成します。

        MANUAL_EDITという名前のモデルが存在しない場合は新規作成します。
        model_typesテーブルへの関連付けは行いません（手動編集はAIカテゴリに属さない）。

        Args:
            session (Session): データベースセッション

        Returns:
            int: MANUAL_EDITモデルのID

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合

        """
        try:
            # 既存のMANUAL_EDITモデルを検索
            stmt = select(Model).where(Model.name == "MANUAL_EDIT")
            existing_model = session.execute(stmt).scalar_one_or_none()

            if existing_model:
                logger.debug(f"既存のMANUAL_EDITモデルを使用: ID={existing_model.id}")
                return existing_model.id

            # 新規作成
            manual_edit_model = Model(name="MANUAL_EDIT", provider="user")
            session.add(manual_edit_model)
            session.flush()  # IDを取得するためにflush

            logger.info(f"MANUAL_EDITモデルを新規作成: ID={manual_edit_model.id}")
            return manual_edit_model.id

        except SQLAlchemyError as e:
            logger.error(f"MANUAL_EDITモデルの取得/作成中にエラーが発生しました: {e}", exc_info=True)
            raise

    def insert_model(
        self,
        name: str,
        provider: str | None,
        model_types: list[str],
        api_model_id: str | None = None,
        estimated_size_gb: float | None = None,
        requires_api_key: bool = False,
        discontinued_at: datetime.datetime | None = None,
    ) -> int:
        """新規モデルをDBに登録

        Args:
            name: モデル名（一意）
            provider: プロバイダー名（openai, anthropic, google, None）
            model_types: LoRAIroのmodel_typeリスト（["captioner"], ["llm", "captioner"], ["score"], ["tagger"]等）
            api_model_id: API呼び出し時のモデルID
            estimated_size_gb: ローカルモデルの推定サイズ（GB）
            requires_api_key: APIキー要否
            discontinued_at: 廃止日時（該当する場合）

        Returns:
            int: 登録されたモデルのID

        Raises:
            IntegrityError: 同名モデルが既に存在する場合
            ValueError: model_typesが無効な場合（存在しないmodel_type名）

        """
        with self.session_factory() as session:
            try:
                # ModelTypeオブジェクトを取得
                model_type_objects = []
                for type_name in model_types:
                    stmt = select(ModelType).where(ModelType.name == type_name)
                    model_type = session.execute(stmt).scalar_one_or_none()
                    if not model_type:
                        valid_types = session.execute(select(ModelType.name)).scalars().all()
                        raise ValueError(
                            f"Invalid model_type: '{type_name}'. Valid types: {', '.join(valid_types)}",
                        )
                    model_type_objects.append(model_type)

                # Model作成
                new_model = Model(
                    name=name,
                    provider=provider,
                    api_model_id=api_model_id,
                    estimated_size_gb=estimated_size_gb,
                    requires_api_key=requires_api_key,
                    discontinued_at=discontinued_at,
                )
                new_model.model_types = model_type_objects

                session.add(new_model)
                session.commit()
                session.refresh(new_model)  # IDを取得するためリフレッシュ

                logger.info(f"モデル登録完了: {name} (ID={new_model.id}, types={model_types})")
                return new_model.id

            except IntegrityError:
                session.rollback()
                logger.warning(f"モデル登録失敗（既存モデルの可能性）: {name}")
                raise
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"モデル登録エラー: {e}", exc_info=True)
                raise

    @staticmethod
    def _apply_simple_field_updates(
        model: Any,
        provider: str | None,
        api_model_id: str | None,
        estimated_size_gb: float | None,
        requires_api_key: bool | None,
        discontinued_at: datetime.datetime | None,
    ) -> bool:
        """モデルの単純フィールドを差分更新する。

        Args:
            model: ModelのORMオブジェクト。
            provider: プロバイダー名。
            api_model_id: APIモデルID。
            estimated_size_gb: 推定サイズ。
            requires_api_key: APIキー要否。
            discontinued_at: 廃止日時。

        Returns:
            変更があった場合True。

        """
        has_changes = False
        simple_fields = {
            "provider": provider,
            "api_model_id": api_model_id,
            "estimated_size_gb": estimated_size_gb,
            "requires_api_key": requires_api_key,
            "discontinued_at": discontinued_at,
        }
        for field_name, new_value in simple_fields.items():
            if new_value is not None:
                current_value = getattr(model, field_name)
                if current_value != new_value:
                    setattr(model, field_name, new_value)
                    has_changes = True
                    logger.debug(f"フィールド更新: {field_name} = {new_value}")
        return has_changes

    @staticmethod
    def _update_model_types(session: Session, model: Any, model_types: list[str]) -> bool:
        """モデルタイプの関連を差分更新する。

        Args:
            session: SQLAlchemyセッション。
            model: ModelのORMオブジェクト。
            model_types: 新しいモデルタイプ名リスト。

        Returns:
            変更があった場合True。

        Raises:
            ValueError: 無効なモデルタイプが指定された場合。

        """
        current_types = {mt.name for mt in model.model_types}
        new_types = set(model_types)

        if current_types == new_types:
            return False

        model_type_objects = []
        for type_name in model_types:
            stmt = select(ModelType).where(ModelType.name == type_name)
            model_type = session.execute(stmt).scalar_one_or_none()
            if not model_type:
                valid_types = session.execute(select(ModelType.name)).scalars().all()
                raise ValueError(
                    f"Invalid model_type: '{type_name}'. Valid types: {', '.join(valid_types)}",
                )
            model_type_objects.append(model_type)

        model.model_types = model_type_objects
        logger.debug(f"model_types更新: {current_types} -> {new_types}")
        return True

    def update_model(
        self,
        model_id: int,
        provider: str | None = None,
        model_types: list[str] | None = None,
        api_model_id: str | None = None,
        estimated_size_gb: float | None = None,
        requires_api_key: bool | None = None,
        discontinued_at: datetime.datetime | None = None,
    ) -> bool:
        """既存モデルのメタデータを更新(差分検出あり)

        NOTE: 引数がNoneの場合は更新しない

        Args:
            model_id: 更新対象モデルのID
            provider: プロバイダー名
            model_types: モデルタイプリスト
            api_model_id: API呼び出し時のモデルID
            estimated_size_gb: 推定サイズ
            requires_api_key: APIキー要否
            discontinued_at: 廃止日時

        Returns:
            実際に更新が発生したかどうか

        Raises:
            ValueError: model_idが存在しない、またはmodel_typesが無効な場合

        """
        with self.session_factory() as session:
            try:
                stmt = select(Model).options(selectinload(Model.model_types)).where(Model.id == model_id)
                model = session.execute(stmt).scalar_one_or_none()

                if not model:
                    raise ValueError(f"Model not found: id={model_id}")

                has_changes = self._apply_simple_field_updates(
                    model,
                    provider,
                    api_model_id,
                    estimated_size_gb,
                    requires_api_key,
                    discontinued_at,
                )

                if model_types is not None:
                    if self._update_model_types(session, model, model_types):
                        has_changes = True

                if has_changes:
                    session.commit()
                    logger.info(f"モデル更新完了: {model.name} (ID={model_id})")
                    return True
                logger.debug(f"モデル更新なし: {model.name} (ID={model_id})")
                return False

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"モデル更新エラー: {e}", exc_info=True)
                raise

    def _image_exists(self, image_id: int) -> bool:
        """指定された画像IDが images テーブルに存在するかを確認します。

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
                    f"画像存在チェック中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def find_duplicate_image_by_phash(self, phash: str) -> int | None:
        """指定されたpHashに一致する画像をデータベースから検索し、Image IDを返します。
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
                    logger.debug(f"pHashによる重複画像が見つかりました: ID {image_id}, pHash {phash}")
                return image_id
            except SQLAlchemyError as e:
                logger.error(f"pHashによる重複画像の検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    def find_image_ids_by_phashes(self, phashes: set[str]) -> dict[str, int]:
        """複数pHashに対応する画像IDを一括取得する。

        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            phashes: 検索するpHashのセット。

        Returns:
            pHash → image_id のマッピング。見つからなかったpHashは含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not phashes:
            return {}

        phash_list = list(phashes)

        with self.session_factory() as session:
            try:
                phash_to_id: dict[str, int] = {}
                for i in range(0, len(phash_list), self.BATCH_CHUNK_SIZE):
                    chunk = phash_list[i : i + self.BATCH_CHUNK_SIZE]
                    stmt = select(Image.phash, Image.id).where(Image.phash.in_(chunk))
                    results = session.execute(stmt).all()
                    phash_to_id.update({row.phash: row.id for row in results})
                logger.debug(f"pHash一括検索: {len(phash_to_id)}/{len(phashes)}件見つかりました")
                return phash_to_id
            except SQLAlchemyError as e:
                logger.error(f"pHash一括検索中にエラー: {e}", exc_info=True)
                raise

    def get_annotated_image_ids(self, image_ids: list[int]) -> set[int]:
        """指定IDリストからアノテーション済み画像IDを一括取得する。

        タグまたはキャプションが存在する画像IDのセットを返す。
        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            image_ids: 検査対象の画像IDリスト。

        Returns:
            アノテーションが存在する画像IDのセット。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return set()

        with self.session_factory() as session:
            try:
                annotated_ids: set[int] = set()
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    # EXISTS サブクエリでタグまたはキャプションの存在を判定
                    stmt = (
                        select(Image.id)
                        .where(Image.id.in_(chunk))
                        .where(
                            or_(
                                exists().where(Tag.image_id == Image.id),
                                exists().where(Caption.image_id == Image.id),
                            ),
                        )
                    )
                    result = session.execute(stmt).scalars().all()
                    annotated_ids.update(result)
                logger.debug(
                    f"アノテーション存在一括チェック: "
                    f"{len(annotated_ids)}/{len(image_ids)}件にアノテーションあり",
                )
                return annotated_ids
            except SQLAlchemyError as e:
                logger.error(
                    f"アノテーション存在一括チェック中にエラー: {e}",
                    exc_info=True,
                )
                raise

    def add_original_image(self, info: dict[str, Any]) -> int:
        """オリジナル画像のメタデータを images テーブルに追加します。
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
                logger.debug(f"オリジナル画像をDBに追加しました: ID={image_id}, UUID={new_image.uuid}")
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
                    f"オリジナル画像の追加中にデータベースエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def _find_existing_processed_image_id(
        self,
        image_id: int,
        width: int,
        height: int,
        filename: str | None,
    ) -> int | None:
        """指定された条件に一致する既存の processed_image の ID を検索します。
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
        """処理済み画像のメタデータを processed_images テーブルに追加します。
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
                logger.debug(
                    f"処理済み画像をDBに追加しました: ID={processed_image_id}, 親画像ID={image_id}",
                )
                return processed_image_id
            except IntegrityError:
                # UNIQUE 制約違反 (image_id, width, height, filename)
                session.rollback()
                logger.warning(
                    f"処理済み画像の追加中に整合性エラーが発生しました。"
                    f" (おそらく重複: image_id={image_id}, width={width}, height={height}, filename={filename})."
                    f" 既存のIDを検索します。",
                )
                # 既存のIDを検索して返す
                existing_id = self._find_existing_processed_image_id(image_id, width, height, filename)
                if existing_id:
                    logger.debug(f"既存の処理済み画像IDが見つかりました: {existing_id}")
                else:
                    # 通常ここには来ないはずだが、もし検索でも見つからなければ警告
                    logger.error(
                        f"整合性エラー後、既存の処理済み画像が見つかりませんでした。"
                        f" 条件: image_id={image_id}, width={width}, height={height}, filename={filename}",
                    )
                return existing_id  # None の可能性もある
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"処理済み画像の追加中に予期せぬデータベースエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise  # IntegrityError 以外の DB エラーは再発生させる

    # --- Annotation Saving Methods ---

    def save_annotations(
        self,
        image_id: int,
        annotations: AnnotationsDict,
        *,
        skip_existence_check: bool = False,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """指定された画像IDに対して、複数のアノテーションを一括で保存・更新します。

        各アノテーションタイプごとにUpsert処理を行います。

        Args:
            image_id: アノテーションを追加/更新する画像のID。
            annotations: 保存するアノテーションデータを含む辞書。
                キー: 'tags', 'captions', 'scores', 'ratings'
                値: 各アノテーションデータのリスト。
            skip_existence_check: Trueの場合、画像存在チェックをスキップする。
                バッチ処理等で事前に存在確認済みの場合に使用。
            tag_id_cache: 正規化済みタグ文字列→tag_idのキャッシュ辞書。
                バッチ処理で事前に一括解決済みのキャッシュを渡す。
                Noneの場合は従来通り個別に外部DB照会する。

        Raises:
            ValueError: 指定された image_id が存在しない場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not skip_existence_check and not self._image_exists(image_id):
            raise ValueError(f"指定された画像ID {image_id} は存在しません。")

        with self.session_factory() as session:
            try:
                # 各アノテーションタイプを処理
                if annotations.get("tags"):
                    self._save_tags(session, image_id, annotations["tags"], tag_id_cache=tag_id_cache)
                if annotations.get("captions"):
                    self._save_captions(session, image_id, annotations["captions"])
                if annotations.get("scores"):
                    self._save_scores(session, image_id, annotations["scores"])
                if annotations.get("ratings"):
                    self._save_ratings(session, image_id, annotations["ratings"])

                session.commit()
                logger.debug(f"画像ID {image_id} のアノテーションを保存・更新しました。")

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"画像ID {image_id} のアノテーション保存中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    @staticmethod
    def _build_existing_tags_map(session: Session, image_ids: list[int]) -> dict[int, set[str]]:
        """画像IDごとの既存タグマップを構築する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 対象画像IDリスト。

        Returns:
            image_id -> タグ名(小文字)のセットのマッピング。

        """
        existing_tags_stmt = select(Tag).where(Tag.image_id.in_(image_ids))
        all_existing_tags = session.execute(existing_tags_stmt).scalars().all()

        existing_tags_by_image: dict[int, set[str]] = {}
        for tag_obj in all_existing_tags:
            if tag_obj.image_id not in existing_tags_by_image:
                existing_tags_by_image[tag_obj.image_id] = set()
            existing_tags_by_image[tag_obj.image_id].add(tag_obj.tag.lower())
        return existing_tags_by_image

    def add_tag_to_images_batch(
        self,
        image_ids: list[int],
        tag: str,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """複数画像に1つのタグを原子的に追加(既存タグに追加、重複スキップ)

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ(正規化済み前提: lower + strip)
            model_id: モデルID(手動編集の場合はマニュアルモデルID)

        Returns:
            (成功フラグ, 追加件数)

        Raises:
            SQLAlchemyError: データベースエラー時(ロールバック後に再送出)

        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch tag add")
            return (False, 0)

        if not tag.strip():
            logger.warning("Empty tag for batch add")
            return (False, 0)

        normalized_tag = tag.strip().lower()
        added_count = 0

        with self.session_factory() as session:
            try:
                existing_tags_by_image = self._build_existing_tags_map(session, image_ids)

                for image_id in image_ids:
                    existing_tags = existing_tags_by_image.get(image_id, set())

                    if normalized_tag in existing_tags:
                        logger.debug(
                            f"Tag '{normalized_tag}' already exists for image_id {image_id}, skipping",
                        )
                        continue

                    external_tag_id = self._get_or_create_tag_id_external(session, normalized_tag)
                    if external_tag_id is None and normalized_tag:
                        logger.warning(
                            f"Tag '{normalized_tag}' could not be linked to external tag_db. "
                            "Saving with tag_id=None.",
                        )

                    new_tag = Tag(
                        image_id=image_id,
                        model_id=model_id,
                        tag=normalized_tag,
                        tag_id=external_tag_id,
                        confidence_score=None,
                        existing=False,
                        is_edited_manually=True,
                    )
                    session.add(new_tag)
                    added_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch tag add completed: tag='{normalized_tag}', "
                    f"processed={len(image_ids)}, added={added_count}",
                )
                return (True, added_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Atomic batch tag add failed, rolled back: {e}", exc_info=True)
                raise

    def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
        """外部 tag_db から tag 文字列に一致する tag_id を検索し、見つからない場合は新規作成する。

        Args:
            session: SQLAlchemy セッション (LoRAIro DB用、tag_db操作には未使用)。
            tag_string: 検索・登録するタグ文字列。

        Returns:
            見つかった/登録したtag_id。エラー時はNone。

        """
        # 1. タグの正規化（ExistingFileReaderと同一処理）
        normalized_tag = TagCleaner.clean_format(tag_string).strip()

        if not normalized_tag:
            logger.warning(f"Tag normalization resulted in empty string: '{tag_string}'")
            return None

        # 2. MergedTagReaderが利用可能か確認
        if self.merged_reader is None:
            logger.debug(
                f"MergedTagReader unavailable, skipping external tag search for '{normalized_tag}'",
            )
            return None

        logger.debug(f"Searching tag in external tag_db: '{tag_string}' → '{normalized_tag}'")

        # 3. 既存タグ検索（公開API search_tags()使用、完全一致）
        try:
            request = TagSearchRequest(
                query=normalized_tag,
                partial=False,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            result = search_tags(self.merged_reader, request)

            if result.items and len(result.items) > 0:
                tag_id: int = result.items[0].tag_id
                logger.debug(f"Found existing tag_id {tag_id} for '{normalized_tag}' in external tag_db")
                return tag_id

            # 検索結果なし → 新規タグ登録
            return self._register_new_tag(normalized_tag, tag_string, request)

        except Exception as e:
            logger.error(
                f"Error searching tag in external tag_db: '{normalized_tag}': {e}",
                exc_info=True,
            )
            return None  # 検索失敗時は縮退動作（tag_id=None で保存）  # その他のエラーも縮退動作

    def _register_new_tag(
        self,
        normalized_tag: str,
        source_tag: str,
        search_request: "TagSearchRequest",
    ) -> int | None:
        """外部tag_dbに新規タグを登録する。競合時はリトライ検索を行う。

        Args:
            normalized_tag: 正規化済みタグ文字列。
            source_tag: 元のタグ文字列。
            search_request: リトライ検索用のリクエストオブジェクト。

        Returns:
            登録されたtag_id。エラー時はNone。

        """
        logger.debug(f"Tag '{normalized_tag}' not found in external tag_db. Attempting registration...")

        # TagRegisterService遅延初期化
        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()
            if self.tag_register_service is None:
                logger.debug("TagRegisterService initialization failed, skipping tag registration")
                return None

        register_request = TagRegisterRequest(
            tag=normalized_tag,
            source_tag=source_tag,
            format_name="Lorairo",
            type_name="unknown",
        )

        try:
            register_result = self.tag_register_service.register_tag(register_request)
            tag_id = register_result.tag_id
            logger.debug(f"Registered new tag_id {tag_id} for '{normalized_tag}'")
            return tag_id
        except ValueError as ve:
            logger.error(f"Tag registration failed (invalid format/type): {ve}")
            return None
        except IntegrityError:
            # 競合検出（他のプロセスが同時に登録）→ リトライ
            logger.warning("Race condition detected during tag registration, retrying search...")
            try:
                retry_result = search_tags(self.merged_reader, search_request)
                if retry_result.items and len(retry_result.items) > 0:
                    tag_id = retry_result.items[0].tag_id
                    logger.debug(f"Found tag_id {tag_id} on retry for '{normalized_tag}'")
                    return tag_id
            except Exception as retry_error:
                logger.error(f"Retry search failed: {retry_error}", exc_info=True)
            return None
        except Exception as reg_error:
            logger.error(f"Unexpected error during tag registration: {reg_error}", exc_info=True)
            return None

    def batch_resolve_tag_ids(self, normalized_tags: set[str]) -> dict[str, int | None]:
        """正規化済みタグ文字列の集合に対して外部タグDBのtag_idを一括解決する。

        search_tags_bulk()で一括検索し、見つからなかったタグのみ個別登録する。
        deprecated=Trueのタグは除外し、現行の単発検索(include_deprecated=False)と同等の動作を保証する。

        Args:
            normalized_tags: TagCleaner.clean_format().strip()で正規化済みのタグ文字列セット。

        Returns:
            正規化済みタグ文字列→tag_id(またはNone)のマッピング辞書。

        """
        if not normalized_tags:
            return {}

        # MergedTagReaderが利用不可の場合は全てNone
        if self.merged_reader is None:
            logger.debug("MergedTagReader unavailable, skipping batch tag resolution")
            return dict.fromkeys(normalized_tags)

        # 一括検索
        try:
            bulk_results = self.merged_reader.search_tags_bulk(
                list(normalized_tags),
                format_name=None,
                resolve_preferred=False,
            )
        except Exception as e:
            logger.error(f"search_tags_bulk failed: {e}", exc_info=True)
            return dict.fromkeys(normalized_tags)

        # deprecated除外フィルタ適用（現行 include_deprecated=False と同等）
        result: dict[str, int | None] = {}
        for tag_str, row in bulk_results.items():
            if row.get("deprecated", False):
                logger.debug(f"Excluding deprecated tag from bulk result: '{tag_str}'")
                continue
            result[tag_str] = row["tag_id"]

        # 見つからなかったタグを個別登録
        missing_tags = normalized_tags - set(result.keys())
        if missing_tags:
            self._register_missing_tags(missing_tags, result)

        logger.info(
            f"Batch tag resolution complete: {len(result)} tags resolved, "
            f"{sum(1 for v in result.values() if v is not None)} with tag_id",
        )
        return result

    def _register_missing_tags(self, missing_tags: set[str], result: dict[str, int | None]) -> None:
        """バッチ検索で見つからなかったタグを個別登録する。

        Args:
            missing_tags: 登録が必要なタグ文字列のセット。
            result: 結果を格納する辞書（副作用で更新）。

        """
        logger.debug(f"Batch resolve: {len(missing_tags)} tags not found, attempting registration")

        # TagRegisterService遅延初期化
        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()

        if self.tag_register_service is None:
            # 初期化失敗 → 全てNone
            for tag_str in missing_tags:
                result[tag_str] = None
            return

        for tag_str in missing_tags:
            result[tag_str] = self._register_single_tag(tag_str)

    def _register_single_tag(self, tag_str: str) -> int | None:
        """単一タグを外部DBに登録し、tag_idを返す。

        競合検出時はリトライ検索を実行する。
        呼び出し元で self.tag_register_service is not None が保証されていること。

        Args:
            tag_str: 正規化済みタグ文字列。

        Returns:
            登録されたtag_id。失敗時はNone。

        """
        assert self.tag_register_service is not None
        try:
            register_request = TagRegisterRequest(
                tag=tag_str,
                source_tag=tag_str,
                format_name="Lorairo",
                type_name="unknown",
            )
            register_result = self.tag_register_service.register_tag(register_request)
            tag_id: int = register_result.tag_id
            logger.debug(f"Registered new tag_id {tag_id} for '{tag_str}'")
            return tag_id
        except IntegrityError:
            # 競合検出 → リトライ検索
            logger.warning(f"Race condition for '{tag_str}', retrying search...")
            return self._retry_tag_search(tag_str)
        except Exception as reg_error:
            logger.error(f"Tag registration failed for '{tag_str}': {reg_error}")
            return None

    def _retry_tag_search(self, tag_str: str) -> int | None:
        """競合検出後のリトライ検索。

        Args:
            tag_str: 検索するタグ文字列。

        Returns:
            見つかったtag_id。失敗時はNone。

        """
        try:
            retry_request = TagSearchRequest(
                query=tag_str,
                partial=False,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            retry_result = search_tags(self.merged_reader, retry_request)
            if retry_result.items:
                tag_id: int = retry_result.items[0].tag_id
                return tag_id
            return None
        except Exception as retry_error:
            logger.error(f"Retry search failed for '{tag_str}': {retry_error}")
            return None

    def _save_tags(
        self,
        session: Session,
        image_id: int,
        tags_data: list[TagAnnotationData],
        *,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """タグ情報を保存・更新 (Upsert)

        Args:
            session: SQLAlchemyセッション。
            image_id: 対象画像のID。
            tags_data: 保存するタグデータのリスト。
            tag_id_cache: 正規化済みタグ文字列→tag_idのキャッシュ。
                バッチ処理で事前解決済みの場合に渡す。キャッシュミス時は
                従来通り_get_or_create_tag_id_external()にフォールバック。

        """
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

            # 外部DBから tag_id を取得/作成
            # キャッシュがある場合は正規化後のタグで検索し、ミス時はフォールバック
            external_tag_id: int | None = None
            if tag_id_cache is not None:
                normalized_key = TagCleaner.clean_format(tag_string).strip()
                if normalized_key in tag_id_cache:
                    external_tag_id = tag_id_cache[normalized_key]
                else:
                    # キャッシュミス: 従来の個別照会にフォールバック
                    external_tag_id = self._get_or_create_tag_id_external(session, tag_string)
            else:
                external_tag_id = self._get_or_create_tag_id_external(session, tag_string)

            if external_tag_id is None and tag_string:
                logger.warning(
                    f"Tag '{tag_string}' could not be linked to external tag_db. "
                    "Saving with tag_id=None (limited taxonomy features).",
                )

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
        self,
        session: Session,
        image_id: int,
        captions_data: list[CaptionAnnotationData],
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
                    "is_edited_manually",
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
        self,
        session: Session,
        image_id: int,
        ratings_data: list[RatingAnnotationData],
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
        """指定されたIDのオリジナル画像メタデータを辞書形式で取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。
                - rating_value: 最新のRating値（ratingsテーブルから取得）
                - score_value: 最新のScore値（scoresテーブルから取得）

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        with self.session_factory() as session:
            try:
                # 主キー検索には session.get が効率的
                # relationshipをeager loadingで取得（ratings, scores）
                stmt = (
                    select(Image)
                    .where(Image.id == image_id)
                    .options(
                        selectinload(Image.ratings),
                        selectinload(Image.scores),
                    )
                )
                image: Image | None = session.execute(stmt).scalar_one_or_none()

                if image is None:
                    logger.warning(f"画像メタデータが見つかりません: image_id={image_id}")
                    return None

                # SQLAlchemy オブジェクトを辞書に変換
                metadata = {c.name: getattr(image, c.name) for c in image.__table__.columns}

                # Rating/Score情報を整形して追加（Issue #4対応）
                annotations = self._format_annotations_for_metadata(image)
                metadata.update(annotations)

                logger.debug(f"画像メタデータを取得しました: image_id={image_id}")
                return metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"画像メタデータの取得中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def get_images_metadata_batch(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """指定された複数IDのオリジナル画像メタデータを一括取得する。

        内部的に _fetch_filtered_metadata() を使用し、joinedloadで取得する。
        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            image_ids: 取得する画像IDのリスト。

        Returns:
            画像メタデータ辞書のリスト。見つからなかったIDは結果に含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return []

        with self.session_factory() as session:
            try:
                # チャンク分割でSQLiteバインド変数上限を回避
                result: list[dict[str, Any]] = []
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    result.extend(self._fetch_filtered_metadata(session, chunk, resolution=0))
                return result
            except SQLAlchemyError as e:
                logger.error(
                    f"画像メタデータの一括取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def get_processed_image(
        self,
        image_id: int,
        resolution: int = 0,
        all_data: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:  # 戻り値の型を調整
        """指定された image_id に関連する処理済み画像のメタデータを取得します。
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
                        f"全 {len(metadata_list)} 件の処理済み画像メタデータを取得しました: image_id={image_id}",
                    )
                    return metadata_list

                # 解像度に基づいてフィルタリング
                selected_metadata: dict[str, Any] | None = None
                if resolution == 0:
                    # 最も解像度が低いもの (面積で比較)
                    selected_metadata = min(metadata_list, key=lambda x: x["width"] * x["height"])
                    logger.debug(
                        f"最低解像度の処理済み画像を選択しました: image_id={image_id}, id={selected_metadata['id']}",
                    )
                else:
                    # 指定解像度に最も近いものを選択
                    selected_metadata = self._filter_by_resolution(metadata_list, resolution)

                # all_data=False の場合、ここで選択されたメタデータ (またはNone) を返す
                if not all_data:
                    if selected_metadata:
                        logger.debug(
                            f"解像度 {resolution} に一致する処理済み画像を選択しました: image_id={image_id}, id={selected_metadata.get('id')}",
                        )
                    else:
                        logger.warning(
                            f"解像度 {resolution} に一致する処理済み画像が見つかりませんでした: image_id={image_id}",
                        )
                    return selected_metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"処理済み画像の取得中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def _filter_by_resolution(
        self,
        metadata_list: list[dict[str, Any]],
        resolution: int,
    ) -> dict[str, Any] | None:
        """解像度に基づいてメタデータをフィルタリングします。
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
                    f"解像度パラメータが文字列として渡されました: '{resolution}' -> {resolution}",
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
                f"Closest resolution match found (error: {min_error_ratio:.2f}): {best_match['id']}",
            )
        else:
            logger.debug(f"No suitable processed image found for resolution {resolution}")

        return best_match  # Return the best match found within tolerance, or None

    @staticmethod
    def _format_tag_annotation(tag: Any) -> dict[str, Any]:
        """タグアノテーションをdict形式にフォーマットする。

        Args:
            tag: タグORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
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

    @staticmethod
    def _format_caption_annotation(caption: Any) -> dict[str, Any]:
        """キャプションアノテーションをdict形式にフォーマットする。

        Args:
            caption: キャプションORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": caption.id,
            "caption": caption.caption,
            "model_id": caption.model_id,
            "existing": caption.existing,
            "is_edited_manually": caption.is_edited_manually,
            "created_at": caption.created_at,
            "updated_at": caption.updated_at,
        }

    @staticmethod
    def _format_score_annotation(score: Any) -> dict[str, Any]:
        """スコアアノテーションをdict形式にフォーマットする。

        Args:
            score: スコアORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": score.id,
            "score": score.score,
            "model_id": score.model_id,
            "is_edited_manually": score.is_edited_manually,
            "created_at": score.created_at,
            "updated_at": score.updated_at,
        }

    @staticmethod
    def _format_rating_annotation(rating: Any) -> dict[str, Any]:
        """レーティングアノテーションをdict形式にフォーマットする。

        Args:
            rating: レーティングORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": rating.id,
            "raw_rating_value": rating.raw_rating_value,
            "normalized_rating": rating.normalized_rating,
            "model_id": rating.model_id,
            "confidence_score": rating.confidence_score,
            "created_at": rating.created_at,
            "updated_at": rating.updated_at,
        }

    def get_image_annotations(self, image_id: int) -> dict[str, list[dict[str, Any]]]:
        """指定された画像IDのアノテーション(タグ、キャプション、スコア、レーティング)を取得する。

        Eager Loadingを使用して関連データを効率的に取得する。

        Args:
            image_id: アノテーションを取得する画像のID。

        Returns:
            アノテーションデータを含む辞書。
            キー: 'tags', 'captions', 'scores', 'ratings'
            画像が存在しない場合は空のリストを持つ辞書を返す。

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
                    return annotations

                if image.tags:
                    annotations["tags"] = [self._format_tag_annotation(t) for t in image.tags]
                if image.captions:
                    annotations["captions"] = [self._format_caption_annotation(c) for c in image.captions]
                if image.scores:
                    annotations["scores"] = [self._format_score_annotation(s) for s in image.scores]
                if image.ratings:
                    annotations["ratings"] = [self._format_rating_annotation(r) for r in image.ratings]

                logger.info(
                    f"取得したアノテーション数: tags={len(annotations['tags'])}, "
                    f"captions={len(annotations['captions'])}, scores={len(annotations['scores'])}, "
                    f"ratings={len(annotations['ratings'])} for image_id={image_id}",
                )
                return annotations

            except SQLAlchemyError as e:
                logger.error(
                    f"画像ID {image_id} のアノテーション取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def _parse_datetime_str(self, date_str: str | None) -> datetime.datetime | None:
        """日付文字列を UTC timezone-aware datetime オブジェクトに変換。

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

    def _apply_ai_rating_filter(self, query: Select, ai_rating_filter: str) -> Select:
        """クエリにAI評価レーティングフィルタを適用します (多数決ロジック)。

        1つの画像に複数のAIモデルによる異なる評価がある場合、
        50%以上のAI評価が指定されたレーティングと一致する画像のみを返します。

        Args:
            query (Select): 適用対象のクエリ
            ai_rating_filter (str): フィルタリングするレーティング値 (PG, PG-13, R, X, XXX, UNRATED)

        Returns:
            Select: AIレーティングフィルタが適用されたクエリ

        """
        logger.debug(f"Applying AI rating filter (majority vote) for rating: '{ai_rating_filter}'")

        # UNRATED: レーティングが存在しない画像をフィルタ
        if ai_rating_filter == "UNRATED":
            has_any_rating = exists(select(Rating.id).where(Rating.image_id == Image.id)).correlate(Image)
            query = query.where(not_(has_any_rating))
            logger.debug("AI rating filter applied: UNRATED (no ratings)")
            return query

        # 多数決ロジック: 画像ごとに総AI評価数とマッチング数を計算
        # マッチング数 >= 総評価数 / 2.0 の画像のみを返す

        # サブクエリ1: 画像ごとの総AI評価数
        total_ratings_subquery = (
            select(Rating.image_id, func.count(Rating.id).label("total_count"))
            .group_by(Rating.image_id)
            .subquery()
        )

        # サブクエリ2: 画像ごとのマッチング評価数
        matching_ratings_subquery = (
            select(Rating.image_id, func.count(Rating.id).label("matching_count"))
            .where(func.lower(Rating.normalized_rating) == ai_rating_filter.lower())
            .group_by(Rating.image_id)
            .subquery()
        )

        # EXISTS条件: マッチング数 >= 総評価数 / 2.0
        # COALESCE(matching_count, 0) で、マッチが0件の画像も処理
        majority_vote_condition = exists(
            select(1)
            .select_from(total_ratings_subquery)
            .outerjoin(
                matching_ratings_subquery,
                total_ratings_subquery.c.image_id == matching_ratings_subquery.c.image_id,
            )
            .where(
                total_ratings_subquery.c.image_id == Image.id,
                func.coalesce(matching_ratings_subquery.c.matching_count, 0)
                >= (total_ratings_subquery.c.total_count / 2.0),
            ),
        ).correlate(Image)

        query = query.where(majority_vote_condition)
        logger.debug("AI rating filter applied with majority vote logic")
        return query

    def _apply_unrated_filter(self, query: Select, include_unrated: bool) -> Select:
        """クエリに未評価画像フィルタを適用します (Either-based ロジック)。

        include_unrated=False の場合、手動評価またはAI評価のいずれか1つ以上を持つ画像のみを返します。
        include_unrated=True の場合、フィルタリングを行いません。

        Args:
            query (Select): 適用対象のクエリ
            include_unrated (bool): 未評価画像を含めるかどうか

        Returns:
            Select: 未評価フィルタが適用されたクエリ

        """
        if not include_unrated:
            logger.debug("Applying unrated filter: excluding images with neither manual nor AI rating")

            # Either-based logic: 手動評価またはAI評価のいずれかが存在する
            has_manual_rating = Image.manual_rating.is_not(None)
            has_ai_rating = exists().where(Rating.image_id == Image.id).correlate(Image)

            # 少なくとも1つの評価が存在する画像のみを含める
            query = query.where(or_(has_manual_rating, has_ai_rating))
            logger.debug("Unrated filter applied: images must have at least one rating (manual OR AI)")

        return query

    def _apply_nsfw_filter(self, query: Select, include_nsfw: bool, session: Session) -> Select:
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

            # 手動レーティングに基づく除外条件（ratingsテーブルから最新のMANUAL_EDIT ratingを参照）
            manual_edit_model_id = self._get_or_create_manual_edit_model(session)
            manual_nsfw_condition = (
                exists()
                .where(
                    Rating.image_id == Image.id,
                    Rating.model_id == manual_edit_model_id,
                    func.lower(Rating.normalized_rating).in_(nsfw_ratings),
                )
                .correlate(Image)
            )

            # AIレーティングまたは手動レーティングがNSFWである画像を除外
            query = query.where(not_(or_(ai_nsfw_condition, manual_nsfw_condition)))
            # レーティング情報がない (NULL) 画像は除外しない
        return query

    def _apply_score_filter(
        self,
        query: Select,
        score_min: float | None,
        score_max: float | None,
    ) -> Select:
        """クエリにスコア範囲フィルタを適用します。

        Args:
            query: 適用対象のクエリ
            score_min: 最小スコア値（0.0-10.0）
            score_max: 最大スコア値（0.0-10.0）

        Returns:
            フィルタ適用済みのクエリ

        """
        if score_min is None and score_max is None:
            return query

        from lorairo.database.schema import Score

        # DB値（0.0-10.0）で直接比較
        db_min = score_min if score_min is not None else 0.0
        db_max = score_max if score_max is not None else 10.0

        # 指定範囲内のスコアを持つ画像のみを含める
        score_condition = (
            exists()
            .where(
                Score.image_id == Image.id,
                Score.score >= db_min,
                Score.score <= db_max,
            )
            .correlate(Image)
        )

        query = query.where(score_condition)
        logger.debug(
            f"Score filter applied: {db_min:.2f} - {db_max:.2f}",
        )

        return query

    def _apply_manual_filters(
        self,
        query: Select,
        manual_rating_filter: str | None,
        manual_edit_filter: bool | None,
        session: Session,
    ) -> Select:
        """クエリに手動評価と手動編集フラグのフィルタを適用します。"""
        if manual_rating_filter:
            manual_edit_model_id = self._get_or_create_manual_edit_model(session)

            if manual_rating_filter == "UNRATED":
                # 手動レーティングが設定されていない画像をフィルタ
                has_manual_rating_subq = (
                    select(Rating.image_id).where(Rating.model_id == manual_edit_model_id).distinct()
                )
                query = query.where(Image.id.notin_(has_manual_rating_subq))
            else:
                # 特定の手動レーティングを持つ画像をフィルタ
                manual_rating_subq = (
                    select(Rating.image_id)
                    .where(Rating.normalized_rating == manual_rating_filter)
                    .where(Rating.model_id == manual_edit_model_id)
                    .distinct()
                )
                query = query.where(Image.id.in_(manual_rating_subq))

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

    def _format_tags(self, image: Image, annotations: dict[str, Any]) -> None:
        """タグアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.tags:
            annotations["tags"] = [
                {
                    "id": tag.id,
                    "tag": tag.tag,
                    "tag_id": tag.tag_id,
                    "model_id": tag.model_id,
                    "model_name": tag.model.name if tag.model else "Unknown",
                    "source": "Manual" if (tag.is_edited_manually or tag.existing) else "AI",
                    "existing": tag.existing,
                    "is_edited_manually": tag.is_edited_manually,
                    "confidence_score": tag.confidence_score,
                    "created_at": tag.created_at,
                    "updated_at": tag.updated_at,
                }
                for tag in image.tags
            ]
            annotations["tags_text"] = ", ".join([tag.tag for tag in image.tags])
        else:
            annotations["tags"] = []
            annotations["tags_text"] = ""

    def _format_captions(self, image: Image, annotations: dict[str, Any]) -> None:
        """キャプションアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.captions:
            annotations["captions"] = [
                {
                    "id": caption.id,
                    "caption": caption.caption,
                    "model_id": caption.model_id,
                    "model_name": caption.model.name if caption.model else "Unknown",
                    "existing": caption.existing,
                    "is_edited_manually": caption.is_edited_manually,
                    "created_at": caption.created_at,
                    "updated_at": caption.updated_at,
                }
                for caption in image.captions
            ]
            from datetime import datetime

            latest_caption = max(
                image.captions,
                key=lambda c: c.created_at if c.created_at else datetime.min,
            )
            annotations["caption_text"] = latest_caption.caption
        else:
            annotations["captions"] = []
            annotations["caption_text"] = ""

    def _format_scores(self, image: Image, annotations: dict[str, Any]) -> None:
        """スコアアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.scores:
            annotations["scores"] = [
                {
                    "id": score.id,
                    "score": score.score,
                    "model_id": score.model_id,
                    "model_name": score.model.name if score.model else "Unknown",
                    "is_edited_manually": score.is_edited_manually,
                    "created_at": score.created_at,
                    "updated_at": score.updated_at,
                }
                for score in image.scores
            ]
            latest_score = max(image.scores, key=lambda s: s.created_at)
            annotations["score_value"] = latest_score.score
        else:
            annotations["scores"] = []
            annotations["score_value"] = 0.0

    def _format_ratings(self, image: Image, annotations: dict[str, Any]) -> None:
        """レーティングアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
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
            latest_rating = max(image.ratings, key=lambda r: r.created_at)
            annotations["rating_value"] = latest_rating.normalized_rating
        else:
            annotations["ratings"] = []
            annotations["rating_value"] = ""

    def _format_annotations_for_metadata(self, image: Image) -> dict[str, Any]:
        """画像のアノテーション情報を辞書形式にフォーマット。

        Args:
            image: 画像オブジェクト。

        Returns:
            フォーマット済みアノテーション情報辞書。

        """
        annotations: dict[str, Any] = {}

        self._format_tags(image, annotations)
        self._format_captions(image, annotations)
        self._format_scores(image, annotations)
        self._format_ratings(image, annotations)

        logger.debug(
            f"Formatted annotations: tags={len(annotations.get('tags', []))}, "
            f"captions={len(annotations.get('captions', []))}, "
            f"scores={len(annotations.get('scores', []))}, "
            f"ratings={len(annotations.get('ratings', []))}",
        )

        return annotations

    def _fetch_original_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
    ) -> list[dict[str, Any]]:
        """オリジナル画像のメタデータをアノテーション付きで取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。

        Returns:
            メタデータ辞書のリスト。

        """
        from sqlalchemy.orm import joinedload

        orig_stmt = (
            select(Image)
            .where(Image.id.in_(image_ids))
            .options(
                joinedload(Image.tags).joinedload(Tag.model),
                joinedload(Image.captions).joinedload(Caption.model),
                joinedload(Image.scores).joinedload(Score.model),
                joinedload(Image.ratings),
            )
        )
        orig_results: list[Image] = list(session.execute(orig_stmt).unique().scalars().all())

        result = []
        for img in orig_results:
            metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
            metadata.update(self._format_annotations_for_metadata(img))
            result.append(metadata)
        return result

    def _fetch_processed_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """処理済み画像のメタデータをアノテーション付きで取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。
            resolution: 対象解像度。

        Returns:
            メタデータ辞書のリスト。

        """
        from sqlalchemy.orm import joinedload

        proc_stmt = select(ProcessedImage).where(ProcessedImage.image_id.in_(image_ids))
        all_proc_images = session.execute(proc_stmt).scalars().all()

        # Original Imageのアノテーション情報を一括取得
        orig_annotations_stmt = (
            select(Image)
            .where(Image.id.in_(image_ids))
            .options(
                joinedload(Image.tags).joinedload(Tag.model),
                joinedload(Image.captions).joinedload(Caption.model),
                joinedload(Image.scores).joinedload(Score.model),
                joinedload(Image.ratings),
            )
        )
        orig_images = session.execute(orig_annotations_stmt).unique().scalars().all()
        annotations_by_image_id = {
            img.id: self._format_annotations_for_metadata(img) for img in orig_images
        }

        # image_id ごとにグループ化
        proc_images_by_id: dict[int, list[dict[str, Any]]] = {}
        for img in all_proc_images:
            if img.image_id not in proc_images_by_id:
                proc_images_by_id[img.image_id] = []
            proc_metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
            if img.image_id in annotations_by_image_id:
                proc_metadata.update(annotations_by_image_id[img.image_id])
            proc_images_by_id[img.image_id].append(proc_metadata)

        result = []
        for image_id in image_ids:
            metadata_list = proc_images_by_id.get(image_id, [])
            if metadata_list:
                selected = self._filter_by_resolution(metadata_list, resolution)
                if selected:
                    result.append(selected)
        return result

    def _fetch_filtered_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """フィルタリングされたIDリストに基づき、指定解像度のメタデータを取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。
            resolution: 対象解像度(0はオリジナル)。

        Returns:
            メタデータ辞書のリスト。

        """
        if not image_ids:
            return []

        if resolution == 0:
            return self._fetch_original_image_metadata(session, image_ids)
        return self._fetch_processed_image_metadata(session, image_ids, resolution)

    # --- Main Filter Method ---

    def _build_image_filter_query(
        self,
        session: Session,
        tags: list[str] | None,
        caption: str | None,
        use_and: bool,
        start_date: str | None,
        end_date: str | None,
        include_untagged: bool,
        include_nsfw: bool,
        include_unrated: bool,
        manual_rating_filter: str | None,
        ai_rating_filter: str | None,
        manual_edit_filter: bool | None,
        score_min: float | None = None,
        score_max: float | None = None,
    ) -> Select:
        """画像フィルタ条件を適用したクエリを構築する。

        Args:
            session: SQLAlchemyセッション。
            tags: 検索タグリスト。
            caption: 検索キャプション文字列。
            use_and: 複数タグのAND/OR指定。
            start_date: 検索開始日時(ISO 8601)。
            end_date: 検索終了日時(ISO 8601)。
            include_untagged: タグなし画像のみ対象とするか。
            include_nsfw: NSFWコンテンツを含むか。
            include_unrated: 未評価画像を含むか。
            manual_rating_filter: 手動レーティングフィルタ。
            ai_rating_filter: AI評価フィルタ。
            manual_edit_filter: 手動編集フラグフィルタ。
            score_min: 最小スコア値（0.0-10.0）。
            score_max: 最大スコア値（0.0-10.0）。

        Returns:
            フィルタ適用済みのSelectクエリ。

        """
        query = select(Image.id)

        start_dt = self._parse_datetime_str(start_date)
        end_dt = self._parse_datetime_str(end_date)
        query = self._apply_date_filter(query, start_dt, end_dt)

        if include_untagged and (tags or caption):
            logger.warning("検索語句と include_untagged が同時に指定されたため、検索語句は無視されます。")

        query = self._apply_tag_filter(query, tags, use_and, include_untagged)
        query = self._apply_caption_filter(query, caption)

        # Rating Filters (Priority-based: manual > AI)
        if manual_rating_filter:
            logger.debug("Applying manual rating filter (priority over AI rating filter)")
            query = self._apply_manual_filters(query, manual_rating_filter, manual_edit_filter, session)
        elif ai_rating_filter:
            logger.debug("Applying AI rating filter (no manual rating filter specified)")
            query = self._apply_ai_rating_filter(query, ai_rating_filter)
            query = self._apply_manual_filters(query, None, manual_edit_filter, session)
        else:
            query = self._apply_manual_filters(query, None, manual_edit_filter, session)

        # Unrated Filter
        query = self._apply_unrated_filter(query, include_unrated)

        # NSFW Filter
        nsfw_values_to_exclude = {"r", "x", "xxx"}
        apply_nsfw_exclusion = not include_nsfw and (
            (manual_rating_filter is None or manual_rating_filter.lower() not in nsfw_values_to_exclude)
            and (ai_rating_filter is None or ai_rating_filter.lower() not in nsfw_values_to_exclude)
        )
        if apply_nsfw_exclusion:
            query = self._apply_nsfw_filter(query, include_nsfw=False, session=session)
        elif include_nsfw:
            query = self._apply_nsfw_filter(query, include_nsfw=True, session=session)

        # Score Filter
        query = self._apply_score_filter(query, score_min, score_max)

        return query.distinct()

    def get_images_by_filter(
        self,
        criteria: ImageFilterCriteria | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """指定された条件に基づいて画像をフィルタリングし、メタデータと件数を返す。

        Args:
            criteria: ImageFilterCriteria形式のフィルター条件（推奨）
            **kwargs: レガシー形式のキーワード引数（後方互換性用）

        Returns:
            条件にマッチした画像メタデータのリストとその総数。
        """
        # criteriaが指定されていればそれを使用、なければkwargsから生成
        filter_criteria = criteria if criteria else ImageFilterCriteria.from_kwargs(**kwargs)

        # 型安全性チェック: resolution が文字列の場合は int に変換
        if isinstance(filter_criteria.resolution, str):
            try:
                filter_criteria.resolution = int(filter_criteria.resolution)
                logger.warning(
                    f"解像度パラメータが文字列として渡されました: '{filter_criteria.resolution}' -> "
                    f"{filter_criteria.resolution}",
                )
            except ValueError:
                logger.error(f"解像度パラメータの変換に失敗しました: '{filter_criteria.resolution}'")
                return [], 0

        with self.session_factory() as session:
            try:
                query = self._build_image_filter_query(
                    session=session,
                    tags=filter_criteria.tags,
                    caption=filter_criteria.caption,
                    use_and=filter_criteria.use_and,
                    start_date=filter_criteria.start_date,
                    end_date=filter_criteria.end_date,
                    include_untagged=filter_criteria.include_untagged,
                    include_nsfw=filter_criteria.include_nsfw,
                    include_unrated=filter_criteria.include_unrated,
                    manual_rating_filter=filter_criteria.manual_rating_filter,
                    ai_rating_filter=filter_criteria.ai_rating_filter,
                    manual_edit_filter=filter_criteria.manual_edit_filter,
                    score_min=filter_criteria.score_min,
                    score_max=filter_criteria.score_max,
                )

                filtered_image_ids: list[int] = list(session.execute(query).scalars().all())

                if not filtered_image_ids:
                    logger.info("指定された条件に一致する画像が見つかりませんでした。")
                    return [], 0

                logger.debug(f"フィルタリングで {len(filtered_image_ids)} 件の候補画像IDを取得しました。")

                final_metadata_list = self._fetch_filtered_metadata(
                    session, filtered_image_ids, filter_criteria.resolution
                )
                list_count = len(final_metadata_list)
                logger.info(f"最終的な検索結果: {list_count} 件")

                return final_metadata_list, list_count

            except SQLAlchemyError as e:
                logger.error(f"画像フィルタリング検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    # --- Model Information Retrieval ---

    def get_models(self) -> list[dict[str, Any]]:
        """データベースに登録されている全てのモデルの情報を取得します。
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
        """データベースから実際のModelオブジェクトを直接取得します（DB中心アーキテクチャ用）

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
        """指定されたタイプ名を持つモデルの情報を取得します。

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
                    f"タイプ '{model_type_name}' のモデル情報を取得しました。 件数: {len(model_list)}",
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
        """指定された画像IDの manual_rating を更新します。

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
                    f"Manual rating の更新中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def update_annotation_manual_edit_flag(
        self,
        annotation_type: str,
        annotation_id: int,
        is_edited: bool,
    ) -> bool:
        """指定されたアノテーションの is_edited_manually フラグを更新します。

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
                        f"type={annotation_type}, id={annotation_id}",
                    )
                    return False
                session.commit()
                logger.info(
                    f"{annotation_type} ID {annotation_id} の is_edited_manually を {is_edited} に更新しました。",
                )
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"手動編集フラグの更新中にエラーが発生しました (Type: {annotation_type}, ID: {annotation_id}): {e}",
                    exc_info=True,
                )
                raise

    # --- Error Record Management Methods ---

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
        """エラーレコードを保存

        Args:
            operation_type: 操作種別 ("registration" | "annotation" | "processing")
            error_type: エラー種別 ("pHash calculation" | "API error" | "DB constraint")
            error_message: エラーメッセージ
            image_id: 画像ID (Optional)
            stack_trace: スタックトレース (Optional)
            file_path: ファイルパス (Optional)
            model_name: モデル名 (Optional)

        Returns:
            int: 作成された error_record_id

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        with self.session_factory() as session:
            try:
                record = ErrorRecord(
                    image_id=image_id,
                    operation_type=operation_type,
                    error_type=error_type,
                    error_message=error_message,
                    stack_trace=stack_trace,
                    file_path=file_path,
                    model_name=model_name,
                    retry_count=0,
                )
                session.add(record)
                session.flush()
                error_id = record.id
                session.commit()
                logger.info(
                    f"エラーレコードを保存しました: ID={error_id}, "
                    f"operation={operation_type}, type={error_type}",
                )
                return error_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エラーレコードの保存中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_count_unresolved(self, operation_type: str | None = None) -> int:
        """未解決エラー件数を取得（resolved_at IS NULL）

        Args:
            operation_type: 操作種別（None = 全操作）

        Returns:
            int: 未解決エラー件数

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        with self.session_factory() as session:
            try:
                query = select(func.count(ErrorRecord.id)).where(ErrorRecord.resolved_at.is_(None))
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                count = session.execute(query).scalar() or 0
                logger.debug(
                    f"未解決エラー件数を取得: {count}件 (operation_type={operation_type or 'all'})",
                )
                return count
            except SQLAlchemyError as e:
                logger.error(f"未解決エラー件数の取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_image_ids(self, operation_type: str | None = None, resolved: bool = False) -> list[int]:
        """エラー画像のID一覧を取得

        Args:
            operation_type: 操作種別フィルタ
            resolved: True = 解決済み（resolved_at IS NOT NULL）、
                     False = 未解決（resolved_at IS NULL）

        Returns:
            list[int]: 画像IDリスト（重複除去済み、Noneを除外）

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        with self.session_factory() as session:
            try:
                query = select(ErrorRecord.image_id).distinct().where(ErrorRecord.image_id.is_not(None))
                if resolved:
                    query = query.where(ErrorRecord.resolved_at.is_not(None))
                else:
                    query = query.where(ErrorRecord.resolved_at.is_(None))
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)

                results = session.execute(query).scalars().all()
                image_ids = [id for id in results if id is not None]
                logger.debug(
                    f"エラー画像ID一覧を取得: {len(image_ids)}件 "
                    f"(operation_type={operation_type or 'all'}, resolved={resolved})",
                )
                return image_ids
            except SQLAlchemyError as e:
                logger.error(f"エラー画像ID一覧の取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_images_by_ids(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """画像IDリストから画像メタデータを取得

        Args:
            image_ids: 画像IDリスト

        Returns:
            list[dict]: 画像メタデータリスト（既存フォーマット互換）

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        if not image_ids:
            return []

        with self.session_factory() as session:
            try:
                # アノテーション情報を含めて取得
                from sqlalchemy.orm import joinedload

                stmt = (
                    select(Image)
                    .where(Image.id.in_(image_ids))
                    .options(
                        joinedload(Image.tags).joinedload(Tag.model),
                        joinedload(Image.captions).joinedload(Caption.model),
                        joinedload(Image.scores).joinedload(Score.model),
                        joinedload(Image.ratings),
                    )
                )
                images = session.execute(stmt).unique().scalars().all()

                # 既存の get_images_by_filter と同じフォーマットで返す
                metadata_list = []
                for img in images:
                    metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
                    # アノテーション情報を追加
                    metadata.update(self._format_annotations_for_metadata(img))
                    metadata_list.append(metadata)

                logger.debug(f"画像メタデータを取得: {len(metadata_list)}件")
                return metadata_list
            except SQLAlchemyError as e:
                logger.error(f"画像メタデータの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_error_records(
        self,
        operation_type: str | None = None,
        resolved: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ErrorRecord]:
        """エラーレコードを取得（ページネーション対応）

        Args:
            operation_type: 操作種別フィルタ
            resolved: None = 全て、True = 解決済み、False = 未解決
            limit: 取得件数上限
            offset: オフセット

        Returns:
            list[ErrorRecord]: エラーレコードリスト

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        with self.session_factory() as session:
            try:
                query = select(ErrorRecord).order_by(ErrorRecord.created_at.desc())
                if operation_type:
                    query = query.where(ErrorRecord.operation_type == operation_type)
                if resolved is not None:
                    if resolved:
                        query = query.where(ErrorRecord.resolved_at.is_not(None))
                    else:
                        query = query.where(ErrorRecord.resolved_at.is_(None))
                query = query.limit(limit).offset(offset)
                records = list(session.execute(query).scalars().all())
                logger.debug(
                    f"エラーレコードを取得: {len(records)}件 "
                    f"(operation_type={operation_type or 'all'}, "
                    f"resolved={resolved}, limit={limit}, offset={offset})",
                )
                return records
            except SQLAlchemyError as e:
                logger.error(f"エラーレコードの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def mark_error_resolved(self, error_id: int) -> None:
        """エラーを解決済みにマーク（resolved_at = 現在時刻）

        Args:
            error_id: エラーレコードID

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        from datetime import UTC

        with self.session_factory() as session:
            try:
                record = session.get(ErrorRecord, error_id)
                if record:
                    record.resolved_at = datetime.datetime.now(UTC)
                    session.commit()
                    logger.info(f"エラーレコードを解決済みにマーク: ID={error_id}")
                else:
                    logger.warning(f"エラーレコードが見つかりません: ID={error_id}")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エラーレコードの解決マーク中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_session(self) -> Session:
        """セッションを取得（Manager層で生SQLを実行する際に使用）

        Returns:
            Session: SQLAlchemyセッション

        """
        return self.session_factory()

    def get_image_id_by_filepath(self, filepath: str) -> int | None:
        """ファイルパスから画像IDを取得

        Args:
            filepath: 画像ファイルの絶対パスまたは相対パス

        Returns:
            int | None: 画像ID（見つからない場合は None）

        """
        with self.session_factory() as session:
            try:
                from pathlib import Path

                from ..database.db_core import resolve_stored_path

                input_path = Path(filepath).resolve()
                filename = input_path.name

                # filenameで候補を検索
                stmt = select(Image).where(Image.filename == filename)
                results = session.execute(stmt).scalars().all()

                # 候補が見つかった場合、stored_image_pathを正規化して比較
                for image in results:
                    resolved_stored_path = resolve_stored_path(image.stored_image_path)
                    if resolved_stored_path.resolve() == input_path:
                        return image.id

                return None

            except Exception as e:
                logger.error(f"ファイルパスからの画像ID取得エラー: {filepath}, {e}")
                return None

    def update_rating_batch(
        self,
        image_ids: list[int],
        rating: str,
        model_id: int,
    ) -> tuple[bool, int]:
        """複数画像のRatingを原子的に更新（既存レコードは更新、なければ挿入）

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            rating: Rating値（正規化済み: "PG", "PG-13", "R", "X", "XXX"）
            model_id: モデルID（手動編集の場合はマニュアルモデルID）

        Returns:
            (成功フラグ, 更新件数)

        Raises:
            SQLAlchemyError: データベースエラー時（ロールバック後に再送出）
        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch rating update")
            return (False, 0)

        if not rating.strip():
            logger.warning("Empty rating for batch update")
            return (False, 0)

        normalized_rating = rating.strip()
        updated_count = 0

        with self.session_factory() as session:
            try:
                # 既存の Rating レコードを一括取得（N+1回避）
                existing_ratings_stmt = select(Rating).where(Rating.image_id.in_(image_ids))
                existing_ratings = session.execute(existing_ratings_stmt).scalars().all()
                existing_rating_map = {r.image_id: r for r in existing_ratings}

                for image_id in image_ids:
                    if image_id in existing_rating_map:
                        # 既存レコードを UPDATE
                        existing_rating = existing_rating_map[image_id]
                        existing_rating.normalized_rating = normalized_rating
                        existing_rating.raw_rating_value = normalized_rating
                        existing_rating.model_id = model_id
                        existing_rating.confidence_score = None  # 手動編集時は信頼度なし
                        existing_rating.updated_at = func.now()
                        logger.debug(f"Updated rating for image_id {image_id}")
                    else:
                        # 新規レコードを INSERT
                        new_rating = Rating(
                            image_id=image_id,
                            model_id=model_id,
                            raw_rating_value=normalized_rating,
                            normalized_rating=normalized_rating,
                            confidence_score=None,
                        )
                        session.add(new_rating)
                        logger.debug(f"Inserted new rating for image_id {image_id}")

                    updated_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch rating update completed: rating='{normalized_rating}', "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
                return (True, updated_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Batch rating update failed: rating='{normalized_rating}', "
                    f"image_ids={len(image_ids)}, error={e}",
                    exc_info=True,
                )
                raise

    def update_score_batch(
        self,
        image_ids: list[int],
        score: float,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """複数画像のScoreを原子的に更新（既存レコードは更新、なければ挿入）

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            score: Score値（DB値 0.0-10.0）
            model_id: モデルID（手動編集の場合はマニュアルモデルID、Noneも許容）

        Returns:
            (成功フラグ, 更新件数)

        Raises:
            SQLAlchemyError: データベースエラー時（ロールバック後に再送出）
        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch score update")
            return (False, 0)

        if not (0.0 <= score <= 10.0):
            logger.warning(f"Invalid score value for batch update: {score}")
            return (False, 0)

        updated_count = 0

        with self.session_factory() as session:
            try:
                # 既存の Score レコードを一括取得（N+1回避）
                existing_scores_stmt = select(Score).where(Score.image_id.in_(image_ids))
                existing_scores = session.execute(existing_scores_stmt).scalars().all()
                existing_score_map = {s.image_id: s for s in existing_scores}

                for image_id in image_ids:
                    if image_id in existing_score_map:
                        # 既存レコードを UPDATE
                        existing_score = existing_score_map[image_id]
                        existing_score.score = score
                        existing_score.model_id = model_id
                        existing_score.is_edited_manually = True
                        existing_score.updated_at = func.now()
                        logger.debug(f"Updated score for image_id {image_id}")
                    else:
                        # 新規レコードを INSERT
                        new_score = Score(
                            image_id=image_id,
                            model_id=model_id,
                            score=score,
                            is_edited_manually=True,
                        )
                        session.add(new_score)
                        logger.debug(f"Inserted new score for image_id {image_id}")

                    updated_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch score update completed: score={score:.2f}, "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
                return (True, updated_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Batch score update failed: score={score:.2f}, image_ids={len(image_ids)}, error={e}",
                    exc_info=True,
                )
                raise
