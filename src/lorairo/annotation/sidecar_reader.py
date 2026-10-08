"""既存の画像ファイルに対応する .txt/.caption ファイルからアノテーションを読み込むモジュール。"""

import os
import stat
from pathlib import Path
from typing import Any

from genai_tag_db_tools.utils.cleanup_str import TagCleaner

from lorairo.utils.log import logger
from lorairo.utils.tools import decode_text_with_fallback

SIDECAR_MAX_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


class SidecarReadError(ValueError):
    """付属テキストを読み込めない、本文を含まないスキップ理由。"""


def _validate_sidecar(info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise SidecarReadError("symbolic link")
    # Windows の reparse point (リンク等) も通常ファイルとして取り込まない。
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise SidecarReadError("reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise SidecarReadError("not a regular file")
    if info.st_size > SIDECAR_MAX_BYTES:
        raise SidecarReadError("exceeds 1 MiB limit")


def _read_sidecar_text(file_path: Path) -> str | None:
    """通常ファイルの同一性を確認し、最大 1 MiB + 超過検出用 1 byte だけ読む。

    POSIX では NOFOLLOW / NONBLOCK で lstat 後のリンク・FIFO への置換にも対応。
    それらのフラグがない Windows でも reparse point と open 後の同一性を検査し、
    本文を読む前に置換を検出する。親ディレクトリの隔離は扱わない。
    """
    try:
        before = file_path.lstat()
    except FileNotFoundError:
        return None
    _validate_sidecar(before)
    flags = os.O_RDONLY
    for flag in ("O_NOFOLLOW", "O_NONBLOCK", "O_BINARY"):
        flags |= getattr(os, flag, 0)
    descriptor = os.open(file_path, flags)
    try:
        opened = os.fstat(descriptor)
        _validate_sidecar(opened)
        current = file_path.lstat()
        _validate_sidecar(current)
        identity = (before.st_dev, before.st_ino)
        if identity != (opened.st_dev, opened.st_ino) or identity != (current.st_dev, current.st_ino):
            raise SidecarReadError("file changed before reading")

        data = bytearray()
        while len(data) <= SIDECAR_MAX_BYTES:
            chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, SIDECAR_MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > SIDECAR_MAX_BYTES:
            raise SidecarReadError("exceeds 1 MiB limit during reading")
        _validate_sidecar(os.fstat(descriptor))
    finally:
        os.close(descriptor)
    return decode_text_with_fallback(bytes(data))


class SidecarAnnotationReader:
    """画像に関連する既存のテキストファイル (.txt, .caption) からアノテーションを読み込む。"""

    def __init__(self) -> None:
        """SidecarAnnotationReader を初期化します。"""
        # TagCleaner.clean_format() is a static method, no instance needed

    def get_existing_annotations(self, image_path: Path) -> dict[str, Any] | None:
        """
        画像の参照元ディレクトリから既存のタグとキャプションを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Optional[dict[str, Any]]: 'tags', 'captions', 'image_path' をキーとする辞書。
            None : 既存のアノテーションが見つからない場合

        例:
        {
            'tags': ['tag1', 'tag2'],
            'captions': ['caption1'],
            'image_path': str(image_path)
        }
        """
        existing_annotations = {
            "tags": [],
            "captions": [],
            "image_path": str(image_path),
        }

        tag_path = image_path.with_suffix(".txt")
        caption_path = image_path.with_suffix(".caption")

        found = False
        for key, file_path, read in (
            ("tags", tag_path, self._read_annotations),
            ("captions", caption_path, self._read_captions),
        ):
            try:
                items = read(file_path)
                if items is not None:
                    found = True
                    existing_annotations[key] = items
            except Exception as error:
                # ファイルごとに縮退し、正常な兄弟ファイルや画像登録を続行する。
                # 例外本文には入力テキストが含まれ得るため、固定理由・型だけを記録。
                found = True
                if isinstance(error, SidecarReadError):
                    reason = str(error)
                elif isinstance(error, OSError):
                    reason = f"read error ({type(error).__name__}, errno={error.errno})"
                else:
                    reason = f"parse error ({type(error).__name__})"
                logger.warning("付属テキストをスキップ: {} - {}", ascii(file_path.name[:256]), reason)

        if not found:
            logger.debug("既存アノテーション無し: {}", ascii(image_path.name[:256]))
            return None

        return existing_annotations

    def _read_annotations(self, file_path: Path) -> list[str] | None:
        """
        指定されたファイルからアノテーションを読み込みカンマで分割してリストとして返す。

        Args:
            file_path (Path): 読み込むファイルのパス

        Returns:
            list[str]: アノテーションのリスト
        """
        text = _read_sidecar_text(file_path)
        if text is None:
            return None
        clean_data = TagCleaner.clean_format(text)
        items = clean_data.strip().split(",")
        # 空文字列を除去
        return [item.strip() for item in items if item.strip()]

    def _read_captions(self, file_path: Path) -> list[str] | None:
        """
        指定されたファイルからキャプションを読み込む。

        Args:
            file_path (Path): 読み込むファイルのパス

        Returns:
            list[str]: キャプションのリスト
        """
        text = _read_sidecar_text(file_path)
        if text is None:
            return None
        clean_data = TagCleaner.clean_format(text)
        if clean_data.strip():
            return [clean_data.strip()]
        return []

    def get_tag_file_path(self, image_path: Path) -> Path:
        """
        画像に対応する .txt ファイルのパスを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Path: .txt ファイルのパス
        """
        return image_path.with_suffix(".txt")

    def get_caption_file_path(self, image_path: Path) -> Path:
        """
        画像に対応する .caption ファイルのパスを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Path: .caption ファイルのパス
        """
        return image_path.with_suffix(".caption")
