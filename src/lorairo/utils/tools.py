"""使い回せそうなスタティックメソッドを提供するモジュール"""

from pathlib import Path

import imagehash
from PIL import Image

from .log import logger


class ToolsStatic:
    """ユーティリティクラス
    スタティックメソッドを提供
    """


def calculate_phash(image_path: Path) -> str:
    """指定された画像パスのpHashを計算します。

    Args:
        image_path: 画像ファイルのパス。

    Returns:
        pHashの文字列表現。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。
        ValueError: ファイルが破損または空で画像として読み込めない場合。
    """
    if image_path.stat().st_size == 0:
        raise ValueError(f"画像ファイルが破損しています（0バイト）: {image_path}")
    try:
        with Image.open(image_path) as img:
            # アルファチャネルがある場合、またはグレースケールの場合、画像をRGBに変換します
            if img.mode in ("RGBA", "LA", "P"):  # Pモードには透明性がある場合があります
                img = img.convert("RGB")
            hash_val = imagehash.phash(img)
            return str(hash_val)
    except FileNotFoundError:
        raise
    except Exception as e:
        raise ValueError(
            f"画像ファイルが破損しているか非対応の形式です: {image_path}"
        ) from e  # 計算失敗時は例外を再発生させる  # 計算失敗時は例外を再発生させる


_FALLBACK_ENCODINGS = ("utf-8", "shift_jis", "euc-jp", "latin-1")


def read_text_with_fallback(file_path: Path, encodings: tuple[str, ...] = _FALLBACK_ENCODINGS) -> str:
    """テキストファイルを複数エンコーディングでフォールバック読み込みする。

    UTF-8 を優先し、失敗した場合は順に別のエンコーディングを試行する。
    latin-1 は全バイト値を受け付けるため、最終フォールバックとして機能する。

    Args:
        file_path: 読み込むファイルのパス。
        encodings: 試行するエンコーディングのタプル（先頭が最優先）。

    Returns:
        ファイルの内容文字列。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。
        UnicodeDecodeError: すべてのエンコーディングで読み込みに失敗した場合。
    """
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = file_path.read_text(encoding=encoding)
            if encoding != "utf-8":
                logger.debug(f"UTF-8以外のエンコーディングで読み込み: {file_path} ({encoding})")
            return text
        except UnicodeDecodeError as e:
            last_error = e
            continue
    raise last_error  # type: ignore[misc]  # latin-1が最終フォールバックのため到達しないが安全策
