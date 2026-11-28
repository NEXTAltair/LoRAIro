"""プロジェクトを横断した画像の検索とコピー (ADR 0112, Issue #1661)。Qt 非依存。

- 別プロジェクトの DB は読み取り専用で開く (`create_project_session_factory(read_only=True)`)。
  schema が head でないプロジェクトは開かず、`ReadOnlyPreconditionError` をそのまま伝える。
- 画像は参照せずコピーする。画像ファイル・処理済み画像・タグ / キャプション / スコア / スコアラベル /
  レーティング・生成メタデータを取り込み先に複製し、コピー元のプロジェクト名と画像 ID / uuid を
  `image_origins` に記録する。DB をまたぐ外部キーは作らない。
- 取り込み先に同じ画像 (ADR 0061 の分類で DUPLICATE) があれば複製せず、既存の画像に由来を足し、
  アノテーションは和集合にする。
- 取り込み先には 1 セッション 1 commit で書く。ファイルは staging に置いてから最終パスへ移し、
  途中で失敗したら rollback して、置いたファイルを消す。
- プロジェクトの統合 (#1660) は `ProjectTransferService.stage_images` を同じ形で再利用する前提。
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from lorairo.database.db_core import (
    IMG_DB_FILENAME,
    create_project_session_factory,
    resolve_stored_path_in_root,
)
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.image import ImageRepository, PhashClassification
from lorairo.database.repository.image_origin import ImageOriginRepository, ImageOriginSnapshot
from lorairo.database.schema import (
    TRANSFER_KIND_COPY_IMAGES,
    Caption,
    GenerationMetadata,
    GenerationMetadataSource,
    Image,
    ImageOrigin,
    Model,
    ModelType,
    ProcessedImage,
    Project,
    ProjectTransferRun,
    Rating,
    Score,
    ScoreLabel,
    Tag,
)
from lorairo.public_api.exceptions import ReadOnlyPreconditionError, ResultSetTooLargeError
from lorairo.utils.log import logger

__all__ = [
    "CrossProjectImageHit",
    "CrossProjectSearchService",
    "ImageTransferItem",
    "ImageTransferResult",
    "ProjectSearchResult",
    "ProjectTransferService",
    "SourceProject",
    "TransferAction",
    "open_read_only_project",
]

# 1 回にまとめて IN 句へ渡す件数 (SQLite のバインド変数上限より十分小さく)
_CHUNK_SIZE = 500
_STAGING_DIR_NAME = ".transfer_staging"

TransferAction = Literal["copy", "link", "already_linked"]
"""画像ごとの扱い。

- ``copy``: 新しい画像として複製する
- ``link``: 同じ画像が既にあるので、既存の画像に由来を足しアノテーションを和集合にする
- ``already_linked``: 同じ由来が既に記録されている (再実行)。足りないアノテーションだけ足す
"""


@dataclass(frozen=True)
class SourceProject:
    """コピー元 (または検索対象) のプロジェクト。

    Attributes:
        name: プロジェクト名。由来に記録する。
        root: プロジェクトディレクトリ。
    """

    name: str
    root: Path

    @property
    def db_path(self) -> Path:
        """プロジェクトの画像 DB のパス。"""
        return self.root / IMG_DB_FILENAME


@contextmanager
def open_read_only_project(project: SourceProject) -> Iterator[sessionmaker[Session]]:
    """プロジェクトの DB を読み取り専用で開き、セッションファクトリを返す。

    閉じるときに engine を破棄する。schema が head でない DB は開かない。

    Args:
        project: 開くプロジェクト。

    Yields:
        読み取り専用のセッションファクトリ。

    Raises:
        ReadOnlyPreconditionError: DB が無い、または schema が head でない場合。
    """
    factory = create_project_session_factory(project.db_path, read_only=True)
    try:
        yield factory
    finally:
        engine = factory.kw.get("bind")
        if isinstance(engine, Engine):
            engine.dispose()


# --- 横断検索 ---


@dataclass(frozen=True)
class CrossProjectImageHit:
    """横断検索で見つかった画像 1 枚。

    Attributes:
        project_name: 画像があるプロジェクト。
        image_id: そのプロジェクトの DB での画像 ID。
        uuid: 画像の uuid。
        phash: 画像の pHash。
        filename: 登録時のファイル名。
        width: 幅 (px)。
        height: 高さ (px)。
        file_path: プロジェクトディレクトリ基準で解決した画像ファイルのパス。
        origins: その画像に既に記録されている由来 (別プロジェクトからコピーした画像なら 1 件以上)。
    """

    project_name: str
    image_id: int
    uuid: str
    phash: str
    filename: str | None
    width: int
    height: int
    file_path: Path
    origins: list[ImageOriginSnapshot]


@dataclass(frozen=True)
class ProjectSearchResult:
    """1 プロジェクト分の検索結果。"""

    project_name: str
    total: int
    hits: list[CrossProjectImageHit]
    # 開けずに飛ばしたときの理由 (`ReadOnlyPreconditionError.details["reason"]`)。開けたときは None
    unavailable_reason: str | None = None


class CrossProjectSearchService:
    """複数プロジェクトから条件に合う画像を読み取り専用で検索する service。"""

    def search(
        self,
        projects: Sequence[SourceProject],
        criteria: ImageFilterCriteria,
        *,
        max_results_per_project: int,
        skip_unavailable: bool = False,
    ) -> list[ProjectSearchResult]:
        """各プロジェクトを読み取り専用で開き、`ImageRepository.get_images_by_filter` で検索する。

        Args:
            projects: 検索するプロジェクト。
            criteria: 検索条件 (`images search` と同じ条件)。
            max_results_per_project: 1 プロジェクトで取得してよい最大件数。画像 ID 指定のない条件で
                これを超えたら取得しない。
            skip_unavailable: True なら、開けない (schema が head でない等) プロジェクトを例外にせず、
                `unavailable_reason` 付きの空の結果にして続ける。

        Returns:
            プロジェクトごとの結果 (渡した順)。

        Raises:
            ReadOnlyPreconditionError: 開けない (schema が head でない等) プロジェクトがあり、
                `skip_unavailable` が False の場合。
            ResultSetTooLargeError: 1 プロジェクトの一致件数が上限を超えた場合。
        """
        results: list[ProjectSearchResult] = []
        for project in projects:
            try:
                results.append(self._search_one(project, criteria, max_results_per_project))
            except ReadOnlyPreconditionError as e:
                if not skip_unavailable:
                    raise
                reason = str(e.details.get("reason", "unavailable"))
                logger.warning(f"開けないプロジェクトを検索から外しました: '{project.name}' ({reason})")
                results.append(ProjectSearchResult(project.name, 0, [], unavailable_reason=reason))
        logger.info(
            f"プロジェクト横断検索: projects={len(projects)}, hits={sum(len(r.hits) for r in results)}"
        )
        return results

    def _search_one(
        self, project: SourceProject, criteria: ImageFilterCriteria, max_results_per_project: int
    ) -> ProjectSearchResult:
        """1 プロジェクトを読み取り専用で開いて検索する。"""
        with open_read_only_project(project) as factory:
            repository = ImageRepository(session_factory=factory)
            total = repository.get_images_count_only(criteria)
            if total > max_results_per_project and criteria.image_ids is None:
                raise ResultSetTooLargeError(matched=total, limit=max_results_per_project)
            records, total = repository.get_images_by_filter(criteria)
            image_ids = [int(str(record.get("id") or record.get("image_id"))) for record in records]
            return ProjectSearchResult(
                project_name=project.name,
                total=total,
                hits=self._load_hits(factory, project, image_ids),
            )

    @staticmethod
    def _load_hits(
        factory: sessionmaker[Session], project: SourceProject, image_ids: list[int]
    ) -> list[CrossProjectImageHit]:
        """画像 ID の順に、画像の基本情報と由来を読む。"""
        if not image_ids:
            return []
        rows: dict[int, Image] = {}
        with factory() as session:
            for offset in range(0, len(image_ids), _CHUNK_SIZE):
                chunk = image_ids[offset : offset + _CHUNK_SIZE]
                for loaded in session.execute(select(Image).where(Image.id.in_(chunk))).scalars():
                    rows[loaded.id] = loaded
        origins = ImageOriginRepository(session_factory=factory).list_origins(image_ids)
        return [
            CrossProjectImageHit(
                project_name=project.name,
                image_id=image.id,
                uuid=image.uuid,
                phash=image.phash,
                filename=image.filename,
                width=image.width,
                height=image.height,
                file_path=resolve_stored_path_in_root(image.stored_image_path, project.root),
                origins=origins.get(image.id, []),
            )
            for image_id in image_ids
            if (image := rows.get(image_id)) is not None
        ]


# --- コピー ---


@dataclass(frozen=True)
class ImageTransferItem:
    """画像 1 枚の取り込み結果 (または計画)。

    Attributes:
        source_image_id: コピー元の画像 ID。
        source_uuid: コピー元の画像の uuid。
        action: 扱い (`TransferAction`)。
        target_image_id: 取り込み先の画像 ID。計画 (dry-run) で新規に複製する画像は None。
        annotations_added: 取り込み先に足したアノテーション行の数 (タグ・キャプション・スコア・
            スコアラベル・レーティングの合計)。
    """

    source_image_id: int
    source_uuid: str
    action: TransferAction
    target_image_id: int | None
    annotations_added: int


@dataclass(frozen=True)
class ImageTransferResult:
    """1 回分の取り込み結果。

    Attributes:
        source_project_name: コピー元のプロジェクト名。
        transfer_run_id: 記録した `project_transfer_runs.id`。計画 (dry-run) では None。
        items: 画像ごとの結果 (指定した画像 ID の順)。
        dry_run: 計画だけで何も書いていない場合 True。
    """

    source_project_name: str
    transfer_run_id: int | None
    items: list[ImageTransferItem]
    dry_run: bool

    def count(self, action: TransferAction) -> int:
        """指定した扱いの画像の数を返す。"""
        return sum(1 for item in self.items if item.action == action)


@dataclass
class _FilePlan:
    """コピーするファイル 1 つ (コピー元 → staging → 最終パス)。"""

    source: Path
    staged: Path
    final: Path


@dataclass
class _StageContext:
    """1 回の取り込みで共有するキャッシュと、後で行うファイル操作。"""

    source: SourceProject
    target_root: Path
    staging_dir: Path
    date_dir: str
    run: ProjectTransferRun
    project_id: int | None
    model_ids: dict[str, int] = field(default_factory=dict)
    tag_ids: dict[str, int] = field(default_factory=dict)
    files: list[_FilePlan] = field(default_factory=list)
    reserved: set[Path] = field(default_factory=set)


def _timestamps(row: object, *, updated: bool = True) -> dict[str, datetime]:
    """コピー元の行の `created_at` / `updated_at` を、値があるものだけ返す。

    値が無い (NULL の) 列は渡さず、取り込み先の既定値 (現在時刻) に任せる。
    """
    names = ("created_at", "updated_at") if updated else ("created_at",)
    values: dict[str, datetime] = {}
    for name in names:
        value = getattr(row, name, None)
        if isinstance(value, datetime):
            values[name] = value
    return values


def _time_key(value: datetime | None) -> datetime | None:
    """重複判定に使う時刻。DB から読んだ値 (タイムゾーンなし) と比べられるようタイムゾーンを外す。"""
    return value.replace(tzinfo=None) if value is not None else None


def _copy_file(source: Path, destination: Path) -> None:
    """ファイルを内容と更新日時ごとコピーする。コピー元は読むだけ。"""
    shutil.copy2(source, destination)


class ProjectTransferService:
    """別プロジェクトの画像を、現在のプロジェクト (取り込み先) にコピーする service。"""

    def __init__(
        self,
        target_session_factory: Callable[[], Session],
        target_root: Path,
        target_project_name: str,
    ) -> None:
        """service を初期化する。

        Args:
            target_session_factory: 取り込み先の DB のセッションファクトリ (書き込み可)。
            target_root: 取り込み先のプロジェクトディレクトリ。
            target_project_name: 取り込み先のプロジェクト名 (`projects.name`)。
        """
        self._target_session_factory = target_session_factory
        self._target_root = target_root.resolve()
        self._target_project_name = target_project_name

    def copy_images(
        self, source: SourceProject, image_ids: Sequence[int], *, dry_run: bool = False
    ) -> ImageTransferResult:
        """コピー元の画像を取り込み先にコピーする。

        `dry_run=True` なら、同じ判定を取り込み先のセッションで行ってから rollback し、
        ファイルも DB も変更しない。

        Args:
            source: コピー元のプロジェクト。
            image_ids: コピー元の画像 ID。重複は 1 つにまとめる。
            dry_run: 計画だけを返す場合 True。

        Returns:
            画像ごとの扱いと、記録した取り込みの ID。

        Raises:
            ValueError: コピー元と取り込み先が同じプロジェクト、または画像 ID が空の場合。
            LookupError: コピー元に無い画像 ID がある場合。
            FileNotFoundError: コピー元の画像ファイルが見つからない場合。
            ReadOnlyPreconditionError: コピー元の DB を開けない (schema が head でない等) 場合。
            SQLAlchemyError / OSError: 取り込み先への書き込みに失敗した場合 (何も残さない)。
        """
        if source.root.resolve() == self._target_root:
            raise ValueError(f"コピー元と取り込み先が同じプロジェクトです: {source.name}")
        ordered_ids = list(dict.fromkeys(image_ids))
        if not ordered_ids:
            raise ValueError("コピーする画像 ID がありません")

        logger.info(
            f"プロジェクト間の画像コピー開始: source='{source.name}', images={len(ordered_ids)}, "
            f"dry_run={dry_run}"
        )
        staging_dir = self._target_root / "image_dataset" / _STAGING_DIR_NAME / uuid.uuid4().hex
        with open_read_only_project(source) as source_factory, source_factory() as source_session:
            source_images = self._load_source_images(source_session, ordered_ids)
            metadata = self._load_generation_metadata(source_session, ordered_ids)
            with self._target_session_factory() as target_session:
                context, items = self.stage_images(
                    target_session, source, source_images, metadata, staging_dir=staging_dir
                )
                if dry_run:
                    target_session.rollback()
                    # 計画では新しく複製する画像の ID はまだ決まらない (rollback した仮の ID は返さない)
                    planned = [
                        replace(item, target_image_id=None) if item.action == "copy" else item
                        for item in items
                    ]
                    result = ImageTransferResult(source.name, None, planned, dry_run=True)
                else:
                    self._write_files_and_commit(target_session, context)
                    result = ImageTransferResult(source.name, context.run.id, items, dry_run=False)

        logger.info(
            f"プロジェクト間の画像コピー完了: source='{source.name}', run_id={result.transfer_run_id}, "
            f"copy={result.count('copy')}, link={result.count('link')}, "
            f"already_linked={result.count('already_linked')}, dry_run={dry_run}"
        )
        return result

    # --- 読み込み ---

    @staticmethod
    def _load_source_images(session: Session, image_ids: list[int]) -> list[Image]:
        """コピー元の画像を、アノテーションと処理済み画像ごと指定順に読む。"""
        loaded: dict[int, Image] = {}
        for offset in range(0, len(image_ids), _CHUNK_SIZE):
            chunk = image_ids[offset : offset + _CHUNK_SIZE]
            stmt = (
                select(Image)
                .where(Image.id.in_(chunk))
                .options(
                    selectinload(Image.tags).selectinload(Tag.model).selectinload(Model.model_types),
                    selectinload(Image.captions)
                    .selectinload(Caption.model)
                    .selectinload(Model.model_types),
                    selectinload(Image.scores).selectinload(Score.model).selectinload(Model.model_types),
                    selectinload(Image.score_labels)
                    .selectinload(ScoreLabel.model)
                    .selectinload(Model.model_types),
                    selectinload(Image.ratings).selectinload(Rating.model).selectinload(Model.model_types),
                    selectinload(Image.processed_images),
                )
            )
            for image in session.execute(stmt).scalars():
                loaded[image.id] = image
        missing = [image_id for image_id in image_ids if image_id not in loaded]
        if missing:
            raise LookupError(f"コピー元に画像がありません: {', '.join(str(i) for i in missing)}")
        return [loaded[image_id] for image_id in image_ids]

    @staticmethod
    def _load_generation_metadata(
        session: Session, image_ids: list[int]
    ) -> dict[int, tuple[GenerationMetadata | None, list[GenerationMetadataSource]]]:
        """コピー元の生成メタデータ (解析結果と原データ) を画像ごとに読む。"""
        result: dict[int, tuple[GenerationMetadata | None, list[GenerationMetadataSource]]] = {}
        parsed: dict[int, GenerationMetadata] = {}
        sources: dict[int, list[GenerationMetadataSource]] = {}
        for offset in range(0, len(image_ids), _CHUNK_SIZE):
            chunk = image_ids[offset : offset + _CHUNK_SIZE]
            for row in session.execute(
                select(GenerationMetadata).where(GenerationMetadata.image_id.in_(chunk))
            ).scalars():
                parsed[row.image_id] = row
            for source_row in session.execute(
                select(GenerationMetadataSource)
                .where(GenerationMetadataSource.image_id.in_(chunk))
                .order_by(GenerationMetadataSource.id)
            ).scalars():
                sources.setdefault(source_row.image_id, []).append(source_row)
        for image_id in image_ids:
            result[image_id] = (parsed.get(image_id), sources.get(image_id, []))
        return result

    # --- 取り込み先のセッションへの書き込み (commit はしない) ---

    def stage_images(
        self,
        target_session: Session,
        source: SourceProject,
        source_images: list[Image],
        metadata: dict[int, tuple[GenerationMetadata | None, list[GenerationMetadataSource]]],
        *,
        staging_dir: Path,
    ) -> tuple[_StageContext, list[ImageTransferItem]]:
        """取り込み先のセッションに画像・アノテーション・由来の行を足す。commit もファイル操作もしない。

        プロジェクトの統合 (#1660) が同じトランザクションで版の取り込みと組み合わせられるよう、
        セッションを引数で受け取る。コピーするファイルは戻り値の文脈に積むだけで、
        `_write_files_and_commit` で staging → 最終パスへ移す。

        Args:
            target_session: 取り込み先のセッション。
            source: コピー元のプロジェクト。
            source_images: コピー元の画像 (アノテーションと処理済み画像を読み込み済み)。
            metadata: コピー元の生成メタデータ (画像 ID ごと)。
            staging_dir: ファイルを一時的に置くディレクトリ (取り込み先のプロジェクト内)。

        Returns:
            ファイル操作を含む文脈と、画像ごとの結果。

        Raises:
            FileNotFoundError: コピー元の画像ファイルが見つからない場合。
        """
        run = ProjectTransferRun(
            kind=TRANSFER_KIND_COPY_IMAGES,
            source_project_name=source.name,
            source_project_path=str(source.root.resolve()),
        )
        target_session.add(run)
        # 由来の行が取り込みの ID を参照できるよう、先に ID を確定させる
        target_session.flush()
        context = _StageContext(
            source=source,
            target_root=self._target_root,
            staging_dir=staging_dir,
            date_dir=datetime.now().strftime("%Y/%m/%d"),
            run=run,
            project_id=self._ensure_target_project(target_session),
        )
        self._prefetch_tag_ids(target_session, context, source_images)
        items = [
            self._stage_one(target_session, context, image, *metadata.get(image.id, (None, [])))
            for image in source_images
        ]
        run.copied_images = sum(1 for item in items if item.action == "copy")
        run.linked_images = len(items) - run.copied_images
        target_session.flush()
        return context, items

    def _ensure_target_project(self, session: Session) -> int:
        """取り込み先の `projects` 行を同じセッションで確保する (無ければ作る)。"""
        project = session.execute(
            select(Project).where(Project.name == self._target_project_name)
        ).scalar_one_or_none()
        if project is None:
            project = Project(name=self._target_project_name, path=str(self._target_root))
            session.add(project)
            session.flush()
        return project.id

    @staticmethod
    def _prefetch_tag_ids(session: Session, context: _StageContext, images: list[Image]) -> None:
        """取り込み先で同じタグ文字列に付いている tag_id をまとめて引く (無いタグは NULL のまま)。"""
        names = sorted({tag.tag for image in images for tag in image.tags})
        for offset in range(0, len(names), _CHUNK_SIZE):
            chunk = names[offset : offset + _CHUNK_SIZE]
            rows = session.execute(
                select(Tag.tag, Tag.tag_id)
                .where(Tag.tag.in_(chunk), Tag.tag_id.is_not(None))
                .order_by(Tag.id)
            ).all()
            for name, tag_id in rows:
                if tag_id is not None:
                    context.tag_ids.setdefault(name, tag_id)

    def _stage_one(
        self,
        session: Session,
        context: _StageContext,
        image: Image,
        parsed: GenerationMetadata | None,
        sources: list[GenerationMetadataSource],
    ) -> ImageTransferItem:
        """画像 1 枚を取り込み先のセッションに足す。"""
        candidates = [
            {
                "id": row.id,
                "width": row.width,
                "height": row.height,
                "has_alpha": row.has_alpha,
                "is_grayscale_like": row.is_grayscale_like,
            }
            for row in session.execute(
                select(Image.id, Image.width, Image.height, Image.has_alpha, Image.is_grayscale_like).where(
                    Image.phash == image.phash
                )
            ).all()
        ]
        new_attrs = {
            "width": image.width,
            "height": image.height,
            "has_alpha": image.has_alpha,
            "is_grayscale_like": image.is_grayscale_like,
        }
        classification, existing_id = ImageRepository.classify_phash_candidate(new_attrs, candidates)

        action: TransferAction
        if classification is PhashClassification.DUPLICATE and existing_id is not None:
            target_id = existing_id
            has_origin = session.execute(
                select(ImageOrigin.id).where(
                    ImageOrigin.image_id == target_id,
                    ImageOrigin.source_project_name == context.source.name,
                    ImageOrigin.source_image_uuid == image.uuid,
                )
            ).first()
            action = "already_linked" if has_origin is not None else "link"
        else:
            target_id = self._stage_new_image(session, context, image)
            action = "copy"

        added = self._merge_annotations(session, context, image, target_id)
        self._merge_generation_metadata(session, target_id, parsed, sources)
        if action != "already_linked":
            session.add(
                ImageOrigin(
                    image_id=target_id,
                    transfer_run_id=context.run.id,
                    source_project_name=context.source.name,
                    source_image_id=image.id,
                    source_image_uuid=image.uuid,
                )
            )
        # 同じ実行の後続の画像が、ここで足した画像を同じ画像として見つけられるよう flush する
        session.flush()
        logger.debug(
            f"画像を取り込み: source_id={image.id}, target_id={target_id}, action={action}, "
            f"annotations_added={added}"
        )
        return ImageTransferItem(
            source_image_id=image.id,
            source_uuid=image.uuid,
            action=action,
            target_image_id=target_id,
            annotations_added=added,
        )

    def _stage_new_image(self, session: Session, context: _StageContext, image: Image) -> int:
        """新しい画像の行と処理済み画像の行を足し、ファイルのコピーを予約する。"""
        source_file = self._existing_source_file(context, image.stored_image_path)
        original_final = self._reserve_path(
            context,
            context.target_root
            / "image_dataset"
            / "original_images"
            / context.date_dir
            / context.source.root.name
            / source_file.name,
        )
        self._plan_file(context, source_file, original_final)
        new_image = Image(
            uuid=str(uuid.uuid4()),
            phash=image.phash,
            original_image_path=image.original_image_path,
            stored_image_path=original_final.as_posix(),
            width=image.width,
            height=image.height,
            format=image.format,
            mode=image.mode,
            has_alpha=image.has_alpha,
            filename=image.filename,
            extension=image.extension,
            color_space=image.color_space,
            icc_profile=image.icc_profile,
            is_grayscale_like=image.is_grayscale_like,
            colorfulness_score=image.colorfulness_score,
            project_id=context.project_id,
            reviewed_at=image.reviewed_at,
            **_timestamps(image),
        )
        session.add(new_image)
        session.flush()
        for processed in image.processed_images:
            processed_file = self._existing_source_file(context, processed.stored_image_path)
            processed_final = self._reserve_path(
                context,
                context.target_root
                / "image_dataset"
                / self._resolution_dir_name(processed.stored_image_path)
                / context.date_dir
                / context.source.root.name
                / processed_file.name,
            )
            self._plan_file(context, processed_file, processed_final)
            session.add(
                ProcessedImage(
                    image_id=new_image.id,
                    stored_image_path=processed_final.as_posix(),
                    width=processed.width,
                    height=processed.height,
                    mode=processed.mode,
                    has_alpha=processed.has_alpha,
                    filename=processed_final.name,
                    color_space=processed.color_space,
                    icc_profile=processed.icc_profile,
                    upscaler_used=processed.upscaler_used,
                    **_timestamps(processed),
                )
            )
        return new_image.id

    @staticmethod
    def _existing_source_file(context: _StageContext, stored_path: str) -> Path:
        """コピー元の DB の保存パスを、コピー元のプロジェクト基準で解決し、存在を確かめる。"""
        path = resolve_stored_path_in_root(stored_path, context.source.root)
        if not path.is_file():
            raise FileNotFoundError(f"コピー元の画像ファイルが見つかりません: {path}")
        return path

    @staticmethod
    def _resolution_dir_name(stored_path: str) -> str:
        """処理済み画像の保存パスから解像度のディレクトリ名 (`image_dataset/<解像度>/...`) を取る。"""
        parts = Path(stored_path.replace("\\", "/")).parts
        if "image_dataset" in parts:
            index = parts.index("image_dataset")
            if index + 1 < len(parts) and parts[index + 1].isdigit():
                return parts[index + 1]
        return "processed"

    @staticmethod
    def _reserve_path(context: _StageContext, desired: Path) -> Path:
        """既存のファイルとも、同じ実行で予約したパスとも重ならない最終パスを決める。"""
        candidate = desired
        counter = 1
        while candidate in context.reserved or candidate.exists():
            candidate = desired.with_name(f"{desired.stem}_{counter}{desired.suffix}")
            counter += 1
        context.reserved.add(candidate)
        return candidate

    @staticmethod
    def _plan_file(context: _StageContext, source: Path, final: Path) -> None:
        staged = context.staging_dir / f"{len(context.files):06d}_{final.name}"
        context.files.append(_FilePlan(source=source, staged=staged, final=final))

    def _target_model_id(self, session: Session, context: _StageContext, model: Model | None) -> int | None:
        """コピー元のモデルに対応する取り込み先のモデル ID (`litellm_model_id` で対応付け、無ければ作る)。"""
        if model is None:
            return None
        cached = context.model_ids.get(model.litellm_model_id)
        if cached is not None:
            return cached
        target = session.execute(
            select(Model).where(Model.litellm_model_id == model.litellm_model_id)
        ).scalar_one_or_none()
        if target is None:
            type_names = [model_type.name for model_type in model.model_types]
            model_types = (
                list(session.execute(select(ModelType).where(ModelType.name.in_(type_names))).scalars())
                if type_names
                else []
            )
            target = Model(
                name=model.name,
                provider=model.provider,
                discontinued_at=model.discontinued_at,
                litellm_model_id=model.litellm_model_id,
                estimated_size_gb=model.estimated_size_gb,
                requires_api_key=model.requires_api_key,
                model_types=model_types,
            )
            session.add(target)
            session.flush()
        context.model_ids[model.litellm_model_id] = target.id
        return target.id

    def _merge_annotations(
        self, session: Session, context: _StageContext, image: Image, target_id: int
    ) -> int:
        """アノテーションを和集合で足し、足した行数を返す。

        行の `created_at` / `updated_at` はコピー元の値を引き継ぐ。「現在の値」を最新の `created_at` で
        選ぶ処理 (`ImageRepository._derive_manual_score` 等) が、コピーで選ぶ行を変えないようにするため。

        タグは (モデル, タグ) が既にあれば既存を優先する (一意制約)。キャプション・スコア・スコアラベル・
        レーティングは、値と `created_at` が一致する行があれば足さない。同じ値でも別の時点の記録
        (例: 2 → 8 → 2 の履歴) は残し、同じコピーを繰り返しても行は増えない。
        """
        return (
            self._merge_tags(session, context, image, target_id)
            + self._merge_captions(session, context, image, target_id)
            + self._merge_scores(session, context, image, target_id)
            + self._merge_score_labels(session, context, image, target_id)
            + self._merge_ratings(session, context, image, target_id)
        )

    def _merge_tags(self, session: Session, context: _StageContext, image: Image, target_id: int) -> int:
        added = 0
        tag_keys = {
            (row.model_id, row.tag)
            for row in session.execute(select(Tag.model_id, Tag.tag).where(Tag.image_id == target_id))
        }
        for tag in image.tags:
            model_id = self._target_model_id(session, context, tag.model)
            if (model_id, tag.tag) in tag_keys:
                continue
            tag_keys.add((model_id, tag.tag))
            session.add(
                Tag(
                    image_id=target_id,
                    model_id=model_id,
                    tag=tag.tag,
                    tag_id=context.tag_ids.get(tag.tag),
                    existing=tag.existing,
                    is_edited_manually=tag.is_edited_manually,
                    confidence_score=tag.confidence_score,
                    rejected_at=tag.rejected_at,
                    reject_reason=tag.reject_reason,
                    **_timestamps(tag),
                )
            )
            added += 1
        return added

    def _merge_captions(
        self, session: Session, context: _StageContext, image: Image, target_id: int
    ) -> int:
        added = 0
        caption_keys = {
            (row.model_id, row.caption, _time_key(row.created_at))
            for row in session.execute(
                select(Caption.model_id, Caption.caption, Caption.created_at).where(
                    Caption.image_id == target_id
                )
            )
        }
        for caption in image.captions:
            model_id = self._target_model_id(session, context, caption.model)
            caption_key = (model_id, caption.caption, _time_key(caption.created_at))
            if caption_key in caption_keys:
                continue
            caption_keys.add(caption_key)
            session.add(
                Caption(
                    image_id=target_id,
                    model_id=model_id,
                    caption=caption.caption,
                    existing=caption.existing,
                    is_edited_manually=caption.is_edited_manually,
                    rejected_at=caption.rejected_at,
                    reject_reason=caption.reject_reason,
                    **_timestamps(caption),
                )
            )
            added += 1
        return added

    def _merge_scores(self, session: Session, context: _StageContext, image: Image, target_id: int) -> int:
        added = 0
        score_keys = {
            (row.model_id, row.score, bool(row.is_edited_manually), _time_key(row.created_at))
            for row in session.execute(
                select(Score.model_id, Score.score, Score.is_edited_manually, Score.created_at).where(
                    Score.image_id == target_id
                )
            )
        }
        for score in image.scores:
            model_id = self._target_model_id(session, context, score.model)
            score_key = (model_id, score.score, bool(score.is_edited_manually), _time_key(score.created_at))
            if score_key in score_keys:
                continue
            score_keys.add(score_key)
            session.add(
                Score(
                    image_id=target_id,
                    model_id=model_id,
                    score=score.score,
                    display_score=score.display_score,
                    is_edited_manually=score.is_edited_manually,
                    **_timestamps(score),
                )
            )
            added += 1
        return added

    def _merge_score_labels(
        self, session: Session, context: _StageContext, image: Image, target_id: int
    ) -> int:
        added = 0
        label_keys = {
            (row.model_id, row.label, _time_key(row.created_at))
            for row in session.execute(
                select(ScoreLabel.model_id, ScoreLabel.label, ScoreLabel.created_at).where(
                    ScoreLabel.image_id == target_id
                )
            )
        }
        for label in image.score_labels:
            label_model_id = self._target_model_id(session, context, label.model)
            label_key = (label_model_id, label.label, _time_key(label.created_at))
            if label_model_id is None or label_key in label_keys:
                continue
            label_keys.add(label_key)
            session.add(
                ScoreLabel(
                    image_id=target_id,
                    model_id=label_model_id,
                    label=label.label,
                    is_edited_manually=label.is_edited_manually,
                    **_timestamps(label),
                )
            )
            added += 1
        return added

    def _merge_ratings(self, session: Session, context: _StageContext, image: Image, target_id: int) -> int:
        added = 0
        rating_keys = {
            (row.model_id, row.raw_rating_value, row.normalized_rating, _time_key(row.created_at))
            for row in session.execute(
                select(
                    Rating.model_id, Rating.raw_rating_value, Rating.normalized_rating, Rating.created_at
                ).where(Rating.image_id == target_id)
            )
        }
        for rating in image.ratings:
            rating_model_id = self._target_model_id(session, context, rating.model)
            key = (
                rating_model_id,
                rating.raw_rating_value,
                rating.normalized_rating,
                _time_key(rating.created_at),
            )
            if rating_model_id is None or key in rating_keys:
                continue
            rating_keys.add(key)
            session.add(
                Rating(
                    image_id=target_id,
                    model_id=rating_model_id,
                    raw_rating_value=rating.raw_rating_value,
                    normalized_rating=rating.normalized_rating,
                    confidence_score=rating.confidence_score,
                    **_timestamps(rating),
                )
            )
            added += 1
        return added

    @staticmethod
    def _merge_generation_metadata(
        session: Session,
        target_id: int,
        parsed: GenerationMetadata | None,
        sources: list[GenerationMetadataSource],
    ) -> None:
        """生成メタデータを足す。解析結果は取り込み先に無いときだけ、原データは無いキーだけ足す。"""
        if parsed is not None:
            exists = session.execute(
                select(GenerationMetadata.id).where(GenerationMetadata.image_id == target_id)
            ).first()
            if exists is None:
                session.add(
                    GenerationMetadata(
                        image_id=target_id,
                        status=parsed.status,
                        tool=parsed.tool,
                        parser_name=parsed.parser_name,
                        parser_version=parsed.parser_version,
                        input_sha256=parsed.input_sha256,
                        positive_prompt=parsed.positive_prompt,
                        negative_prompt=parsed.negative_prompt,
                        model_name=parsed.model_name,
                        model_hash=parsed.model_hash,
                        seed=parsed.seed,
                        steps=parsed.steps,
                        sampler=parsed.sampler,
                        cfg_scale=parsed.cfg_scale,
                        loras_json=parsed.loras_json,
                        extra_json=parsed.extra_json,
                        error_message=parsed.error_message,
                        analyzed_at=parsed.analyzed_at,
                    )
                )
        if not sources:
            return
        existing_keys = {
            (row.source_kind, row.source_key)
            for row in session.execute(
                select(GenerationMetadataSource.source_kind, GenerationMetadataSource.source_key).where(
                    GenerationMetadataSource.image_id == target_id
                )
            )
        }
        for source_row in sources:
            if (source_row.source_kind, source_row.source_key) in existing_keys:
                continue
            existing_keys.add((source_row.source_kind, source_row.source_key))
            session.add(
                GenerationMetadataSource(
                    image_id=target_id,
                    source_kind=source_row.source_kind,
                    source_key=source_row.source_key,
                    raw_text=source_row.raw_text,
                    raw_bytes=source_row.raw_bytes,
                    sha256=source_row.sha256,
                    **_timestamps(source_row, updated=False),
                )
            )

    # --- ファイルの配置と commit ---

    @staticmethod
    def _write_files_and_commit(session: Session, context: _StageContext) -> None:
        """ファイルを staging に置いて最終パスへ移し、commit する。失敗したら何も残さない。

        commit に失敗した場合も、移したファイルと作ったディレクトリを消してから例外を伝える。

        Raises:
            OSError: ファイルのコピー・移動に失敗した場合。
            SQLAlchemyError: commit に失敗した場合。
        """
        moved: list[Path] = []
        created_dirs: list[Path] = []
        committed = False
        try:
            context.staging_dir.mkdir(parents=True, exist_ok=True)
            for plan in context.files:
                _copy_file(plan.source, plan.staged)
            for plan in context.files:
                created_dirs.extend(_make_parents(plan.final.parent))
                plan.staged.replace(plan.final)
                moved.append(plan.final)
            session.commit()
            committed = True
        finally:
            if not committed:
                session.rollback()
                for path in moved:
                    path.unlink(missing_ok=True)
                for directory in reversed(created_dirs):
                    _remove_empty_dir(directory)
                logger.warning(
                    f"画像のコピーが失敗したため、取り込み先の変更を取り消しました: "
                    f"source='{context.source.name}', files={len(moved)}"
                )
            shutil.rmtree(context.staging_dir, ignore_errors=True)
            _remove_empty_dir(context.staging_dir.parent)


def _make_parents(directory: Path) -> list[Path]:
    """ディレクトリを作り、新しく作ったディレクトリを親から順に返す。"""
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    directory.mkdir(parents=True, exist_ok=True)
    return list(reversed(missing))


def _remove_empty_dir(directory: Path) -> None:
    """空のディレクトリだけを消す (中身があれば残す)。"""
    try:
        directory.rmdir()
    except OSError:
        return
