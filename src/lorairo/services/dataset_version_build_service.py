"""プロジェクト内の画像 (別プロジェクトからコピーした画像を含む) からデータセットの版を作る service。

ADR 0112 (Issue #1661)。Qt 非依存。

- 学習テキスト (`.txt`) は画像の通常タグのうち採用中 (`rejected_at IS NULL`) のものを、登録順・重複なしで
  「, 」区切りに連結して作る (`learning_text.join_elements`。書き出しと同じ書式)。
- 版の作り方は Kohya 取り込み (#1658) と揃える: 作業中 (`is_working=True`) で作り、フォルダを
  書き終えてから確定し、`KOHYA_DATASET` のタグを最新版へ同期する。途中で失敗したら版を削除する。
- 画像ごとの由来 (コピー元のプロジェクトと画像 ID) は `image_origins` から読んで示す。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
)
from lorairo.database.repository.image_origin import ImageOriginRepository, ImageOriginSnapshot
from lorairo.database.schema import Dataset, DatasetVersion, Image, Tag
from lorairo.services.kohya_scanner import parse_folder_name
from lorairo.services.learning_text import join_elements
from lorairo.utils.log import logger

__all__ = [
    "BuildVersionPlan",
    "BuildVersionRequest",
    "BuildVersionResult",
    "DatasetVersionBuildService",
    "PlannedVersionImage",
    "VersionImageOrigins",
]

_CHUNK_SIZE = 500
_TEXT_EXTENSION = ".txt"


@dataclass(frozen=True)
class BuildVersionRequest:
    """作る版の指定。

    Attributes:
        dataset_name: データセット名 (無ければ作る)。
        version_name: 版の名前 (同じデータセット内で一意)。
        dir_name: フォルダ名 (`<繰り返し数>_<名前>`)。
        image_ids: 版に入れる画像 ID (この順に並べる)。
        trigger_word: フォルダのトリガーワード。指定すると学習テキストの先頭に置く。
        parent_version_id: 派生元の版 ID。
    """

    dataset_name: str
    version_name: str
    dir_name: str
    image_ids: Sequence[int]
    trigger_word: str | None = None
    parent_version_id: int | None = None


@dataclass(frozen=True)
class PlannedVersionImage:
    """版に入れる画像 1 枚。"""

    image_id: int
    file_stem: str
    elements: list[str]
    origins: list[ImageOriginSnapshot]

    @property
    def text(self) -> str:
        """学習テキスト (`.txt`) の内容。"""
        return join_elements(self.elements)


@dataclass(frozen=True)
class BuildVersionPlan:
    """版の作成計画。"""

    request: BuildVersionRequest
    num_repeats: int
    folder_name: str
    images: list[PlannedVersionImage]


@dataclass(frozen=True)
class BuildVersionResult:
    """版の作成結果。"""

    dataset_id: int
    version_id: int
    plan: BuildVersionPlan
    tags_added: int
    tags_removed: int


@dataclass(frozen=True)
class VersionImageOrigins:
    """版の中の画像 1 枚と、その学習テキスト・由来。"""

    dir_name: str
    file_stem: str
    image_id: int
    text: str | None
    origins: list[ImageOriginSnapshot]


class DatasetVersionBuildService:
    """画像 ID の集まりからデータセットの版を作る service。"""

    def __init__(self, session_factory: Callable[[], Session], repository: DatasetRepository) -> None:
        """service を初期化する。

        Args:
            session_factory: プロジェクトの DB のセッションファクトリ。
            repository: 同じ DB の `DatasetRepository`。
        """
        self._session_factory = session_factory
        self._repository = repository
        self._origins = ImageOriginRepository(session_factory=session_factory)

    def propose(self, request: BuildVersionRequest) -> BuildVersionPlan:
        """版の作成計画を作る。何も書かない。

        Args:
            request: 作る版の指定。

        Returns:
            フォルダの繰り返し数・名前と、画像ごとの学習テキスト・由来。

        Raises:
            ValueError: フォルダ名が `<繰り返し数>_<名前>` でない、または画像 ID が空の場合。
            LookupError: 存在しない画像 ID がある場合。
            DatasetConflictError: 同じデータセットに同名の版が既にある場合。
        """
        parsed = parse_folder_name(request.dir_name)
        if parsed is None:
            raise ValueError(f"フォルダ名は <繰り返し数>_<名前> の形にしてください: '{request.dir_name}'")
        image_ids = list(dict.fromkeys(request.image_ids))
        if not image_ids:
            raise ValueError("版に入れる画像 ID がありません")
        trigger = request.trigger_word.strip() if request.trigger_word else None

        with self._session_factory() as session:
            self._ensure_version_name_free(session, request)
            stored_paths = self._load_stored_paths(session, image_ids)
            tags = self._load_adopted_tags(session, image_ids)
        origins = self._origins.list_origins(image_ids)

        used_stems: set[str] = set()
        images: list[PlannedVersionImage] = []
        for image_id in image_ids:
            stem = Path(stored_paths[image_id].replace("\\", "/")).stem
            if stem in used_stems:
                stem = f"{stem}_{image_id}"
            used_stems.add(stem)
            elements = tags.get(image_id, [])
            if trigger:
                elements = [trigger, *(element for element in elements if element != trigger)]
            images.append(PlannedVersionImage(image_id, stem, elements, origins.get(image_id, [])))
        return BuildVersionPlan(
            request=request, num_repeats=parsed[0], folder_name=parsed[1], images=images
        )

    def build(self, request: BuildVersionRequest) -> BuildVersionResult:
        """計画どおりに版を作る。

        Args:
            request: 作る版の指定。

        Returns:
            作った版の ID と、タグ同期の結果。

        Raises:
            ValueError / LookupError / DatasetConflictError: `propose` と同じ。
            SQLAlchemyError: 書き込みに失敗した場合 (作りかけの版は削除する)。
        """
        plan = self.propose(request)
        dataset_id = self._repository.ensure_dataset(request.dataset_name)
        # 取り込み (#1658) と同じく作業中の版として作り、書き終えてから確定する
        version_id = self._repository.create_version(
            dataset_id, request.version_name, request.parent_version_id, is_working=True
        )
        completed = False
        try:
            folder_images = [
                FolderImageSpec(
                    image_id=image.image_id,
                    file_stem=image.file_stem,
                    texts=[LearningTextSpec(_TEXT_EXTENSION, image.text, list(image.elements))],
                )
                for image in plan.images
            ]
            spec = FolderSpec(
                dir_name=request.dir_name,
                name=plan.folder_name,
                num_repeats=plan.num_repeats,
                trigger_word=request.trigger_word.strip() if request.trigger_word else None,
                position=0,
            )
            self._repository.add_folder(version_id, spec, folder_images)
            self._repository.finalize_imported_version(version_id)
            tag_sync = self._repository.sync_kohya_tags_for_dataset(dataset_id)
            completed = True
        finally:
            if not completed:
                self._rollback(version_id)
        logger.info(
            f"版を作成: dataset='{request.dataset_name}', version='{request.version_name}', "
            f"version_id={version_id}, images={len(plan.images)}, "
            f"projects={len({o.source_project_name for i in plan.images for o in i.origins})}"
        )
        return BuildVersionResult(
            dataset_id=dataset_id,
            version_id=version_id,
            plan=plan,
            tags_added=tag_sync.tags_added,
            tags_removed=tag_sync.tags_removed,
        )

    def describe_version(self, version_id: int) -> tuple[str, str, list[VersionImageOrigins]]:
        """版の画像・学習テキスト・由来を返す。

        Args:
            version_id: `dataset_versions.id`。

        Returns:
            (データセット名, 版の名前, フォルダ順・登録順の画像ごとの一覧)。

        Raises:
            LookupError: 版が存在しない場合。
        """
        snapshot = self._repository.get_version_snapshot(version_id)
        image_ids = [image.image_id for folder in snapshot.folders for image in folder.images]
        origins = self._origins.list_origins(image_ids)
        rows: list[VersionImageOrigins] = []
        for folder in snapshot.folders:
            for image in folder.images:
                text = next((t.raw_text for t in image.texts if t.extension == _TEXT_EXTENSION), None)
                rows.append(
                    VersionImageOrigins(
                        dir_name=folder.dir_name,
                        file_stem=image.file_stem,
                        image_id=image.image_id,
                        text=text,
                        origins=origins.get(image.image_id, []),
                    )
                )
        return snapshot.dataset_name, snapshot.version_name, rows

    @staticmethod
    def _ensure_version_name_free(session: Session, request: BuildVersionRequest) -> None:
        exists = session.execute(
            select(DatasetVersion.id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.name == request.dataset_name, DatasetVersion.name == request.version_name)
        ).first()
        if exists is not None:
            raise DatasetConflictError(
                f"同じ名前の版が既にあります: dataset='{request.dataset_name}', version='{request.version_name}'"
            )

    @staticmethod
    def _load_stored_paths(session: Session, image_ids: list[int]) -> dict[int, str]:
        paths: dict[int, str] = {}
        for offset in range(0, len(image_ids), _CHUNK_SIZE):
            chunk = image_ids[offset : offset + _CHUNK_SIZE]
            for image_id, stored in session.execute(
                select(Image.id, Image.stored_image_path).where(Image.id.in_(chunk))
            ).all():
                paths[image_id] = stored
        missing = [image_id for image_id in image_ids if image_id not in paths]
        if missing:
            raise LookupError(f"画像が見つかりません: {', '.join(str(i) for i in missing)}")
        return paths

    @staticmethod
    def _load_adopted_tags(session: Session, image_ids: list[int]) -> dict[int, list[str]]:
        """画像ごとの採用中のタグを、登録順・重複なしで返す (書き出しと同じく却下済みは除く)。"""
        tags: dict[int, list[str]] = {}
        for offset in range(0, len(image_ids), _CHUNK_SIZE):
            chunk = image_ids[offset : offset + _CHUNK_SIZE]
            rows = session.execute(
                select(Tag.image_id, Tag.tag)
                .where(Tag.image_id.in_(chunk), Tag.rejected_at.is_(None))
                .order_by(Tag.image_id, Tag.id)
            ).all()
            for image_id, tag in rows:
                if image_id is None or not tag:
                    continue
                collected = tags.setdefault(image_id, [])
                if tag not in collected:
                    collected.append(tag)
        return tags

    def _rollback(self, version_id: int) -> None:
        """作りかけの版を削除する。元の例外を隠さないため、後始末の失敗はログに残すだけにする。"""
        try:
            self._repository.delete_imported_version(version_id, [])
        except SQLAlchemyError:
            logger.opt(exception=True).error(f"作りかけの版を削除できませんでした: version_id={version_id}")
        else:
            logger.warning(f"版の作成が失敗したため、作りかけの版を削除しました: version_id={version_id}")
