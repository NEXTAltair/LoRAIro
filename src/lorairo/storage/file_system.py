import json
import math
import os
import shutil
from datetime import datetime
from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Any, ClassVar, Literal

import toml
from PIL import Image, ImageCms

from ..utils.log import logger

Image.MAX_IMAGE_PIXELS = 1000000000  # 大きな画像に対応(ローカルアプリ前提)


class FileSystemManager:
    image_extensions: ClassVar[list[str]] = [
        ".jpg",
        ".png",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".jpeg",
        ".webp",
    ]

    def __init__(self) -> None:
        self.initialized = False
        self.image_dataset_dir: Path | None = None
        self.resolution_dir: Path | None = None
        self.original_images_dir: Path | None = None
        self.resized_images_dir: Path | None = None
        self.batch_request_dir: Path | None = None
        self._sequence_counters: dict[Path, int] = {}
        logger.debug("初期化")

    def __enter__(self) -> "FileSystemManager":
        if not self.initialized:
            raise RuntimeError("FileSystemManagerが初期化されていません。")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, traceback: Any) -> Literal[False]:
        if exc_type is not None:
            # 例外が発生した場合のログ記録
            logger.error("FileSystemManager使用中にエラーが発生: {}", exc_val)
        return False  # 例外を伝播させる

    def initialize(self, output_dir: Path) -> None:
        """
        FileSystemManagerを初期化｡ 基本的なディレクトリ構造のみ作成

        Args:
            output_dir (Path): 出力ディレクトリのパス
        """
        # 画像出力ディレクトリをセットアップ
        self.image_dataset_dir = output_dir / "image_dataset"
        original_dir = self.image_dataset_dir / "original_images"

        # 日付ベースのサブディレクトリ
        current_date = datetime.now().strftime("%Y/%m/%d")
        self.original_images_dir = original_dir / current_date

        # batch Request jsonl ファイルの保存先
        self.batch_request_dir = output_dir / "batch_request_jsonl"

        # 基本的なディレクトリのみ作成（解像度ディレクトリは遅延作成）
        directories_to_create = [
            output_dir,
            self.image_dataset_dir,
            original_dir,
            self.original_images_dir,
            self.batch_request_dir,
        ]
        for dir_path in directories_to_create:
            self._create_directory(dir_path)

        self.initialized = True
        logger.debug("FileSystemManagerが正常に初期化されました。")

    def initialize_from_dataset_selection(self, selected_dir: Path) -> Path:
        """データセット選択からoutput_dirを決定・初期化

        現在のプロジェクトディレクトリをoutput_dirとして使用し初期化する。
        画像はプロジェクトディレクトリ内の image_dataset/ に保存される。

        Args:
            selected_dir: ユーザーが選択したデータセットディレクトリ

        Returns:
            Path: 初期化されたoutput_dirのパス（プロジェクトルート）

        Raises:
            RuntimeError: 初期化失敗時
        """
        from ..database.db_core import get_current_project_root

        output_dir = get_current_project_root()
        self.initialize(output_dir)
        logger.info(f"データセット選択から初期化完了: {output_dir}")
        return output_dir

    def get_resolution_dir(self, target_resolution: int) -> Path:
        """
        解像度ディレクトリを取得し、存在しなければ作成する

        Args:
            target_resolution (int): 学習元モデルのベース解像度

        Returns:
            Path: 解像度ディレクトリのパス
        """
        if not self.initialized:
            raise RuntimeError("FileSystemManagerが初期化されていません。")

        resolution_dir = self.image_dataset_dir / str(target_resolution)
        current_date = datetime.now().strftime("%Y/%m/%d")
        resized_images_dir = resolution_dir / current_date

        # 解像度ディレクトリを必要時に作成
        self._create_directory(resolution_dir)
        self._create_directory(resized_images_dir)

        return resized_images_dir

    def _create_directory(self, path: str | Path) -> None:
        """
        指定されたパスにディレクトリがなければ作成｡

        Args:
            path (str | Path ): 作成するディレクトリのパス
        """
        path = Path(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
            logger.debug("ディレクトリを作成: {}", path)
        except Exception as e:
            logger.error(
                "ディレクトリの作成に失敗: {}. FileSystemManager._create_directory: {}", path, str(e)
            )
            raise

    @staticmethod
    def get_image_files(input_dir: Path) -> list[Path]:
        """
        ディレクトリから画像ファイルのリストを取得｡

        Returns:
            list[Path]: 画像ファイルのパスのリスト
        """
        exts = {ext.lower() for ext in FileSystemManager.image_extensions}
        image_files: list[Path] = []
        for path in input_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in exts:
                image_files.append(path)
        logger.debug("get_image_files found={} dir={}", len(image_files), input_dir)
        return image_files

    @staticmethod
    def get_image_info(image_path: Path) -> dict[str, Any]:
        """
        画像ファイルから基本的な情報を取得する 不足している情報は登録時に設定

        編集前 uuid, stored_image_path

        編集後 image_id, stored_image_path

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            dict[str, Any]: 画像の基本情報(幅、高さ、フォーマット、モード、アルファチャンネル情報、ファイル名、ファイルの拡張子)
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format_value = img.format.lower() if img.format else "unknown"
                mode = img.mode
                # アルファチャンネル画像情報 BOOL
                has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
                icc_profile = img.info.get("icc_profile")

            # 色域情報の詳細な取得
            color_space = mode
            if icc_profile:
                profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                color_space = str(ImageCms.getProfileName(profile)).strip()

            return {
                "width": width,
                "height": height,
                "format": format_value,
                "mode": mode,
                "has_alpha": has_alpha,
                "filename": image_path.name,
                "extension": image_path.suffix,
                "color_space": color_space,
                "icc_profile": "Present" if icc_profile else "Not present",
            }
        except Exception as e:
            message = f"画像情報の取得失敗: {image_path}. FileSystemManager.get_image_info: {e!s}"
            logger.error(message)
            raise

    def _get_next_sequence_number(self, save_dir: str | Path) -> int:
        """
        処理後画像のリネーム書利用連番

        指定されたディレクトリ内の次のシーケンス番号を取得します。

        Args:
            save_dir (str | Path ): シーケンス番号を取得するディレクトリのパス

        Returns:
            int: 次のシーケンス番号
        """
        save_dir_path = Path(save_dir)
        try:
            next_seq = self._sequence_counters.get(save_dir_path)
            if next_seq is None:
                next_seq = self._scan_next_sequence_number(save_dir_path)

            # 外部要因(並列処理/手動操作)で衝突しても回避できるように存在チェック
            candidate = next_seq
            while (save_dir_path / f"{save_dir_path.name}_{candidate:05d}.webp").exists():
                candidate += 1

            self._sequence_counters[save_dir_path] = candidate + 1
            return candidate
        except Exception as e:
            logger.error(
                "シーケンス番号の取得に失敗: {}. FileSystemManager._get_next_sequence_number: {}",
                save_dir_path,
                str(e),
            )
            raise

    @staticmethod
    def _scan_next_sequence_number(save_dir: Path) -> int:
        """
        既存ファイル名から次の連番を推定する。

        Args:
            save_dir: 連番付きファイルが保存されるディレクトリ

        Returns:
            int: 次に使用可能な連番(0始まり)
        """
        prefix = f"{save_dir.name}_"
        max_seq = -1
        for file_path in save_dir.glob(f"{save_dir.name}_*.webp"):
            stem = file_path.stem
            if not stem.startswith(prefix):
                continue
            suffix = stem[len(prefix) :]
            if not suffix.isdigit():
                continue
            max_seq = max(max_seq, int(suffix))
        return max_seq + 1

    def save_processed_image(self, image: Image.Image, original_path: Path, target_resolution: int) -> Path:
        """
        処理済みの画像を保存｡

        Args:
            image (Image.Image): 保存する画像オブジェクト
            original_path (Path): 元のファイルpath
            target_resolution (int): 学習元モデルのベース解像度

        Returns:
            Path: 保存された画像のパス
        """
        try:
            # 解像度ディレクトリを動的に取得
            resized_images_dir = self.get_resolution_dir(target_resolution)

            parent_name = original_path.parent.name
            parent_dir = resized_images_dir / parent_name
            self._create_directory(parent_dir)

            sequence = self._get_next_sequence_number(parent_dir)
            new_filename = f"{parent_name}_{sequence:05d}.webp"
            output_path = parent_dir / new_filename

            image.save(output_path)
            logger.debug("処理済み画像を保存: {}", output_path)
            return output_path
        except Exception as e:
            logger.error(
                "処理済み画像の保存に失敗: {}. FileSystemManager.save_original_image: {}",
                new_filename,
                str(e),
            )
            raise

    @staticmethod
    def copy_file(src: Path, dst: Path, buffer_size: int = 64 * 1024 * 1024) -> None:  # デフォルト64MB
        """
        ファイルをコピーする独自の関数。
        異なるドライブ間でのコピーにも対応。

        Args:
            src (Path): コピー元のファイルパス
            dst (Path): コピー先のファイルパス
            buffer_size (int): バッファサイズ(バイト)。デフォルトは64MB。
        """
        with open(src, "rb") as fsrc:
            with open(dst, "wb") as fdst:
                while True:
                    buffer = fsrc.read(buffer_size)
                    if not buffer:
                        break
                    fdst.write(buffer)

        # ファイルの更新日時と作成日時を設定
        src_stat = src.stat()
        os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))
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
            if self.original_images_dir is None:
                raise RuntimeError("original_images_dir is not set. Call initialize() first.")
            save_dir = self.original_images_dir / parent_name
            self._create_directory(save_dir)
            # 新しいファイル名を生成(元のファイル名を保持)
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

            logger.debug(f"元画像を保存: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"元画像の保存に失敗: {image_file}. FileSystemManager.save_original_image: {e!s}")
            raise

    def create_batch_request_file(self) -> Path:
        """新しいバッチリクエストJSONLファイルを作成します。

        Returns:
            Path: 作成されたJSONLファイルのパス
        """
        if self.batch_request_dir is None:
            raise RuntimeError("batch_request_dir is not set. Call initialize() first.")
        batch_request = self.batch_request_dir / "batch_request.jsonl"
        return batch_request

    def save_batch_request(self, file_path: Path, data: dict[str, Any]) -> None:
        """バッチリクエストデータをJSONLファイルとして保存します。

        Args:
            file_path (Path): 追加先のJSONLファイルのパス
            data (dict[str, Any]): 追加するデータ
        """
        with open(file_path, "a", encoding="utf-8") as f:
            json.dump(data, f)
            f.write("\n")

    def split_jsonl(self, jsonl_path: Path, jsonl_size: int, json_maxsize: int) -> None:
        """
        JSONLが96MB[OpenAIの制限]を超えないようにするために分割して保存する
        保存先はjsonl_pathのサブフォルダに保存される

        Args:
            jsonl_path (Path): 分割が必要なjsonlineファイルのpath
            jsonl_size (int): 分割が必要なjsonlineファイルのサイズ
            json_maxsize (int): OpenAI API が受け付ける最大サイズ
        """
        if json_maxsize <= 0:
            raise ValueError("json_maxsize must be > 0")
        if jsonl_size <= 0:
            raise ValueError("jsonl_size must be > 0")

        split_size = math.ceil(jsonl_size / json_maxsize)
        if split_size <= 1:
            return

        # 保存先は元ファイルの親ディレクトリ配下に作成する
        split_dir = jsonl_path.parent / f"{jsonl_path.stem}_split"
        split_dir.mkdir(parents=True, exist_ok=True)

        # 行数を先に数えて均等配分(巨大ファイルでもメモリを使い切らない)
        with open(jsonl_path, encoding="utf-8") as f:
            total_lines = sum(1 for _ in f)
        lines_per_file = math.ceil(total_lines / split_size)

        with open(jsonl_path, encoding="utf-8") as fsrc:
            for i in range(split_size):
                split_filename = f"instructions_{i}.jsonl"
                split_path = split_dir / split_filename
                with open(split_path, "w", encoding="utf-8") as fdst:
                    chunk = list(islice(fsrc, lines_per_file))
                    if not chunk:
                        break
                    fdst.writelines(chunk)

    @staticmethod
    def export_dataset_to_txt(
        image_data: dict[str, Any], save_dir: Path, merge_caption: bool = False
    ) -> None:
        """学習用データセットをテキスト形式で指定ディレクトリに出力する

        Args:
            image_data (dict]): 画像データ. 各辞書は 'path', 'tags', 'caption' をキーに持つ
            save_dir (Path): 保存先のディレクトリパス
            merge_caption (bool): キャプションをタグに追加する
        """
        image_path = image_data["path"]
        file_name = image_path.stem

        with open(save_dir / f"{file_name}.txt", "w", encoding="utf-8") as f:
            tags = ", ".join([tag_data["tag"] for tag_data in image_data["tags"]])
            if merge_caption:
                captions = ", ".join([caption_data["caption"] for caption_data in image_data["captions"]])
                tags = f"{tags}, {captions}"
            f.write(tags)
        with open(save_dir / f"{file_name}.caption", "w", encoding="utf-8") as f:
            captions = ", ".join([caption_data["caption"] for caption_data in image_data["captions"]])
            f.write(captions)
        FileSystemManager.copy_file(image_path, save_dir / image_path.name)

    @staticmethod
    def export_dataset_to_json(image_data: dict[str, Any], save_dir: Path) -> None:
        """学習用データセットをJSON形式で指定ディレクトリに出力する

        Note: この関数は単一画像用です。複数画像の場合は呼び出し側でJSONを統合してください。

        Args:
            image_data (dict[str, Any]): 画像データ. 各辞書は 'path', 'tags', 'caption' をキーに持つ
            save_dir (Path): 保存先のディレクトリパス
        """
        image_path = image_data["path"]
        save_image = save_dir / image_path.name
        FileSystemManager.copy_file(image_path, save_image)

        tags = ", ".join([tag_data["tag"] for tag_data in image_data["tags"]])
        captions = ", ".join([caption_data["caption"] for caption_data in image_data["captions"]])

        json_data = {str(save_image): {"tags": tags, "caption": captions}}

        # 既存のJSONファイルを読み込み、データを追加
        metadata_path = save_dir / "meta_data.json"
        existing_data = {}

        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # ファイルが存在しないか無効なJSONの場合は空の辞書を使用
                existing_data = {}

        # 新しいデータを追加
        existing_data.update(json_data)

        # 完全なJSONとして書き込み
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def save_toml_config(config: dict, filename: str) -> None:
        try:
            with open(filename, "w") as f:
                toml.dump(config, f)
        except Exception as e:
            logger.error(f"保存エラー: {e!s}")
            raise OSError(f"設定の保存中にエラーが発生しました: {e!s}") from e
