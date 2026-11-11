"""ディレクトリ取り込み時のサブフォルダ共通タグ (Issue #1409)。

取り込みダイアログで、画像を直接含むサブフォルダごとに共通タグを入力できる。
入力したタグは、そのサブフォルダ直下の全画像へ手動タグ (MANUAL_EDIT) として付く。
タグ DB の入力規則には合わせず、入力した表記のまま保存する。
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..filesystem import FileSystemManager

FolderCommonTags = Mapping[Path, Sequence[str]]
"""選択ディレクトリからの相対パス (サブフォルダ) → 共通タグ列。"""


@dataclass(frozen=True)
class ImageSubfolder:
    """画像を直接含むサブフォルダ。

    Attributes:
        relative_path: 選択ディレクトリからの相対パス。
        image_count: サブフォルダ直下の画像数。
    """

    relative_path: Path
    image_count: int


def list_image_subfolders(
    directory: Path,
    cancel_check: Callable[[], None] | None = None,
) -> list[ImageSubfolder]:
    """画像を直接含むサブフォルダを相対パス順で列挙する。

    走査対象と拡張子判定は登録処理と同じ ``FileSystemManager.get_image_files`` に従う
    (ADR 0086)。選択ディレクトリ直下の画像はサブフォルダではないため含めない。

    Args:
        directory: 取り込み対象として選んだディレクトリ。
        cancel_check: 走査中にキャンセル要求を検査するコールバック。

    Returns:
        サブフォルダの一覧。ディレクトリでなければ空。
    """
    if not directory.is_dir():
        return []
    counts: dict[Path, int] = {}
    if cancel_check is None:
        for image_path in FileSystemManager.get_image_files(directory):
            relative = image_path.parent.relative_to(directory)
            if relative == Path("."):
                continue
            counts[relative] = counts.get(relative, 0) + 1
    else:
        exts = {ext.lower() for ext in FileSystemManager.image_extensions}
        for path in directory.rglob("*"):
            cancel_check()
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            relative = path.parent.relative_to(directory)
            if relative == Path("."):
                continue
            counts[relative] = counts.get(relative, 0) + 1
    return [ImageSubfolder(path, counts[path]) for path in sorted(counts, key=lambda p: p.as_posix())]


def parse_common_tags(text: str) -> tuple[str, ...]:
    """カンマ区切りの入力をタグ列にする。

    前後の空白と空要素だけを除き、表記の書き換え (``TagCleaner.clean_format`` 等) はしない。
    同じ表記の重複は先頭だけ残す。

    Args:
        text: 入力欄の文字列。

    Returns:
        入力順のタグ列。
    """
    tags: list[str] = []
    for part in text.split(","):
        tag = part.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tuple(tags)
