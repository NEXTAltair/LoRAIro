"""Kohya-ss 形式の学習データセットを、版・フォルダ・学習テキストとして取り込む service (Issue #1418)。

設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`。

- 画像は `ImageDatabaseManager.register_original_image` で登録するだけで、画像直下の `Tag` /
  `Caption` には書かない。学習テキストは `DatasetRepository` 側にフォルダごとに保存する。
- トリガーワードは計画 (`FolderImportPlan.trigger_word`) の値だけを保存する。スキャンの候補は
  確認なしに確定しない。
- 書き込みの前に計画を検証し、設定 json も正規化しておく。版の作成で衝突した場合は何も書かない。
- 設定 json の秘密の値は `normalize_kohya_gui_config` が取り除いたものだけを保存する。
"""

import json
from dataclasses import dataclass
from pathlib import Path

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.filesystem import FileSystemManager
from lorairo.services.kohya_config_normalizer import (
    NormalizedConfig,
    NormalizedValue,
    normalize_kohya_gui_config,
)
from lorairo.services.kohya_scanner import ScannedFolder, scan_kohya_directory
from lorairo.utils.log import logger

CONFIG_SOURCE_KIND = "kohya_gui_json"


@dataclass(frozen=True)
class FolderImportPlan:
    """取り込むフォルダ 1 つ分の確定値。"""

    dir_name: str
    name: str
    num_repeats: int
    trigger_word: str | None
    include: bool


@dataclass(frozen=True)
class DatasetImportPlan:
    """取り込みの計画 (ユーザーが確認・確定したもの)。"""

    dataset_name: str
    version_name: str
    parent_version_id: int | None
    folders: list[FolderImportPlan]
    config_files: list[Path]


@dataclass(frozen=True)
class DatasetImportResult:
    """取り込み結果。

    Attributes:
        dataset_id: `datasets.id`。
        version_id: 作成した版の ID。
        folder_count: 取り込んだフォルダ数。
        image_count: フォルダへの所属を記録した画像数 (同じ画像が 2 フォルダにあれば 2 と数える)。
        skipped_images: 画像の登録に失敗し、所属を記録しなかった画像数。
        training_config_ids: 追加した学習設定の ID。
    """

    dataset_id: int
    version_id: int
    folder_count: int
    image_count: int
    skipped_images: int
    training_config_ids: list[int]


@dataclass(frozen=True)
class _PreparedConfig:
    """書き込み前に読み込み・正規化した設定 json。"""

    path: Path
    normalized: NormalizedConfig


def _read_config_text(path: Path) -> str:
    # Windows で保存された BOM 付き json も読めるようにする
    return path.read_text(encoding="utf-8-sig")


def _detect_configs(root: Path) -> list[_PreparedConfig]:
    """`root` 直下の設定 json を自動検出する。読めない json はスキップする。"""
    prepared: list[_PreparedConfig] = []
    # 設定 json でない json も置かれうるため、読めないものは黙ってスキップする
    for path in sorted(root.glob("*.json"), key=lambda p: p.name):
        if not path.is_file():
            continue
        try:
            normalized = normalize_kohya_gui_config(_read_config_text(path))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            # json.JSONDecodeError は ValueError の派生
            logger.debug(f"設定 json として読めないためスキップ: {path.name}: {type(e).__name__}")
            continue
        prepared.append(_PreparedConfig(path, normalized))
    return prepared


def _load_explicit_configs(paths: list[Path]) -> list[_PreparedConfig]:
    """明示指定の設定 json を読む。1 つでも読めなければ拒否する。

    黙って落とすと設定を欠いた版がコミットされるため、自動検出と違いスキップしない。

    Raises:
        FileNotFoundError: 設定 json が存在しない場合。
        ValueError: 設定 json が不正 (json でない・最上位がオブジェクトでない・UTF-8 でない) な場合。
        OSError: 設定 json を読めない場合。
    """
    prepared: list[_PreparedConfig] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"指定された設定 json が見つかりません: {path.name}")
        try:
            normalized = normalize_kohya_gui_config(_read_config_text(path))
        except UnicodeDecodeError as e:
            # UnicodeDecodeError は ValueError の派生だが、原因が分かるよう明示する
            raise ValueError(f"指定された設定 json を UTF-8 として読めません: {path.name}") from e
        except ValueError as e:
            raise ValueError(f"指定された設定 json が不正です: {path.name}") from e
        prepared.append(_PreparedConfig(path, normalized))
    return prepared


def _as_str(value: NormalizedValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: NormalizedValue | None) -> int | None:
    # bool は int の派生だが数値として扱わない
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_float(value: NormalizedValue | None) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _to_training_config_spec(prepared: _PreparedConfig) -> TrainingConfigSpec:
    """正規化結果を `TrainingConfigSpec` にする。主要な値は `normalized` から取り出す。"""
    config = prepared.normalized
    normalized = config.normalized
    return TrainingConfigSpec(
        source_kind=CONFIG_SOURCE_KIND,
        source_file_name=prepared.path.name,
        raw_content=config.raw_content,
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        unmapped_json=json.dumps(config.unmapped, ensure_ascii=False),
        target_script=config.target_script,
        output_name=_as_str(normalized.get("output_name")),
        base_model=_as_str(normalized.get("pretrained_model_name_or_path")),
        resolution=_as_str(normalized.get("resolution")),
        network_dim=_as_int(normalized.get("network_dim")),
        network_alpha=_as_float(normalized.get("network_alpha")),
        learning_rate=_as_float(normalized.get("learning_rate")),
    )


def _validate_folders(
    plan: DatasetImportPlan, scanned_by_dir: dict[str, ScannedFolder]
) -> list[tuple[FolderImportPlan, ScannedFolder]]:
    """取り込むフォルダを検証し、計画とスキャン結果の組を計画順に返す。

    Raises:
        DatasetConflictError: 計画に同じフォルダが重複する、またはフォルダ内で `file_stem` が重複する場合。
        ValueError: 計画のフォルダがスキャン結果に無い (存在しない・除外対象) 場合。
    """
    targets: list[tuple[FolderImportPlan, ScannedFolder]] = []
    seen: set[str] = set()
    for folder_plan in plan.folders:
        if not folder_plan.include:
            continue
        if folder_plan.dir_name in seen:
            raise DatasetConflictError(f"計画に同じフォルダが重複しています: '{folder_plan.dir_name}'")
        seen.add(folder_plan.dir_name)
        scanned = scanned_by_dir.get(folder_plan.dir_name)
        if scanned is None:
            raise ValueError(f"取り込み対象のフォルダが見つかりません: '{folder_plan.dir_name}'")
        stems = [image.file_stem for image in scanned.images]
        if len(stems) != len(set(stems)):
            raise DatasetConflictError(
                f"フォルダ内に同じ名前 (拡張子違い) の画像があります: '{folder_plan.dir_name}'"
            )
        targets.append((folder_plan, scanned))
    return targets


class DatasetImportService:
    """Kohya 形式のディレクトリを、データセットの版として取り込む service (Qt-free)。"""

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        repository: DatasetRepository,
        fsm: FileSystemManager,
    ) -> None:
        """service を初期化する。

        Args:
            db_manager: 画像の登録に使う DB マネージャ。
            repository: データセットの Repository。
            fsm: 画像の保存先を管理する FileSystemManager (初期化済みであること)。
        """
        self._db_manager = db_manager
        self._repository = repository
        self._fsm = fsm

    def propose_plan(
        self,
        root: Path,
        dataset_name: str,
        version_name: str,
        explicit_config_files: list[Path] | None = None,
    ) -> DatasetImportPlan:
        """スキャン結果から取り込み計画の候補を作る。DB には何も書かない。

        トリガーワードはスキャンの候補を確定値にしないため `None` とする。版名は、
        `version_name` が空なら `root` 直下の設定 json の `output_name` を候補にし、
        それも無ければ `root` のフォルダ名を使う。

        Args:
            root: Kohya 形式のルートディレクトリ。
            dataset_name: データセット名。
            version_name: 版名。空文字なら候補を作る。
            explicit_config_files: 設定 json を明示する場合のパス。`None` なら `root` 直下を自動検出する。
                自動検出では読めない json をスキップするが、明示指定は 1 つでも読めなければ拒否する。

        Returns:
            確認前の取り込み計画。

        Raises:
            FileNotFoundError: 明示指定の設定 json が存在しない場合。
            ValueError: 明示指定の設定 json が不正 (json でない・UTF-8 でない等) な場合。
            OSError: 明示指定の設定 json を読めない場合。
        """
        scanned = scan_kohya_directory(root)
        folders = [
            FolderImportPlan(
                dir_name=folder.dir_name,
                name=folder.name,
                num_repeats=folder.num_repeats,
                trigger_word=None,
                include=True,
            )
            for folder in scanned
        ]

        prepared = (
            _detect_configs(root)
            if explicit_config_files is None
            else _load_explicit_configs(explicit_config_files)
        )
        config_files = [config.path for config in prepared]
        output_names = [
            config.normalized.output_name for config in prepared if config.normalized.output_name
        ]

        proposed_version = version_name.strip()
        if not proposed_version:
            proposed_version = output_names[0] if output_names else root.name
        return DatasetImportPlan(
            dataset_name=dataset_name,
            version_name=proposed_version,
            parent_version_id=None,
            folders=folders,
            config_files=config_files,
        )

    def import_directory(self, root: Path, plan: DatasetImportPlan) -> DatasetImportResult:
        """計画に従ってディレクトリを取り込み、新しい版を作る。

        書き込み前に計画の検証と設定 json の正規化を済ませ、版の作成で衝突した場合は
        何も書かない。フォルダは 1 つずつ 1 トランザクションで追加する。

        Args:
            root: Kohya 形式のルートディレクトリ。
            plan: 確認済みの取り込み計画。

        Returns:
            取り込み結果。

        Raises:
            DatasetConflictError: 同じデータセットに同名の版がある、計画に同じフォルダが重複する、
                フォルダ内で画像名が重複する場合。
            ValueError: 計画のフォルダがスキャン結果に無い、または設定 json が読めない場合。
            OSError: 設定 json を読めない場合。
        """
        scanned_by_dir = {folder.dir_name: folder for folder in scan_kohya_directory(root)}
        targets = _validate_folders(plan, scanned_by_dir)
        prepared_configs = [
            _PreparedConfig(path, normalize_kohya_gui_config(_read_config_text(path)))
            for path in plan.config_files
        ]

        logger.info(
            f"データセット取り込み開始: {root} (dataset='{plan.dataset_name}', "
            f"version='{plan.version_name}', folders={len(targets)})"
        )
        dataset_id = self._repository.ensure_dataset(plan.dataset_name)
        version_id = self._repository.create_version(dataset_id, plan.version_name, plan.parent_version_id)

        image_count = 0
        skipped_images = 0
        for position, (folder_plan, scanned) in enumerate(targets):
            images: list[FolderImageSpec] = []
            for scanned_image in scanned.images:
                registered = self._db_manager.register_original_image(scanned_image.path, self._fsm)
                if registered is None:
                    skipped_images += 1
                    logger.debug(f"画像を登録できないため所属を記録しません: {scanned_image.path}")
                    continue
                images.append(
                    FolderImageSpec(
                        image_id=registered[0],
                        file_stem=scanned_image.file_stem,
                        texts=[
                            LearningTextSpec(text.extension, text.raw_text, list(text.elements))
                            for text in scanned_image.texts
                        ],
                    )
                )
            spec = FolderSpec(
                dir_name=folder_plan.dir_name,
                name=folder_plan.name,
                num_repeats=folder_plan.num_repeats,
                trigger_word=folder_plan.trigger_word,
                position=position,
            )
            self._repository.add_folder(version_id, spec, images)
            image_count += len(images)

        training_config_ids = [
            self._repository.add_training_config(dataset_id, version_id, _to_training_config_spec(prepared))
            for prepared in prepared_configs
        ]

        logger.info(
            f"データセット取り込み完了: version_id={version_id}, folders={len(targets)}, "
            f"images={image_count}, skipped={skipped_images}, configs={len(training_config_ids)}"
        )
        return DatasetImportResult(
            dataset_id=dataset_id,
            version_id=version_id,
            folder_count=len(targets),
            image_count=image_count,
            skipped_images=skipped_images,
            training_config_ids=training_config_ids,
        )
