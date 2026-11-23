"""登録時タグ解決のリテラル完全一致とバイナリ様 sidecar の skip を実 SQLite で検証 (#1620)。"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from genai_tag_db_tools.db import schema as tag_schema
from genai_tag_db_tools.db.overlay_reader import OverlayTagReader
from genai_tag_db_tools.db.repository import MergedTagReader, TagReader, TagRepository
from genai_tag_db_tools.db.user_tag_repository import UserTagRepository
from genai_tag_db_tools.services.tag_register import TagRegisterService
from PIL import Image as PILImage
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager, RegistrationOutcome
from lorairo.database.schema import SIDECAR_IMPORT_LITELLM_ID, Base, Caption, Image, Model, Tag
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor, _expand_single_keyword
from lorairo.services.tag_suggestion_service import TagSuggestionService
from lorairo.utils.log import logger

pytestmark = pytest.mark.integration

_USER_TAG_ID = tag_schema.USER_TAG_ID_OFFSET
# ワイルドカード検索なら先に一致する別タグを、正解より小さい ID で置く
_BASE_TAGS = {
    1: "cat",
    2: "kitty",
    3: "1950s",
    4: "alphabet",
    5: "100% orange juice",
    6: "100%",
    7: "a*b",
    8: "x*y",
    9: "^o^ face",
    10: "^_^",
    11: r"\(o\)",
    12: "meow meow",
}
_BASE_ALIASES = {2: 1, 8: 1}
# .txt の表記 -> 保存される (タグ, ID)
_KNOWN = {
    "cat": ("cat", 1),
    "100%": ("100%", 6),
    "a*b": ("a*b", 7),
    "^_^": ("^_^", 10),
    "(o)": (r"\(o\)", 11),
    "my*tag": ("my*tag", _USER_TAG_ID),
}
_ALIASES = ["kitty", "x*y", "meow*"]
# .txt の表記 -> 未登録として保存・登録されるタグ
_UNREGISTERED = {
    "50%": "50%",
    "al*bet": "al*bet",
    "^_^*": "^_^*",
    "50%(x)": r"50%\(x\)",
    "zz*": "zz*",
    "plain new": "plain new",
}


@dataclass
class RegistrationEnv:
    """画像 DB と合成タグ DB、発行 SQL の記録。"""

    manager: ImageDatabaseManager
    reader: MergedTagReader
    images: sessionmaker
    user_tags: sessionmaker
    statements: list[str]

    def like_queries(self) -> list[str]:
        return [sql for sql in self.statements if " LIKE " in sql.upper()]

    def registered_id(self, tag: str) -> int | None:
        with self.user_tags() as session:
            return session.scalar(select(tag_schema.Tag.tag_id).where(tag_schema.Tag.tag == tag))


@pytest.fixture
def env(tmp_path: Path) -> Iterator[RegistrationEnv]:
    engines = {name: create_engine(f"sqlite:///{tmp_path / name}.db") for name in ("base", "user", "image")}
    statements: list[str] = []
    for name in ("base", "user"):
        event.listen(engines[name], "before_cursor_execute", lambda *args: statements.append(args[2]))
        tag_schema.Base.metadata.create_all(engines[name])
    tag_schema.UserOverlayBase.metadata.create_all(engines["user"])
    Base.metadata.create_all(engines["image"])
    base, user, images = (sessionmaker(bind=engines[name]) for name in ("base", "user", "image"))

    with base() as session:
        session.add(tag_schema.TagFormat(format_id=1, format_name="danbooru"))
        session.add(tag_schema.TagTypeName(type_name_id=1, type_name="unknown"))
        session.flush()
        session.add(tag_schema.TagTypeFormatMapping(format_id=1, type_id=0, type_name_id=1))
        session.add_all(tag_schema.Tag(tag_id=i, tag=t, source_tag=t) for i, t in _BASE_TAGS.items())
        session.flush()
        session.add_all(
            tag_schema.TagStatus(
                tag_id=i,
                format_id=1,
                type_id=0,
                alias=i in _BASE_ALIASES,
                preferred_tag_id=_BASE_ALIASES.get(i, i),
            )
            for i in _BASE_TAGS
        )
        session.commit()
    with user() as session:
        for tag_id, tag, preferred_scope, preferred in (
            (_USER_TAG_ID, "my*tag", "user", _USER_TAG_ID),
            (_USER_TAG_ID + 1, "meow*", "base", 1),
        ):
            session.add(tag_schema.UserTag(tag_id=tag_id, tag=tag, source_tag=tag))
            session.add(
                tag_schema.UserTagStatusPatch(
                    target_scope="user",
                    target_tag_id=tag_id,
                    format_id=1,
                    type_id=0,
                    alias=preferred != tag_id,
                    preferred_scope=preferred_scope,
                    preferred_tag_id=preferred,
                )
            )
        session.commit()

    reader = MergedTagReader(base_repo=TagReader(base), user_repo=OverlayTagReader(user))
    manager = ImageDatabaseManager(config_service=ConfigurationService(), session_factory=images)
    manager.annotation_repo.merged_reader = reader
    manager.annotation_repo.tag_register_service = TagRegisterService(
        repository=TagRepository(session_factory=user, reader=reader),
        reader=reader,
        user_tag_repo=UserTagRepository(user),
    )
    statements.clear()
    SearchCriteriaProcessor._ensure_cache_reader(reader)
    try:
        yield RegistrationEnv(manager, reader, images, user, statements)
    finally:
        for engine in engines.values():
            engine.dispose()


def _make_image(folder: Path, index: int, sidecar: bytes | None, suffix: str = ".txt") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"image{index}.png"
    # 単色でもサイズ違いなら別版として新しい行になる
    PILImage.new("RGB", (64 + index * 16, 64), "red").save(path)
    if sidecar is not None:
        path.with_suffix(suffix).write_bytes(sidecar)
    return path


def _register(env, fs_manager, monkeypatch, entry: str, paths: list[Path]):
    if entry == "worker":
        monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter(paths))
        result = DatabaseRegistrationWorker(paths[0].parent, env.manager, fs_manager).execute()
        assert result.error_count == 0
        return result
    for path in paths:
        outcome = env.manager.register_image_with_side_effects(path, fs_manager).outcome
        assert outcome is not RegistrationOutcome.FAILED
    return None


def _saved_tags(env: RegistrationEnv) -> list[tuple]:
    with env.images() as session:
        rows = session.execute(
            select(Image.filename, Tag.tag, Tag.tag_id, Model.litellm_model_id, Tag.existing)
            .select_from(Tag)
            .join(Image, Tag.image_id == Image.id)
            .join(Model, Tag.model_id == Model.id)
        ).all()
    return sorted(tuple(row) for row in rows)


def _expected_rows(env: RegistrationEnv, filename: str, texts: list[str]) -> list[tuple]:
    rows = []
    for text in texts:
        if text in _KNOWN:
            tag, tag_id = _KNOWN[text]
        elif text in _ALIASES:
            tag, tag_id = "cat", 1
        else:
            tag = _UNREGISTERED[text]
            tag_id = env.registered_id(tag)
            assert tag_id is not None, f"未登録タグが登録されていない: {tag}"
        rows.append((filename, tag, tag_id, SIDECAR_IMPORT_LITELLM_ID, True))
    return rows


@pytest.mark.parametrize("entry", ["worker", "common"])
def test_registration_resolves_symbol_tags_literally(tmp_path, env, fs_manager, monkeypatch, entry):
    first_tags = [*_KNOWN, *_UNREGISTERED]
    paths = [
        _make_image(tmp_path / "in", 0, ", ".join(first_tags).encode()),
        # alias は同じ canonical へ畳まれるため画像を分ける
        *(_make_image(tmp_path / "in", i, alias.encode()) for i, alias in enumerate(_ALIASES, start=1)),
    ]

    _register(env, fs_manager, monkeypatch, entry, paths)

    assert env.like_queries() == []
    expected = _expected_rows(env, paths[0].name, first_tags)
    for path, alias in zip(paths[1:], _ALIASES, strict=True):
        expected += _expected_rows(env, path.name, [alias])
    assert _saved_tags(env) == sorted(expected)


@pytest.mark.parametrize("entry", ["worker", "common"])
def test_reregistration_keeps_rows_ids_and_provenance(tmp_path, env, fs_manager, monkeypatch, entry):
    texts = ["100%", "50%", "my*tag"]
    paths = [_make_image(tmp_path / "in", 0, ", ".join(texts).encode())]
    _register(env, fs_manager, monkeypatch, entry, paths)
    first = _saved_tags(env)

    second = _register(env, fs_manager, monkeypatch, entry, paths)

    if second is not None:
        assert (second.registered_count, second.variant_count, second.skipped_count) == (0, 0, 1)
    assert _saved_tags(env) == first == sorted(_expected_rows(env, paths[0].name, texts))
    with env.images() as session:
        assert len(list(session.scalars(select(Image)))) == 1
    assert env.like_queries() == []


def test_failed_image_does_not_stop_literal_tag_import(tmp_path, env, fs_manager, monkeypatch):
    broken = tmp_path / "in" / "broken.png"
    broken.parent.mkdir()
    broken.write_bytes(b"not an image")
    broken.with_suffix(".txt").write_text("al*bet")
    good = _make_image(tmp_path / "in", 0, b"50%")
    monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter([broken, good]))

    result = DatabaseRegistrationWorker(good.parent, env.manager, fs_manager).execute()

    assert (result.registered_count, result.error_count, result.processed_paths) == (1, 1, [good])
    assert _saved_tags(env) == _expected_rows(env, good.name, ["50%"])
    assert env.like_queries() == []


def test_cancel_keeps_only_images_registered_before_it(tmp_path, env, fs_manager, monkeypatch):
    paths = [_make_image(tmp_path / "in", i, b"50%") for i in range(3)]
    monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter(paths))
    worker = DatabaseRegistrationWorker(paths[0].parent, env.manager, fs_manager)
    register = env.manager.register_image_with_side_effects

    def register_then_cancel(*args, **kwargs):
        result = register(*args, **kwargs)
        worker.cancel()
        return result

    monkeypatch.setattr(env.manager, "register_image_with_side_effects", register_then_cancel)
    # #1621: キャンセルは例外でなく、処理済み件数と中断状態を持つ結果で返る
    result = worker.execute()
    assert result.cancelled is True
    assert [item.filename for item in result.detail] == [paths[0].name]
    assert result.total_count == 3

    with env.images() as session:
        assert list(session.scalars(select(Image.filename))) == [paths[0].name]
    assert _saved_tags(env) == _expected_rows(env, paths[0].name, ["50%"])
    assert env.like_queries() == []


@pytest.mark.parametrize("text", list(_UNREGISTERED.values()))
def test_batch_resolve_registers_literal_tag(env, text):
    resolved = env.manager.annotation_repo.batch_resolve_tag_ids({text})

    assert resolved[text] is not None
    assert resolved[text] == env.registered_id(text)
    assert env.like_queries() == []


@pytest.mark.parametrize(
    "text,expected",
    [("100%", 6), ("a*b", 7), (r"\(o\)", 11), ("my*tag", _USER_TAG_ID), ("meow*", _USER_TAG_ID + 1)],
)
def test_individual_fallback_finds_literal_tag(env, text, expected):
    repo = env.manager.annotation_repo
    with env.images() as session:
        assert repo._get_or_create_tag_id_external(session, text) == expected
    assert repo._retry_tag_search(text) == expected
    assert env.like_queries() == []


@pytest.mark.parametrize("text", list(_UNREGISTERED.values()))
def test_individual_fallback_registers_instead_of_taking_wildcard_match(env, text):
    with env.images() as session:
        tag_id = env.manager.annotation_repo._get_or_create_tag_id_external(session, text)

    assert tag_id is not None
    assert tag_id == env.registered_id(text)
    assert env.like_queries() == []


@pytest.mark.parametrize("method", ["_get_or_create_tag_id_external", "_resolve_canonical_and_tag_id"])
@pytest.mark.parametrize("text", ["50%", "al*bet"])
def test_retry_after_register_conflict_is_literal(env, monkeypatch, method, text):
    repo = env.manager.annotation_repo

    def conflict(_request):
        raise IntegrityError("insert", {}, Exception("conflict"))

    monkeypatch.setattr(repo.tag_register_service, "register_tag", conflict)
    with env.images() as session:
        resolved = getattr(repo, method)(session, text)

    assert resolved in (None, (text, None))
    assert repo._retry_tag_search(text) is None
    assert env.like_queries() == []


@pytest.mark.parametrize(
    "text,expected",
    [("100%", ("100%", 6)), ("x*y", ("cat", 1)), ("my*tag", ("my*tag", _USER_TAG_ID)), ("50%", None)],
)
def test_manual_tag_save_resolution_is_literal(env, text, expected):
    with env.images() as session:
        resolved = env.manager.annotation_repo._resolve_canonical_and_tag_id(session, text)

    assert resolved == (expected or (text, env.registered_id(text)))
    assert resolved[1] is not None
    assert env.like_queries() == []


@pytest.mark.parametrize("entry", ["worker", "common"])
@pytest.mark.parametrize("suffix", [".txt", ".caption"])
@pytest.mark.parametrize(
    "payload",
    [bytes(767), b"SECRET*\x00%\xff\xfe\x81", b"SECRET tag, 50%\x00"],
    ids=["all_zero", "undecodable_nul", "utf8_nul"],
)
def test_binary_like_sidecar_is_skipped_and_image_registered(
    tmp_path, env, fs_manager, monkeypatch, entry, suffix, payload
):
    image = _make_image(tmp_path / "in", 0, payload, suffix)
    sibling = ".caption" if suffix == ".txt" else ".txt"
    image.with_suffix(sibling).write_text("cat")
    records = []
    sink = logger.add(lambda message: records.append(message.record), level="TRACE")
    try:
        _register(env, fs_manager, monkeypatch, entry, [image])
    finally:
        logger.remove(sink)

    with env.images() as session:
        assert list(session.scalars(select(Image.filename))) == [image.name]
        assert list(session.scalars(select(Tag.tag))) == (["cat"] if suffix == ".caption" else [])
        assert list(session.scalars(select(Caption.caption))) == (["cat"] if suffix == ".txt" else [])
    skipped = [r for r in records if "スキップ" in r["message"] and "NUL" in r["message"]]
    # 先読みと登録本体で重ねて警告しない
    assert [r["level"].name for r in skipped] == ["WARNING"]
    assert image.with_suffix(suffix).name in skipped[0]["message"]
    assert all("SECRET" not in r["message"] and "\x00" not in r["message"] for r in records)
    assert env.like_queries() == []


@pytest.mark.parametrize(
    "keyword,expected",
    [
        ("alph*", {"alphabet"}),
        ('"50%"', {"1950s"}),
        ('"100%"', {"100% orange juice", "100%"}),
        ("my*", {"my*tag"}),
    ],
)
def test_search_ui_keeps_wildcard_expansion(env, keyword, expected):
    found = _expand_single_keyword(env.reader, keyword, 20, 500)

    assert set(found) == expected
    assert env.like_queries()


@pytest.mark.parametrize(
    "query,expected",
    # 候補の並べ替えは記号を含む query の部分一致で絞るため "alph*" は現状どおり 0 件
    [("alph*", set()), ("100%", {"100% orange juice", "100%"})],
)
def test_tag_suggestion_keeps_wildcard_search(env, query, expected):
    assert set(TagSuggestionService(env.reader).get_suggestions(query)) == expected
    assert env.like_queries()
