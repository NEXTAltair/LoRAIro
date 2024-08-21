import os
from pathlib import Path
from typing import Any
from PIL import Image, ImageCms
from io import BytesIO
import math
import json
import shutil
import logging
from datetime import datetime

class FileSystemManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.initialized = False
        self.image_extensions = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp']
        self.image_dataset_dir = None
        self.resolution_dir = None
        self.original_images_dir = None
        self.resized_images_dir = None
        self.batch_request_dir = None

    def __enter__(self):
        if not self.initialized:
            raise RuntimeError("FileSystemManagerが初期化されていません。")
        return self

    def __exit__(self, exc_type, exc_val, _):
        if exc_type is not None:
            # 例外が発生した場合のログ記録
            self.logger.error("FileSystemManager使用中にエラーが発生: %s",exc_val)
        return False  # 例外を伝播させる

    def initialize(self, output_dir: Path, target_resolution: int):
        """
        FileSystemManagerを初期化｡

        Args:
            output_dir (Path): 出力ディレクトリのパス
            target_resolution (int): 学習元モデルのベース解像度
        """
        # 画像出力ディレクトリをセットアップ
        self.image_dataset_dir = output_dir / 'image_dataset'
        original_dir = self.image_dataset_dir / 'original_images'
        self.resolution_dir = self.image_dataset_dir  / str(target_resolution)

        # 日付ベースのサブディレクトリ
        current_date = datetime.now().strftime("%Y/%m/%d")
        self.original_images_dir = original_dir / current_date
        self.resized_images_dir = self.resolution_dir / current_date

        # batch Request jsonl ファイルの保存先
        self.batch_request_dir = output_dir / 'batch_request_jsonl'


        # 必要なすべてのディレクトリを作成
        directories_to_create = [
            output_dir,
            self.image_dataset_dir, original_dir, self.resolution_dir,
            self.original_images_dir, self.resized_images_dir,self.batch_request_dir
        ]
        for dir_path in directories_to_create:
            self._create_directory(dir_path)

        self.initialized = True
        self.logger.debug ("FileSystemManagerが正常に初期化されました。")

    def _create_directory(self, path: str | Path ):
        """
        指定されたパスにディレクトリがなければ作成｡

        Args:
            path (str | Path ): 作成するディレクトリのパス
        """
        path = Path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
            self.logger.debug ("ディレクトリを作成: %s", path)
        except Exception as e:
            self.logger.error("ディレクトリの作成に失敗: %s. FileSystemManager._create_directory: %s", path, str(e))
            raise

    def get_image_files(self, input_dir: Path) -> list[Path]:
        """
        ディレクトリから画像ファイルのリストを取得｡

        Returns:
            list[Path]: 画像ファイルのパスのリスト
        """
        image_files = []
        for ext in self.image_extensions:
            for image_file in input_dir.rglob(f'*{ext}'):
                image_files.append(image_file)
        return image_files


    def get_image_info(self, image_path: Path) -> dict[str, Any]:
        """
        画像ファイルから基本的な情報を取得する 不足している情報は登録時に設定

        編集前 uuid, stored_image_path

        編集後 image_id, stored_image_path

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            dict[str, Any]: 画像の基本情報（幅、高さ、フォーマット、モード、アルファチャンネル情報、ファイル名、ファイルの拡張子）
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format_value = img.format.lower() if img.format else 'unknown'
                mode = img.mode
                # アルファチャンネル画像情報 BOOL
                has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

            # 色域情報の詳細な取得
            color_space = mode
            icc_profile = img.info.get('icc_profile')
            if icc_profile:
                try:
                    profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                    color_space = ImageCms.getProfileName(profile).strip()
                except:
                    pass

            return {
                'width': width,
                'height': height,
                'format': format_value,
                'mode': mode,
                'has_alpha': has_alpha,
                'filename': image_path.name,
                'extension': image_path.suffix,
                'color_space': color_space,
                'icc_profile': 'Present' if icc_profile else 'Not present'
            }
        except Exception as e:
            message = f"画像情報の取得失敗: {image_path}. FileSystemManager.get_image_info: {str(e)}"
            self.logger.error(message)
            raise

    def _get_next_sequence_number(self, save_dir: str | Path ) -> int:
        """
        処理後画像のリネーム書利用連番

        指定されたディレクトリ内の次のシーケンス番号を取得します。

        Args:
            save_dir (str | Path ): シーケンス番号を取得するディレクトリのパス

        Returns:
            int: 次のシーケンス番号
        """
        try:
            files = list(Path(save_dir).glob(f'{Path(save_dir).name}_*.webp'))
            return len(files)
        except Exception as e:
            self.logger.error("シーケンス番号の取得に失敗: %s. FileSystemManager._get_next_sequence_number: %s", save_dir, str(e))
            raise

    def save_processed_image(self, image: Image.Image, original_path: Path) -> Path:
        """
        処理済みの画像を保存｡

        Args:
            image (Image.Image): 保存する画像オブジェクト
            original_filename (Path): 元のファイルpath

        Returns:
            Path: 保存された画像のパス
        """
        try:
            parent_name = original_path.parent.name
            parent_dir = self.resized_images_dir / parent_name # type: ignore
            self._create_directory(parent_dir)

            sequence = self._get_next_sequence_number(parent_dir)
            new_filename = f"{parent_name}_{sequence:05d}.webp"
            output_path = parent_dir /new_filename

            image.save(output_path)
            self.logger.info("処理済み画像を保存: %s", output_path)
            return output_path
        except Exception as e:
            self.logger.error("処理済み画像の保存に失敗: %s. FileSystemManager.save_original_image: %s", new_filename, str(e))
            raise

    @staticmethod
    def copy_file(src: Path, dst: Path, buffer_size: int = 64 * 1024 * 1024):  # デフォルト64MB
        """
        ファイルをコピーする独自の関数。
        異なるドライブ間でのコピーにも対応。

        Args:
            src (Path): コピー元のファイルパス
            dst (Path): コピー先のファイルパス
            buffer_size (int): バッファサイズ（バイト）。デフォルトは64MB。
        """
        with open(src, 'rb') as fsrc:
            with open(dst, 'wb') as fdst:
                while True:
                    buffer = fsrc.read(buffer_size)
                    if not buffer:
                        break
                    fdst.write(buffer)

        # ファイルの更新日時と作成日時を設定
        os.utime(dst, (os.path.getatime(src), os.path.getmtime(src)))
        shutil.copystat(src, dst)

    def save_original_image(self, image_file: Path) -> Path:
        """
        元の画像をデータベース用ディレクトリに保存します。

        Args:
            image_file (Path): 保存する元画像のパス

        Returns:
            Path: 保存された画像のパス
        """
        try:
            # 保存先のディレクトリパスを生成
            parent_name = image_file.parent.name
            save_dir = self.original_images_dir / parent_name # type: ignore
            self._create_directory(save_dir)
            # 新しいファイル名を生成（元のファイル名を保持）
            new_filename = image_file.name
            output_path = save_dir / new_filename
            # ファイル名の重複をチェックし、必要に応じて連番を付加
            counter = 1
            while output_path.exists():
                new_filename = f"{image_file.stem}_{counter}{image_file.suffix}"
                output_path = save_dir / new_filename
                counter += 1
            # 画像をコピー
            self.copy_file(image_file, output_path)

            self.logger.info("元画像を保存: %s", output_path)
            return output_path
        except Exception as e:
            self.logger.error("元画像の保存に失敗: %s. FileSystemManager.save_original_image: %s", image_file, str(e))
            raise

    def create_batch_request_file(self) -> Path:
        """新しいバッチリクエストJSONLファイルを作成します。

        Returns:
            Path: 作成されたJSONLファイルのパス
        """
        batch_request = self.batch_request_dir / 'batch_request.jsonl' # type: ignore
        return batch_request

    def save_batch_request(self, file_path: Path, data: dict[str, Any]):
        """バッチリクエストデータをJSONLファイルとして保存します。

        Args:
            file_path (Path): 追加先のJSONLファイルのパス
            data (dict[str, Any]): 追加するデータ
        """
        with open(file_path, 'a', encoding='utf-8') as f:
            json.dump(data, f)
            f.write('\n')

    def split_jsonl(self, jsonl_path: Path, jsonl_size: int, json_maxsize: int) -> None:
        """
        JSONLが96MB[OpenAIの制限]を超えないようにするために分割して保存する
        保存先はjsonl_pathのサブフォルダに保存される

        Args:
            jsonl_path (Path): 分割が必要なjsonlineファイルのpath
            jsonl_size (int): 分割が必要なjsonlineファイルのサイズ
            json_maxsize (int): OpenAI API が受け付ける最大サイズ
        """
        # jsonl_sizeに基づいてファイルを分割
        split_size = math.ceil(jsonl_size / json_maxsize)
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        lines_per_file = math.ceil(len(lines) / split_size)  # 各ファイルに必要な行数
        split_dir = jsonl_path / "split"
        split_dir.mkdir(parents=True, exist_ok=True)
        for i in range(split_size):
            split_filename = f'instructions_{i}.jsonl'
            split_path = split_dir / split_filename
            with open(split_path, 'w', encoding='utf-8') as f:
                f.writelines(lines[i * lines_per_file:(i + 1) * lines_per_file])

    @staticmethod
    def export_dataset_to_txt(image_paths: list[Path], all_tags: list[str], all_captions: list[str], save_dir: Path):
        """学習用データセットをテキスト形式で指定ディレクトリに出力する

        Args:
            image_paths (list[Path]): 画像ファイルのパスのリスト
            all_tags (list[str]): 各画像に対応するカンマ区切りのタグ文字列のリスト
            all_captions (list[str]): 各画像に対応するキャプション文字列のリスト
            save_dir (Path): 保存先のディレクトリパス
        """
        for i, image_path in enumerate(image_paths):
            file_name = image_path.stem

            with open(save_dir / f"{file_name}.txt", "w", encoding="utf-8") as f:
                f.write(all_tags[i])

            with open(save_dir / f"{file_name}.caption", "w", encoding="utf-8") as f:
                f.write(all_captions[i])

            FileSystemManager.copy_file(image_path, save_dir / image_path.name)

    @staticmethod
    def export_dataset_to_json(image_paths: list[Path], all_tags: list[str], all_captions: list[str], save_dir: Path):
        """学習用データセットをJSON形式で指定ディレクトリに出力する

        Args:
            image_paths (list[Path]): 画像ファイルのパスのリスト
            all_tags (list[str]): 各画像に対応するカンマ区切りのタグ文字列のリスト
            all_captions (list[str]): 各画像に対応するキャプション文字列のリスト
            save_dir (Path): 保存先のディレクトリパス
        """
        data = {}
        for image_path, tags, caption in zip(image_paths, all_tags, all_captions):
            save_image = save_dir / image_path.name
            FileSystemManager.copy_file(image_path, save_image)
            data[str(image_path)] = {"tags": tags, "caption": caption}


        with open(save_dir / "meta_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)