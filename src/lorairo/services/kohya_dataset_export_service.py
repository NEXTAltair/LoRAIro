"""Kohya-ss 形式のデータセット書き出し service (Issue #1419)。

保存済みの版 (フォルダ・画像・学習テキスト) を、取り込み時と同じ形
(`<dir_name>/<file_stem><画像拡張子>` + 学習テキスト + sd-scripts 用 TOML) で書き出す。
Qt には依存しない。設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from ..database.db_core import resolve_stored_path
from ..database.repository.dataset import (
    DatasetRepository,
    FolderSnapshot,
    LearningTextSnapshot,
)
from ..database.schema import Image
from ..utils.log import logger
from .learning_text import join_elements
from .sd_scripts_toml import SubsetSpec, TomlValue, render_dataset_config, render_training_config

_DATASET_CONFIG_NAME = "dataset_config.toml"
_TRAINING_CONFIG_NAME = "training_config.toml"
_DEFAULT_CAPTION_EXTENSION = ".txt"
# 秘密の値を持つキーの接尾辞 (保存時にマスク済みだが書き出し側でも防御する)
_SECRET_KEY_SUFFIXES = ("_api_key", "_token")


@dataclass(frozen=True)
class KohyaExportResult:
    """書き出し結果。"""

    output_dir: Path
    folder_count: int
    image_count: int
    text_count: int
    dataset_config_path: Path
    training_config_path: Path | None


@dataclass(frozen=True)
class _CopyPlan:
    """書き出し前に解決済みの画像コピー 1 件。"""

    source: Path
    destination: Path


class KohyaDatasetExportService:
    """保存済みの版を Kohya-ss 形式で書き出す service。"""

    def __init__(self, repository: DatasetRepository) -> None:
        """初期化。

        Args:
            repository: データセット Repository。
        """
        self._repository = repository

    def export_version(
        self,
        version_id: int,
        output_dir: Path,
        *,
        training_config_id: int | None = None,
    ) -> KohyaExportResult:
        """版を `output_dir` に書き出す。

        Args:
            version_id: 書き出す版の ID。
            output_dir: 出力先。存在しないか空のディレクトリであること。
            training_config_id: 指定時は `training_config.toml` も書き出す。

        Returns:
            書き出し結果。

        Raises:
            FileExistsError: 出力先が存在し空でない場合。
            FileNotFoundError: 保存済み画像のファイルが無い場合。
            LookupError: 版・画像・学習設定が存在しない場合。
            ValueError: 版にフォルダが無い場合。
        """
        # 何も書く前に出力先を判定する
        if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
            raise FileExistsError(f"出力先が空ではありません: {output_dir}")

        snapshot = self._repository.get_version_snapshot(version_id)
        training_config = (
            self._repository.get_training_config(training_config_id)
            if training_config_id is not None
            else None
        )
        # 画像の実在確認も書き込み前に済ませ、中途半端な出力を避ける
        copy_plans = self._plan_image_copies(snapshot.folders, output_dir)

        subsets = [
            SubsetSpec(
                image_dir=output_dir / folder.dir_name,
                num_repeats=folder.num_repeats,
                caption_extension=self._caption_extension(folder),
            )
            for folder in snapshot.folders
        ]
        dataset_toml = render_dataset_config(subsets)

        output_dir.mkdir(parents=True, exist_ok=True)
        for folder in snapshot.folders:
            (output_dir / folder.dir_name).mkdir(parents=True, exist_ok=True)

        text_count = 0
        for folder in snapshot.folders:
            for image in folder.images:
                for text in image.texts:
                    text_path = output_dir / folder.dir_name / f"{image.file_stem}{text.extension}"
                    self._write_text(text_path, text)
                    text_count += 1
        for plan in copy_plans:
            shutil.copyfile(plan.source, plan.destination)

        dataset_config_path = output_dir / _DATASET_CONFIG_NAME
        dataset_config_path.write_text(dataset_toml, encoding="utf-8")

        training_config_path: Path | None = None
        if training_config is not None:
            normalized = self._load_normalized(training_config.normalized_json)
            training_toml = render_training_config(
                normalized,
                {
                    "train_data_dir": output_dir,
                    "output_dir": output_dir / "output",
                    "logging_dir": output_dir / "logs",
                },
            )
            training_config_path = output_dir / _TRAINING_CONFIG_NAME
            training_config_path.write_text(training_toml, encoding="utf-8")

        logger.info(
            f"Kohya 形式で書き出し完了: version_id={version_id}, folders={len(snapshot.folders)}, "
            f"images={len(copy_plans)}, texts={text_count}, output_dir={output_dir}"
        )
        return KohyaExportResult(
            output_dir=output_dir,
            folder_count=len(snapshot.folders),
            image_count=len(copy_plans),
            text_count=text_count,
            dataset_config_path=dataset_config_path,
            training_config_path=training_config_path,
        )

    def _plan_image_copies(self, folders: list[FolderSnapshot], output_dir: Path) -> list[_CopyPlan]:
        """画像のコピー元・コピー先を解決し、元ファイルの実在を確認する。"""
        image_ids = [image.image_id for folder in folders for image in folder.images]
        stored_paths = self._load_stored_paths(image_ids)
        plans: list[_CopyPlan] = []
        for folder in folders:
            for image in folder.images:
                stored_path = stored_paths.get(image.image_id)
                if stored_path is None:
                    raise LookupError(f"画像が見つかりません: image_id={image.image_id}")
                source = resolve_stored_path(stored_path)
                if not source.is_file():
                    raise FileNotFoundError(f"保存済み画像がありません: image_id={image.image_id}")
                destination = output_dir / folder.dir_name / f"{image.file_stem}{source.suffix}"
                plans.append(_CopyPlan(source=source, destination=destination))
        return plans

    def _load_stored_paths(self, image_ids: list[int]) -> dict[int, str]:
        """画像 ID から保存済みオリジナル画像のパス (DB 上の値) を一括取得する。"""
        if not image_ids:
            return {}
        with self._repository.session_factory() as session:
            rows = session.execute(
                select(Image.id, Image.stored_image_path).where(Image.id.in_(set(image_ids)))
            ).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _caption_extension(folder: FolderSnapshot) -> str:
        """フォルダの学習テキスト拡張子 (最初に見つかったもの) を返す。無ければ `.txt`。"""
        for image in folder.images:
            for text in image.texts:
                return text.extension
        return _DEFAULT_CAPTION_EXTENSION

    @staticmethod
    def _write_text(path: Path, text: LearningTextSnapshot) -> None:
        """学習テキストを書く。未編集なら raw_text を無変換で (BOM なし、改行変換なし) 書く。"""
        content = join_elements(text.elements) if text.is_edited else text.raw_text
        with path.open("w", encoding="utf-8", newline="") as file:
            file.write(content)
        logger.debug(f"学習テキストを書き出し: {path}")

    @staticmethod
    def _load_normalized(normalized_json: str) -> dict[str, TomlValue]:
        """正規化済み設定を読み込み、秘密のキーを除いて返す。"""
        loaded = json.loads(normalized_json)
        return {
            key: value
            for key, value in loaded.items()
            if not str(key).lower().endswith(_SECRET_KEY_SUFFIXES)
        }
