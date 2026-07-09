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

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from genai_tag_db_tools import recommend_manual_refinement, search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest, TagSearchResult
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
    REJECT_REASON_INCORRECT,
    REJECT_REASON_REPLACED,
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

# ADR 0068 (改訂): 保存境界で焼き込む基準フォーマット。非手動タグはこの format の
# preferred (canonical) へ解決して保存し、表示は verbatim にする。
_DANBOORU_FORMAT = "danbooru"
# LoRAIro が登録するタグ/alias の format 名 (register_user_tag / register_user_alias /
# _register_new_tag が共有)。classify_manual_tag の第2検索スコープもこれに揃える。
_LORAIRO_FORMAT = "Lorairo"


@dataclass(frozen=True)
class ManualTagClassification:
    """手動タグ追加時の外部 tag_db 分類結果 (Issue #1174)。

    Attributes:
        input_tag: 入力タグ文字列 (verbatim)。
        normalized_tag: TagCleaner.clean_format 正規化後 (空文字なら invalid)。
        classification: 分類コード。
            "invalid": 正規化後が空 (登録・追加の対象外)
            "exact": tag_db 完全一致
            "alias_resolved": 既知 alias → preferred へ自動解決
            "typo_candidate": typo 候補あり (自動適用しない、候補を surface)
            "ambiguous": 複数候補 (決め打ちしない、候補を surface)
            "unregistered": tag_db 未登録 (真の新タグ)
        canonical_tag: 保存すべきタグ文字列 (exact/alias は canonical、他は入力 verbatim)。
        tag_id: 解決済み外部 tag_id (未解決は None)。
        candidates: typo/ambiguous の候補タグ文字列。
    """

    input_tag: str
    normalized_tag: str
    classification: str
    canonical_tag: str
    tag_id: int | None
    candidates: list[str]


@dataclass(frozen=True, slots=True)
class AnnotationSaveItem:
    """1画像分の annotation 保存入力。"""

    image_id: int
    annotations: AnnotationsDict
    skip_existence_check: bool = False
    tag_id_cache: dict[str, int | None] | None = None


@dataclass(frozen=True, slots=True)
class CanonicalTag:
    """danbooru preferred へ解決済みのタグ (文字列 + preferred tag_id)。"""

    tag: str
    tag_id: int | None


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

    def get_merged_reader(self) -> MergedTagReader | None:
        """外部タグDBリーダーを明示的に初期化して返す。

        GUI など外部タグDB翻訳を表示面で必要とする呼び出し元向けの公開 accessor。
        """
        return self._get_merged_reader()

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
            logger.opt(exception=True).warning(f"Failed to initialize TagRegisterService: {e}")
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
                logger.opt(exception=True).error(
                    f"画像ID {image_id} のアノテーション保存中にエラーが発生しました: {e}"
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
                        f"chunk={start // effective_chunk_size + 1}, saved={len(chunk)}",
                    )
                except Exception as e:
                    session.rollback()
                    logger.opt(exception=True).error(
                        f"アノテーションのバッチ保存に失敗しました: chunk_start={start}, "
                        f"chunk_size={len(chunk)}, error={e}"
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
        existing_tags_stmt = select(Tag).where(
            Tag.image_id.in_(image_ids),
            Tag.rejected_at.is_(None),
        )
        all_existing_tags = session.execute(existing_tags_stmt).scalars().all()

        existing_tags_by_image: dict[int, set[str]] = {}
        for tag_obj in all_existing_tags:
            if tag_obj.image_id is None:
                continue
            if tag_obj.image_id not in existing_tags_by_image:
                existing_tags_by_image[tag_obj.image_id] = set()
            existing_tags_by_image[tag_obj.image_id].add(tag_obj.tag.lower())
        return existing_tags_by_image

    def _plan_tag_addition(
        self,
        session: Session,
        image_ids: list[int],
        resolved_tag: str,
        model_id: int | None,
    ) -> tuple[list[int], dict[int, Tag]]:
        """タグ追加の適用計画を読み取り専用で組み立てる (書き込み/preview 共有、Issue #1217)。

        dedup は canonical 解決後の値で判定する。既存行は書式が揃っていない
        ことがある (旧行が `blue sky`、解決後が `blue_sky` 等) ため、両辺を
        TagCleaner.clean_format で正規化してから比較する (Codex P2 / PR #994)。

        同一 (image, model) の soft-reject 済み行は復活対象として分離する。
        uq_tags_image_model_tag (Issue #1065) 下で新規 INSERT すると
        IntegrityError になるため、INSERT 経路には乗せない。

        Args:
            session: SQLAlchemy セッション。
            image_ids: 対象画像 ID リスト。
            resolved_tag: canonical 解決済みの保存タグ文字列。
            model_id: モデル ID (手動編集は None)。

        Returns:
            (新規 INSERT 対象の image_id リスト, 復活対象の image_id -> soft-reject 済み Tag 行)。
            既にタグを持つ画像はどちらにも含まれない。
        """
        dedup_key = self._dedup_key(resolved_tag)
        existing_tags_by_image = self._build_existing_tags_map(session, image_ids)

        rejected_rows_stmt = select(Tag).where(
            Tag.image_id.in_(image_ids),
            Tag.rejected_at.is_not(None),
            (Tag.model_id == model_id) if model_id is not None else Tag.model_id.is_(None),
        )
        rejected_by_image: dict[int, dict[str, Tag]] = {}
        for row in session.execute(rejected_rows_stmt).scalars():
            if row.image_id is None:
                continue
            rejected_by_image.setdefault(row.image_id, {}).setdefault(self._dedup_key(row.tag), row)

        to_insert: list[int] = []
        to_revive: dict[int, Tag] = {}
        for image_id in image_ids:
            existing_tags = existing_tags_by_image.get(image_id, set())
            existing_dedup_keys = {self._dedup_key(t) for t in existing_tags}

            if dedup_key in existing_dedup_keys:
                logger.debug(
                    f"Tag '{resolved_tag}' already exists for image_id {image_id}, skipping",
                )
                continue

            rejected_row = rejected_by_image.get(image_id, {}).get(dedup_key)
            if rejected_row is not None:
                to_revive[image_id] = rejected_row
            else:
                to_insert.append(image_id)
        return to_insert, to_revive

    def preview_add_tag_to_images_batch(
        self,
        image_ids: list[int],
        resolved_tag: str,
        model_id: int | None = None,
    ) -> int:
        """タグ追加の dry-run 見積り件数 (would_add) を返す (読み取り専用、Issue #1217)。

        `add_tag_to_images_batch` と同じ計画ロジック (`_plan_tag_addition`) で
        「新規 INSERT + soft-reject 復活」の件数を数える。DB へは書き込まない。

        Args:
            image_ids: 対象画像 ID リスト。
            resolved_tag: canonical 解決済みの保存タグ文字列 (呼び出し元が
                classify_manual_tag の結果から組み立てる。未解決タグの外部 DB
                登録が走らないよう、本メソッドは canonical 解決を行わない)。
            model_id: モデル ID (手動編集は None)。

        Returns:
            --apply 時に追加される見込みの件数。
        """
        if not image_ids or not resolved_tag.strip():
            return 0
        with self.session_factory() as session:
            to_insert, to_revive = self._plan_tag_addition(
                session, image_ids, resolved_tag.strip().lower(), model_id
            )
        return len(to_insert) + len(to_revive)

    def add_tag_to_images_batch(
        self,
        image_ids: list[int],
        tag: str,
        model_id: int | None,
        resolved: tuple[str, int | None] | None = None,
    ) -> tuple[bool, int]:
        """複数画像に1つのタグを原子的に追加(既存タグに追加、重複スキップ)

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ(正規化済み前提: lower + strip)
            model_id: モデルID(手動編集の場合はマニュアルモデルID)
            resolved: 呼び出し元が事前解決済みの (保存タグ文字列, 外部 tag_id)。
                CLI の分類経路 (Issue #1174) が classify_manual_tag / register_user_tag の
                結果を渡し、内部の再解決 (danbooru スコープ検索 + base DB 登録) をスキップする。

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

        # 外部 tag_db の翻訳は case-sensitive に照合されるため、検索キーは大小を保持する
        # (genai-tag-db-tools#139 / #1288)。小文字化は保存値の fallback と dedup キー
        # (`_dedup_key`) に限定する。
        input_tag = tag.strip()
        added_count = 0

        with self.session_factory() as session:
            try:
                # canonical 解決を dedup の前に1回だけ行う (日本語→canonical, alias→preferred)。
                # 保存する tags.tag を解決後の canonical 文字列に置換する (ADR 0083 §4 / #988)。
                resolved_tag, external_tag_id = self._resolution_for_batch_add(session, input_tag, resolved)
                if external_tag_id is None:
                    logger.warning(
                        f"Tag '{input_tag}' could not be linked to external tag_db. "
                        "Saving with tag_id=None.",
                    )

                to_insert, to_revive = self._plan_tag_addition(session, image_ids, resolved_tag, model_id)

                for image_id, rejected_row in to_revive.items():
                    rejected_row.rejected_at = None
                    rejected_row.reject_reason = None
                    rejected_row.is_edited_manually = True
                    rejected_row.updated_at = func.now()
                    added_count += 1
                    logger.debug(
                        f"Revived soft-rejected tag '{resolved_tag}' for image_id {image_id}",
                    )

                for image_id in to_insert:
                    new_tag = Tag(
                        image_id=image_id,
                        model_id=model_id,
                        tag=resolved_tag,
                        tag_id=external_tag_id,
                        confidence_score=None,
                        existing=False,
                        is_edited_manually=True,
                    )
                    session.add(new_tag)
                    added_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch tag add completed: tag='{resolved_tag}', "
                    f"processed={len(image_ids)}, added={added_count}",
                )
                return (True, added_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Atomic batch tag add failed, rolled back: {e}")
                raise

    def _plan_tag_removal(
        self, session: Session, image_ids: list[int], normalized_tag: str
    ) -> list[tuple[int, str]]:
        """タグ削除の適用計画 (image_id ごとの changed/skipped) を読み取り専用で組み立てる。

        `remove_tag_from_images_batch` と `preview_remove_tag_from_images_batch` が
        共有する (Issue #1217: dry-run 見積りと実適用の判定ロジックをドリフトさせない)。

        Args:
            session: SQLAlchemy セッション。
            image_ids: 対象画像 ID リスト。
            normalized_tag: strip + lower 済みタグ文字列。

        Returns:
            [(image_id, "changed"|"skipped"), ...] (タグを持たない画像は skipped)。
        """
        existing_tags_by_image = self._build_existing_tags_map(session, image_ids)
        per_item: list[tuple[int, str]] = []
        for image_id in image_ids:
            existing_tags = existing_tags_by_image.get(image_id, set())
            if normalized_tag not in existing_tags:
                logger.debug(
                    f"Tag '{normalized_tag}' not found for image_id {image_id}, skipping",
                )
                per_item.append((image_id, "skipped"))
            else:
                per_item.append((image_id, "changed"))
        return per_item

    def preview_remove_tag_from_images_batch(self, image_ids: list[int], tag: str) -> list[tuple[int, str]]:
        """タグ削除の dry-run 見積り (would_remove の根拠) を返す (読み取り専用、Issue #1217)。

        `remove_tag_from_images_batch` と同じ判定 (`_plan_tag_removal`) で
        image_id ごとの changed/skipped を返す。DB へは書き込まない。

        Args:
            image_ids: 対象画像 ID リスト。
            tag: 削除予定のタグ (正規化前可)。

        Returns:
            [(image_id, "changed"|"skipped"), ...]。入力が空の場合は空リスト。
        """
        if not image_ids or not tag.strip():
            return []
        with self.session_factory() as session:
            return self._plan_tag_removal(session, image_ids, tag.strip().lower())

    def remove_tag_from_images_batch(
        self,
        image_ids: list[int],
        tag: str,
        reason: str = REJECT_REASON_INCORRECT,
    ) -> tuple[bool, list[tuple[int, str]]]:
        """複数画像から1つのタグを原子的に soft-reject する (Issue #1003)。

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。
        ``rejected_at`` を立てると同時に ``reject_reason`` へ種別を記録する。
        既定は ``'incorrect'`` (✕ 相当のバッチ削除)。chip 単クリックの無効化は
        呼び出し元が ``reason='not_needed'`` を渡す。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 削除するタグ
            reason: soft-reject 種別 (``'not_needed'`` / ``'incorrect'``)。
                既定は ``'incorrect'``。

        Returns:
            (成功フラグ, [(image_id, "changed"|"skipped"), ...])

        Raises:
            SQLAlchemyError: データベースエラー時(ロールバック後に再送出)

        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch tag remove")
            return (False, [])

        if not tag.strip():
            logger.warning("Empty tag for batch remove")
            return (False, [])

        normalized_tag = tag.strip().lower()

        with self.session_factory() as session:
            try:
                per_item = self._plan_tag_removal(session, image_ids, normalized_tag)

                # bulk soft-reject (1回のみ)
                images_to_reject = [iid for iid, s in per_item if s == "changed"]
                if images_to_reject:
                    session.execute(
                        update(Tag)
                        .where(
                            Tag.image_id.in_(images_to_reject),
                            Tag.tag == normalized_tag,
                            Tag.rejected_at.is_(None),
                        )
                        .values(
                            rejected_at=datetime.datetime.now(datetime.UTC),
                            reject_reason=reason,
                            updated_at=datetime.datetime.now(datetime.UTC),
                        )
                    )

                session.commit()
                changed = sum(1 for _, s in per_item if s == "changed")
                logger.info(
                    f"Atomic batch tag remove completed: tag='{normalized_tag}', "
                    f"processed={len(image_ids)}, rejected={changed}",
                )
                return (True, per_item)

            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Atomic batch tag remove failed, rolled back: {e}")
                raise

    def replace_tag_for_images_batch(
        self,
        image_ids: list[int],
        from_tag: str,
        to_tag: str,
    ) -> tuple[bool, list[tuple[int, str]]]:
        """複数画像のタグを原子的に置換する。

        変換元タグが存在する画像のみ処理。変換先タグが既に存在する場合は
        変換元を削除のみ行い（重複させない）、ステータスは changed 扱い。

        Args:
            image_ids: 対象画像のIDリスト
            from_tag: 置換元タグ
            to_tag: 置換先タグ

        Returns:
            (成功フラグ, [(image_id, "changed"|"skipped"), ...])
            per-item リストにより呼び出し元が再クエリ不要で結果を判別できる。

        Raises:
            SQLAlchemyError: データベースエラー時(ロールバック後に再送出)

        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch tag replace")
            return (False, [])

        if not from_tag.strip() or not to_tag.strip():
            logger.warning("Empty from_tag or to_tag for batch replace")
            return (False, [])

        normalized_from = from_tag.strip().lower()
        normalized_to = to_tag.strip().lower()
        per_item: list[tuple[int, str]] = []

        with self.session_factory() as session:
            try:
                existing_tags_by_image = self._build_existing_tags_map(session, image_ids)

                # per-item 分類
                for image_id in image_ids:
                    existing_tags = existing_tags_by_image.get(image_id, set())
                    if normalized_from not in existing_tags:
                        per_item.append((image_id, "skipped"))
                    else:
                        per_item.append((image_id, "changed"))

                # bulk soft-reject: 変換元タグを持つ画像から一括除外
                images_to_change = [iid for iid, s in per_item if s == "changed"]
                if images_to_change:
                    session.execute(
                        update(Tag)
                        .where(
                            Tag.image_id.in_(images_to_change),
                            Tag.tag == normalized_from,
                            Tag.rejected_at.is_(None),
                        )
                        .values(
                            rejected_at=datetime.datetime.now(datetime.UTC),
                            reject_reason=REJECT_REASON_REPLACED,
                            updated_at=datetime.datetime.now(datetime.UTC),
                        )
                    )

                    # 変換先タグを追加（各画像で既存チェックして重複回避）
                    to_tag_external_id: int | None = None
                    for image_id in images_to_change:
                        existing_tags = existing_tags_by_image.get(image_id, set())
                        if normalized_to not in existing_tags:
                            if to_tag_external_id is None:
                                to_tag_external_id = self._get_or_create_tag_id_external(
                                    session, normalized_to
                                )
                            new_tag = Tag(
                                image_id=image_id,
                                model_id=None,
                                tag=normalized_to,
                                tag_id=to_tag_external_id,
                                confidence_score=None,
                                existing=False,
                                is_edited_manually=True,
                            )
                            session.add(new_tag)

                session.commit()
                changed = len(images_to_change)
                logger.info(
                    f"Atomic batch tag replace completed: '{normalized_from}' -> '{normalized_to}', "
                    f"processed={len(image_ids)}, changed={changed}",
                )
                return (True, per_item)

            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Atomic batch tag replace failed, rolled back: {e}")
                raise

    def restore_tag_for_images_batch(
        self,
        image_ids: list[int],
        tag: str,
    ) -> tuple[bool, list[tuple[int, str]]]:
        """soft-reject されたタグを復活する (rejected_at を NULL に戻す、Issue #792)。

        ``remove_tag_from_images_batch`` の逆操作。rejected_at が値を持つ行のみ対象。

        Args:
            image_ids: 対象画像の ID リスト。
            tag: 復活するタグ (正規化済み前提: lower + strip)。

        Returns:
            (成功フラグ, [(image_id, "changed"|"skipped"), ...])。

        Raises:
            SQLAlchemyError: データベースエラー時 (ロールバック後に再送出)。
        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch tag restore")
            return (False, [])
        if not tag.strip():
            logger.warning("Empty tag for batch restore")
            return (False, [])

        normalized_tag = tag.strip().lower()
        per_item: list[tuple[int, str]] = []

        with self.session_factory() as session:
            try:
                # rejected_at が値を持つ (= soft-reject 済み) 行を image ごとに把握
                rejected_rows = session.execute(
                    select(Tag.image_id)
                    .where(
                        Tag.image_id.in_(image_ids),
                        Tag.tag == normalized_tag,
                        Tag.rejected_at.is_not(None),
                    )
                    .distinct()
                ).scalars()
                rejected_image_ids = set(rejected_rows)

                for image_id in image_ids:
                    per_item.append((image_id, "changed" if image_id in rejected_image_ids else "skipped"))

                if rejected_image_ids:
                    session.execute(
                        update(Tag)
                        .where(
                            Tag.image_id.in_(rejected_image_ids),
                            Tag.tag == normalized_tag,
                            Tag.rejected_at.is_not(None),
                        )
                        .values(
                            rejected_at=None,
                            reject_reason=None,
                            updated_at=datetime.datetime.now(datetime.UTC),
                        )
                    )

                session.commit()
                restored = len(rejected_image_ids)
                logger.info(
                    f"Atomic batch tag restore completed: tag='{normalized_tag}', "
                    f"processed={len(image_ids)}, restored={restored}",
                )
                return (True, per_item)

            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(f"Atomic batch tag restore failed, rolled back: {e}")
                raise

    def get_rejected_tags(self, image_id: int) -> list[dict[str, Any]]:
        """画像の soft-reject 済みタグ (rejected_at IS NOT NULL) を返す (Issue #792 / #1003)。

        TagEdit の「soft-rejected」復活セクション表示と、reject_reason に基づく表示種別の
        再構築 (無効化=打ち消し線 / 除外・置換=非表示) に使う。

        Args:
            image_id: 対象画像 ID。

        Returns:
            ``{"tag": str, "tag_id": int | None, "is_edited_manually": bool | None,
            "reject_reason": str | None}`` の dict リスト (rejected_at 昇順)。

        Raises:
            SQLAlchemyError: データベースエラー時 (再送出)。
        """
        with self.session_factory() as session:
            try:
                rows = session.execute(
                    select(Tag.tag, Tag.tag_id, Tag.is_edited_manually, Tag.reject_reason)
                    .where(Tag.image_id == image_id, Tag.rejected_at.is_not(None))
                    .order_by(Tag.rejected_at)
                ).all()
            except SQLAlchemyError:
                logger.opt(exception=True).error(f"Failed to fetch rejected tags for image_id={image_id}")
                raise
        return [
            {
                "tag": row.tag,
                "tag_id": row.tag_id,
                "is_edited_manually": row.is_edited_manually,
                "reject_reason": row.reject_reason,
            }
            for row in rows
        ]

    # --- External tag_db: resolve / register ---

    def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
        """外部 tag_db から tag 文字列に一致する tag_id を検索し、見つからない場合は新規作成する。

        Args:
            session: SQLAlchemy セッション (LoRAIro DB用、tag_db操作には未使用)。
            tag_string: 検索・登録するタグ文字列。

        Returns:
            見つかった/登録したtag_id。エラー時はNone。

        """
        # 1. タグの正規化（SidecarAnnotationReaderと同一処理）
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
            logger.opt(exception=True).error(
                f"Error searching tag in external tag_db: '{normalized_tag}': {e}"
            )
            return None  # 検索失敗時は縮退動作（tag_id=None で保存）  # その他のエラーも縮退動作

    @staticmethod
    def _dedup_key(tag: str) -> str:
        """タグ重複判定用の正規化キーを返す。

        書式の揺れ (underscore/space 等) を吸収するため TagCleaner.clean_format で
        正規化し、小文字化する。保存値そのものではなく比較専用のキー (Codex P2 / #994)。

        Args:
            tag: 正規化前のタグ文字列。

        Returns:
            clean_format + lower 済みの比較キー。
        """
        cleaned: str = TagCleaner.clean_format(tag)
        return cleaned.strip().lower()

    def _search_exact_resolved(
        self, merged_reader: MergedTagReader, normalized_tag: str
    ) -> TagSearchResult:
        """手動タグの exact 検索を 3 段フォールバックで行い、preferred 解決済み結果を返す。

        1. danbooru スコープ: alias→preferred は単一 format スコープ時のみ解決される
           ため danbooru に絞る (Codex P2 / PR #994)。ADR 0068 の保存境界 = danbooru。
        2. Lorairo スコープ: user 登録タグ/alias (`tags alias` で確定した typo 等) を
           解決する (Codex P2 / PR #1183)。
        3. danbooru スコープ deprecated 込み (Issue #1212): `sparkles` のように
           deprecated な alias 行しか持たない実在タグを preferred へ解決する。
           これが無いと実在タグが unregistered 扱いになり、重複 user タグ +
           GUI から見えない孤立翻訳が無言で作られる。

        Args:
            merged_reader: マージ済みタグリーダー。
            normalized_tag: clean_format 済みタグ文字列。

        Returns:
            最初にヒットした段の TagSearchResult。全段ミス時は空の結果。

        Raises:
            search_tags 由来の例外はそのまま伝播する (縮退判断は呼び出し元が行う)。
        """
        result = TagSearchResult(items=[], total=0)
        for format_name, include_deprecated in (
            (_DANBOORU_FORMAT, False),
            (_LORAIRO_FORMAT, False),
            (_DANBOORU_FORMAT, True),
        ):
            request = TagSearchRequest(
                query=normalized_tag,
                partial=False,
                format_names=[format_name],
                resolve_preferred=True,
                include_aliases=True,
                include_deprecated=include_deprecated,
            )
            result = search_tags(merged_reader, request)
            if result.items:
                return result
        return result

    def _resolve_canonical_and_tag_id(self, session: Session, tag_string: str) -> tuple[str, int | None]:
        """手動タグ追加用に外部 tag_db で canonical 解決し、(canonical 文字列, tag_id) を返す。

        日本語入力は `TAG_TRANSLATIONS` 経由で canonical へ、alias は preferred へ
        解決する (`resolve_preferred=True`)。翻訳テーブルにヒットしない日本語などは
        正規化した入力をそのまま canonical 扱いで新規登録し、`source_tag` に生入力を
        保持する (ADR 0083 §4 / #988)。

        `_get_or_create_tag_id_external` との違い:
          - 戻り値に canonical 文字列を含める (保存する `tags.tag` を canonical へ置換するため)。
          - `resolve_preferred=True` で alias→preferred を解決する (手動追加経路専用)。

        Args:
            session: SQLAlchemy セッション (LoRAIro DB 用、tag_db 操作には未使用)。
            tag_string: 正規化前のタグ文字列 (日本語可)。

        Returns:
            (保存すべきタグ文字列, 外部 tag_id)。ヒット時は canonical 文字列を、未ヒット/
            縮退時は入力 `tag_string` をそのまま (ADR 0083 §4 の「そのまま登録」) 返す。
            tag_id は解決/登録失敗時は None。

        """
        # 検索・登録には clean_format 正規化を使うが、未ヒット時の保存値は入力をそのまま
        # 残す (既存挙動を踏襲: tags.tag は入力 verbatim、外部 DB 側のみ正規化形を使う)。
        normalized_tag = TagCleaner.clean_format(tag_string).strip()
        if not normalized_tag:
            logger.warning(f"Tag normalization resulted in empty string: '{tag_string}'")
            return (tag_string, None)

        merged_reader = self._get_merged_reader()
        if merged_reader is None:
            logger.debug(
                f"MergedTagReader unavailable, storing tag verbatim: '{tag_string}'",
            )
            return (tag_string, None)

        try:
            result = self._search_exact_resolved(merged_reader, normalized_tag)

            if result.items:
                item = result.items[0]
                canonical: str = item.tag
                tag_id: int = item.tag_id
                logger.debug(
                    f"Resolved tag '{tag_string}' → canonical '{canonical}' (tag_id={tag_id})",
                )
                return (canonical, tag_id)

            # 翻訳/エイリアス未ヒット → 入力をそのまま保存しつつ外部 DB へ新規登録
            # (source_tag に生入力を保持。tags.tag は入力 verbatim を維持)
            retry_request = TagSearchRequest(
                query=normalized_tag,
                partial=False,
                format_names=[_LORAIRO_FORMAT],
                resolve_preferred=True,
                include_aliases=True,
                include_deprecated=False,
            )
            new_tag_id = self._register_new_tag(normalized_tag, tag_string, retry_request)
            return (tag_string, new_tag_id)

        except Exception as e:
            # 外部 tag_db 境界の縮退動作 (tag_db は任意依存): 入力をそのまま保存
            logger.opt(exception=True).error(
                f"Error resolving canonical tag in external tag_db: '{normalized_tag}': {e}"
            )
            return (tag_string, None)

    def _resolution_for_batch_add(
        self, session: Session, input_tag: str, resolved: tuple[str, int | None] | None
    ) -> tuple[str, int | None]:
        """batch add 用の (保存タグ, tag_id)。事前解決があればそれを優先する (Issue #1174)。"""
        if resolved is not None:
            return resolved
        return self._resolve_canonical_and_tag_id(session, input_tag)

    def classify_manual_tag(self, tag_string: str) -> ManualTagClassification:
        """手動追加タグを外部 tag_db の refinement 検索で分類する (読み取り専用、Issue #1174)。

        書き込み経路 (`_resolve_canonical_and_tag_id`) と同じ 3 段 exact 検索
        (`_search_exact_resolved`) で解決し、ミス時は `recommend_manual_refinement`
        で typo / 曖昧候補を分類する。tag_db への登録は行わない (dry-run で安全に呼べる)。

        Args:
            tag_string: 入力タグ文字列 (正規化前、日本語可)。

        Returns:
            ManualTagClassification: 分類結果。tag_db 不通時は unregistered に縮退。
        """
        normalized = TagCleaner.clean_format(tag_string).strip()
        if not normalized:
            return ManualTagClassification(tag_string, "", "invalid", tag_string, None, [])

        merged_reader = self._get_merged_reader()
        if merged_reader is None:
            return ManualTagClassification(tag_string, normalized, "unregistered", tag_string, None, [])

        try:
            result = self._search_exact_resolved(merged_reader, normalized)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"タグ分類検索に失敗 (unregistered へ縮退): '{normalized}': {e}")
            return ManualTagClassification(tag_string, normalized, "unregistered", tag_string, None, [])

        if result.items:
            item = result.items[0]
            # resolve_preferred=True なので alias はここで preferred に置換済み。
            # 入力と canonical の正規化キーが同じなら完全一致、異なれば alias 解決。
            classification = (
                "exact" if self._dedup_key(item.tag) == self._dedup_key(normalized) else "alias_resolved"
            )
            return ManualTagClassification(
                tag_string, normalized, classification, item.tag, item.tag_id, []
            )

        # exact ミス → refinement 分類で typo / 曖昧候補を拾う (自動適用はしない)
        try:
            recommendation = recommend_manual_refinement(
                normalized, merged_reader, format_name=_DANBOORU_FORMAT
            )
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"refinement 分類に失敗 (unregistered へ縮退): '{normalized}': {e}")
            recommendation = None

        if recommendation is not None and recommendation.reasons:
            codes = {reason.code for reason in recommendation.reasons}
            candidates = [s.tag for s in recommendation.suggestions if s.tag]
            if "ambiguous_alias_candidates" in codes:
                return ManualTagClassification(
                    tag_string, normalized, "ambiguous", tag_string, None, candidates
                )
            if "typo_alias_candidate" in codes:
                return ManualTagClassification(
                    tag_string, normalized, "typo_candidate", tag_string, None, candidates
                )

        return ManualTagClassification(tag_string, normalized, "unregistered", tag_string, None, [])

    def register_user_tag(self, tag_string: str) -> int | None:
        """真の新タグを user DB (scope="user", format 1000+) へ登録する (Issue #1174)。

        登録失敗 (format 未定義 / tagdb #124 の読み戻し失敗等) は警告ログを残して
        None を返す縮退 (呼び出し元が tag_id=None を surface する)。

        Args:
            tag_string: 入力タグ文字列 (正規化前)。

        Returns:
            登録された tag_id。空正規化・登録失敗時は None。
        """
        normalized = TagCleaner.clean_format(tag_string).strip()
        if not normalized:
            # 空/無効に正規化されるトークンは登録しない (#124 回避・user DB 汚染防止)
            logger.warning(f"空正規化のため user DB 登録をスキップ: '{tag_string}'")
            return None

        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()
            if self.tag_register_service is None:
                logger.warning("TagRegisterService 初期化失敗のため user DB 登録をスキップ")
                return None

        register_request = TagRegisterRequest(
            tag=normalized,
            source_tag=tag_string,
            format_name=_LORAIRO_FORMAT,
            type_name="unknown",
            scope="user",
        )
        try:
            register_result = self.tag_register_service.register_tag(register_request)
            logger.debug(
                f"user DB へタグ登録: '{normalized}' tag_id={register_result.tag_id} "
                f"created={register_result.created}"
            )
            return cast("int | None", register_result.tag_id)
        except IntegrityError:
            # 競合 (他プロセスが同時登録) → 全 format exact でリトライ検索 (既存 helper 再利用)
            retry = self._retry_tag_search(normalized)
            if retry is None:
                logger.warning(f"user DB 登録競合後のリトライ検索でも未解決: '{normalized}'")
            return retry
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            # tagdb #124 (TAG_ID_NOT_FOUND_AFTER_INSERT) 等は tag_id=None + 警告で縮退
            logger.warning(f"user DB へのタグ登録に失敗 (tag_id=None で継続): '{normalized}': {e}")
            return None

    def register_user_alias(self, tag_string: str, preferred_tag: str) -> int | None:
        """typo 等の別表記を preferred タグへの alias として user DB に登録する (Issue #1173)。

        `tags alias` コマンド用。#1174 の分類で surface された typo 候補を人間/エージェント
        が確定させる導線 (typo の自動 alias 化はしない)。

        Args:
            tag_string: alias 元のタグ文字列 (正規化前)。
            preferred_tag: 解決先の preferred タグ文字列 (tag DB に存在すること)。

        Returns:
            登録された alias 行の tag_id。空正規化・登録失敗時は None。
        """
        normalized = TagCleaner.clean_format(tag_string).strip()
        if not normalized:
            logger.warning(f"空正規化のため alias 登録をスキップ: '{tag_string}'")
            return None

        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()
            if self.tag_register_service is None:
                logger.warning("TagRegisterService 初期化失敗のため alias 登録をスキップ")
                return None

        register_request = TagRegisterRequest(
            tag=normalized,
            source_tag=tag_string,
            format_name=_LORAIRO_FORMAT,
            type_name="unknown",
            alias=True,
            preferred_tag=preferred_tag,
            scope="user",
        )
        try:
            register_result = self.tag_register_service.register_tag(register_request)
            logger.debug(
                f"user DB へ alias 登録: '{normalized}' → '{preferred_tag}' "
                f"tag_id={register_result.tag_id} created={register_result.created}"
            )
            return cast("int | None", register_result.tag_id)
        except IntegrityError:
            retry = self._retry_tag_search(normalized)
            if retry is None:
                logger.warning(f"alias 登録競合後のリトライ検索でも未解決: '{normalized}'")
            return retry
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(
                f"user DB への alias 登録に失敗 (None で継続): '{normalized}' → '{preferred_tag}': {e}"
            )
            return None

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
            format_name=_LORAIRO_FORMAT,
            type_name="unknown",
        )

        try:
            register_result = self.tag_register_service.register_tag(register_request)
            tag_id = register_result.tag_id
            logger.debug(f"Registered new tag_id {tag_id} for '{normalized_tag}'")
            return cast("int | None", tag_id)
        except IntegrityError:
            # 競合検出（他のプロセスが同時に登録）→ リトライ
            logger.warning("Race condition detected during tag registration, retrying search...")
            return self._retry_new_tag_search(normalized_tag, search_request)
        except ValueError as ve:
            # genai-tag-db-tools は FK IntegrityError を ValueError に包んで返す (#1239)。
            # FK/DB 操作失敗由来なら競合として retry し、無効な format/type 等はそのまま
            # None 縮退させる。
            if self._is_retryable_db_error(ve):
                logger.warning("Race condition (wrapped) during tag registration, retrying search...")
                return self._retry_new_tag_search(normalized_tag, search_request)
            logger.error(f"Tag registration failed (invalid format/type): {ve}")
            return None
        except Exception as reg_error:
            logger.opt(exception=True).error(f"Unexpected error during tag registration: {reg_error}")
            return None

    def _retry_new_tag_search(self, normalized_tag: str, search_request: TagSearchRequest) -> int | None:
        """競合検出後、merged reader で全 format exact リトライ検索する。

        Args:
            normalized_tag: 正規化済みタグ文字列（ログ用）。
            search_request: リトライ検索用のリクエストオブジェクト。

        Returns:
            見つかった tag_id。失敗時は None。
        """
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
            logger.opt(exception=True).error(f"Retry search failed: {retry_error}")
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
            logger.opt(exception=True).error(f"search_tags_bulk failed: {e}")
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

    @staticmethod
    def _is_retryable_db_error(error: Exception) -> bool:
        """genai-tag-db-tools が ValueError に包んだ FK / DB 操作失敗を retry 対象と判定する。

        submodule は sqlite3/SQLAlchemy の IntegrityError を ValueError
        (``データベース操作に失敗しました: ...`` / ``DB operation failed: ...``) に変換して
        返すため、LoRAIro 側の ``except IntegrityError`` では捕捉できない (#1239)。
        並行登録由来の FK 制約失敗・DB 操作失敗のみ retry し、正規化後空文字などの正当な
        入力エラーは message pattern に一致しないため retry しない。

        Args:
            error: register_tag が送出した例外。

        Returns:
            競合として retry すべきなら True。
        """
        message = str(error)
        retryable_markers = (
            "FOREIGN KEY constraint failed",
            "データベース操作に失敗しました",
            "DB operation failed",
        )
        return any(marker in message for marker in retryable_markers)

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
                format_name=_LORAIRO_FORMAT,
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
        except ValueError as value_error:
            # genai-tag-db-tools は sqlite3/SQLAlchemy IntegrityError を ValueError に包んで
            # 返す (repository.py の DB_OPERATION_FAILED / "DB operation failed") ため、
            # 上の except IntegrityError では FK 制約由来の競合を捕捉できない (#1239)。
            # FK / DB 操作失敗由来の ValueError のみ競合として retry し、正規化空文字などの
            # 正当な入力エラー (message pattern 非一致) は retry せず None を返す。
            if self._is_retryable_db_error(value_error):
                logger.warning(f"Race condition (wrapped) for '{tag_str}', retrying search...")
                return self._retry_tag_search(tag_str)
            logger.error(f"Tag registration failed for '{tag_str}': {value_error}")
            return None
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

    def _resolve_danbooru_canonical(self, clean_tags: set[str]) -> dict[str, CanonicalTag]:
        """clean_format 済みタグ集合を danbooru preferred (canonical) へ一括解決する。

        ADR 0068 (改訂) の保存境界方針。`search_tags_bulk` を 1 回だけ呼び、
        alias→preferred を解決した canonical 文字列と preferred tag_id を返す。
        reader 不在・未登録・deprecated なタグは結果に含めず、呼び出し元が整形済み
        文字列を維持する (graceful degradation)。

        Args:
            clean_tags: `TagCleaner.clean_format().strip()` 済みタグ文字列の集合。

        Returns:
            clean_format 済みタグ → CanonicalTag のマッピング。解決できたタグのみ含む。
        """
        if not clean_tags:
            return {}

        merged_reader = self._get_merged_reader()
        if merged_reader is None:
            logger.debug("MergedTagReader unavailable, skipping danbooru canonical resolution")
            return {}

        try:
            bulk_results = merged_reader.search_tags_bulk(
                list(clean_tags),
                format_name=_DANBOORU_FORMAT,
                resolve_preferred=True,
            )
        except Exception as e:
            # tag_db は任意依存 (ADR 0068): 解決失敗時は整形済みのまま保存へ縮退する。
            logger.opt(exception=True).error(f"danbooru canonical の一括解決に失敗: {e}")
            return {}

        result: dict[str, CanonicalTag] = {}
        for clean_tag, row in bulk_results.items():
            if row.get("deprecated", False):
                continue
            canonical_str = row.get("tag")
            if not canonical_str:
                continue
            result[clean_tag] = CanonicalTag(tag=canonical_str, tag_id=row.get("tag_id"))
        return result

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

        ADR 0068 (改訂) の保存境界: 非手動タグは clean_format 整形後に danbooru
        canonical (preferred) へ焼き込んで保存する。手動編集タグ
        (is_edited_manually=True) は整形のみでユーザー表記を維持する。これにより
        表示/export は変換なしの verbatim で済む。

        Args:
            session: SQLAlchemyセッション。
            image_id: 対象画像のID。
            tags_data: 保存するタグデータのリスト。
            tag_id_cache: 正規化済みタグ文字列→tag_idのキャッシュ。
                canonical 解決できなかった非手動タグ・手動タグの tag_id 解決に使う。
                キャッシュミス時は従来通り_get_or_create_tag_id_external()にフォールバック。

        """
        logger.debug(f"Saving/Updating {len(tags_data)} tags for image_id {image_id}")

        # 既存のタグを image_id と tag 文字列で取得 (効率化のため)
        existing_tags_stmt = select(Tag).where(Tag.image_id == image_id)
        existing_tags_result = session.execute(existing_tags_stmt).scalars().all()
        # (整形済み tag_string, model_id) をキーとする辞書を作成。
        # 旧 raw 行 (clean_format 前) も整形後キーに揃え、整形後の入力と突合できるようにする。
        existing_tags_map = {
            (TagCleaner.clean_format(t.tag).strip(), t.model_id): t for t in existing_tags_result
        }

        # ADR 0068 (改訂): 非手動タグは保存時に danbooru canonical (preferred) へ焼き込む。
        # 手動編集タグ (is_edited_manually=True) はユーザーの表記を尊重し canonical 化しない。
        canonical_targets = {
            clean
            for tag_info in tags_data
            if not tag_info.get("is_edited_manually")
            and (clean := TagCleaner.clean_format(tag_info["tag"]).strip())
        }
        canonical_map = self._resolve_danbooru_canonical(canonical_targets)

        for tag_info in tags_data:
            # 全取込経路の tag をまず clean_format 整形に統一する (lower 化はしない)。
            clean_tag = TagCleaner.clean_format(tag_info["tag"]).strip()
            if not clean_tag:
                # 整形後に空文字になったタグはスキップ
                continue

            # 非手動タグは canonical 解決できれば preferred 文字列 + preferred tag_id を採用する。
            is_manual = bool(tag_info.get("is_edited_manually"))
            canonical = None if is_manual else canonical_map.get(clean_tag)
            tag_string = canonical.tag if canonical is not None else clean_tag

            model_id = tag_info.get("model_id")  # Optional
            confidence = tag_info.get("confidence_score")  # Optional
            is_existing_tag = tag_info.get("existing", False)  # 元ファイル由来か

            # 外部DBから tag_id を取得/作成。
            # canonical 解決済みなら preferred tag_id を最優先し、文字列と tag_id の整合を保つ。
            # それ以外は呼び出し元設定値 → キャッシュ (clean_format キー) → 個別照会の順。
            external_tag_id: int | None
            if canonical is not None:
                external_tag_id = canonical.tag_id
            else:
                external_tag_id = tag_info.get("tag_id")
                if external_tag_id is None:
                    if tag_id_cache is not None and clean_tag in tag_id_cache:
                        external_tag_id = tag_id_cache[clean_tag]
                    else:
                        # キャッシュミス / キャッシュ無し: 従来の個別照会にフォールバック
                        external_tag_id = self._get_or_create_tag_id_external(session, clean_tag)

            if external_tag_id is None:
                logger.warning(
                    f"Tag '{tag_string}' could not be linked to external tag_db. "
                    "Saving with tag_id=None (limited taxonomy features).",
                )

            # 既存レコードを整形後キーで検索
            existing_record = existing_tags_map.get((tag_string, model_id))

            if existing_record:
                # 更新 (旧 raw 行は整形後の値へ揃える)。
                # 同一モデルの再付与は「最終付与日時」として updated_at を必ず更新する
                # (他カラム無変更だと onupdate が発火しないため明示。Issue #1065)。
                # rejected_at / reject_reason は触らない: soft-reject はユーザー判断を
                # 優先して維持する (Issue #1065 ユーザー確認済みポリシー / ADR 0065)。
                logger.debug(f"Updating existing tag: id={existing_record.id}, tag='{tag_string}'")
                existing_record.tag = tag_string
                existing_record.tag_id = external_tag_id
                existing_record.confidence_score = confidence
                existing_record.existing = is_existing_tag
                existing_record.is_edited_manually = tag_info.get("is_edited_manually")
                existing_record.updated_at = func.now()
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
            display_score = score_info.get("display_score")
            is_edited = score_info.get("is_edited_manually", False)

            existing_record = existing_scores_map.get(model_id)

            if existing_record:
                # 更新
                logger.debug(f"Updating existing score: id={existing_record.id}")
                existing_record.score = score_value
                existing_record.display_score = display_score
                existing_record.is_edited_manually = is_edited or False  # None → False
            else:
                # 新規作成
                logger.debug(f"Adding new score: model_id={model_id}, score={score_value}")
                new_score = Score(
                    image_id=image_id,
                    model_id=model_id,
                    score=score_value,
                    display_score=display_score,
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
        """Canonical scorer の score_label を保存・更新 (Upsert by model_id).

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
                    ),
                )
                if rating is not None:
                    session.add(
                        Rating(
                            image_id=image_id,
                            model_id=manual_edit_model_id,
                            raw_rating_value=rating,
                            normalized_rating=rating,
                            confidence_score=None,
                        ),
                    )

                session.commit()
                logger.debug(f"画像ID {image_id} の manual_rating を '{rating}' に更新しました")
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.opt(exception=True).error(
                    f"Manual rating の更新中にエラーが発生しました (ID: {image_id}): {e}"
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
                logger.opt(exception=True).error(
                    f"手動編集フラグの更新中にエラーが発生しました (Type: {annotation_type}, ID: {annotation_id}): {e}"
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
                logger.opt(exception=True).error(
                    f"Batch rating update failed: rating='{normalized_rating}', "
                    f"image_ids={len(image_ids)}, error={e}"
                )
                raise

    def get_rating_breakdown_for_images(self, image_ids: list[int]) -> dict[str, int]:
        """指定画像IDセットの normalized_rating 別件数を返す。

        Args:
            image_ids: 対象画像IDのリスト。

        Returns:
            normalized_rating → 件数のdict (例: {"PG": 122, "PG-13": 19})。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return {}

        with self.session_factory() as session:
            stmt = (
                select(Rating.normalized_rating, func.count(Rating.id))
                .where(Rating.image_id.in_(image_ids))
                .group_by(Rating.normalized_rating)
            )
            rows = session.execute(stmt).all()
            return {row[0]: row[1] for row in rows if row[0] is not None}

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
                        # 手動編集スコアは DB 値 (0-10) をそのまま表示スコアとして使う。
                        existing_score.display_score = score
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
                            # 手動編集スコアは DB 値 (0-10) をそのまま表示スコアとして使う。
                            display_score=score,
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
                logger.opt(exception=True).error(
                    f"Batch score update failed: score={score:.2f}, image_ids={len(image_ids)}, error={e}"
                )
                raise
