"""画像一括登録の協調キャンセルを実 SQLite で検証する (#1621)。

停止箇所は 3 つ: 関連ファイルの先読み中、画像と画像の間、タグ DB の検索中。
タグ DB の接続には SQLite progress handler を入れ、worker スレッドのキャンセル要求で
実行中の SQL を ``interrupted`` で打ち切る (アプリは genai-tag-db-tools の
``set_query_abort_check`` で同じ判定を登録する)。テストでは小さな DB でも確実に
打ち切れるよう呼び出し間隔を 1 命令にする。

キャンセル後に同じ入力を再登録し、画像行の重複と関連タグの欠落が残らないことも確かめる。
"""

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from genai_tag_db_tools.db import schema as tag_schema
from genai_tag_db_tools.db.overlay_reader import OverlayTagReader
from genai_tag_db_tools.db.repository import MergedTagReader, TagReader, TagRepository
from genai_tag_db_tools.db.user_tag_repository import UserTagRepository
from genai_tag_db_tools.services.tag_register import TagRegisterService
from PIL import Image as PILImage
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import Base, ErrorRecord, Image, Tag
from lorairo.gui.workers import sql_abort
from lorairo.gui.workers.registration_worker import DatabaseRegistrationResult, DatabaseRegistrationWorker
from lorairo.services.configuration_service import ConfigurationService

pytestmark = pytest.mark.integration

_BASE_TAGS = {1: "cat", 2: "dog", 3: "outdoors"}
# 画像ごとの関連 .txt。未登録タグ (new_*) はタグ DB への登録も伴う
_SIDECARS = {
    0: ["cat", "new alpha"],
    1: ["dog", "outdoors", "new beta"],
    2: ["cat", "dog", "new gamma"],
}


@dataclass
class CancelEnv:
    """画像 DB と合成タグ DB、タグ DB へ発行された SQL の記録。"""

    manager: ImageDatabaseManager
    images: sessionmaker
    user_tags: sessionmaker
    tag_statements: list[str] = field(default_factory=list)
    # タグ DB の SQL 発行直前に呼ばれる (キャンセル要求の差し込み口)
    on_tag_statement: Callable[[], None] | None = None

    def user_tag_count(self) -> int:
        with self.user_tags() as session:
            return session.scalar(select(func.count()).select_from(tag_schema.UserTag)) or 0


def _abort_when_canceled(dbapi_connection: Any, _record: Any) -> None:
    # アプリの progress handler と同じ判定 (worker スレッドのキャンセル要求) を 1 命令ごとに見る
    dbapi_connection.set_progress_handler(
        lambda: 1 if sql_abort.current_thread_cancel_requested() else 0, 1
    )


@pytest.fixture
def env(tmp_path: Path) -> Iterator[CancelEnv]:
    engines: dict[str, Engine] = {
        name: create_engine(f"sqlite:///{tmp_path / name}.db") for name in ("base", "user", "image")
    }
    for name in ("base", "user"):
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
            tag_schema.TagStatus(tag_id=i, format_id=1, type_id=0, alias=False, preferred_tag_id=i)
            for i in _BASE_TAGS
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
    cancel_env = CancelEnv(manager, images, user)

    def record(*args: Any) -> None:
        if cancel_env.on_tag_statement is not None:
            cancel_env.on_tag_statement()
        cancel_env.tag_statements.append(args[2])

    for name in ("base", "user"):
        # 既に張られた接続にも handler を入れるため pool を捨ててから listen する
        engines[name].dispose()
        event.listen(engines[name], "connect", _abort_when_canceled)
        event.listen(engines[name], "before_cursor_execute", record)
    try:
        yield cancel_env
    finally:
        for engine in engines.values():
            engine.dispose()


@pytest.fixture
def source_images(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "source"
    folder.mkdir()
    paths = []
    for index, tags in _SIDECARS.items():
        path = folder / f"image{index}.png"
        # サイズ違いで別画像として登録させる
        PILImage.new("RGB", (64 + index * 16, 64), "blue").save(path)
        path.with_suffix(".txt").write_text(", ".join(tags), encoding="utf-8")
        paths.append(path)
    return paths


def _run(worker: DatabaseRegistrationWorker) -> tuple[list[object], list[str], list[str]]:
    """worker.run() を同期実行し、(finished の結果, canceled, error) を返す。"""
    finished: list[object] = []
    canceled: list[str] = []
    errors: list[str] = []
    worker.finished.connect(finished.append)
    worker.canceled.connect(lambda: canceled.append("canceled"))
    worker.error_occurred.connect(errors.append)
    worker.run()
    return finished, canceled, errors


def _make_worker(env: CancelEnv, fs_manager, monkeypatch, paths: list[Path]) -> DatabaseRegistrationWorker:
    monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter(paths))
    return DatabaseRegistrationWorker(paths[0].parent, env.manager, fs_manager)


def _cancelled_result(finished: list[object]) -> DatabaseRegistrationResult:
    assert len(finished) == 1, "キャンセル時も処理結果 (完了件数・中断状態) が届くこと"
    result = finished[0]
    assert isinstance(result, DatabaseRegistrationResult)
    assert result.cancelled is True
    return result


def _registered_filenames(env: CancelEnv) -> list[str]:
    with env.images() as session:
        return sorted(session.scalars(select(Image.filename)))


def _tags_by_image(env: CancelEnv) -> dict[str, list[tuple[str, int | None]]]:
    with env.images() as session:
        rows = session.execute(
            select(Image.filename, Tag.tag, Tag.tag_id, Tag.model_id).join(Image, Tag.image_id == Image.id)
        ).all()
    duplicates = [key for key, count in Counter(rows).items() if count > 1]
    assert duplicates == [], f"同じタグ行が重複している: {duplicates}"
    grouped: dict[str, list[tuple[str, int | None]]] = {}
    for filename, tag, tag_id, _model_id in rows:
        grouped.setdefault(filename, []).append((tag, tag_id))
    return {name: sorted(tags, key=lambda item: item[0]) for name, tags in grouped.items()}


def _error_record_count(env: CancelEnv) -> int:
    with env.images() as session:
        return session.scalar(select(func.count()).select_from(ErrorRecord)) or 0


def _assert_fully_registered(env: CancelEnv) -> None:
    """全画像が 1 行ずつ、関連タグがすべて tag_id 付きで 1 行ずつ保存されている。"""
    assert _registered_filenames(env) == [f"image{index}.png" for index in _SIDECARS]
    tags = _tags_by_image(env)
    for index, expected in _SIDECARS.items():
        saved = tags.get(f"image{index}.png", [])
        assert sorted(tag for tag, _ in saved) == sorted(expected)
        assert all(tag_id is not None for _, tag_id in saved), saved


def _rerun(env: CancelEnv, fs_manager, monkeypatch, paths: list[Path]) -> DatabaseRegistrationResult:
    env.on_tag_statement = None
    finished, canceled, errors = _run(_make_worker(env, fs_manager, monkeypatch, paths))
    assert canceled == [] and errors == []
    result = finished[0]
    assert isinstance(result, DatabaseRegistrationResult)
    assert result.cancelled is False
    assert result.error_count == 0
    return result


def test_cancel_during_preload_stops_before_any_write(env, fs_manager, monkeypatch, source_images, qapp):
    """先読み中のキャンセル: 画像・タグとも何も書かず、未着手として結果を返す。"""
    worker = _make_worker(env, fs_manager, monkeypatch, source_images)
    original_read = worker.file_reader.get_existing_annotations
    reads: list[Path] = []

    def read_then_cancel(path: Path) -> dict[str, Any] | None:
        reads.append(path)
        if len(reads) == 2:
            worker.cancel()
        return original_read(path)

    monkeypatch.setattr(worker.file_reader, "get_existing_annotations", read_then_cancel)

    finished, canceled, errors = _run(worker)

    result = _cancelled_result(finished)
    assert canceled == [] and errors == []
    assert reads == source_images[:2], "3 枚目の先読みに進まない"
    assert (result.registered_count, result.skipped_count, result.error_count) == (0, 0, 0)
    assert result.total_count == 3
    assert result.interrupted_file is None
    assert env.tag_statements == [], "タグ DB を検索しない"
    assert _registered_filenames(env) == []

    _rerun(env, fs_manager, monkeypatch, source_images)
    _assert_fully_registered(env)


def test_cancel_between_images_keeps_finished_images(env, fs_manager, monkeypatch, source_images, qapp):
    """画像の間のキャンセル: 完了済みの 1 枚を残し、残りは未着手のまま止まる。"""
    worker = _make_worker(env, fs_manager, monkeypatch, source_images)
    original_register = env.manager.register_image_with_side_effects

    def register_then_cancel(path: Path, *args: Any, **kwargs: Any) -> Any:
        outcome = original_register(path, *args, **kwargs)
        worker.cancel()
        return outcome

    monkeypatch.setattr(env.manager, "register_image_with_side_effects", register_then_cancel)

    finished, canceled, errors = _run(worker)

    result = _cancelled_result(finished)
    assert canceled == [] and errors == []
    assert (len(result.detail), result.error_count, result.total_count) == (1, 0, 3)
    assert result.interrupted_file is None
    assert [item.filename for item in result.detail] == ["image0.png"]
    assert _registered_filenames(env) == ["image0.png"]
    assert sorted(tag for tag, _ in _tags_by_image(env)["image0.png"]) == sorted(_SIDECARS[0])

    monkeypatch.setattr(env.manager, "register_image_with_side_effects", original_register)
    rerun = _rerun(env, fs_manager, monkeypatch, source_images)
    # 完了済みの 1 枚は重複 skip、未着手の 2 枚は新規行 (同色サイズ違いは別版に分類される)
    assert (rerun.skipped_count, rerun.registered_count + rerun.variant_count) == (1, 2)
    _assert_fully_registered(env)


def test_cancel_during_tag_search_interrupts_without_fallback(
    env, fs_manager, monkeypatch, source_images, qapp
):
    """タグ検索中のキャンセル: 実行中の SQL を打ち切り、縮退保存・個別検索・エラー記録へ進まない。"""
    worker = _make_worker(env, fs_manager, monkeypatch, source_images)
    original_register = env.manager.register_image_with_side_effects
    current: dict[str, Path] = {}

    def track(path: Path, *args: Any, **kwargs: Any) -> Any:
        current["path"] = path
        return original_register(path, *args, **kwargs)

    monkeypatch.setattr(env.manager, "register_image_with_side_effects", track)
    statements_at_cancel: list[int] = []

    def cancel_in_second_image() -> None:
        if current.get("path") == source_images[1] and not worker.cancellation.is_canceled():
            statements_at_cancel.append(len(env.tag_statements))
            worker.cancel()

    env.on_tag_statement = cancel_in_second_image

    finished, canceled, errors = _run(worker)

    result = _cancelled_result(finished)
    assert canceled == [] and errors == []
    assert statements_at_cancel, "2 枚目のタグ検索中にキャンセルを要求できていない"
    # 打ち切られた 1 文の後に、別の検索・retry・個別フォールバックの SQL を出さない
    assert len(env.tag_statements) == statements_at_cancel[0] + 1
    assert (len(result.detail), result.error_count, result.total_count) == (1, 0, 3)
    assert result.interrupted_file == "image1.png"
    assert _error_record_count(env) == 0, "キャンセルを画像エラーとして記録しない"
    # 中断対象の画像は元画像の行まで確定済みでも、関連タグはロールバックされて残らない
    tags = _tags_by_image(env)
    assert "image1.png" not in tags
    assert "image2.png" not in _registered_filenames(env), "未着手の画像に進まない"

    monkeypatch.setattr(env.manager, "register_image_with_side_effects", original_register)
    _rerun(env, fs_manager, monkeypatch, source_images)
    _assert_fully_registered(env)


def test_cancel_during_batch_tag_resolution_skips_fallback(
    env, fs_manager, monkeypatch, source_images, qapp
):
    """先読み後のタグ一括解決中のキャンセル: 個別登録へフォールバックせず、画像も書かない。"""
    worker = _make_worker(env, fs_manager, monkeypatch, source_images)

    def cancel_on_first_statement() -> None:
        if not worker.cancellation.is_canceled():
            worker.cancel()

    env.on_tag_statement = cancel_on_first_statement
    user_tags_before = env.user_tag_count()

    finished, canceled, errors = _run(worker)

    result = _cancelled_result(finished)
    assert canceled == [] and errors == []
    assert len(env.tag_statements) == 1, "打ち切り後に個別検索・登録の SQL を出さない"
    assert env.user_tag_count() == user_tags_before
    assert (result.registered_count, result.error_count) == (0, 0)
    assert _registered_filenames(env) == []

    _rerun(env, fs_manager, monkeypatch, source_images)
    _assert_fully_registered(env)
