"""Model / ModelType 永続化担当 Repository (ADR 0035 §1)。

`ImageRepository` god class 分割の段階 1 として、Model / ModelType 関連の
CRUD・検索を本 Repository に集約する。

ADR 0023 Phase 1.11 (Issue #238) の registry key SSoT 設計に基づき、
`Model.litellm_model_id` (UNIQUE NOT NULL) を一意キーとして扱う。
"""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from ...utils.log import logger
from ..schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    MANUAL_EDIT_PROVIDER,
    Model,
    ModelType,
)
from .base import BaseRepository


class ModelRepository(BaseRepository):
    """Model / ModelType の永続化を担当する Repository (ADR 0035)。

    管轄 entity:
      - `Model`
      - `ModelType`
      - モデル関連アソシエーション (`model_model_types`)
    """

    # 単純フィールド差分更新の対象集合 (update_model で使用)
    _MODEL_SIMPLE_UPDATE_FIELDS: ClassVar[tuple[str, ...]] = (
        "provider",
        "litellm_model_id",
        "estimated_size_gb",
        "requires_api_key",
        "discontinued_at",
    )

    def _get_model_id(self, litellm_model_id: str) -> int | None:
        """`litellm_model_id` (registry key SSoT) から Model.id を取得する。

        ADR 0023 Phase 1.11 (Issue #238) 以降、モデルの一意キーは
        `Model.litellm_model_id` (UNIQUE NOT NULL)。`Model.name` は表示名 (非 UNIQUE)
        になったため lookup には使えない。

        Args:
            litellm_model_id: 検索する registry key (例: `openai/gpt-4o`,
                `wd-vit-tagger-v3`, `__manual_edit__`)。

        Returns:
            int | None: 見つかったモデルのID。見つからない場合はNone。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Model.id).where(Model.litellm_model_id == litellm_model_id)
                result = session.execute(stmt).scalar_one_or_none()
                if result is None:
                    logger.warning(
                        f"litellm_model_id '{litellm_model_id}' がデータベースに見つかりません。"
                    )
                return result
            except SQLAlchemyError as e:
                logger.error(f"モデルIDの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_model_by_litellm_id(self, litellm_model_id: str) -> Model | None:
        """`litellm_model_id` (registry key SSoT) から Model オブジェクトを取得する。

        ADR 0023 Phase 1.11 (Issue #238): 旧 `get_model_by_name` を本 API に置換。
        registry key は WebAPI モデルで LiteLLM 完全 ID (`anthropic/claude-3-5-sonnet-...`)、
        ローカル ML モデルで bare name (`wd-vit-tagger-v3`)、特殊行で sentinel
        (`__manual_edit__`, `__legacy_<id>__`) を取る。

        Args:
            litellm_model_id: registry key (UNIQUE)。

        Returns:
            Model | None: 見つかった場合は Model (model_types eager load 済み)、
                なければ None。

        Raises:
            SQLAlchemyError: DB 操作エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = (
                    select(Model)
                    .options(selectinload(Model.model_types))
                    .where(Model.litellm_model_id == litellm_model_id)
                )
                result = session.execute(stmt).scalar_one_or_none()
                if result is None:
                    logger.debug(f"モデル '{litellm_model_id}' は登録されていません")
                return result
            except SQLAlchemyError as e:
                logger.error(
                    f"モデル取得エラー (litellm_model_id={litellm_model_id}): {e}",
                    exc_info=True,
                )
                raise

    def get_models_by_name(self, name: str) -> list[Model]:
        """`Model.name` に完全一致する全行を返す (Issue #245)。

        ADR 0023 Phase 1.11 以降、`Model.name` は非 UNIQUE となり、同一表示名で
        provider/route の異なる行が共存しうる (例: migration 経由 OpenRouter 行と
        新規 sync 経路の直接版が両方 `name='openai/gpt-4o'`)。CLI `--model` 入力で
        ユーザーが name を打ったときの曖昧マッチ検出に使う。

        Args:
            name: `Model.name` 値 (表示名)。

        Returns:
            list[Model]: 一致した行のリスト。0 件なら空リスト。

        Raises:
            SQLAlchemyError: DB 操作エラー。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Model).options(selectinload(Model.model_types)).where(Model.name == name)
                results = session.execute(stmt).scalars().all()
                logger.debug(f"name='{name}' に一致するモデル: {len(results)}件")
                return list(results)
            except SQLAlchemyError as e:
                logger.error(f"モデル取得エラー (name={name}): {e}", exc_info=True)
                raise

    def get_models_by_litellm_ids(self, litellm_model_ids: set[str]) -> dict[str, Model]:
        """複数の `litellm_model_id` から Model オブジェクトを一括取得する。

        ADR 0023 Phase 1.11 (Issue #238): 旧 `get_models_by_names` を本 API に置換。

        Args:
            litellm_model_ids: 取得する registry key のセット。

        Returns:
            litellm_model_id → Model のマッピング。見つからなかった key は含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        if not litellm_model_ids:
            return {}

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Model)
                    .options(selectinload(Model.model_types))
                    .where(Model.litellm_model_id.in_(litellm_model_ids))
                )
                results = session.execute(stmt).scalars().all()
                models_map = {model.litellm_model_id: model for model in results}
                logger.debug(f"モデル一括取得: {len(models_map)}/{len(litellm_model_ids)}件見つかりました")
                return models_map
            except SQLAlchemyError as e:
                logger.error(f"モデル一括取得エラー: {e}", exc_info=True)
                raise

    @staticmethod
    def _get_or_create_manual_edit_model(session: Session) -> int:
        """手動編集用のモデルIDを取得または作成します。

        ADR 0023 Phase 1.11 (Issue #238): `litellm_model_id` UNIQUE NOT NULL 化に伴い、
        MANUAL_EDIT 行は sentinel `__manual_edit__` で lookup・作成する。
        model_types テーブルへの関連付けは行わない (手動編集は AI カテゴリに属さない)。

        本メソッドは既存セッションを受け取って動作する (`session_factory` を使わない)。
        Image filter / annotation 更新など、呼び出し元が独自にセッションを管理する
        コンテキストから利用される。

        Args:
            session: データベースセッション。

        Returns:
            int: MANUAL_EDIT モデルの ID。

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合。

        """
        try:
            stmt = select(Model).where(Model.litellm_model_id == MANUAL_EDIT_LITELLM_ID)
            existing_model = session.execute(stmt).scalar_one_or_none()

            if existing_model:
                logger.debug(f"既存のMANUAL_EDITモデルを使用: ID={existing_model.id}")
                return existing_model.id

            manual_edit_model = Model(
                name=MANUAL_EDIT_NAME,
                provider=MANUAL_EDIT_PROVIDER,
                litellm_model_id=MANUAL_EDIT_LITELLM_ID,
            )
            session.add(manual_edit_model)
            session.flush()
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
        litellm_model_id: str,
        estimated_size_gb: float | None = None,
        requires_api_key: bool = False,
        discontinued_at: datetime.datetime | None = None,
    ) -> int:
        """新規モデルをDBに登録する。

        ADR 0023 Phase 1.11 (Issue #238): `litellm_model_id` は registry key SSoT
        として必須 (UNIQUE NOT NULL)。`name` は表示名 (非 UNIQUE) になった。

        Args:
            name: 表示名 (例: `gpt-4.1`)。
            provider: ルーティング元プロバイダー (例: `openai`, `anthropic`,
                `openrouter`)。ローカル ML モデルは None。
            model_types: LoRAIro の model_type リスト (`["caption"]`,
                `["multimodal"]`, `["scores"]`, `["tags"]`, `["upscaler"]`, `["ratings"]` など)。
            litellm_model_id: registry key (UNIQUE)。WebAPI では LiteLLM 完全 ID
                (`openai/gpt-4o`)、ローカル ML では bare name (`wd-vit-tagger-v3`)。
            estimated_size_gb: ローカルモデルの推定サイズ (GB)。
            requires_api_key: API キー要否。
            discontinued_at: 廃止日時 (該当する場合)。

        Returns:
            登録されたモデルのID。

        Raises:
            IntegrityError: `litellm_model_id` が既存モデルと重複する場合。
            ValueError: model_types が無効な場合 (存在しない model_type 名)。
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
                    litellm_model_id=litellm_model_id,
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
        litellm_model_id: str | None,
        estimated_size_gb: float | None,
        requires_api_key: bool | None,
        discontinued_at: datetime.datetime | None,
    ) -> bool:
        """モデルの単純フィールドを差分更新する。

        Args:
            model: ModelのORMオブジェクト。
            provider: プロバイダー名。
            litellm_model_id: APIモデルID。
            estimated_size_gb: 推定サイズ。
            requires_api_key: APIキー要否。
            discontinued_at: 廃止日時。

        Returns:
            変更があった場合True。

        """
        has_changes = False
        simple_fields = {
            "provider": provider,
            "litellm_model_id": litellm_model_id,
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
        litellm_model_id: str | None = None,
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
            litellm_model_id: API呼び出し時のモデルID
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
                    litellm_model_id,
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
