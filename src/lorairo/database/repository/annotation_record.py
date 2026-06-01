"""Annotation 永続化担当 Repository (ADR 0035 §1, 最終段階)。

`db_repository.py` god class 分割の段階 5 として、Annotation エンティティ
(`Tag` / `Caption` / `Score` / `ScoreLabel` / `Rating`) の書き込み・更新と
genai-tag-db-tools (外部 tag_db) 統合を本 Repository に集約する。

管轄 entity:
  - `Tag` (per-image annotation + 外部 tag_db との tag_id 連携)
  - `Caption` (per-image annotation)
  - `Score` (per-model 数値スコア + 手動編集)
  - `ScoreLabel` (canonical scorer の categorical 分類、ADR 0028)
  - `Rating` (per-model レーティング + MANUAL_EDIT 経由の手動レーティング)

カバー領域:
  - Annotation 一括書き込み: `save_annotations` (Upsert)
  - エンティティ別 Upsert: `_save_tags` / `_save_captions` / `_save_scores` /
    `_save_score_labels` / `_save_ratings`
  - 一括 Tag 追加: `add_tag_to_images_batch` (原子的、N+1 回避)
  - Tag 更新 (フラグ): `update_annotation_manual_edit_flag`
  - 手動 Rating: `update_manual_rating`, `update_rating_batch`
  - 手動 Score: `update_score_batch`
  - 外部 tag_db 連携 (genai-tag-db-tools):
    `_initialize_merged_reader`, `_initialize_tag_register_service`,
    `_get_or_create_tag_id_external`, `batch_resolve_tag_ids`,
    `_register_*`, `_retry_tag_search`

段階 1-4 で確立した基盤:
  - `BaseRepository` (`session_factory` + `BATCH_CHUNK_SIZE`) を継承。
  - `ModelRepository._get_or_create_manual_edit_model` static helper を利用
    (MANUAL_EDIT model lookup)。
  - `Image` 存在確認 (`_image_exists`) は本 Repository 内で session を共有する
    軽量 query として inline (Repository 間の cross-call を避けるため)。

注:
  - `merged_reader` / `tag_register_service` は外部 tag_db に依存する。LoRAIro
    自体は外部 tag_db 無しでも動作可能 (`tag_id=None` 許容設計) なので、
    初期化失敗時は warning + None でグレースフルデグラデーションする。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from sqlalchemy import delete, func, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from ...utils.log import logger
from ..db_core import ensure_tag_db_initialized
from ..schema import (
    AnnotationsDict,
    Caption,
    CaptionAnnotationData,
    Image,
    Rating,
    RatingAnnotationData,
    Score,
    ScoreAnnotationData,
    ScoreLabel,
    ScoreLabelAnnotationData,
    Tag,
    TagAnnotationData,
)
from .base import BaseRepository
from .model import ModelRepository


@dataclass(frozen=True, slots=True)
class AnnotationSaveItem:
    """1画像分の annotation 保存入力。"""

    image_id: int
    annotations: AnnotationsDict
    skip_existence_check: bool = False
    tag_id_cache: dict[str, int | None] | None = None


class AnnotationRepository(BaseRepository):
    """Annotation エンティティの永続化を担当する Repository (ADR 0035)。

    管轄 entity:
      - `Tag` / `Caption` / `Score` / `ScoreLabel` / `Rating`
      - 外部 tag_db 統合 (`MergedTagReader` / `TagRegisterService`)
    """

    def __init__(self, session_factory=None) -> None:  # type: ignore[no-untyped-def]
        """AnnotationRepository のコンストラクタ。

        Args:
            session_factory: SQLAlchemy セッションファクトリ。BaseRepository に委譲。

        Note:
            外部 tag_db (`MergedTagReader` / `TagRegisterService`) は初期化失敗時に
            `None` に縮退する。LoRAIro は外部 tag_db 無しでも動作可能。
        """
        if session_factory is None:
            super().__init__()
        else:
            super().__init__(session_factory)

        # 外部 tag_db 統合は実際に tag_id 解決が必要になるまで遅延する。
        # TagCleaner.clean_format() は静的メソッドなのでインスタンス化不要。
        self.merged_reader: MergedTagReader | None = None
        self._merged_reader_initialized = False
        # TagRegisterService は遅延初期化 (登録時のみ必要)。
        self.tag_register_service: TagRegisterService | None = None

    # --- External tag_db initialization ---

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
            ensure_tag_db_initialized()
            return get_default_reader()
        except Exception as e:
            logger.warning(
                f"Failed to initialize MergedTagReader (external tag DB unavailable): {e}. "
                "Tag operations will continue without external tag_id.",
            )
            return None

    def _get_merged_reader(self) -> MergedTagReader | None:
        """外部タグDBリーダーを必要時に初期化して返す。"""
        if self.merged_reader is not None:
            self._merged_reader_initialized = True
            return self.merged_reader
        if not self._merged_reader_initialized:
            self.merged_reader = self._initialize_merged_reader()
            self._merged_reader_initialized = True
        return self.merged_reader

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
        merged_reader = self._get_merged_reader()
        if merged_reader is None:
            logger.warning("MergedTagReader unavailable, cannot initialize TagRegisterService")
            return None

        try:
            return TagRegisterService(reader=merged_reader)
        except Exception as e:
            logger.warning(f"Failed to initialize TagRegisterService: {e}", exc_info=True)
            return None  # エラー時はNoneで継続

    # --- save_annotations + helpers (Upsert) ---

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
        item = AnnotationSaveItem(
            image_id=image_id,
            annotations=annotations,
            skip_existence_check=skip_existence_check,
            tag_id_cache=tag_id_cache,
        )
        with self.session_factory() as session:
            try:
                self._save_annotations_in_session(session, item)
                session.commit()
                logger.debug(f"画像ID {image_id} のアノテーションを保存・更新しました。")

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"画像ID {image_id} のアノテーション保存中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def save_annotations_batch(
        self,
        items: Sequence[AnnotationSaveItem],
        *,
        chunk_size: int | None = None,
    ) -> int:
        """複数画像の annotation をチャンク単位の単一トランザクションで保存する。

        チャンク内は all-or-nothing。呼び出し側は例外時にチャンクを per-image
        fallback することで、従来の部分成功カウントを維持できる。
        """
        if not items:
            return 0

        effective_chunk_size = chunk_size or self.BATCH_CHUNK_SIZE
        if effective_chunk_size <= 0:
            effective_chunk_size = len(items)

        saved_count = 0
        for start in range(0, len(items), effective_chunk_size):
            chunk = items[start : start + effective_chunk_size]
            with self.session_factory() as session:
                try:
                    for item in chunk:
                        self._save_annotations_in_session(session, item)
                        # autoflush=False のため、同一 chunk 内で同じ image_id が再登場した場合も
                        # 後続 item の upsert query が先行 item の行を参照できるよう明示 flush する。
                        session.flush()
                    session.commit()
                    saved_count += len(chunk)
                    logger.debug(
                        f"アノテーションをバッチ保存しました: "
                        f"chunk={start // effective_chunk_size + 1}, saved={len(chunk)}"
                    )
                except Exception as e:
                    session.rollback()
                    logger.error(
                        f"アノテーションのバッチ保存に失敗しました: chunk_start={start}, "
                        f"chunk_size={len(chunk)}, error={e}",
                        exc_info=True,
                    )
                    raise

        return saved_count

    def _save_annotations_in_session(self, session: Session, item: AnnotationSaveItem) -> None:
        """既存 session 内で1画像分の annotation を保存する（commitしない）。"""
        image_id = item.image_id
        annotations = item.annotations
        # ADR 0035 段階 5: cross-repo 呼び出しを避けるため、Image 存在チェックを
        # 同一 session 内で inline 実行する (本 Repository は Annotation 担当だが、
        # 親 Image の存在は前提条件のため query は必要)。
        if not item.skip_existence_check:
            exists = session.execute(select(Image.id).where(Image.id == image_id)).scalar_one_or_none()
            if exists is None:
                raise ValueError(f"指定された画像ID {image_id} は存在しません。")

        # 各アノテーションタイプを処理
        if annotations.get("tags"):
            self._save_tags(session, image_id, annotations["tags"], tag_id_cache=item.tag_id_cache)
        if annotations.get("captions"):
            self._save_captions(session, image_id, annotations["captions"])
        if annotations.get("scores"):
            self._save_scores(session, image_id, annotations["scores"])
        if annotations.get("score_labels"):
            self._save_score_labels(session, image_id, annotations["score_labels"])
        if annotations.get("ratings"):
            self._save_ratings(session, image_id, annotations["ratings"])

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
            if tag_obj.image_id is None:
                continue
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

    # --- External tag_db: resolve / register ---

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
        merged_reader = self._get_merged_reader()
        if merged_reader is None:
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
            result = search_tags(merged_reader, request)

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
        search_request: TagSearchRequest,
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
            return cast("int | None", tag_id)
        except ValueError as ve:
            logger.error(f"Tag registration failed (invalid format/type): {ve}")
            return None
        except IntegrityError:
            # 競合検出（他のプロセスが同時に登録）→ リトライ
            logger.warning("Race condition detected during tag registration, retrying search...")
            try:
                merged_reader = self._get_merged_reader()
                if merged_reader is None:
                    return None
                retry_result = search_tags(merged_reader, search_request)
                if retry_result.items and len(retry_result.items) > 0:
                    tag_id = retry_result.items[0].tag_id
                    logger.debug(f"Found tag_id {tag_id} on retry for '{normalized_tag}'")
                    return cast("int | None", tag_id)
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
        merged_reader = self._get_merged_reader()
        if merged_reader is None:
            logger.debug("MergedTagReader unavailable, skipping batch tag resolution")
            return dict.fromkeys(normalized_tags)

        # 一括検索
        try:
            bulk_results = merged_reader.search_tags_bulk(
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
            merged_reader = self._get_merged_reader()
            if merged_reader is None:
                return None
            retry_result = search_tags(merged_reader, retry_request)
            if retry_result.items:
                tag_id: int = retry_result.items[0].tag_id
                return tag_id
            return None
        except Exception as retry_error:
            logger.error(f"Retry search failed for '{tag_str}': {retry_error}")
            return None

    # --- _save_* (Upsert by entity) ---

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
            # 呼び出し元が設定済みの tag_id を優先し、未設定時はキャッシュ→個別照会の順
            external_tag_id: int | None = tag_info.get("tag_id")
            if external_tag_id is None:
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
                existing_record.is_edited_manually = is_edited or False  # None → False
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

    def _save_score_labels(
        self,
        session: Session,
        image_id: int,
        score_labels_data: list[ScoreLabelAnnotationData],
    ) -> None:
        """canonical scorer の score_label を保存・更新 (Upsert by model_id).

        ADR 0027 / iam-lib ADR 0002: aesthetic_shadow / cafe_aesthetic 等の
        canonical scorer は ``(image, model)`` 単位で単一 label を返す契約のため、
        ``_save_ratings`` と同じ ``model_id`` キーの Upsert pattern を採る。
        同一 model_id で複数 label が渡された場合は最後の値で確定する。
        """
        logger.debug(f"Saving/Updating {len(score_labels_data)} score_labels for image_id {image_id}")

        # 既存 score_label を image_id で取得
        existing_stmt = select(ScoreLabel).where(ScoreLabel.image_id == image_id)
        existing_records = session.execute(existing_stmt).scalars().all()
        existing_map: dict[int, ScoreLabel] = {r.model_id: r for r in existing_records}

        for label_info in score_labels_data:
            model_id = label_info["model_id"]
            label = label_info["label"]
            is_edited = label_info.get("is_edited_manually")

            existing_record = existing_map.get(model_id)

            if existing_record:
                logger.debug(f"Updating existing score_label: id={existing_record.id}")
                existing_record.label = label
                existing_record.is_edited_manually = is_edited
            else:
                logger.debug(f"Adding new score_label: model_id={model_id}, label='{label}'")
                new_record = ScoreLabel(
                    image_id=image_id,
                    model_id=model_id,
                    label=label,
                    is_edited_manually=is_edited,
                )
                session.add(new_record)
                existing_map[model_id] = new_record

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

    # --- Manual edit / batch updates ---

    def update_manual_rating(self, image_id: int, rating: str | None) -> bool:
        """指定された画像IDの手動レーティングを Rating テーブルに保存します。

        常に既存の MANUAL_EDIT レコードを削除してから INSERT する upsert 方式。
        rating=None の場合は削除のみ（解除）。手動レーティングは「現在値」のみ意味を持つため
        履歴を保持しない。詳細は ADR 0015 参照。

        Args:
            image_id (int): 更新する画像のID。
            rating (str | None): 新しいレーティング値 ('PG', 'R' など)。None で解除。

        Returns:
            bool: 更新が成功した場合はTrue、画像が見つからない場合はFalse。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        with self.session_factory() as session:
            try:
                image = session.get(Image, image_id)
                if image is None:
                    logger.warning(f"Manual rating の更新対象画像が見つかりません: image_id={image_id}")
                    return False

                # ADR 0035 段階 5: MANUAL_EDIT model lookup は ModelRepository static helper を直接呼ぶ。
                manual_edit_model_id = ModelRepository._get_or_create_manual_edit_model(session)

                session.execute(
                    delete(Rating).where(
                        Rating.image_id == image_id,
                        Rating.model_id == manual_edit_model_id,
                    )
                )
                if rating is not None:
                    session.add(
                        Rating(
                            image_id=image_id,
                            model_id=manual_edit_model_id,
                            raw_rating_value=rating,
                            normalized_rating=rating,
                            confidence_score=None,
                        )
                    )

                session.commit()
                logger.debug(f"画像ID {image_id} の manual_rating を '{rating}' に更新しました")
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
                result = cast("CursorResult[Any]", session.execute(stmt))
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
