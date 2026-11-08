"""Kohya-ss 学習データセット (版・フォルダ・学習テキスト・学習設定) の Repository (Issue #1413)。

設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`。

- 学習テキストは画像直下の `Tag` とは別に、フォルダ内の画像ごとに保持する。
- 版の `raw_text` は取り込み後に書き換えない。本 Repository は `raw_text` の更新 API を持たない。
- 同名の版・フォルダの作成や、フォルダ追加中の制約違反は `DatasetConflictError` とし、
  フォルダ追加は 1 トランザクションで中途半端な行を残さない。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, fields

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ...utils.log import logger
from ..schema import (
    Dataset,
    DatasetFolder,
    DatasetFolderImage,
    DatasetLearningText,
    DatasetVersion,
    TrainingConfig,
)
from .base import BaseRepository


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


def _dump_elements(elements: list[str]) -> str:
    # 日本語などをエスケープせずに保存する
    return json.dumps(elements, ensure_ascii=False)


def _load_elements(elements_json: str) -> list[str]:
    loaded = json.loads(elements_json)
    return [str(element) for element in loaded]


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
            )

    def update_learning_text_elements(self, text_id: int, elements: list[str]) -> None:
        """学習テキストの要素を更新し、編集済みにする。`raw_text` は変更しない。

        既存の行を直接書き換えるため、確定した版に対して呼ぶと ADR 0098 の「版は後から書き換えない」
        に反する。現在 service・CLI・GUI からは呼ばれていない (Issue #1455 で外部編集 + 取り込み直しを採用)。
        LoRAIro 内での編集 (作業中の版を編集して確定する案) を実装するときは、確定前の版にだけ使う。

        Args:
            text_id: `dataset_learning_texts.id`。
            elements: 新しい要素のリスト。

        Raises:
            LookupError: 学習テキストが存在しない場合。
        """
        with self.session_factory() as session:
            text = session.get(DatasetLearningText, text_id)
            if text is None:
                raise LookupError(f"学習テキストが見つかりません: text_id={text_id}")
            text.elements_json = _dump_elements(elements)
            text.is_edited = True
            session.commit()
            logger.debug(f"学習テキストの要素を更新: id={text_id}, elements={len(elements)}")

    def set_folder_trigger_word(self, folder_id: int, trigger_word: str | None) -> None:
        """フォルダのトリガーワードを設定する。

        Args:
            folder_id: `dataset_folders.id`。
            trigger_word: トリガーワード。`None` で解除する。

        Raises:
            LookupError: フォルダが存在しない場合。
        """
        with self.session_factory() as session:
            folder = session.get(DatasetFolder, folder_id)
            if folder is None:
                raise LookupError(f"フォルダが見つかりません: folder_id={folder_id}")
            folder.trigger_word = trigger_word
            session.commit()
            logger.debug(f"トリガーワードを設定: folder_id={folder_id}, trigger_word={trigger_word!r}")

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
