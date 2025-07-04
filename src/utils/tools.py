"""使い回せそうなスタティックメソッドを提供するモジュール"""

from pathlib import Path


class ToolsStatic:
    """ユーティリティクラス
    スタティックメソッドを提供
    """

    @staticmethod
    def join_txt_and_caption_files(dir_path: Path):
        """指定したディレクトリ内の.captionファイルを.txtファイルに追加する
        # TODO: 使用箇所なし src.ImageEditor.py src.DatasetExportWidget.py で使えるように実装
        """
        file_dict = {}
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
