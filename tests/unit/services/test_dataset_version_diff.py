"""`dataset_version_diff` の単体テスト (Issue #1455)。

版のスナップショット同士を比べ、フォルダ・画像・学習テキストの追加 / 削除 / 変更を出す。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.database.repository.dataset import (
    FolderImageSnapshot,
    FolderSnapshot,
    LearningTextSnapshot,
    VersionSnapshot,
)
from lorairo.services.dataset_version_diff import (
    ChangeStatus,
    DatasetVersionDiffService,
    diff_snapshots,
)
from lorairo.services.learning_text import split_elements

pytestmark = pytest.mark.unit


def _text(raw: str, extension: str = ".txt", elements: list[str] | None = None) -> LearningTextSnapshot:
    return LearningTextSnapshot(
        id=0,
        extension=extension,
        raw_text=raw,
        elements=split_elements(raw) if elements is None else elements,
        is_edited=elements is not None,
    )


def _image(stem: str, image_id: int, *texts: LearningTextSnapshot) -> FolderImageSnapshot:
    return FolderImageSnapshot(image_id=image_id, file_stem=stem, texts=list(texts))


def _folder(
    dir_name: str,
    *images: FolderImageSnapshot,
    num_repeats: int = 10,
    trigger_word: str | None = None,
) -> FolderSnapshot:
    return FolderSnapshot(
        id=0,
        dir_name=dir_name,
        name=dir_name.split("_", 1)[1],
        num_repeats=num_repeats,
        trigger_word=trigger_word,
        position=0,
        images=list(images),
    )


def _version(*folders: FolderSnapshot, name: str = "v") -> VersionSnapshot:
    return VersionSnapshot(
        dataset_name="ds", version_name=name, parent_version_id=None, folders=list(folders)
    )


def test_identical_versions_have_no_changes() -> None:
    folder = _folder("10_a", _image("a1", 1, _text("trig, smile")))

    diff = diff_snapshots(_version(folder), _version(folder))

    assert diff.has_changes is False
    assert diff.folders == []
    assert diff.summary.folders_added == 0


def test_folder_added_and_removed() -> None:
    base = _version(_folder("10_a", _image("a1", 1)))
    target = _version(_folder("5_b", _image("b1", 2), _image("b2", 3)))

    diff = diff_snapshots(base, target)

    statuses = {change.dir_name: change for change in diff.folders}
    assert statuses["10_a"].status is ChangeStatus.REMOVED
    assert statuses["10_a"].base_image_count == 1
    assert statuses["5_b"].status is ChangeStatus.ADDED
    assert statuses["5_b"].target_image_count == 2
    assert diff.summary.folders_added == 1
    assert diff.summary.folders_removed == 1


def test_folder_attribute_change_is_reported() -> None:
    base = _version(_folder("10_a", _image("a1", 1), trigger_word=None))
    target = _version(_folder("10_a", _image("a1", 1), num_repeats=10, trigger_word="trig"))

    diff = diff_snapshots(base, target)

    (change,) = diff.folders
    assert change.status is ChangeStatus.CHANGED
    assert change.trigger_word == (None, "trig")
    assert change.num_repeats is None
    assert change.images == []


def test_image_added_removed_and_replaced() -> None:
    base = _version(_folder("10_a", _image("a1", 1), _image("a2", 2), _image("a3", 3)))
    target = _version(_folder("10_a", _image("a1", 1), _image("a2", 20), _image("a4", 4)))

    diff = diff_snapshots(base, target)

    (folder,) = diff.folders
    images = {change.file_stem: change for change in folder.images}
    assert set(images) == {"a2", "a3", "a4"}
    assert images["a2"].status is ChangeStatus.REPLACED
    assert (images["a2"].base_image_id, images["a2"].target_image_id) == (2, 20)
    assert images["a3"].status is ChangeStatus.REMOVED
    assert images["a4"].status is ChangeStatus.ADDED
    assert diff.summary.images_added == 1
    assert diff.summary.images_removed == 1
    assert diff.summary.images_replaced == 1


def test_learning_text_elements_added_removed() -> None:
    base = _version(_folder("10_a", _image("a1", 1, _text("trig, smile, blue eyes"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("trig, blue eyes, long hair"))))

    diff = diff_snapshots(base, target)

    (image,) = diff.folders[0].images
    assert image.status is ChangeStatus.CHANGED
    (text,) = image.texts
    assert text.extension == ".txt"
    assert text.status is ChangeStatus.CHANGED
    assert text.added_elements == ["long hair"]
    assert text.removed_elements == ["smile"]
    assert text.reordered is False
    assert diff.summary.texts_changed == 1


def test_learning_text_reorder_only() -> None:
    base = _version(_folder("10_a", _image("a1", 1, _text("trig, smile"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("smile, trig"))))

    (text,) = diff_snapshots(base, target).folders[0].images[0].texts

    assert text.added_elements == []
    assert text.removed_elements == []
    assert text.reordered is True


def test_whitespace_only_change_is_reported_as_changed_without_element_diff() -> None:
    """要素は同じでも、書き出される本文 (原文) が違えば変更として出す。"""
    base = _version(_folder("10_a", _image("a1", 1, _text("trig, smile"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("trig,smile\n"))))

    (text,) = diff_snapshots(base, target).folders[0].images[0].texts

    assert text.status is ChangeStatus.CHANGED
    assert text.added_elements == []
    assert text.removed_elements == []
    assert text.reordered is False


def test_edited_text_is_compared_by_exported_content() -> None:
    """編集済みの学習テキストは、書き出しと同じく要素から組み立てた本文で比べる。"""
    base = _version(_folder("10_a", _image("a1", 1, _text("trig, smile"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("old raw", elements=["trig", "smile"]))))

    diff = diff_snapshots(base, target)

    assert diff.has_changes is False


def test_learning_text_added_and_removed_by_extension() -> None:
    base = _version(_folder("10_a", _image("a1", 1, _text("trig"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("a caption", extension=".caption"))))

    (image,) = diff_snapshots(base, target).folders[0].images
    texts = {text.extension: text for text in image.texts}

    assert texts[".txt"].status is ChangeStatus.REMOVED
    assert texts[".txt"].removed_elements == ["trig"]
    assert texts[".caption"].status is ChangeStatus.ADDED
    assert texts[".caption"].added_elements == ["a caption"]


def test_duplicated_elements_are_counted_as_multiset() -> None:
    base = _version(_folder("10_a", _image("a1", 1, _text("a, a, b"))))
    target = _version(_folder("10_a", _image("a1", 1, _text("a, b"))))

    (text,) = diff_snapshots(base, target).folders[0].images[0].texts

    assert text.removed_elements == ["a"]
    assert text.added_elements == []


def test_service_loads_both_snapshots_from_repository() -> None:
    repository = MagicMock()
    base = _version(_folder("10_a", _image("a1", 1)), name="v1")
    target = _version(_folder("10_a", _image("a1", 1), _image("a2", 2)), name="v2")
    repository.get_version_snapshot.side_effect = lambda version_id: {1: base, 2: target}[version_id]

    diff = DatasetVersionDiffService(repository).diff_versions(1, 2)

    assert (diff.base_version_id, diff.target_version_id) == (1, 2)
    assert (diff.base_version_name, diff.target_version_name) == ("v1", "v2")
    assert diff.summary.images_added == 1


def test_service_propagates_lookup_error_for_missing_version() -> None:
    repository = MagicMock()
    repository.get_version_snapshot.side_effect = LookupError("missing")

    with pytest.raises(LookupError):
        DatasetVersionDiffService(repository).diff_versions(1, 99)
