"""ディレクトリ取り込み時のサブフォルダ共通タグをユーザーフローとして固定 (Issue #1409)。"""

import random
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from lorairo.database.schema import Image, Model, Tag
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker
from lorairo.services.folder_common_tags import parse_common_tags

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "folder_common_tags.feature"
scenarios(str(_FEATURE_FILE))


@dataclass
class FolderTagsContext:
    source: Path
    images_by_folder: dict[str, list[Path]] = field(default_factory=dict)
    folder_tags: dict[Path, tuple[str, ...]] = field(default_factory=dict)
    resolve_calls: list[str] = field(default_factory=list)
    seed: int = 0


@pytest.fixture
def folder_ctx(tmp_path, test_db_manager, monkeypatch):
    ctx = FolderTagsContext(source=tmp_path / "source")
    ctx.source.mkdir()
    test_db_manager.annotation_repo._merged_reader_initialized = True

    def record_resolve(_session, tag):
        ctx.resolve_calls.append(tag)
        return tag, None

    # 共通タグ経路はタグ DB の canonical 解決 (= 未登録タグの新規登録) を通らないことを確認する
    monkeypatch.setattr(test_db_manager.annotation_repo, "_resolve_canonical_and_tag_id", record_resolve)
    return ctx


def _add_image(ctx: FolderTagsContext, folder: str, sidecar: str | None = None) -> Path:
    """pHash が衝突しないノイズ画像を作る。"""
    ctx.seed += 1
    rng = random.Random(ctx.seed)
    image = PILImage.new("RGB", (64, 64))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(64 * 64)])
    directory = ctx.source / folder if folder else ctx.source
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"img_{ctx.seed}.png"
    image.save(path)
    if sidecar is not None:
        path.with_suffix(".txt").write_text(sidecar)
    ctx.images_by_folder.setdefault(folder, []).append(path)
    return path


def _tags_of(db_session_factory, path: Path) -> list[tuple[str, int | None, bool, str]]:
    with db_session_factory() as session:
        image_id = session.scalars(select(Image.id).where(Image.filename == path.name)).one()
        rows = session.execute(
            select(Tag.tag, Tag.tag_id, Tag.is_edited_manually, Model.name)
            .join(Model, Tag.model_id == Model.id, isouter=True)
            .where(Tag.image_id == image_id, Tag.rejected_at.is_(None))
        ).all()
    return sorted((row[0], row[1], row[2], row[3] or "") for row in rows)


def _register(ctx: FolderTagsContext, db_manager, fs_manager) -> None:
    result = DatabaseRegistrationWorker(
        ctx.source, db_manager, fs_manager, folder_tags=ctx.folder_tags
    ).execute()
    assert result.error_count == 0


@given(
    parsers.parse(
        'サブフォルダ "{first}" に画像が2枚、"{second}" に画像が1枚、選択ディレクトリ直下に画像が1枚ある'
    )
)
def tree_with_two_folders(folder_ctx, first, second):
    _add_image(folder_ctx, first)
    _add_image(folder_ctx, first)
    _add_image(folder_ctx, second)
    _add_image(folder_ctx, "")


@given(parsers.parse('サブフォルダ "{folder}" に付属テキスト "{sidecar}" を持つ画像が1枚ある'))
def image_with_sidecar(folder_ctx, folder, sidecar):
    _add_image(folder_ctx, folder, sidecar=sidecar)


@given(parsers.parse('サブフォルダ "{folder}" の共通タグに "{text}" を入力する'))
def enter_folder_tags(folder_ctx, folder, text):
    folder_ctx.folder_tags[Path(folder)] = parse_common_tags(text)


@when("ディレクトリを取り込む")
def import_directory(folder_ctx, test_db_manager, fs_manager):
    _register(folder_ctx, test_db_manager, fs_manager)


@when("同じディレクトリを同じ共通タグで再度取り込む")
def import_directory_again(folder_ctx, test_db_manager, fs_manager):
    _register(folder_ctx, test_db_manager, fs_manager)


@then(parsers.parse('"{folder}" の画像2枚に手動タグ "{first}" と "{second}" が tag_id なしで付く'))
def tagged_folder_images(folder_ctx, db_session_factory, folder, first, second):
    images = folder_ctx.images_by_folder[folder]
    assert len(images) == 2
    for path in images:
        assert _tags_of(db_session_factory, path) == sorted(
            [(first, None, True, "MANUAL_EDIT"), (second, None, True, "MANUAL_EDIT")]
        )


@then(parsers.parse('"{folder}" の画像と選択ディレクトリ直下の画像には共通タグが付かない'))
def untagged_other_images(folder_ctx, db_session_factory, folder):
    for path in folder_ctx.images_by_folder[folder] + folder_ctx.images_by_folder[""]:
        assert _tags_of(db_session_factory, path) == []


@then("タグ DB への解決や登録は行われない")
def no_tag_db_resolution(folder_ctx):
    assert folder_ctx.resolve_calls == []


@then(parsers.parse('"{folder}" の画像には "{first}" と "{second}" が1件ずつだけある'))
def no_duplicate_tags(folder_ctx, db_session_factory, folder, first, second):
    (path,) = folder_ctx.images_by_folder[folder]
    tags = [row[0] for row in _tags_of(db_session_factory, path)]
    assert sorted(tags) == sorted([first, second])
