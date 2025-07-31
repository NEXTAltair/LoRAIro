"""使い回せそうなスタティックメソッドを提供するモジュール"""

from pathlib import Path

import imagehash
from PIL import Image

from .log import logger


class ToolsStatic:
    """ユーティリティクラス
    スタティックメソッドを提供
    """

    @staticmethod
    def join_txt_and_caption_files(dir_path: Path) -> None:
        """指定したディレクトリ内の.captionファイルを.txtファイルに追加する
        # TODO: 使用箇所なし src.ImageEditor.py src.DatasetExportWidget.py で使えるように実装
        """
        file_dict: dict[str, list[str]] = {}
        for file in dir_path.iterdir():
            if file.is_file():
                basename = file.stem
                ext = file.suffix
                if basename not in file_dict:
                    file_dict[basename] = []
                file_dict[basename].append(ext)

        # .txtと.captionの両方が存在するファイルを処理
        for basename, extensions in file_dict.items():
            if ".txt" in extensions and ".caption" in extensions:
                txt_file = dir_path / f"{basename}.txt"
                caption_file = dir_path / f"{basename}.caption"

                # .captionファイルの内容を読み込む
                with open(caption_file, encoding="utf-8") as cf:
                    caption_content = cf.read()

                # .txtファイルに内容を追加
                with open(txt_file, "a", encoding="utf-8") as tf:
                    tf.write("\n")  # 区切りのために改行を追加
                    tf.write(caption_content)

                print(f"{caption_file} を {txt_file} に追加しました。")


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
