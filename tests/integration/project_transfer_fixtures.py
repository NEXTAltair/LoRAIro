"""プロジェクト横断の検索・コピー・版作成のテストで使う、合成プロジェクトの組み立て (Issue #1661)。

プロジェクトの DB は、`Base.metadata.create_all` で作った DB から ADR 0112 の 3 表を外して直前の
revision に stamp し、本物の `alembic upgrade head` で本 PR の migration を通したものを複製して使う。
画像ファイルは PIL で作った本物の PNG を、各プロジェクトの `image_dataset/` に置く。
"""

from __future__ import annotations

import hashlib
import random
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from PIL import Image as PILImage
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database import db_core
from lorairo.database.schema import (
    Base,
    Caption,
    GenerationMetadata,
    Image,
    Model,
    ModelType,
    ProcessedImage,
    Rating,
    Score,
    Tag,
)
from lorairo.services.project_transfer_service import SourceProject

PREVIOUS_REVISION = "b1c2d3e4f5a6"
NEW_TABLES = ("dataset_version_origins", "image_origins", "project_transfer_runs")
TAGGER = "wd/tagger-v3"


def build_migrated_template(path: Path) -> Path:
    """本 PR の migration を本物の upgrade で通した、空のプロジェクト DB を作る。"""
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    db_core._ensure_model_types_seeded(engine)
    with engine.begin() as conn:
        for name in NEW_TABLES:
            conn.execute(text(f"DROP TABLE {name}"))
    engine.dispose()
    config = db_core._make_alembic_config(path)
    command.stamp(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


@dataclass
class SyntheticProject:
    """テスト用のプロジェクト 1 つ。"""

    name: str
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "image_database.db"

    @property
    def source(self) -> SourceProject:
        return SourceProject(name=self.name, root=self.root)

    def session_factory(self) -> sessionmaker[Session]:
        """アプリと同じ設定 (外部キー有効) の書き込み可能なセッションファクトリ。"""
        return db_core.create_session_factory(
            db_core.create_db_engine(f"sqlite:///{self.db_path}?check_same_thread=False")
        )


def make_project(base: Path, name: str, template: Path) -> SyntheticProject:
    root = base / name
    root.mkdir(parents=True)
    shutil.copyfile(template, root / "image_database.db")
    return SyntheticProject(name=name, root=root)


def save_noise_png(path: Path, seed: int, size: tuple[int, int] = (32, 32)) -> None:
    rng = random.Random(seed)
    image = PILImage.new("RGB", size)
    image.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _get_model(session: Session, litellm_id: str, type_name: str) -> Model:
    model = session.execute(select(Model).where(Model.litellm_model_id == litellm_id)).scalar_one_or_none()
    if model is None:
        model_type = session.execute(select(ModelType).where(ModelType.name == type_name)).scalar_one()
        model = Model(
            name=litellm_id, provider="local", litellm_model_id=litellm_id, model_types=[model_type]
        )
        session.add(model)
        session.flush()
    return model


def add_image(
    project: SyntheticProject,
    stem: str,
    seed: int,
    *,
    tags: tuple[str, ...] = (),
    caption: str | None = None,
    score: float | None = None,
    rating: str | None = None,
    prompt: str | None = None,
    with_processed: bool = True,
) -> int:
    """プロジェクトに画像を 1 枚登録する。同じ seed なら同じ画像 (同じ pHash と属性) になる。"""
    original = (
        project.root / "image_dataset" / "original_images" / "2026" / "01" / "01" / "src" / f"{stem}.png"
    )
    save_noise_png(original, seed)
    factory = project.session_factory()
    with factory() as session:
        image = Image(
            uuid=f"{project.name}-{stem}",
            phash=f"phash-{seed:04d}",
            original_image_path=f"/import/{stem}.png",
            stored_image_path=original.as_posix(),
            width=32,
            height=32,
            format="PNG",
            mode="RGB",
            has_alpha=False,
            filename=f"{stem}.png",
            extension=".png",
            is_grayscale_like=False,
        )
        session.add(image)
        session.flush()
        if with_processed:
            processed = (
                project.root / "image_dataset" / "512" / "2026" / "01" / "01" / "src" / f"{stem}.webp"
            )
            save_noise_png(processed, seed + 1000)
            # 相対パスで保存し、コピー元のプロジェクト基準で解決されることも確かめる
            session.add(
                ProcessedImage(
                    image_id=image.id,
                    stored_image_path=processed.relative_to(project.root).as_posix(),
                    width=32,
                    height=32,
                    has_alpha=False,
                    filename=processed.name,
                )
            )
        if tags:
            tagger = _get_model(session, TAGGER, "tags")
            for tag in tags:
                session.add(Tag(image_id=image.id, model_id=tagger.id, tag=tag, existing=False))
        if caption is not None:
            captioner = _get_model(session, "openai/gpt-4o", "caption")
            session.add(Caption(image_id=image.id, model_id=captioner.id, caption=caption, existing=False))
        if score is not None:
            scorer = _get_model(session, "local/aesthetic", "scores")
            session.add(Score(image_id=image.id, model_id=scorer.id, score=score))
        if rating is not None:
            rater = _get_model(session, "openai/omni-moderation-latest", "ratings")
            session.add(
                Rating(
                    image_id=image.id, model_id=rater.id, raw_rating_value=rating, normalized_rating=rating
                )
            )
        if prompt is not None:
            session.add(
                GenerationMetadata(
                    image_id=image.id,
                    status="parsed",
                    parser_name="test",
                    parser_version="1",
                    positive_prompt=prompt,
                )
            )
        session.commit()
        image_id: int = image.id
    factory.kw["bind"].dispose()
    return image_id


def file_fingerprints(root: Path) -> dict[str, tuple[str, int]]:
    """ディレクトリ以下の全ファイルの (sha256, mtime_ns)。-shm / -wal は除く (読み取り接続が作り得る)。"""
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.endswith(("-shm", "-wal")):
            continue
        result[path.relative_to(root).as_posix()] = (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
    return result


def table_counts(project: SyntheticProject, tables: tuple[str, ...]) -> dict[str, int]:
    with closing(sqlite3.connect(project.db_path)) as conn:
        return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}


def add_version(
    project: SyntheticProject,
    dataset: str,
    version: str,
    dir_name: str,
    images: list[tuple[int, str, dict[str, str]]],
    *,
    parent_version_id: int | None = None,
    is_working: bool = False,
) -> int:
    """プロジェクトにデータセットの版を 1 つ作る (Issue #1660)。

    `images` は (画像 ID, file_stem, {拡張子: 学習テキスト}) の並び。確定した版は、取り込みと同じく
    `KOHYA_DATASET` のタグを最新版へ同期する。
    """
    from lorairo.database.repository.dataset import (
        DatasetRepository,
        FolderImageSpec,
        FolderSpec,
        LearningTextSpec,
    )

    factory = project.session_factory()
    repository = DatasetRepository(session_factory=factory)
    dataset_id = repository.ensure_dataset(dataset)
    version_id = repository.create_version(dataset_id, version, parent_version_id, is_working=is_working)
    repeats, _, name = dir_name.partition("_")
    repository.add_folder(
        version_id,
        FolderSpec(dir_name=dir_name, name=name, num_repeats=int(repeats), trigger_word=None, position=0),
        [
            FolderImageSpec(
                image_id=image_id,
                file_stem=stem,
                texts=[
                    LearningTextSpec(
                        extension, raw, [part.strip() for part in raw.split(",") if part.strip()]
                    )
                    for extension, raw in texts.items()
                ],
            )
            for image_id, stem, texts in images
        ],
    )
    if not is_working:
        repository.sync_kohya_tags_for_dataset(dataset_id)
    factory.kw["bind"].dispose()
    return version_id
