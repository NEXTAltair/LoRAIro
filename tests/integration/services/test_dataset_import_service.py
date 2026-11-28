"""`DatasetImportService` の統合テスト (Issue #1418)。

実 DB (ファイル SQLite) と実 `ImageDatabaseManager` / `FileSystemManager` で、Kohya 形のディレクトリを
取り込む。画像直下の `Tag` には最新版の .txt の要素を `KOHYA_DATASET` の行としてだけ書くこと
(#1647)、同じ画像が 2 フォルダにあっても学習テキストが別々に残ること、二重取り込みで中途半端な行が
残らないことを確認する。
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image as PILImage
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    TagSyncResult,
    TrainingConfigSpec,
)
from lorairo.database.schema import KOHYA_DATASET_LITELLM_ID, Base
from lorairo.filesystem import FileSystemManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.dataset_import_service import (
    DatasetImportPlan,
    DatasetImportService,
    EmptyDatasetImportError,
    FolderImportPlan,
    VersionCandidate,
    order_version_candidates,
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

    # 本番の接続 (db_core) と同じく外部キーを有効にし、版の削除が ON DELETE CASCADE で子へ及ぶようにする
    @event.listens_for(eng, "connect")
    def _enable_foreign_keys(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

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


def _tags_by_image(engine: Engine) -> dict[int, list[tuple[str, str]]]:
    """画像ごとの (表記, モデルの litellm_model_id) を返す。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.image_id, t.tag, m.litellm_model_id FROM tags t "
                "JOIN models m ON m.id = t.model_id"
            )
        ).all()
    result: dict[int, list[tuple[str, str]]] = {}
    for image_id, tag, litellm_id in rows:
        result.setdefault(image_id, []).append((tag, litellm_id))
    return {key: sorted(value) for key, value in result.items()}


def _kohya(*tags: str) -> list[tuple[str, str]]:
    return sorted((tag, KOHYA_DATASET_LITELLM_ID) for tag in tags)


def test_same_image_in_two_folders_keeps_separate_texts_and_unions_kohya_tags(
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
    # 通常タグは KOHYA_DATASET の行だけで、2 フォルダに属する画像はフォルダ間の和集合 (#1647)
    a1 = next(image for image in folder_a.images if image.file_stem == "a1")
    assert _tags_by_image(engine) == {
        shared_a.image_id: _kohya("trig_a", "red hair", "trig_b", "blue eyes"),
        a1.image_id: _kohya("trig_a", "smile"),
    }
    assert (result.tags_added, result.tags_removed) == (6, 0)
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


def _folder_dir_names(repository: DatasetRepository, version_name: str) -> list[str]:
    summary = next(v for v in repository.list_versions() if v.version_name == version_name)
    return [folder.dir_name for folder in repository.get_version_snapshot(summary.version_id).folders]


def test_add_folder_failure_on_second_folder_leaves_no_committed_version(
    service: DatasetImportService,
    repository: DatasetRepository,
    engine: Engine,
    kohya_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 つ目のフォルダの追加で失敗しても、その取り込みの版・フォルダ・設定は残らず、取り込み直せる (#1658)。"""
    plan = _plan(kohya_root, config_files=[kohya_root / "config.json"])
    before = _counts(engine)
    original_add_folder = repository.add_folder
    calls: list[bool] = []

    def failing_add_folder(version_id: int, spec: FolderSpec, images: list[FolderImageSpec]) -> int:
        # 取り込みの最中は、版が作業中 (未確定) のまま見えない
        calls.append(all(v.is_working for v in repository.list_versions() if v.version_id == version_id))
        if len(calls) == 2:
            raise RuntimeError("2 つ目のフォルダで失敗")
        return original_add_folder(version_id, spec, images)

    monkeypatch.setattr(repository, "add_folder", failing_add_folder)

    with pytest.raises(RuntimeError, match="2 つ目のフォルダ"):
        service.import_directory(kohya_root, plan)

    assert calls == [True, True]
    assert repository.list_versions() == []
    assert _count(engine, "dataset_versions") == before["dataset_versions"]
    assert _count(engine, "dataset_folders") == before["dataset_folders"]
    assert _count(engine, "dataset_folder_images") == before["dataset_folder_images"]
    assert _count(engine, "dataset_learning_texts") == before["dataset_learning_texts"]
    assert _count(engine, "training_configs") == before["training_configs"]

    # 同じ版名で取り込み直せる
    monkeypatch.setattr(repository, "add_folder", original_add_folder)
    result = service.import_directory(kohya_root, plan)
    assert result.folder_count == 2
    assert _folder_dir_names(repository, "v1") == ["10_a", "5_b"]
    assert [v.is_working for v in repository.list_versions()] == [False]


def test_training_config_failure_leaves_no_committed_version(
    service: DatasetImportService,
    repository: DatasetRepository,
    engine: Engine,
    kohya_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """設定 JSON の追加で失敗しても、版・フォルダは残らず、取り込み直せる (#1658)。"""
    plan = _plan(kohya_root, config_files=[kohya_root / "config.json"])
    before = _counts(engine)
    original_add_config = repository.add_training_config

    def failing_add_config(dataset_id: int, version_id: int | None, spec: TrainingConfigSpec) -> int:
        raise RuntimeError("設定の追加で失敗")

    monkeypatch.setattr(repository, "add_training_config", failing_add_config)

    with pytest.raises(RuntimeError, match="設定の追加"):
        service.import_directory(kohya_root, plan)

    for table in ("dataset_versions", "dataset_folders", "dataset_folder_images", "training_configs"):
        assert _count(engine, table) == before[table]

    monkeypatch.setattr(repository, "add_training_config", original_add_config)
    result = service.import_directory(kohya_root, plan)
    assert len(result.training_config_ids) == 1


def test_tag_sync_failure_leaves_no_version_and_retry_syncs_latest_texts(
    service: DatasetImportService,
    repository: DatasetRepository,
    engine: Engine,
    kohya_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """タグ同期で失敗したら 2 版目を残さず、同じ版名で取り込み直すと KOHYA_DATASET が最新版になる (#1658)。"""
    first = service.import_directory(kohya_root, _plan(kohya_root))
    shared_id = next(
        image.image_id
        for image in repository.get_version_snapshot(first.version_id).folders[0].images
        if image.file_stem == "shared"
    )
    assert _tags_by_image(engine)[shared_id] == _kohya("trig_a", "red hair", "trig_b", "blue eyes")
    before = _counts(engine)

    (kohya_root / "10_a" / "shared.txt").write_text("trig_a, green hair", encoding="utf-8")
    plan_v2 = replace(_plan(kohya_root, config_files=[kohya_root / "config.json"]), version_name="v2")
    plan_v2 = replace(plan_v2, parent_version_id=first.version_id)

    def failing_sync(dataset_id: int, extension: str = ".txt") -> TagSyncResult:
        raise RuntimeError("タグ同期で失敗")

    original_sync = repository.sync_kohya_tags_for_dataset
    monkeypatch.setattr(repository, "sync_kohya_tags_for_dataset", failing_sync)

    with pytest.raises(RuntimeError, match="タグ同期"):
        service.import_directory(kohya_root, plan_v2)

    assert [v.version_name for v in repository.list_versions()] == ["v1"]
    assert _tags_by_image(engine)[shared_id] == _kohya("trig_a", "red hair", "trig_b", "blue eyes")
    for table in ("dataset_versions", "dataset_folders", "dataset_folder_images", "training_configs"):
        assert _count(engine, table) == before[table]

    # 同じ版名で取り込み直すと、KOHYA_DATASET は最新版 (v2) の内容になる
    monkeypatch.setattr(repository, "sync_kohya_tags_for_dataset", original_sync)
    second = service.import_directory(kohya_root, plan_v2)
    assert [v.version_name for v in repository.list_versions()] == ["v1", "v2"]
    assert second.version_id != first.version_id
    assert _tags_by_image(engine)[shared_id] == _kohya("trig_a", "green hair", "trig_b", "blue eyes")


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


def test_propose_plan_uses_explicit_config_files_for_version_hint(
    service: DatasetImportService, kohya_root: Path, tmp_path: Path
) -> None:
    # 画像ディレクトリの外にある json の output_name を版名の候補にし、直下の json は使わない
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"output_name": "outside_name"}), encoding="utf-8")

    plan = service.propose_plan(kohya_root, "ds", "", [outside])

    assert plan.version_name == "outside_name"
    assert plan.config_files == [outside]


def test_propose_plan_rejects_missing_explicit_config_and_writes_nothing(
    service: DatasetImportService, engine: Engine, kohya_root: Path, tmp_path: Path
) -> None:
    # 選択後に削除された json を黙って落とすと、設定を欠いた版がコミットされる
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"output_name": "valid_name"}), encoding="utf-8")
    missing = tmp_path / "deleted.json"

    with pytest.raises(FileNotFoundError):
        service.propose_plan(kohya_root, "ds", "", [valid, missing])

    assert all(count == 0 for count in _counts(engine).values())


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"{not json", id="broken_json"),
        pytest.param(b"[1, 2]", id="not_object"),
        pytest.param(b"\xff\xfe\x00broken", id="not_utf8"),
    ],
)
def test_propose_plan_rejects_unreadable_explicit_config_and_writes_nothing(
    service: DatasetImportService, engine: Engine, kohya_root: Path, tmp_path: Path, content: bytes
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_bytes(content)

    with pytest.raises(ValueError, match=r"broken\.json"):
        service.propose_plan(kohya_root, "ds", "", [broken])

    assert all(count == 0 for count in _counts(engine).values())


def test_propose_plan_auto_detect_still_skips_unreadable_json(
    service: DatasetImportService, kohya_root: Path
) -> None:
    # 自動検出は任意の json を拾うため、読めないものはこれまでどおりスキップする
    (kohya_root / "zz_broken.json").write_text("{not json", encoding="utf-8")

    plan = service.propose_plan(kohya_root, "ds", "")

    assert plan.config_files == [kohya_root / "config.json"]


def test_propose_plan_keeps_given_version_name(service: DatasetImportService, kohya_root: Path) -> None:
    plan = service.propose_plan(kohya_root, "ds", "v_user")

    assert plan.version_name == "v_user"


def test_propose_plan_carries_scan_summary_without_confirming_trigger(
    service: DatasetImportService, kohya_root: Path
) -> None:
    """計画にスキャン情報 (画像数・学習テキストの無い画像数・候補) が載り、候補は確定値にならない (#1452)。"""
    plan = service.propose_plan(kohya_root, "ds", "v1")

    by_dir = {folder.dir_name: folder for folder in plan.folders}
    scan_a = by_dir["10_a"].scan
    assert scan_a is not None
    assert scan_a.image_count == 4
    assert scan_a.images_without_text == 1
    assert scan_a.trigger_candidate == "trig_a"
    assert scan_a.trigger_match_rate == pytest.approx(0.5)
    assert by_dir["10_a"].trigger_word is None
    scan_b = by_dir["5_b"].scan
    assert scan_b is not None
    assert (scan_b.image_count, scan_b.images_without_text, scan_b.trigger_candidate) == (1, 0, "trig_b")
    assert by_dir["5_b"].trigger_word is None


def test_import_reports_images_without_text(service: DatasetImportService, kohya_root: Path) -> None:
    result = service.import_directory(kohya_root, _plan(kohya_root))

    # 学習テキストの無い画像も取り込み、件数だけ返す
    assert result.images_without_text == 1
    assert result.image_count == 5


def test_import_with_no_included_folder_raises_and_creates_no_version(
    service: DatasetImportService, engine: Engine, kohya_root: Path
) -> None:
    plan = _plan(kohya_root)
    plan = replace(plan, folders=[replace(folder, include=False) for folder in plan.folders])

    with pytest.raises(EmptyDatasetImportError):
        service.import_directory(kohya_root, plan)

    assert all(count == 0 for count in _counts(engine).values())


def test_import_without_kohya_folders_suggests_train_data_dir(
    service: DatasetImportService, engine: Engine, tmp_path: Path
) -> None:
    """学習プロジェクト全体をルートにして 0 フォルダになったら、設定 json の train_data_dir を示す。"""
    root = tmp_path / "project"
    _save_noise_image(root / "img_v02" / "x.png", seed=11)
    (root / "config.json").write_text(
        json.dumps({"output_name": "v02", "train_data_dir": "D:/train/img_v02"}), encoding="utf-8"
    )
    plan = service.propose_plan(root, "ds", "v1")
    assert plan.included_folders == []
    assert plan.train_data_dir_hints == ["D:/train/img_v02"]

    with pytest.raises(EmptyDatasetImportError, match="img_v02") as excinfo:
        service.import_directory(root, plan)

    assert excinfo.value.train_data_dir_hints == ["D:/train/img_v02"]
    assert all(count == 0 for count in _counts(engine).values())


def test_images_without_text_excludes_images_that_failed_to_register(
    service: DatasetImportService, kohya_root: Path
) -> None:
    """登録に失敗した (壊れた) 画像は、学習テキストが無くても images_without_text に数えない。"""
    (kohya_root / "5_b" / "broken.png").write_bytes(b"not a png")

    result = service.import_directory(kohya_root, _plan(kohya_root))

    assert result.skipped_images == 1
    assert result.images_without_text == 1  # 10_a/no_text.png のみ


# --- 親フォルダからの版の探索と取り込み (Issue #1648) ---


def _make_versions(parent: Path) -> Path:
    """版を 3 つ持つ親フォルダを作る (名前順は v2 < v10 になる自然順を含む)。

    - `raikou_v10ps/raikou_v10.json` は版フォルダ直下の設定 json
    - `raikou_v2/lora_train_data/train_dir/` と `raikou_v10ps/lora_train_data/train_dir/` は 3 階層下
    - `raikou_v01/` は版フォルダ直下が取り込みのルート
    - `sample/1_x/` は除外フォルダ
    """
    seed = 100
    for version, train in (
        ("raikou_v01", ()),
        ("raikou_v2", ("lora_train_data", "train_dir")),
        ("raikou_v10ps", ("lora_train_data", "train_dir")),
    ):
        root = parent.joinpath(version, *train)
        for folder in ("10_raikou", "5_extra"):
            seed += 1
            _save_noise_image(root / folder / f"{version}.png", seed=seed)
            (root / folder / f"{version}.txt").write_text(f"raikou, {version}", encoding="utf-8")
    (parent / "raikou_v10ps" / "raikou_v10.json").write_text(
        json.dumps({"output_name": "raikou_v10"}), encoding="utf-8"
    )
    _save_noise_image(parent / "sample" / "1_x" / "s.png", seed=1)
    return parent


def test_discover_versions_names_versions_after_top_folder_in_name_order(
    service: DatasetImportService, engine: Engine, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")

    candidates = service.discover_versions(parent, "raikou")

    # 名前順 (数字は数として比べる) が初期値。最新版は決めない
    assert [c.version_name for c in candidates] == ["raikou_v01", "raikou_v2", "raikou_v10ps"]
    assert [c.root for c in candidates] == [
        parent / "raikou_v01",
        parent / "raikou_v2" / "lora_train_data" / "train_dir",
        parent / "raikou_v10ps" / "lora_train_data" / "train_dir",
    ]
    assert all(c.plan.version_name == c.version_name for c in candidates)
    assert all(c.plan.parent_version_id is None for c in candidates)
    assert [len(c.plan.folders) for c in candidates] == [2, 2, 2]
    assert _count(engine, "datasets") == 0


def test_discover_versions_detects_config_json_in_version_folder(
    service: DatasetImportService, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")

    by_name = {c.version_name: c for c in service.discover_versions(parent, "raikou")}

    assert by_name["raikou_v10ps"].plan.config_files == [parent / "raikou_v10ps" / "raikou_v10.json"]
    # 設定 json の output_name ではなく版フォルダ名を版名の候補にする
    assert by_name["raikou_v10ps"].plan.version_name == "raikou_v10ps"
    assert by_name["raikou_v2"].plan.config_files == []


def test_discover_versions_returns_empty_for_a_single_root(
    service: DatasetImportService, kohya_root: Path
) -> None:
    """取り込みのルートを直接指定したら探索しない (従来の取り込みを使う)。"""
    assert service.discover_versions(kohya_root, "ds") == []


def test_discover_versions_ignores_symlinked_repeat_folder_beside_versions(
    service: DatasetImportService, tmp_path: Path
) -> None:
    """Codex P2 (PR #1652): 親フォルダの `10_link` のリンクで、本物の版の探索を止めない。"""
    parent = _make_versions(tmp_path / "ライコウLoRA")
    (parent / "10_link").symlink_to(parent / "raikou_v01" / "10_raikou", target_is_directory=True)

    names = [c.version_name for c in service.discover_versions(parent, "raikou")]

    assert names == ["raikou_v01", "raikou_v2", "raikou_v10ps"]


def test_discover_versions_keeps_single_root_made_only_of_symlinked_folders(
    service: DatasetImportService, kohya_root: Path, tmp_path: Path
) -> None:
    """学習フォルダがリンクだけのルートは、従来どおり単一ルートの取り込みとする。"""
    linked = tmp_path / "linked_train_dir"
    linked.mkdir()
    for child in kohya_root.iterdir():
        if child.is_dir():
            (linked / child.name).symlink_to(child, target_is_directory=True)

    assert service.discover_versions(linked, "ds") == []


def test_discover_versions_names_two_roots_in_one_top_folder_by_relative_path(
    service: DatasetImportService, tmp_path: Path
) -> None:
    parent = tmp_path / "p"
    _save_noise_image(parent / "v1" / "a" / "10_x" / "x.png", seed=1)
    _save_noise_image(parent / "v1" / "b" / "10_x" / "x.png", seed=2)

    names = [c.version_name for c in service.discover_versions(parent, "ds")]

    assert names == ["v1/a", "v1/b"]


def _candidates(*names: str) -> list[VersionCandidate]:
    return [
        VersionCandidate(
            name,
            Path(name),
            DatasetImportPlan(
                dataset_name="ds", version_name=name, parent_version_id=None, folders=[], config_files=[]
            ),
        )
        for name in names
    ]


def test_order_version_candidates_defaults_to_given_name_order() -> None:
    ordered, skipped = order_version_candidates(_candidates("v1", "v2", "v3"), [])

    assert [c.version_name for c in ordered] == ["v1", "v2", "v3"]
    assert skipped == []


def test_order_version_candidates_follows_given_order_and_skips_others() -> None:
    ordered, skipped = order_version_candidates(_candidates("v1", "v2", "v3"), ["v3", "v1"])

    assert [c.version_name for c in ordered] == ["v3", "v1"]
    assert [c.version_name for c in skipped] == ["v2"]


@pytest.mark.parametrize("order", [["v1", "v1"], ["v1", "nope"]])
def test_order_version_candidates_rejects_unknown_or_duplicated_names(order: list[str]) -> None:
    with pytest.raises(ValueError):
        order_version_candidates(_candidates("v1", "v2"), order)


def test_import_versions_sets_parent_from_order(
    service: DatasetImportService, repository: DatasetRepository, engine: Engine, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")
    candidates = service.discover_versions(parent, "raikou")
    ordered, _ = order_version_candidates(candidates, ["raikou_v10ps", "raikou_v01"])

    results = service.import_versions(ordered)

    versions = {v.version_name: v for v in repository.list_versions()}
    assert set(versions) == {"raikou_v10ps", "raikou_v01"}
    assert versions["raikou_v10ps"].parent_version_id is None
    assert versions["raikou_v01"].parent_version_id == results[0].version_id
    assert [r.folder_count for r in results] == [2, 2]
    # 最新版は順番の末尾 (raikou_v01)。通常タグは最新版の画像・要素だけ (#1647)
    v01 = repository.get_version_snapshot(versions["raikou_v01"].version_id)
    v01_images = {image.image_id for folder in v01.folders for image in folder.images}
    assert _tags_by_image(engine) == {image_id: _kohya("raikou", "raikou_v01") for image_id in v01_images}


def test_import_versions_uses_given_parent_for_first_version(
    service: DatasetImportService, repository: DatasetRepository, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")
    first, *rest = service.discover_versions(parent, "raikou")
    base = service.import_versions([first])[0].version_id

    results = service.import_versions(rest, parent_version_id=base)

    versions = {v.version_id: v for v in repository.list_versions()}
    assert versions[results[0].version_id].parent_version_id == base
    assert versions[results[1].version_id].parent_version_id == results[0].version_id


def test_import_versions_rejects_existing_version_name_and_writes_nothing(
    service: DatasetImportService, engine: Engine, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")
    candidates = service.discover_versions(parent, "raikou")
    service.import_versions(candidates[1:2])
    before = _counts(engine)

    with pytest.raises(DatasetConflictError):
        service.import_versions(candidates)

    assert _counts(engine) == before


def test_import_versions_rejects_invalid_later_version_and_writes_nothing(
    service: DatasetImportService, engine: Engine, tmp_path: Path
) -> None:
    """Codex P2 (PR #1652): 後ろの版の入力不備で、前の版だけ書き込まれた状態を残さない。"""
    parent = _make_versions(tmp_path / "ライコウLoRA")
    candidates = service.discover_versions(parent, "raikou")
    # 最後の版の学習フォルダに、同じ名前 (拡張子違い) の画像を足す
    folder = candidates[-1].root / "10_raikou"
    _save_noise_image(folder / "dup.png", seed=900)
    _save_noise_image(folder / "dup.jpg", seed=901)
    candidates = service.discover_versions(parent, "raikou")
    before = _counts(engine)

    with pytest.raises(DatasetConflictError):
        service.import_versions(candidates)

    assert _counts(engine) == before


def test_import_versions_rejects_version_without_folder_and_writes_nothing(
    service: DatasetImportService, engine: Engine, tmp_path: Path
) -> None:
    parent = _make_versions(tmp_path / "ライコウLoRA")
    candidates = service.discover_versions(parent, "raikou")
    last = candidates[-1]
    emptied = replace(
        last,
        plan=replace(last.plan, folders=[replace(f, include=False) for f in last.plan.folders]),
    )
    before = _counts(engine)

    with pytest.raises(EmptyDatasetImportError):
        service.import_versions([*candidates[:-1], emptied])

    assert _counts(engine) == before
