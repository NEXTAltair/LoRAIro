"""Kohya-ss 形式の学習データセットディレクトリのスキャナ。

`<繰り返し数>_<名前>/` フォルダ直下の画像と、同名の `.txt` / `.caption` (学習テキスト) を読み取る。
学習テキストは正規化せず原文のまま保持する。
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from lorairo.filesystem import FileSystemManager
from lorairo.services.learning_text import split_elements
from lorairo.utils.log import logger

DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "sample*",
    "終了",
    "*__Processed",
    "reg",
    "log",
    "logs",
    "wandb",
)

# 先頭要素の最頻値がこの割合以上ならトリガーワード候補とする
TRIGGER_CANDIDATE_MIN_RATE = 0.5

TEXT_EXTENSIONS: tuple[str, ...] = (".txt", ".caption")

# 文字コードの試行順 (utils.tools の decode_text_with_fallback と同じ)
_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8", "shift_jis", "euc-jp", "latin-1")

_FOLDER_NAME_PATTERN = re.compile(r"^(\d+)_(.+)$")

# 親フォルダから版の候補 (`<数字>_<名前>` フォルダを持つディレクトリ) を探す深さの上限 (Issue #1648)
DEFAULT_DISCOVERY_MAX_DEPTH = 4


@dataclass(frozen=True)
class ScannedText:
    """スキャンした学習テキスト。"""

    extension: str
    raw_text: str
    elements: list[str]


@dataclass(frozen=True)
class ScannedImage:
    """スキャンした画像と、それに付随する学習テキスト。"""

    path: Path
    file_stem: str
    texts: list[ScannedText]


@dataclass(frozen=True)
class ScannedFolder:
    """スキャンした Kohya 形式フォルダ。"""

    dir_path: Path
    dir_name: str
    name: str
    num_repeats: int
    images: list[ScannedImage]
    trigger_candidate: str | None
    trigger_match_rate: float


def parse_folder_name(dir_name: str) -> tuple[int, str] | None:
    """`10_kariginu` 形式のフォルダ名を繰り返し数と名前に分解する。

    Args:
        dir_name: フォルダ名。

    Returns:
        (繰り返し数, 名前)。接頭辞が数字+`_` でなければ None。
    """
    match = _FOLDER_NAME_PATTERN.match(dir_name)
    if match is None:
        return None
    return int(match.group(1)), match.group(2)


def _is_excluded(dir_name: str, exclude_patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(dir_name, pattern) for pattern in exclude_patterns)


def _has_kohya_folder(directory: Path, exclude_patterns: tuple[str, ...]) -> bool:
    """`directory` 直下に、除外されない `<数字>_<名前>` フォルダがあるか。"""
    return any(
        child.is_dir() and not _is_excluded(child.name, exclude_patterns) and parse_folder_name(child.name)
        for child in directory.iterdir()
    )


def discover_kohya_roots(
    parent: Path,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
    max_depth: int = DEFAULT_DISCOVERY_MAX_DEPTH,
) -> list[Path]:
    """親フォルダの配下から、`<数字>_<名前>` フォルダを持つディレクトリ (取り込みのルート候補) を探す。

    - `parent` 自身を深さ 0 とし、`max_depth` までのディレクトリを調べる。
    - 候補が見つかったディレクトリの下には潜らない (直下は学習フォルダのため)。
    - 除外パターンに一致するディレクトリの下には潜らない。
    - ディレクトリへのシンボリックリンクはたどらない (循環を避ける)。
    - アーカイブ (`.7z` など) はファイルなので対象にならない (展開しない)。

    Args:
        parent: 探索の起点。
        exclude_patterns: 除外するフォルダ名の fnmatch パターン。
        max_depth: 探索する深さの上限。

    Returns:
        候補のディレクトリ (パスの並び順)。
    """
    roots: list[Path] = []
    pending: list[tuple[Path, int]] = [(parent, 0)]
    while pending:
        directory, depth = pending.pop()
        if _has_kohya_folder(directory, exclude_patterns):
            roots.append(directory)
            continue
        if depth >= max_depth:
            continue
        for child in sorted(directory.iterdir(), key=lambda p: p.name, reverse=True):
            if not child.is_dir() or child.is_symlink():
                continue
            if _is_excluded(child.name, exclude_patterns):
                logger.debug(f"除外フォルダのため探索しません: {child}")
                continue
            pending.append((child, depth + 1))
    roots.sort(key=lambda p: p.relative_to(parent).parts)
    logger.debug(f"Kohya ルート候補の探索: {len(roots)}件 ({parent})")
    return roots


def _read_raw_text(path: Path) -> str:
    """改行を変換せずにテキストを読む。

    decode_text_with_fallback は CRLF を LF に変換するため、原文保持のためここでは
    bytes.decode を同じ文字コード順で使う。
    """
    data = path.read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in _TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error
    assert last_error is not None
    raise last_error


def _detect_trigger(images: list[ScannedImage]) -> tuple[str | None, float]:
    """最頻の先頭要素と、それを先頭に持つ画像の割合を返す。閾値未満なら候補は None。"""
    firsts: list[str] = []
    for image in images:
        for text in image.texts:
            if text.elements:
                firsts.append(text.elements[0])
                break
    if not images or not firsts:
        return None, 0.0
    element, count = Counter(firsts).most_common(1)[0]
    rate = count / len(images)
    return (element if rate >= TRIGGER_CANDIDATE_MIN_RATE else None), rate


def _scan_folder(
    dir_path: Path,
    num_repeats: int,
    name: str,
    cancel_check: Callable[[], bool] | None = None,
) -> ScannedFolder | None:
    """1 フォルダ直下の画像と学習テキストを読む。キャンセル時は None を返す。"""
    image_extensions = {ext.lower() for ext in FileSystemManager.image_extensions}
    images: list[ScannedImage] = []
    for image_path in sorted(dir_path.iterdir(), key=lambda p: p.name):
        if cancel_check is not None and cancel_check():
            return None
        if not image_path.is_file() or image_path.suffix.lower() not in image_extensions:
            continue
        texts: list[ScannedText] = []
        for extension in TEXT_EXTENSIONS:
            if cancel_check is not None and cancel_check():
                return None
            text_path = image_path.with_suffix(extension)
            if not text_path.is_file():
                continue
            raw_text = _read_raw_text(text_path)
            texts.append(ScannedText(extension, raw_text, split_elements(raw_text)))
        images.append(ScannedImage(image_path, image_path.stem, texts))
        logger.debug(f"画像をスキャン: {image_path}")

    trigger_candidate, match_rate = _detect_trigger(images)
    return ScannedFolder(
        dir_path=dir_path,
        dir_name=dir_path.name,
        name=name,
        num_repeats=num_repeats,
        images=images,
        trigger_candidate=trigger_candidate,
        trigger_match_rate=match_rate,
    )


def scan_kohya_directory(
    root: Path,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> list[ScannedFolder]:
    """Kohya 形式のルートディレクトリをスキャンする。

    Args:
        root: `<数字>_<名前>` フォルダを含むディレクトリ。
        exclude_patterns: 除外するフォルダ名の fnmatch パターン。
        cancel_check: 協調キャンセル判定コールバック。True を返したら即座に走査を打ち切る。

    Returns:
        スキャンしたフォルダのリスト (フォルダ名順)。
    """
    folders: list[ScannedFolder] = []
    for dir_path in sorted(root.iterdir(), key=lambda p: p.name):
        if cancel_check is not None and cancel_check():
            break
        if not dir_path.is_dir():
            continue
        if _is_excluded(dir_path.name, exclude_patterns):
            logger.debug(f"除外フォルダ: {dir_path.name}")
            continue
        parsed = parse_folder_name(dir_path.name)
        if parsed is None:
            logger.debug(f"繰り返し数接頭辞なし、スキップ: {dir_path.name}")
            continue
        scanned = _scan_folder(dir_path, parsed[0], parsed[1], cancel_check=cancel_check)
        if scanned is None:
            break
        folders.append(scanned)
    logger.info(f"Kohya スキャン完了: {len(folders)}フォルダ ({root})")
    return folders
