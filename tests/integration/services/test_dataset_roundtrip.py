"""Kohya データセットの取り込み → 書き出し往復の結合テスト (Issue #1420)。

実 DB と実 `ImageDatabaseManager` で取り込み、編集なしの書き出しが元の .txt と文字列として
一致すること、`Tag` テーブルが増えないことを確認する。
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image as PILImage
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.database.schema import Base
from lorairo.filesystem import FileSystemManager
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.dataset_import_service import DatasetImportService
from lorairo.services.kohya_dataset_export_service import KohyaDatasetExportService

pytestmark = pytest.mark.integration

_TEXTS: dict[str, bytes] = {
    "crlf": b"a_tag, b_tag\r\nc_tag\r\n",
    "weight": b"(tag:1.2), (tag2:0.8), \\(escaped\\)",
    "upper": b"Kariginu, LONG_SLEEVES, Red_Hair",
    "underscore": b"long_sleeves, hair_over_one_eye, 1girl",
    "multiline": b"first line,\nsecond line,\n\nthird, trailing\n",
}


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
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
def import_service(
    session_factory: Callable[[], Session],
    repository: DatasetRepository,
    fs_manager: FileSystemManager,
) -> DatasetImportService:
    db_manager = ImageDatabaseManager(
        config_service=ConfigurationService(), session_factory=session_factory
    )
    return DatasetImportService(db_manager, repository, fs_manager)


@pytest.fixture
def kohya_root(tmp_path: Path) -> Path:
    root = tmp_path / "kohya"
    folder = root / "10_mix"
    folder.mkdir(parents=True)
    for seed, (stem, payload) in enumerate(_TEXTS.items(), start=1):
        rng = random.Random(seed)
        image = PILImage.new("RGB", (64, 64))
        image.putdata(
            [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(64 * 64)]
        )
        image.save(folder / f"{stem}.png")
        (folder / f"{stem}.txt").write_bytes(payload)
    return root


def test_unedited_roundtrip_preserves_texts_and_writes_no_tags(
    import_service: DatasetImportService,
    repository: DatasetRepository,
    session_factory: Callable[[], Session],
    kohya_root: Path,
    tmp_path: Path,
) -> None:
    """CRLF・(tag:1.2)・大文字・アンダースコア・複数行が往復で一致し、Tag は 0 行のまま。"""
    plan = import_service.propose_plan(kohya_root, "ds", "v1")
    result = import_service.import_directory(kohya_root, plan)
    assert result.image_count == len(_TEXTS)

    out_dir = tmp_path / "out"
    KohyaDatasetExportService(repository).export_version(result.version_id, out_dir)

    for stem, payload in _TEXTS.items():
        exported = (out_dir / "10_mix" / f"{stem}.txt").read_bytes()
        assert exported == payload, stem
        assert (out_dir / "10_mix" / f"{stem}.png").is_file()

    with session_factory() as session:
        assert session.execute(text("SELECT count(*) FROM tags")).scalar_one() == 0
