"""Kohya-ss 学習データセット (版・フォルダ・学習テキスト・学習設定) の Repository (Issue #1413)。

設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`。

- 学習テキストは画像直下の `Tag` とは別に、フォルダ内の画像ごとに保持する。
- 版の `raw_text` は取り込み後に書き換えない。本 Repository は `raw_text` の更新 API を持たない。
- 同名の版・フォルダの作成や、フォルダ追加中の制約違反は `DatasetConflictError` とし、
  フォルダ追加は 1 トランザクションで中途半端な行を残さない。
- 学習テキストをライブラリの `Tag` へ写すのは明示的な操作 (`copy_learning_texts_to_tags`) だけで、
  擬似モデル `KOHYA_DATASET` の行として追加する (ADR 0104)。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, fields

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ...utils.log import logger
from ..schema import (
    Dataset,
    DatasetFolder,
    DatasetFolderImage,
    DatasetImage,
    DatasetLearningText,
    DatasetVersion,
    Tag,
    TrainingConfig,
)
from .base import BaseRepository
from .model import ModelRepository

__all__ = [
    "DatasetConflictError",
    "DatasetFolderImage",
    "DatasetImage",
    "DatasetRepository",
    "FolderImageSnapshot",
    "FolderImageSpec",
    "FolderSnapshot",
    "FolderSpec",
    "LearningTextSnapshot",
    "LearningTextSpec",
    "TagCopyResult",
    "TrainingConfigSnapshot",
    "TrainingConfigSpec",
    "VersionSnapshot",
    "VersionSummary",
]


class DatasetConflictError(ValueError):
    """同名の版・フォルダの作成や、取り込み中の制約違反で登録できないときの例外。"""


@dataclass(frozen=True)
class FolderSpec:
    """版に追加するフォルダの値。"""

    dir_name: str
    name: str
    num_repeats: int
    trigger_word: str | None
    position: int


@dataclass(frozen=True)
class LearningTextSpec:
    """画像 1 枚分の学習テキスト (`.txt` / `.caption`)。"""

    extension: str
    raw_text: str
    elements: list[str]


@dataclass(frozen=True)
class FolderImageSpec:
    """フォルダに所属させる画像と、その学習テキスト。"""

    image_id: int
    file_stem: str
    texts: list[LearningTextSpec]


@dataclass(frozen=True)
class LearningTextSnapshot:
    """保存済みの学習テキスト。"""

    id: int
    extension: str
    raw_text: str
    elements: list[str]
    is_edited: bool


@dataclass(frozen=True)
class FolderImageSnapshot:
    """保存済みのフォルダ内画像。"""

    image_id: int
    file_stem: str
    texts: list[LearningTextSnapshot]


@dataclass(frozen=True)
class FolderSnapshot:
    """保存済みのフォルダ。"""

    id: int
    dir_name: str
    name: str
    num_repeats: int
    trigger_word: str | None
    position: int
    images: list[FolderImageSnapshot]


@dataclass(frozen=True)
class VersionSnapshot:
    """版の中身一式。"""

    dataset_name: str
    version_name: str
    parent_version_id: int | None
    folders: list[FolderSnapshot]
    is_working: bool = False


@dataclass(frozen=True)
class VersionSummary:
    """版の一覧の 1 行。"""

    version_id: int
    version_name: str
    dataset_id: int
    dataset_name: str
    parent_version_id: int | None
    created_at: datetime.datetime | None
    folder_count: int
    image_count: int
    is_working: bool = False


@dataclass(frozen=True)
class ImageDatasetUsage:
    """画像が使われたデータセット・版・フォルダ・学習テキストの 1 件 (フォルダ所属単位)。"""

    image_id: int
    dataset_id: int
    dataset_name: str
    version_id: int
    version_name: str
    parent_version_id: int | None
    folder_id: int
    dir_name: str
    folder_name: str
    num_repeats: int
    trigger_word: str | None
    file_stem: str
    texts: list[LearningTextSnapshot]


@dataclass(frozen=True)
class TrainingConfigSpec:
    """追加する学習設定 (`TrainingConfig` の列と同名)。秘密の値は呼び出し側で除去済みであること。"""

    source_kind: str
    source_file_name: str
    raw_content: str
    normalized_json: str
    unmapped_json: str
    target_script: str | None = None
    output_name: str | None = None
    base_model: str | None = None
    resolution: str | None = None
    network_dim: int | None = None
    network_alpha: float | None = None
    learning_rate: float | None = None


@dataclass(frozen=True)
class TrainingConfigSnapshot:
    """保存済みの学習設定 (`TrainingConfig` の列と同名)。"""

    id: int
    dataset_id: int
    version_id: int | None
    source_kind: str
    source_file_name: str
    raw_content: str
    normalized_json: str
    unmapped_json: str
    target_script: str | None
    output_name: str | None
    base_model: str | None
    resolution: str | None
    network_dim: int | None
    network_alpha: float | None
    learning_rate: float | None
    created_at: datetime.datetime


@dataclass(frozen=True)
class TagCopyResult:
    """学習テキストをライブラリの `Tag` へ写した結果。"""

    folders: int
    images: int
    tags_added: int
    tags_skipped: int
    dry_run: bool


def _dump_elements(elements: list[str]) -> str:
    # 日本語などをエスケープせずに保存する
    return json.dumps(elements, ensure_ascii=False)


def _load_elements(elements_json: str) -> list[str]:
    loaded = json.loads(elements_json)
    return [str(element) for element in loaded]


def _join_elements(elements: list[str]) -> str:
    return ", ".join(elements)


def _resolve_version_id(version_or_id: int | DatasetVersion) -> int:
    return version_or_id.id if isinstance(version_or_id, DatasetVersion) else version_or_id


def _normalize_extension(extension: str) -> str:
    return extension if extension.startswith(".") else f".{extension}"


def _collect_elements_by_image(folders: list[DatasetFolder], extension: str) -> dict[int, list[str]]:
    """フォルダ群の学習テキストの要素を、画像ごとの和集合 (最初に現れた順) にまとめる。"""
    elements_by_image: dict[int, list[str]] = {}
    for folder in folders:
        for folder_image in sorted(folder.images, key=lambda i: i.id):
            for text in folder_image.learning_texts:
                if text.extension != extension:
                    continue
                collected = elements_by_image.setdefault(folder_image.image_id, [])
                for element in _load_elements(text.elements_json):
                    if element and element not in collected:
                        collected.append(element)
    return elements_by_image


def _to_config_snapshot(config: TrainingConfig) -> TrainingConfigSnapshot:
    return TrainingConfigSnapshot(
        id=config.id,
        dataset_id=config.dataset_id,
        version_id=config.version_id,
        source_kind=config.source_kind,
        source_file_name=config.source_file_name,
        raw_content=config.raw_content,
        normalized_json=config.normalized_json,
        unmapped_json=config.unmapped_json,
        target_script=config.target_script,
        output_name=config.output_name,
        base_model=config.base_model,
        resolution=config.resolution,
        network_dim=config.network_dim,
        network_alpha=config.network_alpha,
        learning_rate=config.learning_rate,
        created_at=config.created_at,
    )


def _copy_folders_from_version(base_version: DatasetVersion) -> list[DatasetFolder]:
    """派生元の版のフォルダ・画像所属・学習テキストを全量コピーした新しい ORM 行群を返す。"""
    copied_folders: list[DatasetFolder] = []
    for base_folder in sorted(base_version.folders, key=lambda f: (f.position, f.id)):
        folder = DatasetFolder(
            dir_name=base_folder.dir_name,
            name=base_folder.name,
            num_repeats=base_folder.num_repeats,
            trigger_word=base_folder.trigger_word,
            position=base_folder.position,
        )
        for base_image in sorted(base_folder.images, key=lambda i: i.id):
            folder_image = DatasetFolderImage(
                image_id=base_image.image_id,
                file_stem=base_image.file_stem,
            )
            folder_image.learning_texts = [
                DatasetLearningText(
                    extension=base_text.extension,
                    raw_text=base_text.raw_text,
                    elements_json=base_text.elements_json,
                    is_edited=base_text.is_edited,
                )
                for base_text in sorted(base_image.learning_texts, key=lambda t: t.id)
            ]
            folder.images.append(folder_image)
        copied_folders.append(folder)
    return copied_folders


def _reset_folder_image_texts(folder_image: DatasetFolderImage, trigger_word: str | None) -> None:
    """画像の差し替え時に学習テキストをリセットする (既存拡張子を保ちトリガーワードがあればそれだけ残す)。"""
    target_ext: str | None = None
    if any(t.extension == ".txt" for t in folder_image.learning_texts):
        target_ext = ".txt"
    elif folder_image.learning_texts:
        target_ext = folder_image.learning_texts[0].extension
    for text in folder_image.learning_texts:
        if text.extension == target_ext:
            reset_elements = [trigger_word] if trigger_word else []
        else:
            reset_elements = []
        text.elements_json = _dump_elements(reset_elements)
        text.raw_text = _join_elements(reset_elements)
        text.is_edited = True
    if target_ext is None and trigger_word:
        folder_image.learning_texts.append(
            DatasetLearningText(
                extension=".txt",
                raw_text=trigger_word,
                elements_json=_dump_elements([trigger_word]),
                is_edited=True,
            )
        )


def _image_has_trigger_word(folder_image: DatasetFolderImage, trigger_word: str, extension: str) -> bool:
    """指定拡張子の学習テキスト要素にトリガーワードが含まれるか判定する。"""
    for text in folder_image.learning_texts:
        if text.extension == extension and trigger_word in _load_elements(text.elements_json):
            return True
    return False


class DatasetRepository(BaseRepository):
    """学習データセットの版・フォルダ・学習テキスト・学習設定を扱う Repository。"""

    def ensure_dataset(self, name: str, description: str | None = None) -> int:
        """同名のデータセットがあればその ID を、無ければ作成して ID を返す。

        Args:
            name: データセット名 (UNIQUE)。
            description: 新規作成時の説明。既存のデータセットは変更しない。

        Returns:
            `datasets.id`。

        Raises:
            DatasetConflictError: 同時に同名で作成され一意制約に違反した場合。
        """
        with self.session_factory() as session:
            existing_id = session.execute(
                select(Dataset.id).where(Dataset.name == name)
            ).scalar_one_or_none()
            if existing_id is not None:
                return existing_id
            dataset = Dataset(name=name, description=description)
            session.add(dataset)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(f"データセットを作成できません: name='{name}'") from e
            dataset_id: int = dataset.id
            logger.debug(f"データセットを作成: id={dataset_id}, name='{name}'")
            return dataset_id

    def create_version(self, dataset_id: int, name: str, parent_version_id: int | None = None) -> int:
        """データセットに版を作成する。

        Args:
            dataset_id: `datasets.id`。
            name: 版の名前。同じデータセット内で一意。
            parent_version_id: 派生元の版 ID。

        Returns:
            `dataset_versions.id`。

        Raises:
            DatasetConflictError: 同じデータセットに同名の版がある、または参照先が存在しない場合。
        """
        with self.session_factory() as session:
            version = DatasetVersion(dataset_id=dataset_id, name=name, parent_version_id=parent_version_id)
            session.add(version)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"版を作成できません: dataset_id={dataset_id}, name='{name}'"
                ) from e
            version_id: int = version.id
            logger.debug(f"版を作成: id={version_id}, dataset_id={dataset_id}, name='{name}'")
            return version_id

    def add_folder(self, version_id: int, spec: FolderSpec, images: list[FolderImageSpec]) -> int:
        """版にフォルダと、その画像の所属・学習テキストを 1 トランザクションで追加する。

        途中で制約違反が起きた場合は全体をロールバックし、フォルダ行も画像行も残さない。

        Args:
            version_id: `dataset_versions.id`。
            spec: フォルダの値。
            images: フォルダに所属させる画像と学習テキスト。

        Returns:
            `dataset_folders.id`。

        Raises:
            DatasetConflictError: 同じ版に同名のフォルダがある、同じフォルダに同じ `file_stem` が
                重複する、存在しない画像 ID を参照するなど、制約に違反した場合。
        """
        with self.session_factory() as session:
            folder = DatasetFolder(
                version_id=version_id,
                dir_name=spec.dir_name,
                name=spec.name,
                num_repeats=spec.num_repeats,
                trigger_word=spec.trigger_word,
                position=spec.position,
            )
            for image_spec in images:
                folder_image = DatasetFolderImage(
                    image_id=image_spec.image_id, file_stem=image_spec.file_stem
                )
                folder_image.learning_texts = [
                    DatasetLearningText(
                        extension=text.extension,
                        raw_text=text.raw_text,
                        elements_json=_dump_elements(text.elements),
                        is_edited=False,
                    )
                    for text in image_spec.texts
                ]
                folder.images.append(folder_image)
            session.add(folder)
            try:
                session.commit()
            except IntegrityError as e:
                # UNIQUE / FK 違反はまとめて衝突として扱い、行を一切残さない
                session.rollback()
                raise DatasetConflictError(
                    f"フォルダを追加できません: version_id={version_id}, dir_name='{spec.dir_name}'"
                ) from e
            folder_id: int = folder.id
            logger.debug(
                f"フォルダを追加: id={folder_id}, version_id={version_id}, "
                f"dir_name='{spec.dir_name}', images={len(images)}"
            )
            return folder_id

    def get_version_snapshot(self, version_id: int) -> VersionSnapshot:
        """版の中身 (フォルダ・画像・学習テキスト) を取得する。

        フォルダは `position` 順、画像と学習テキストは登録順に並ぶ。

        Args:
            version_id: `dataset_versions.id`。

        Returns:
            版のスナップショット。

        Raises:
            LookupError: 版が存在しない場合。
        """
        with self.session_factory() as session:
            stmt = (
                select(DatasetVersion)
                .where(DatasetVersion.id == version_id)
                .options(
                    selectinload(DatasetVersion.dataset),
                    selectinload(DatasetVersion.folders)
                    .selectinload(DatasetFolder.images)
                    .selectinload(DatasetFolderImage.learning_texts),
                )
            )
            version = session.execute(stmt).scalar_one_or_none()
            if version is None:
                raise LookupError(f"版が見つかりません: version_id={version_id}")

            folders = [
                FolderSnapshot(
                    id=folder.id,
                    dir_name=folder.dir_name,
                    name=folder.name,
                    num_repeats=folder.num_repeats,
                    trigger_word=folder.trigger_word,
                    position=folder.position,
                    images=[
                        FolderImageSnapshot(
                            image_id=folder_image.image_id,
                            file_stem=folder_image.file_stem,
                            texts=[
                                LearningTextSnapshot(
                                    id=text.id,
                                    extension=text.extension,
                                    raw_text=text.raw_text,
                                    elements=_load_elements(text.elements_json),
                                    is_edited=text.is_edited,
                                )
                                for text in sorted(folder_image.learning_texts, key=lambda t: t.id)
                            ],
                        )
                        for folder_image in sorted(folder.images, key=lambda i: i.id)
                    ],
                )
                for folder in sorted(version.folders, key=lambda f: (f.position, f.id))
            ]
            return VersionSnapshot(
                dataset_name=version.dataset.name,
                version_name=version.name,
                parent_version_id=version.parent_version_id,
                folders=folders,
                is_working=version.is_working,
            )

    def create_working_version(
        self,
        dataset_id: int,
        base_version_id: int | None = None,
        version_name: str | None = None,
    ) -> DatasetVersion:
        """確定済みの版を全量コピーして、編集可能な「作業中の版」(`is_working=True`) を作成する。

        Args:
            dataset_id: `datasets.id`。
            base_version_id: 派生元の確定済み版の ID。`None` なら最新の確定済み版を使う。
            version_name: 作業中の版の名前。`None` なら派生元の名前から自動採番する。

        Returns:
            作成した作業中の版 (`DatasetVersion`)。

        Raises:
            ValueError: 同じデータセットに未確定の作業中の版が既にある、派生元の確定済み版が
                存在しない、または同名の版と衝突した場合。
        """
        if version_name is not None and not version_name.strip():
            raise ValueError("版の名前を空にはできません")

        with self.session_factory() as session:
            existing_working_id = session.execute(
                select(DatasetVersion.id).where(
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.is_working.is_(True),
                )
            ).scalar_one_or_none()
            if existing_working_id is not None:
                raise ValueError(
                    f"作業中の版が既に存在します: dataset_id={dataset_id}, version_id={existing_working_id}"
                )

            base_stmt = (
                select(DatasetVersion)
                .where(
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.is_working.is_(False),
                )
                .options(
                    selectinload(DatasetVersion.folders)
                    .selectinload(DatasetFolder.images)
                    .selectinload(DatasetFolderImage.learning_texts)
                )
            )
            if base_version_id is not None:
                base_stmt = base_stmt.where(DatasetVersion.id == base_version_id)
            else:
                base_stmt = base_stmt.order_by(DatasetVersion.id.desc()).limit(1)
            base_version = session.execute(base_stmt).scalar_one_or_none()
            if base_version is None:
                raise ValueError(
                    f"派生元となる確定済みの版が見つかりません: dataset_id={dataset_id}, "
                    f"base_version_id={base_version_id}"
                )

            resolved_name = version_name or self._propose_working_version_name(
                dataset_id, base_version.name, session
            )
            working = DatasetVersion(
                dataset_id=dataset_id,
                name=resolved_name,
                parent_version_id=base_version.id,
                is_working=True,
                folders=_copy_folders_from_version(base_version),
            )
            session.add(working)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"作業中の版を作成できません: dataset_id={dataset_id}, name='{resolved_name}'"
                ) from e

            loaded = self._load_detached_version(session, working.id)
            logger.debug(
                f"作業中の版を作成: id={loaded.id}, dataset_id={dataset_id}, "
                f"base_version_id={loaded.parent_version_id}, name='{loaded.name}'"
            )
            return loaded

    @staticmethod
    def _propose_working_version_name(dataset_id: int, base_name: str, session: Session) -> str:
        existing_names = set(
            session.execute(
                select(DatasetVersion.name).where(DatasetVersion.dataset_id == dataset_id)
            ).scalars()
        )
        candidate = f"{base_name}-working"
        suffix = 2
        while candidate in existing_names:
            candidate = f"{base_name}-working-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _load_detached_version(session: Session, version_id: int) -> DatasetVersion:
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.id == version_id)
            .options(
                selectinload(DatasetVersion.dataset),
                selectinload(DatasetVersion.folders)
                .selectinload(DatasetFolder.images)
                .selectinload(DatasetFolderImage.learning_texts),
            )
        )
        loaded = session.execute(stmt).scalar_one()
        session.expunge_all()
        return loaded

    @staticmethod
    def _get_working_folder(session: Session, folder_id: int) -> DatasetFolder:
        stmt = (
            select(DatasetFolder)
            .where(DatasetFolder.id == folder_id)
            .options(selectinload(DatasetFolder.version))
        )
        folder = session.execute(stmt).scalar_one_or_none()
        if folder is None:
            raise LookupError(f"フォルダが見つかりません: folder_id={folder_id}")
        if not folder.version.is_working:
            raise ValueError(f"確定済みの版は編集できません: version_id={folder.version.id}")
        return folder

    def update_learning_text_elements(
        self,
        text_id: int | None = None,
        elements: list[str] | None = None,
        *,
        learning_text_id: int | None = None,
    ) -> None:
        """作業中の版の学習テキスト要素を更新し、編集済みにする。`raw_text` は変更しない。

        確定済みの版 (`is_working=False`) に対して呼ぶと ADR 0098 の「版は後から書き換えない」に
        反するため `ValueError` で拒否する。

        Args:
            text_id: `dataset_learning_texts.id`。
            elements: 新しい要素のリスト。
            learning_text_id: `text_id` のキーワード別名。

        Raises:
            LookupError: 学習テキストが存在しない場合。
            ValueError: 確定済みの版 (`is_working=False`) の学習テキストを編集しようとした場合。
        """
        resolved_id = text_id if text_id is not None else learning_text_id
        if resolved_id is None or elements is None:
            raise TypeError("text_id (または learning_text_id) と elements を指定してください")
        with self.session_factory() as session:
            stmt = (
                select(DatasetLearningText)
                .where(DatasetLearningText.id == resolved_id)
                .options(
                    selectinload(DatasetLearningText.folder_image)
                    .selectinload(DatasetFolderImage.folder)
                    .selectinload(DatasetFolder.version)
                )
            )
            text = session.execute(stmt).scalar_one_or_none()
            if text is None:
                raise LookupError(f"学習テキストが見つかりません: text_id={resolved_id}")
            version = text.folder_image.folder.version
            if not version.is_working:
                raise ValueError(f"確定済みの版は編集できません: version_id={version.id}")
            text.elements_json = _dump_elements(elements)
            text.is_edited = True
            session.commit()
            logger.debug(f"学習テキストの要素を更新: id={resolved_id}, elements={len(elements)}")

    def update_working_folder_trigger_word(self, folder_id: int, trigger_word: str | None) -> None:
        """作業中の版のフォルダのトリガーワードを更新する。

        Args:
            folder_id: `dataset_folders.id`。
            trigger_word: トリガーワード。`None` または空文字で解除する。

        Raises:
            LookupError: フォルダが存在しない場合。
            ValueError: 確定済みの版 (`is_working=False`) のフォルダを編集しようとした場合。
        """
        with self.session_factory() as session:
            folder = self._get_working_folder(session, folder_id)
            cleaned = trigger_word.strip() if trigger_word is not None else None
            folder.trigger_word = cleaned or None
            session.commit()
            logger.debug(
                f"トリガーワードを設定: folder_id={folder_id}, trigger_word={folder.trigger_word!r}"
            )

    def set_folder_trigger_word(self, folder_id: int, trigger_word: str | None) -> None:
        """作業中の版のフォルダのトリガーワードを設定する (`update_working_folder_trigger_word` の別名)。"""
        self.update_working_folder_trigger_word(folder_id, trigger_word)

    def add_image_to_working_folder(
        self,
        folder_id: int,
        image_id: int,
        file_stem: str,
        elements: list[str] | None = None,
        extension: str = ".txt",
        auto_prepend_trigger_word: bool = True,
    ) -> DatasetFolderImage:
        """作業中の版のフォルダに画像と学習テキストを追加する。

        `auto_prepend_trigger_word=True` かつフォルダに `trigger_word` が設定されていて、
        まだ `elements` に含まれていない場合は先頭に付与する。

        Args:
            folder_id: `dataset_folders.id`。
            image_id: 追加する `images.id`。
            file_stem: フォルダ内でのファイル名 (拡張子なし)。
            elements: 学習テキストの要素リスト。
            extension: 学習テキストの拡張子 (既定 `.txt`)。
            auto_prepend_trigger_word: トリガーワードを先頭に自動付与するか。

        Returns:
            追加した `DatasetFolderImage`。

        Raises:
            LookupError: フォルダが存在しない場合。
            ValueError: 確定済みの版に対して呼んだ場合、または同名 `file_stem`・不正 `image_id` 等の制約違反。
        """
        normalized_ext = _normalize_extension(extension)
        with self.session_factory() as session:
            folder = self._get_working_folder(session, folder_id)
            final_elements = list(elements) if elements is not None else []
            if (
                auto_prepend_trigger_word
                and folder.trigger_word
                and folder.trigger_word not in final_elements
            ):
                final_elements = [folder.trigger_word, *final_elements]

            folder_image = DatasetFolderImage(
                folder_id=folder.id,
                image_id=image_id,
                file_stem=file_stem,
                learning_texts=[
                    DatasetLearningText(
                        extension=normalized_ext,
                        raw_text=_join_elements(final_elements),
                        elements_json=_dump_elements(final_elements),
                        is_edited=True,
                    )
                ],
            )
            session.add(folder_image)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"フォルダに画像を追加できません: folder_id={folder_id}, file_stem='{file_stem}'"
                ) from e

            loaded = session.execute(
                select(DatasetFolderImage)
                .where(DatasetFolderImage.id == folder_image.id)
                .options(selectinload(DatasetFolderImage.learning_texts))
            ).scalar_one()
            session.expunge_all()
            logger.debug(
                f"作業中のフォルダに画像を追加: folder_id={folder_id}, image_id={image_id}, "
                f"file_stem='{file_stem}'"
            )
            return loaded

    def replace_image_in_working_folder(
        self,
        folder_id: int,
        old_file_stem: str,
        new_image_id: int,
        new_file_stem: str | None = None,
        inherit_texts: bool = True,
    ) -> DatasetFolderImage:
        """作業中の版のフォルダ内の画像を別画像に差し替える。

        `inherit_texts=True` (既定) のときは旧画像の学習テキスト (`raw_text`・`elements`) をそのまま
        引き継ぐ。`False` のときは学習テキストをリセットする (フォルダに `trigger_word` があれば
        `.txt` にそのトリガーワードだけを残し、無ければ空にする)。

        Args:
            folder_id: `dataset_folders.id`。
            old_file_stem: 差し替え元の `file_stem`。
            new_image_id: 差し替え先の `images.id`。
            new_file_stem: 新しい `file_stem`。`None` なら `old_file_stem` を維持する。
            inherit_texts: 旧画像の学習テキストを引き継ぐか (既定 `True`)。

        Returns:
            更新後の `DatasetFolderImage`。

        Raises:
            LookupError: フォルダまたは差し替え元の画像が存在しない場合。
            ValueError: 確定済みの版に対して呼んだ場合、または制約違反。
        """
        with self.session_factory() as session:
            folder = self._get_working_folder(session, folder_id)
            folder_image = session.execute(
                select(DatasetFolderImage)
                .where(
                    DatasetFolderImage.folder_id == folder_id,
                    DatasetFolderImage.file_stem == old_file_stem,
                )
                .options(selectinload(DatasetFolderImage.learning_texts))
            ).scalar_one_or_none()
            if folder_image is None:
                raise LookupError(
                    f"フォルダ内に画像が見つかりません: folder_id={folder_id}, file_stem='{old_file_stem}'"
                )

            folder_image.image_id = new_image_id
            if new_file_stem is not None:
                folder_image.file_stem = new_file_stem
            if not inherit_texts:
                _reset_folder_image_texts(folder_image, folder.trigger_word)

            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"フォルダ内の画像を差し替えできません: folder_id={folder_id}, "
                    f"old_file_stem='{old_file_stem}'"
                ) from e

            loaded = session.execute(
                select(DatasetFolderImage)
                .where(DatasetFolderImage.id == folder_image.id)
                .options(selectinload(DatasetFolderImage.learning_texts))
            ).scalar_one()
            session.expunge_all()
            logger.debug(
                f"作業中のフォルダの画像を差し替え: folder_id={folder_id}, "
                f"file_stem='{loaded.file_stem}', new_image_id={new_image_id}, "
                f"inherit_texts={inherit_texts}"
            )
            return loaded

    def remove_image_from_working_folder(self, folder_id: int, file_stem: str) -> None:
        """作業中の版のフォルダから画像とその学習テキストを削除する。

        Args:
            folder_id: `dataset_folders.id`。
            file_stem: 削除する画像の `file_stem`。

        Raises:
            LookupError: フォルダまたは対象の画像が存在しない場合。
            ValueError: 確定済みの版に対して呼んだ場合。
        """
        with self.session_factory() as session:
            self._get_working_folder(session, folder_id)
            folder_image = session.execute(
                select(DatasetFolderImage).where(
                    DatasetFolderImage.folder_id == folder_id,
                    DatasetFolderImage.file_stem == file_stem,
                )
            ).scalar_one_or_none()
            if folder_image is None:
                raise LookupError(
                    f"フォルダ内に画像が見つかりません: folder_id={folder_id}, file_stem='{file_stem}'"
                )
            session.delete(folder_image)
            session.commit()
            logger.debug(f"作業中のフォルダから画像を削除: folder_id={folder_id}, file_stem='{file_stem}'")

    def find_images_missing_trigger_word(
        self,
        version_id: int | DatasetVersion,
        extension: str = ".txt",
    ) -> list[DatasetFolderImage]:
        """トリガーワードが設定されたフォルダ内で、学習テキスト要素にそのトリガーワードを含まない画像を返す。

        Args:
            version_id: `dataset_versions.id` または `DatasetVersion`。
            extension: 検査する学習テキストの拡張子 (既定 `.txt`)。

        Returns:
            トリガーワードが欠落している `DatasetFolderImage` のリスト。

        Raises:
            LookupError: 版が存在しない場合。
        """
        resolved_id = _resolve_version_id(version_id)
        normalized_ext = _normalize_extension(extension)
        with self.session_factory() as session:
            if session.get(DatasetVersion, resolved_id) is None:
                raise LookupError(f"版が見つかりません: version_id={resolved_id}")
            stmt = (
                select(DatasetFolder)
                .where(DatasetFolder.version_id == resolved_id)
                .options(
                    selectinload(DatasetFolder.images).selectinload(DatasetFolderImage.learning_texts),
                    selectinload(DatasetFolder.images).selectinload(DatasetFolderImage.image),
                    selectinload(DatasetFolder.images).selectinload(DatasetFolderImage.folder),
                )
                .order_by(DatasetFolder.position, DatasetFolder.id)
            )
            folders = list(session.execute(stmt).scalars())
            missing: list[DatasetFolderImage] = []
            for folder in folders:
                if not folder.trigger_word:
                    continue
                for folder_image in sorted(folder.images, key=lambda i: i.id):
                    if not _image_has_trigger_word(folder_image, folder.trigger_word, normalized_ext):
                        missing.append(folder_image)
            session.expunge_all()
            return missing

    def commit_working_version(
        self,
        version_id: int | DatasetVersion,
        version_name: str | None = None,
    ) -> DatasetVersion:
        """作業中の版を確定して不変 (`is_working=False`) にする。

        Args:
            version_id: 確定する作業中の版の ID または `DatasetVersion`。
            version_name: 確定時の新しい版名。`None` なら現在の名前を維持する。

        Returns:
            確定した `DatasetVersion` (`is_working=False`)。

        Raises:
            LookupError: 版が存在しない場合。
            ValueError: 既に確定済みの版に対して呼んだ場合、版名が空の場合、または版名が衝突した場合。
        """
        resolved_id = _resolve_version_id(version_id)
        if version_name is not None and not version_name.strip():
            raise ValueError("版の名前を空にはできません")
        with self.session_factory() as session:
            version = session.get(DatasetVersion, resolved_id)
            if version is None:
                raise LookupError(f"版が見つかりません: version_id={resolved_id}")
            if not version.is_working:
                raise ValueError(f"既に確定済みの版です: version_id={resolved_id}")
            if version_name is not None:
                version.name = version_name
            version.is_working = False
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"作業中の版を確定できません: version_id={resolved_id}, name={version.name!r}"
                ) from e
            loaded = self._load_detached_version(session, resolved_id)
            logger.debug(f"作業中の版を確定: id={loaded.id}, name='{loaded.name}'")
            return loaded

    def discard_working_version(self, version_id: int | DatasetVersion) -> None:
        """作業中の版 (`is_working=True`) を破棄し、そのフォルダ・画像所属・学習テキストを削除する。

        確定済みの版 (`is_working=False`) は破棄できない。

        Args:
            version_id: 破棄する作業中の版の ID または `DatasetVersion`。

        Raises:
            LookupError: 版が存在しない場合。
            ValueError: 確定済みの版 (`is_working=False`) を破棄しようとした場合。
        """
        resolved_id = _resolve_version_id(version_id)
        with self.session_factory() as session:
            version = session.get(DatasetVersion, resolved_id)
            if version is None:
                raise LookupError(f"版が見つかりません: version_id={resolved_id}")
            if not version.is_working:
                raise ValueError(f"確定済みの版は破棄できません: version_id={resolved_id}")
            session.delete(version)
            session.commit()
            logger.debug(f"作業中の版を破棄: id={resolved_id}")

    def add_training_config(self, dataset_id: int, version_id: int | None, spec: TrainingConfigSpec) -> int:
        """学習設定を追加する。

        Args:
            dataset_id: `datasets.id`。
            version_id: 対応する版の ID。版に紐づかない場合は `None`。
            spec: 学習設定の値。

        Returns:
            `training_configs.id`。

        Raises:
            DatasetConflictError: 参照先のデータセット・版が存在しない場合。
        """
        with self.session_factory() as session:
            values = {field.name: getattr(spec, field.name) for field in fields(spec)}
            config = TrainingConfig(dataset_id=dataset_id, version_id=version_id, **values)
            session.add(config)
            try:
                session.commit()
            except IntegrityError as e:
                session.rollback()
                raise DatasetConflictError(
                    f"学習設定を追加できません: dataset_id={dataset_id}, version_id={version_id}"
                ) from e
            config_id: int = config.id
            logger.debug(
                f"学習設定を追加: id={config_id}, dataset_id={dataset_id}, source_kind='{spec.source_kind}'"
            )
            return config_id

    def list_training_configs(self, dataset_id: int) -> list[TrainingConfigSnapshot]:
        """データセットの学習設定を登録順に返す。

        Args:
            dataset_id: `datasets.id`。

        Returns:
            学習設定のリスト。無ければ空。
        """
        with self.session_factory() as session:
            stmt = (
                select(TrainingConfig)
                .where(TrainingConfig.dataset_id == dataset_id)
                .order_by(TrainingConfig.id)
            )
            return [_to_config_snapshot(config) for config in session.execute(stmt).scalars()]

    def get_training_config(self, config_id: int) -> TrainingConfigSnapshot:
        """学習設定を 1 件取得する。

        Args:
            config_id: `training_configs.id`。

        Returns:
            学習設定。

        Raises:
            LookupError: 学習設定が存在しない場合。
        """
        with self.session_factory() as session:
            config = session.get(TrainingConfig, config_id)
            if config is None:
                raise LookupError(f"学習設定が見つかりません: config_id={config_id}")
            return _to_config_snapshot(config)

    def copy_learning_texts_to_tags(
        self,
        version_id: int,
        dir_names: list[str] | None = None,
        extension: str = ".txt",
        dry_run: bool = False,
    ) -> TagCopyResult:
        """版の学習テキストの要素を、画像直下の `Tag` へ擬似モデル `KOHYA_DATASET` の行として写す。

        ADR 0104 の規則に従う:

        - 対象は選んだフォルダ (`None` なら版の全フォルダ) の、指定した拡張子の学習テキスト。
          同じ画像が対象の複数フォルダにあるときは要素の和集合を写す。
        - 表記は要素のまま (`clean_format` もタグ DB での解決もしない)。`tag_id` は空、
          `existing=True`, `is_edited_manually=False`。
        - 追加だけを行う。`KOHYA_DATASET` の同じ行 (soft-reject 済みを含む) が既にあれば飛ばし、
          他のモデルの行には触れない。1 トランザクションで行い、途中で失敗したら何も残さない。

        Args:
            version_id: `dataset_versions.id`。
            dir_names: 対象のフォルダ名。`None` なら版の全フォルダ。
            extension: 写す学習テキストの拡張子 (例: `.txt`)。
            dry_run: True なら件数だけ数えて書き込まない (擬似モデル行も作らない)。

        Returns:
            写した件数。

        Raises:
            LookupError: 版、または指定したフォルダが存在しない場合。
        """
        with self.session_factory() as session:
            if session.get(DatasetVersion, version_id) is None:
                raise LookupError(f"版が見つかりません: version_id={version_id}")
            stmt = (
                select(DatasetFolder)
                .where(DatasetFolder.version_id == version_id)
                .options(selectinload(DatasetFolder.images).selectinload(DatasetFolderImage.learning_texts))
                .order_by(DatasetFolder.position, DatasetFolder.id)
            )
            folders = list(session.execute(stmt).scalars())
            if dir_names is not None:
                unknown = sorted(set(dir_names) - {folder.dir_name for folder in folders})
                if unknown:
                    raise LookupError(f"フォルダが見つかりません: {', '.join(unknown)}")
                folders = [folder for folder in folders if folder.dir_name in set(dir_names)]

            elements_by_image = _collect_elements_by_image(folders, extension)

            model_id = ModelRepository.get_or_create_kohya_dataset_model(session)
            # SQLite のバインド変数上限を超えないよう、画像 ID を分割して既存行を引く
            existing: set[tuple[int, str]] = set()
            image_ids = list(elements_by_image)
            for offset in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                chunk = image_ids[offset : offset + self.BATCH_CHUNK_SIZE]
                rows = session.execute(
                    select(Tag.image_id, Tag.tag).where(Tag.model_id == model_id, Tag.image_id.in_(chunk))
                ).all()
                existing.update((row.image_id, row.tag) for row in rows if row.image_id is not None)

            new_tags = [
                Tag(
                    image_id=image_id,
                    model_id=model_id,
                    tag=element,
                    tag_id=None,
                    confidence_score=None,
                    existing=True,
                    is_edited_manually=False,
                )
                for image_id, elements in elements_by_image.items()
                for element in elements
                if (image_id, element) not in existing
            ]
            total = sum(len(elements) for elements in elements_by_image.values())
            result = TagCopyResult(
                folders=len(folders),
                images=len(elements_by_image),
                tags_added=len(new_tags),
                tags_skipped=total - len(new_tags),
                dry_run=dry_run,
            )
            if dry_run:
                session.rollback()
                return result
            session.add_all(new_tags)
            session.commit()
            logger.debug(
                f"学習テキストを Tag へ写す: version_id={version_id}, folders={result.folders}, "
                f"images={result.images}, added={result.tags_added}, skipped={result.tags_skipped}"
            )
            return result

    def list_versions(self) -> list[VersionSummary]:
        """全データセットの版を、フォルダ数・画像数 (フォルダごとの所属数の合計) とともに返す。

        Returns:
            データセット名、版 ID の順に並べた版の一覧。無ければ空。
        """
        with self.session_factory() as session:
            folder_counts = (
                select(DatasetFolder.version_id, func.count(DatasetFolder.id).label("folders"))
                .group_by(DatasetFolder.version_id)
                .subquery()
            )
            image_counts = (
                select(DatasetFolder.version_id, func.count(DatasetFolderImage.id).label("images"))
                .join(DatasetFolderImage, DatasetFolderImage.folder_id == DatasetFolder.id)
                .group_by(DatasetFolder.version_id)
                .subquery()
            )
            stmt = (
                select(
                    DatasetVersion.id,
                    DatasetVersion.name,
                    Dataset.id,
                    Dataset.name,
                    DatasetVersion.parent_version_id,
                    DatasetVersion.created_at,
                    func.coalesce(folder_counts.c.folders, 0),
                    func.coalesce(image_counts.c.images, 0),
                    DatasetVersion.is_working,
                )
                .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
                .outerjoin(folder_counts, folder_counts.c.version_id == DatasetVersion.id)
                .outerjoin(image_counts, image_counts.c.version_id == DatasetVersion.id)
                .order_by(Dataset.name, DatasetVersion.id)
            )
            return [
                VersionSummary(
                    version_id=row[0],
                    version_name=row[1],
                    dataset_id=row[2],
                    dataset_name=row[3],
                    parent_version_id=row[4],
                    created_at=row[5],
                    folder_count=int(row[6]),
                    image_count=int(row[7]),
                    is_working=bool(row[8]),
                )
                for row in session.execute(stmt).all()
            ]

    def list_image_usage(self, image_id: int) -> list[ImageDatasetUsage]:
        """画像が使われたデータセット・版・フォルダ・学習テキストの一覧を返す。

        使われていない画像 (または存在しない画像 ID) では空のリストを返す。
        所属行と親テーブルは JOIN の 1 クエリ、学習テキストは `selectinload` の 1 クエリで
        まとめて引き、N+1 にしない。

        Args:
            image_id: `images.id`。

        Returns:
            データセット名、版 ID、フォルダ順 (`position`, `id`)、所属 ID 順に並べた一覧。
        """
        with self.session_factory() as session:
            stmt = (
                select(DatasetFolderImage, DatasetFolder, DatasetVersion, Dataset)
                .join(DatasetFolder, DatasetFolder.id == DatasetFolderImage.folder_id)
                .join(DatasetVersion, DatasetVersion.id == DatasetFolder.version_id)
                .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
                .where(DatasetFolderImage.image_id == image_id)
                .options(selectinload(DatasetFolderImage.learning_texts))
                .order_by(
                    Dataset.name,
                    DatasetVersion.id,
                    DatasetFolder.position,
                    DatasetFolder.id,
                    DatasetFolderImage.id,
                )
            )
            rows = session.execute(stmt).all()
            return [
                ImageDatasetUsage(
                    image_id=folder_image.image_id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    version_id=version.id,
                    version_name=version.name,
                    parent_version_id=version.parent_version_id,
                    folder_id=folder.id,
                    dir_name=folder.dir_name,
                    folder_name=folder.name,
                    num_repeats=folder.num_repeats,
                    trigger_word=folder.trigger_word,
                    file_stem=folder_image.file_stem,
                    texts=[
                        LearningTextSnapshot(
                            id=text.id,
                            extension=text.extension,
                            raw_text=text.raw_text,
                            elements=_load_elements(text.elements_json),
                            is_edited=text.is_edited,
                        )
                        for text in sorted(folder_image.learning_texts, key=lambda t: t.id)
                    ],
                )
                for folder_image, folder, version, dataset in rows
            ]
