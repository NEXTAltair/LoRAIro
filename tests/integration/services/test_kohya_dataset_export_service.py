"""`KohyaDatasetExportService` の統合テスト (Issue #1419)。

取り込み service (Task 8) には依存せず、DatasetRepository と Image 行を直接作って検証する。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import toml
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.dataset import (
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.database.schema import Base, Image
from lorairo.services.kohya_dataset_export_service import (
    KohyaDatasetExportService,
    MixedCaptionExtensionError,
)
from lorairo.services.learning_text import split_elements

pytestmark = pytest.mark.integration

_COMPLEX_TEXT = "Kariginu, long_sleeves, (tag:1.2),\r\nsecond line, \\(x\\)\r\n"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_db_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def repo(session_factory: Callable[[], Session]) -> DatasetRepository:
    return DatasetRepository(session_factory=session_factory)


@pytest.fixture
def service(repo: DatasetRepository) -> KohyaDatasetExportService:
    return KohyaDatasetExportService(repo)


def _make_image(session_factory: Callable[[], Session], tmp_path: Path, uuid: str, payload: bytes) -> int:
    """実在する保存済み画像ファイルと Image 行を作る。"""
    path = tmp_path / "stored" / f"{uuid}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    with session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=str(path),
            stored_image_path=str(path),
            width=64,
            height=64,
            format="PNG",
            extension=".png",
            filename=path.name,
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _text(raw_text: str, extension: str = ".txt") -> LearningTextSpec:
    return LearningTextSpec(extension=extension, raw_text=raw_text, elements=split_elements(raw_text))


def _folder(dir_name: str, repeats: int, position: int) -> FolderSpec:
    return FolderSpec(
        dir_name=dir_name,
        name=dir_name.split("_", 1)[1],
        num_repeats=repeats,
        trigger_word=None,
        position=position,
    )


@pytest.fixture
def version_id(repo: DatasetRepository, session_factory: Callable[[], Session], tmp_path: Path) -> int:
    """10_a/x と 5_b/x (同じ画像、別の .txt) を持つ版。"""
    image_id = _make_image(session_factory, tmp_path, "img-1", b"\x89PNG-bytes-1")
    dataset_id = repo.ensure_dataset("ds")
    vid = repo.create_version(dataset_id, "v1")
    repo.add_folder(
        vid,
        _folder("10_a", 10, 0),
        [FolderImageSpec(image_id=image_id, file_stem="x", texts=[_text(_COMPLEX_TEXT)])],
    )
    repo.add_folder(
        vid,
        _folder("5_b", 5, 1),
        [FolderImageSpec(image_id=image_id, file_stem="x", texts=[_text("other, tags")])],
    )
    return vid


def test_unedited_export_matches_raw_text_exactly(
    service: KohyaDatasetExportService, version_id: int, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    service.export_version(version_id, out)

    exported = (out / "10_a" / "x.txt").read_text(encoding="utf-8", newline="")
    assert exported == _COMPLEX_TEXT
    # BOM が付かないこと
    assert not (out / "10_a" / "x.txt").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (out / "5_b" / "x.txt").read_text(encoding="utf-8", newline="") == "other, tags"


def test_edited_text_is_exported_from_elements(
    service: KohyaDatasetExportService, repo: DatasetRepository, version_id: int, tmp_path: Path
) -> None:
    dataset_id = repo.ensure_dataset("ds")
    working = repo.create_working_version(dataset_id, base_version_id=version_id, version_name="v2")
    snapshot = repo.get_version_snapshot(working.id)
    text_id = snapshot.folders[0].images[0].texts[0].id
    repo.update_learning_text_elements(text_id, ["Kariginu", "new_tag"])
    committed = repo.commit_working_version(working.id)

    out = tmp_path / "out"
    service.export_version(committed.id, out)

    assert (out / "10_a" / "x.txt").read_text(encoding="utf-8", newline="") == "Kariginu, new_tag"
    # 編集していない側は raw_text のまま
    assert (out / "5_b" / "x.txt").read_text(encoding="utf-8", newline="") == "other, tags"
    # 派生元の確定済み版は書き換わっていない
    assert repo.get_version_snapshot(version_id).folders[0].images[0].texts[0].is_edited is False


def test_export_layout_and_images(
    service: KohyaDatasetExportService, version_id: int, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = service.export_version(version_id, out)

    assert (out / "10_a" / "x.png").read_bytes() == b"\x89PNG-bytes-1"
    assert (out / "5_b" / "x.png").read_bytes() == b"\x89PNG-bytes-1"
    assert result.folder_count == 2
    assert result.image_count == 2
    assert result.text_count == 2
    assert result.training_config_path is None


def test_image_without_text_gets_no_text_file(
    service: KohyaDatasetExportService,
    repo: DatasetRepository,
    session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    image_id = _make_image(session_factory, tmp_path, "img-2", b"bytes-2")
    vid = repo.create_version(repo.ensure_dataset("ds2"), "v1")
    repo.add_folder(
        vid, _folder("3_c", 3, 0), [FolderImageSpec(image_id=image_id, file_stem="y", texts=[])]
    )

    out = tmp_path / "out"
    result = service.export_version(vid, out)

    assert (out / "3_c" / "y.png").is_file()
    assert not (out / "3_c" / "y.txt").exists()
    assert result.text_count == 0


def test_dataset_config_toml_lists_subsets_with_repeats(
    service: KohyaDatasetExportService, version_id: int, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = service.export_version(version_id, out)

    config = toml.load(result.dataset_config_path)
    assert result.dataset_config_path == out / "dataset_config.toml"
    subsets = config["datasets"][0]["subsets"]
    assert [s["num_repeats"] for s in subsets] == [10, 5]
    assert [s["image_dir"] for s in subsets] == [str(out / "10_a"), str(out / "5_b")]
    assert all(s["caption_extension"] == ".txt" for s in subsets)
    assert config["general"]["caption_extension"] == ".txt"


def test_training_config_toml_overrides_paths(
    service: KohyaDatasetExportService, repo: DatasetRepository, version_id: int, tmp_path: Path
) -> None:
    dataset_id = repo.ensure_dataset("ds")
    normalized = {
        "learning_rate": 0.0001,
        "train_data_dir": "H:/old",
        "output_dir": "H:/old/out",
        "wandb_api_key": "SECRET",
        "hf_token": "SECRET2",
    }
    config_id = repo.add_training_config(
        dataset_id,
        version_id,
        TrainingConfigSpec(
            source_kind="json",
            source_file_name="cfg.json",
            raw_content="{}",
            normalized_json=json.dumps(normalized),
            unmapped_json="{}",
        ),
    )

    out = tmp_path / "out"
    result = service.export_version(version_id, out, training_config_id=config_id)

    assert result.training_config_path == out / "training_config.toml"
    text = result.training_config_path.read_text(encoding="utf-8")
    assert "SECRET" not in text
    loaded = toml.loads(text)
    assert loaded["learning_rate"] == 0.0001
    assert loaded["train_data_dir"] == str(out)
    assert loaded["output_dir"] == str(out / "output")
    assert loaded["logging_dir"] == str(out / "logs")


def test_non_empty_output_dir_raises(
    service: KohyaDatasetExportService, version_id: int, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        service.export_version(version_id, out)

    # 何も書かれていない
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


def test_mixed_caption_extensions_in_folder_is_rejected_before_writing(
    service: KohyaDatasetExportService,
    repo: DatasetRepository,
    session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    id1 = _make_image(session_factory, tmp_path, "img-m1", b"m1")
    id2 = _make_image(session_factory, tmp_path, "img-m2", b"m2")
    vid = repo.create_version(repo.ensure_dataset("dsm"), "v1")
    repo.add_folder(
        vid,
        _folder("2_mix", 2, 0),
        [
            FolderImageSpec(image_id=id1, file_stem="a", texts=[_text("t1", ".txt")]),
            FolderImageSpec(image_id=id2, file_stem="b", texts=[_text("t2", ".caption")]),
        ],
    )

    out = tmp_path / "out"
    with pytest.raises(
        MixedCaptionExtensionError, match=r"2_mix.*\.caption.*\.txt|2_mix.*\.txt.*\.caption"
    ):
        service.export_version(vid, out)

    assert not out.exists()


def test_training_config_dataset_config_points_to_generated_file(
    service: KohyaDatasetExportService, repo: DatasetRepository, version_id: int, tmp_path: Path
) -> None:
    config_id = repo.add_training_config(
        repo.ensure_dataset("ds"),
        version_id,
        TrainingConfigSpec(
            source_kind="json",
            source_file_name="cfg.json",
            raw_content="{}",
            normalized_json=json.dumps({"dataset_config": "H:/old/dataset_config.toml"}),
            unmapped_json="{}",
        ),
    )

    out = tmp_path / "out"
    result = service.export_version(version_id, out, training_config_id=config_id)

    assert result.training_config_path is not None
    loaded = toml.loads(result.training_config_path.read_text(encoding="utf-8"))
    assert loaded["dataset_config"] == str(out / "dataset_config.toml")
