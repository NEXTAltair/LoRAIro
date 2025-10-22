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
    """指定された画像パスのpHashを計算します。"""
    try:
        with Image.open(image_path) as img:
            # アルファチャネルがある場合、またはグレースケールの場合、画像をRGBに変換します
            if img.mode in ("RGBA", "LA", "P"):  # Pモードには透明性がある場合があります
                img = img.convert("RGB")
            hash_val = imagehash.phash(img)
            return str(hash_val)
    except FileNotFoundError:
        logger.error(f"pHash計算エラー: ファイルが見つかりません - {image_path}")
        raise
    except Exception as e:
        logger.error(f"pHash計算中に予期せぬエラーが発生しました: {image_path}, Error: {e}", exc_info=True)
        raise  # 計算失敗時は例外を再発生させる
