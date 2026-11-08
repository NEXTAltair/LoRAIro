"""Kohya-ss データセットの 2 つの版を比べる (Issue #1455, Qt-free)。

ADR 0098 のとおり版は全量を持ち、比較は表示時に計算する。保存はしない。

- フォルダは `dir_name` で対応させ、追加 / 削除と、繰り返し回数・トリガーワードの変更を出す。
- フォルダ内の画像は `file_stem` (学習テキストのファイル名の基準) で対応させる。
  同じ `file_stem` で `image_id` が違えば差し替えとする。
- 学習テキストは拡張子ごとに対応させ、書き出される本文 (未編集なら原文、編集済みなら要素から
  組み立てた本文。`KohyaDatasetExportService` と同じ) が違えば変更とする。
  要素の追加 / 削除は重複を数える多重集合で数え、並び替えだけのときは `reordered` を立てる。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ..database.repository.dataset import (
    FolderImageSnapshot,
    FolderSnapshot,
    LearningTextSnapshot,
    VersionSnapshot,
)
from .learning_text import join_elements


class ChangeStatus(StrEnum):
    """差分の種類。"""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    REPLACED = "replaced"


@dataclass(frozen=True)
class TextChange:
    """学習テキスト 1 件 (拡張子単位) の差分。"""

    extension: str
    status: ChangeStatus
    added_elements: list[str]
    removed_elements: list[str]
    reordered: bool


@dataclass(frozen=True)
class ImageChange:
    """フォルダ内の画像 1 枚 (`file_stem` 単位) の差分。"""

    file_stem: str
    status: ChangeStatus
    base_image_id: int | None
    target_image_id: int | None
    texts: list[TextChange]


@dataclass(frozen=True)
class FolderChange:
    """フォルダ 1 つ (`dir_name` 単位) の差分。

    `num_repeats` / `trigger_word` は変わったときだけ `(比較元, 比較先)` を持つ。
    `images` は両方の版にあるフォルダだけで計算する。
    """

    dir_name: str
    status: ChangeStatus
    base_image_count: int
    target_image_count: int
    num_repeats: tuple[int, int] | None = None
    trigger_word: tuple[str | None, str | None] | None = None
    images: list[ImageChange] = field(default_factory=list)


@dataclass(frozen=True)
class VersionDiffSummary:
    """差分の件数。"""

    folders_added: int = 0
    folders_removed: int = 0
    folders_changed: int = 0
    images_added: int = 0
    images_removed: int = 0
    images_replaced: int = 0
    images_changed: int = 0
    texts_added: int = 0
    texts_removed: int = 0
    texts_changed: int = 0


@dataclass(frozen=True)
class VersionDiff:
    """2 つの版の差分。変更の無いフォルダ・画像・学習テキストは含めない。"""

    base_dataset_name: str
    base_version_name: str
    target_dataset_name: str
    target_version_name: str
    folders: list[FolderChange]
    summary: VersionDiffSummary
    base_version_id: int | None = None
    target_version_id: int | None = None

    @property
    def has_changes(self) -> bool:
        """差分が 1 件でもあれば True。"""
        return bool(self.folders)


class VersionSnapshotSource(Protocol):
    """版のスナップショットを返すもの (`DatasetRepository`)。"""

    def get_version_snapshot(self, version_id: int) -> VersionSnapshot:
        """版のスナップショットを返す。"""
        ...


def _exported_content(text: LearningTextSnapshot) -> str:
    # 書き出しと同じ規則: 未編集なら原文、編集済みなら要素から組み立てる
    return join_elements(text.elements) if text.is_edited else text.raw_text


def _subtract(elements: list[str], other: list[str]) -> list[str]:
    """`elements` から `other` を多重集合として引いた残りを、`elements` の順で返す。"""
    remaining = Counter(other)
    result: list[str] = []
    for element in elements:
        if remaining[element] > 0:
            remaining[element] -= 1
        else:
            result.append(element)
    return result


def _diff_text(base: LearningTextSnapshot | None, target: LearningTextSnapshot | None) -> TextChange | None:
    if base is None and target is not None:
        return TextChange(target.extension, ChangeStatus.ADDED, list(target.elements), [], False)
    if target is None and base is not None:
        return TextChange(base.extension, ChangeStatus.REMOVED, [], list(base.elements), False)
    if base is None or target is None or _exported_content(base) == _exported_content(target):
        return None
    added = _subtract(target.elements, base.elements)
    removed = _subtract(base.elements, target.elements)
    reordered = not added and not removed and base.elements != target.elements
    return TextChange(target.extension, ChangeStatus.CHANGED, added, removed, reordered)


def _diff_texts(base: FolderImageSnapshot, target: FolderImageSnapshot) -> list[TextChange]:
    base_texts = {text.extension: text for text in base.texts}
    target_texts = {text.extension: text for text in target.texts}
    extensions = list(base_texts) + [ext for ext in target_texts if ext not in base_texts]
    changes = [_diff_text(base_texts.get(ext), target_texts.get(ext)) for ext in extensions]
    return [change for change in changes if change is not None]


def _diff_images(base: FolderSnapshot, target: FolderSnapshot) -> list[ImageChange]:
    base_images = {image.file_stem: image for image in base.images}
    target_images = {image.file_stem: image for image in target.images}
    changes: list[ImageChange] = []
    for stem, base_image in base_images.items():
        target_image = target_images.get(stem)
        if target_image is None:
            changes.append(ImageChange(stem, ChangeStatus.REMOVED, base_image.image_id, None, []))
            continue
        texts = _diff_texts(base_image, target_image)
        if base_image.image_id != target_image.image_id:
            status = ChangeStatus.REPLACED
        elif texts:
            status = ChangeStatus.CHANGED
        else:
            continue
        changes.append(ImageChange(stem, status, base_image.image_id, target_image.image_id, texts))
    for stem, target_image in target_images.items():
        if stem not in base_images:
            changes.append(ImageChange(stem, ChangeStatus.ADDED, None, target_image.image_id, []))
    return changes


def _diff_folder(base: FolderSnapshot, target: FolderSnapshot) -> FolderChange | None:
    num_repeats = (base.num_repeats, target.num_repeats) if base.num_repeats != target.num_repeats else None
    trigger_word = (
        (base.trigger_word, target.trigger_word) if base.trigger_word != target.trigger_word else None
    )
    images = _diff_images(base, target)
    if num_repeats is None and trigger_word is None and not images:
        return None
    return FolderChange(
        dir_name=target.dir_name,
        status=ChangeStatus.CHANGED,
        base_image_count=len(base.images),
        target_image_count=len(target.images),
        num_repeats=num_repeats,
        trigger_word=trigger_word,
        images=images,
    )


def _summarize(folders: list[FolderChange]) -> VersionDiffSummary:
    folder_counts = Counter(change.status for change in folders)
    images = [image for folder in folders for image in folder.images]
    image_counts = Counter(image.status for image in images)
    text_counts = Counter(text.status for image in images for text in image.texts)
    return VersionDiffSummary(
        folders_added=folder_counts[ChangeStatus.ADDED],
        folders_removed=folder_counts[ChangeStatus.REMOVED],
        folders_changed=folder_counts[ChangeStatus.CHANGED],
        images_added=image_counts[ChangeStatus.ADDED],
        images_removed=image_counts[ChangeStatus.REMOVED],
        images_replaced=image_counts[ChangeStatus.REPLACED],
        images_changed=image_counts[ChangeStatus.CHANGED],
        texts_added=text_counts[ChangeStatus.ADDED],
        texts_removed=text_counts[ChangeStatus.REMOVED],
        texts_changed=text_counts[ChangeStatus.CHANGED],
    )


def diff_snapshots(
    base: VersionSnapshot,
    target: VersionSnapshot,
    base_version_id: int | None = None,
    target_version_id: int | None = None,
) -> VersionDiff:
    """2 つの版のスナップショットを比べる。

    Args:
        base: 比較元の版。
        target: 比較先の版。
        base_version_id: 比較元の版 ID (結果に載せるだけ)。
        target_version_id: 比較先の版 ID (結果に載せるだけ)。

    Returns:
        比較元から比較先への差分。フォルダは比較元の順、比較先にだけあるものはその後に並ぶ。
    """
    base_folders = {folder.dir_name: folder for folder in base.folders}
    target_folders = {folder.dir_name: folder for folder in target.folders}
    folders: list[FolderChange] = []
    for dir_name, base_folder in base_folders.items():
        target_folder = target_folders.get(dir_name)
        if target_folder is None:
            folders.append(FolderChange(dir_name, ChangeStatus.REMOVED, len(base_folder.images), 0))
            continue
        change = _diff_folder(base_folder, target_folder)
        if change is not None:
            folders.append(change)
    for dir_name, target_folder in target_folders.items():
        if dir_name not in base_folders:
            folders.append(FolderChange(dir_name, ChangeStatus.ADDED, 0, len(target_folder.images)))
    return VersionDiff(
        base_dataset_name=base.dataset_name,
        base_version_name=base.version_name,
        target_dataset_name=target.dataset_name,
        target_version_name=target.version_name,
        folders=folders,
        summary=_summarize(folders),
        base_version_id=base_version_id,
        target_version_id=target_version_id,
    )


class DatasetVersionDiffService:
    """保存済みの 2 つの版を読み込んで比べる (Qt-free)。"""

    def __init__(self, repository: VersionSnapshotSource) -> None:
        """初期化する。

        Args:
            repository: 版のスナップショットを返す Repository。
        """
        self._repository = repository

    def diff_versions(self, base_version_id: int, target_version_id: int) -> VersionDiff:
        """2 つの版を比べる。

        Args:
            base_version_id: 比較元の版 ID。
            target_version_id: 比較先の版 ID。

        Returns:
            比較元から比較先への差分。

        Raises:
            LookupError: どちらかの版が存在しない場合。
        """
        base = self._repository.get_version_snapshot(base_version_id)
        target = self._repository.get_version_snapshot(target_version_id)
        return diff_snapshots(base, target, base_version_id, target_version_id)
