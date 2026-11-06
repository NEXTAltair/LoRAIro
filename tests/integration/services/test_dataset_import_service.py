"""`DatasetImportService` の統合テスト (Issue #1418)。

実 DB (ファイル SQLite) と実 `ImageDatabaseManager` / `FileSystemManager` で、Kohya 形のディレクトリを
取り込む。画像直下の `Tag` に書かないこと、同じ画像が 2 フォルダにあっても学習テキストが別々に
残ること、二重取り込みで中途半端な行が残らないことを確認する。
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image as PILImage
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.dataset import DatasetConflictError, DatasetRepository
from lorairo.database.schema import Base
from lorairo.filesystem import FileSystemManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.dataset_import_service import (
    DatasetImportPlan,
    DatasetImportService,
    FolderImportPlan,
)

pytestmark = pytest.mark.integration

_SECRET = "SECRET-WANDB-KEY-1234"

# 取り込み後に件数を比べるテーブル
_COUNTED_TABLES: tuple[str, ...] = (
    "images",
    "tags",
    "datasets",
    "dataset_versions",
    "dataset_folders",
    "dataset_folder_images",
    "dataset_learning_texts",
    "training_configs",
)


def _save_noise_image(path: Path, seed: int, size: tuple[int, int] = (64, 64)) -> None:
    """seed ごとに異なる模様の画像を作る (pHash が衝突しないように)。"""
    rng = random.Random(seed)
    image = PILImage.new("RGB", size)
    image.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


@pytest.fixture
def kohya_root(tmp_path: Path) -> Path:
    """Kohya 形のディレクトリを作る。

    - `10_a/`: shared.png (+.txt)、a1.png (+.txt)、cap_only.png (+.caption のみ)、no_text.png
      (学習テキストなし)、`sub/deep.png` (直下より深い画像)
    - `5_b/`: shared.png (10_a と同じファイル。.txt は別内容)
    - `sample001/`: 除外フォルダの画像
    - `config.json`: Kohya_ss GUI の設定 (秘密の値を含む)
    """
    root = tmp_path / "kohya"
    folder_a = root / "10_a"
    folder_b = root / "5_b"
    _save_noise_image(folder_a / "shared.png", seed=1)
    (folder_a / "shared.txt").write_bytes(b"trig_a, red hair\r\n")
    _save_noise_image(folder_a / "a1.png", seed=2)
    (folder_a / "a1.txt").write_text("trig_a, smile", encoding="utf-8")
    _save_noise_image(folder_a / "cap_only.png", seed=3)
    (folder_a / "cap_only.caption").write_text("a caption only", encoding="utf-8")
    _save_noise_image(folder_a / "no_text.png", seed=4)
    _save_noise_image(folder_a / "sub" / "deep.png", seed=5)

    folder_b.mkdir(parents=True)
    (folder_b / "shared.png").write_bytes((folder_a / "shared.png").read_bytes())
    (folder_b / "shared.txt").write_text("trig_b, blue eyes", encoding="utf-8")

    _save_noise_image(root / "sample001" / "s.png", seed=6)

    config = {
        "output_name": "mylora_v02",
        "wandb_api_key": _SECRET,
        "use_wandb": True,
        "learning_rate": "0.0001",
        "network_dim": 16,
        "network_alpha": 8,
        "max_resolution": "1024,1024",
        "pretrained_model_name_or_path": "/models/pony.safetensors",
        "LoRA_type": "Standard",
        "sdxl": True,
    }
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'import.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def repository(session_factory: Callable[[], Session]) -> DatasetRepository:
    return DatasetRepository(session_factory=session_factory)


@pytest.fixture
def service(
    session_factory: Callable[[], Session],
    repository: DatasetRepository,
    fs_manager: FileSystemManager,
) -> DatasetImportService:
    db_manager = ImageDatabaseManager(
        config_service=ConfigurationService(), session_factory=session_factory
    )
    return DatasetImportService(db_manager, repository, fs_manager)


def _plan(
    kohya_root: Path,
    *,
    trigger_a: str | None = None,
    trigger_b: str | None = None,
    config_files: list[Path] | None = None,
) -> DatasetImportPlan:
    return DatasetImportPlan(
        dataset_name="ds",
        version_name="v1",
        parent_version_id=None,
        folders=[
            FolderImportPlan(
                dir_name="10_a", name="a", num_repeats=10, trigger_word=trigger_a, include=True
            ),
            FolderImportPlan(dir_name="5_b", name="b", num_repeats=5, trigger_word=trigger_b, include=True),
        ],
        config_files=config_files if config_files is not None else [],
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        value = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
    return int(value)


def _counts(engine: Engine) -> dict[str, int]:
    return {table: _count(engine, table) for table in _COUNTED_TABLES}


def test_same_image_in_two_folders_keeps_separate_texts_and_no_tags(
    service: DatasetImportService, repository: DatasetRepository, engine: Engine, kohya_root: Path
) -> None:
    result = service.import_directory(kohya_root, _plan(kohya_root))

    snapshot = repository.get_version_snapshot(result.version_id)
    folder_a, folder_b = snapshot.folders
    assert (folder_a.dir_name, folder_b.dir_name) == ("10_a", "5_b")
    shared_a = next(image for image in folder_a.images if image.file_stem == "shared")
    shared_b = next(image for image in folder_b.images if image.file_stem == "shared")
    assert shared_a.image_id == shared_b.image_id
    assert shared_a.texts[0].raw_text == "trig_a, red hair\r\n"
    assert shared_b.texts[0].raw_text == "trig_b, blue eyes"
    assert shared_a.texts[0].elements == ["trig_a", "red hair"]
    assert _count(engine, "tags") == 0
    assert _count(engine, "captions") == 0
    assert result.folder_count == 2
    assert result.image_count == 5
    assert result.skipped_images == 0


def test_excluded_folders_are_not_imported(
    service: DatasetImportService, engine: Engine, kohya_root: Path
) -> None:
    service.import_directory(kohya_root, _plan(kohya_root))

    # shared / a1 / cap_only / no_text の 4 枚だけ。sample001 と sub/deep.png は増えない
    assert _count(engine, "images") == 4


def test_image_without_text_is_member_without_text(
    service: DatasetImportService, repository: DatasetRepository, kohya_root: Path
) -> None:
    result = service.import_directory(kohya_root, _plan(kohya_root))

    folder_a = repository.get_version_snapshot(result.version_id).folders[0]
    by_stem = {image.file_stem: image for image in folder_a.images}
    assert set(by_stem) == {"a1", "cap_only", "no_text", "shared"}
    assert by_stem["no_text"].texts == []
    assert [text_.extension for text_ in by_stem["cap_only"].texts] == [".caption"]


def test_trigger_word_is_stored_only_from_plan(
    service: DatasetImportService, repository: DatasetRepository, kohya_root: Path
) -> None:
    # 10_a はスキャンで trig_a が候補になるが、計画は None のまま。5_b は計画の値を保存する
    result = service.import_directory(kohya_root, _plan(kohya_root, trigger_a=None, trigger_b="chosen_b"))

    folders = repository.get_version_snapshot(result.version_id).folders
    assert [folder.trigger_word for folder in folders] == [None, "chosen_b"]


def test_excluded_plan_folder_is_not_imported(
    service: DatasetImportService, repository: DatasetRepository, kohya_root: Path
) -> None:
    plan = _plan(kohya_root)
    plan = replace(plan, folders=[plan.folders[0], replace(plan.folders[1], include=False)])

    result = service.import_directory(kohya_root, plan)

    folders = repository.get_version_snapshot(result.version_id).folders
    assert [folder.dir_name for folder in folders] == ["10_a"]
    assert result.folder_count == 1


def test_duplicate_import_into_same_version_raises_conflict_and_leaves_no_rows(
    service: DatasetImportService, engine: Engine, kohya_root: Path
) -> None:
    plan = _plan(kohya_root, config_files=[kohya_root / "config.json"])
    service.import_directory(kohya_root, plan)
    before = _counts(engine)

    with pytest.raises(DatasetConflictError):
        service.import_directory(kohya_root, plan)

    assert _counts(engine) == before


def test_duplicate_folder_in_plan_raises_conflict_and_leaves_no_rows(
    service: DatasetImportService, engine: Engine, kohya_root: Path
) -> None:
    plan = _plan(kohya_root)
    plan = replace(plan, folders=[plan.folders[0], plan.folders[0]])
    before = _counts(engine)

    with pytest.raises(DatasetConflictError):
        service.import_directory(kohya_root, plan)

    assert _counts(engine) == before


def test_config_json_is_stored_with_masked_secret(
    service: DatasetImportService, repository: DatasetRepository, engine: Engine, kohya_root: Path
) -> None:
    result = service.import_directory(
        kohya_root, _plan(kohya_root, config_files=[kohya_root / "config.json"])
    )

    assert len(result.training_config_ids) == 1
    config = repository.get_training_config(result.training_config_ids[0])
    assert config.version_id == result.version_id
    assert config.source_kind == "kohya_gui_json"
    assert config.source_file_name == "config.json"
    assert _SECRET not in config.raw_content
    assert _SECRET not in config.normalized_json
    assert _SECRET not in config.unmapped_json
    assert config.target_script == "sdxl_train_network.py"
    assert config.output_name == "mylora_v02"
    assert config.base_model == "/models/pony.safetensors"
    assert config.resolution == "1024,1024"
    assert config.network_dim == 16
    assert config.network_alpha == 8.0
    assert config.learning_rate == 0.0001
    # DB のどの列にも秘密の値が残らない
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM training_configs")).all()
    assert all(_SECRET not in str(value) for row in rows for value in row)


def test_propose_plan_uses_output_name_as_version_hint(
    service: DatasetImportService, engine: Engine, kohya_root: Path
) -> None:
    plan = service.propose_plan(kohya_root, "ds", "")

    assert plan.dataset_name == "ds"
    assert plan.version_name == "mylora_v02"
    assert plan.parent_version_id is None
    assert plan.config_files == [kohya_root / "config.json"]
    assert [(f.dir_name, f.name, f.num_repeats, f.include) for f in plan.folders] == [
        ("10_a", "a", 10, True),
        ("5_b", "b", 5, True),
    ]
    # 候補のトリガーワードは確定しない
    assert all(folder.trigger_word is None for folder in plan.folders)
    # 提案は何も書き込まない
    assert _count(engine, "datasets") == 0


def test_propose_plan_keeps_given_version_name(service: DatasetImportService, kohya_root: Path) -> None:
    plan = service.propose_plan(kohya_root, "ds", "v_user")

    assert plan.version_name == "v_user"
