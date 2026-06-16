"""scripts/repair_tag_normalization.py のユニットテスト (Issue #769)。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.schema import Base, Tag

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "repair_tag_normalization.py"
_SPEC = importlib.util.spec_from_file_location("repair_tag_normalization", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
repair_script = importlib.util.module_from_spec(_SPEC)
# dataclass + `from __future__ import annotations` は field 型評価時に sys.modules を参照するため、
# exec_module の前にモジュールを登録しておく。
sys.modules["repair_tag_normalization"] = repair_script
_SPEC.loader.exec_module(repair_script)

# autouse フィクスチャが `_get_canonical_reader` を差し替えるため、実関数参照を捕捉しておく。
_ORIGINAL_GET_CANONICAL_READER = repair_script._get_canonical_reader

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _disable_external_tag_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """ユニットテストを hermetic にするため canonical reader を既定で無効化する。

    `repair_database` 経由のテストは実 HF tag DB に依存させない (clean_format のみへ縮退)。
    canonical 解決の検証は `build_repair_plan` に明示の resolver を渡すテストで行う。
    """
    monkeypatch.setattr(repair_script, "_get_canonical_reader", lambda: None)


def _make_db(tmp_path: Path) -> tuple[Path, sessionmaker[Session]]:
    """テスト用の空 image database を作成してパスとセッションファクトリを返す。"""
    db_path = tmp_path / "image_database.db"
    engine = create_engine(f"sqlite:///{db_path.resolve()}")
    Base.metadata.create_all(engine)
    return db_path, sessionmaker(bind=engine)


def _add_tag(
    session: Session, *, tag: str, image_id: int = 1, model_id: int | None = 1, **kwargs: object
) -> Tag:
    row = Tag(tag=tag, image_id=image_id, model_id=model_id, existing=False, **kwargs)
    session.add(row)
    return row


def test_normalize_tag_value_strips_underscores_without_lowercasing() -> None:
    assert repair_script.normalize_tag_value("blue_hair_") == "blue hair"
    assert repair_script.normalize_tag_value("_touhou") == "touhou"
    assert repair_script.normalize_tag_value("alternate_costume") == "alternate costume"
    # lower 化はしない (ADR 0068)
    assert repair_script.normalize_tag_value("Grey hair") == "Grey hair"


def test_normalize_tag_value_empty_for_symbol_only() -> None:
    assert repair_script.normalize_tag_value("_") == ""
    assert repair_script.normalize_tag_value("___") == ""


def test_build_repair_plan_marks_updates_and_unchanged(tmp_path: Path) -> None:
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue_hair_")
        _add_tag(session, tag="looking at viewer")  # 既に整形済み -> unchanged
        session.commit()

    with factory() as session:
        plan = repair_script.build_repair_plan(session)

    assert plan.total_count == 2
    assert plan.unchanged_count == 1
    assert len(plan.updates) == 1
    assert plan.updates[0].old_tag == "blue_hair_"
    assert plan.updates[0].new_tag == "blue hair"
    assert not plan.duplicate_deletions
    assert not plan.empty_deletions


def test_build_repair_plan_merges_duplicates_within_same_group(tmp_path: Path) -> None:
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue hair", image_id=1, model_id=1)
        _add_tag(session, tag="blue_hair_", image_id=1, model_id=1)
        session.commit()

    with factory() as session:
        plan = repair_script.build_repair_plan(session)

    # 2 行 -> 1 行に統合される (片方は削除、生存行は整形済み)
    assert len(plan.duplicate_deletions) == 1
    assert plan.duplicate_deletions[0].new_tag == "blue hair"


def test_build_repair_plan_does_not_merge_across_model_id(tmp_path: Path) -> None:
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue hair", image_id=1, model_id=1)
        _add_tag(session, tag="blue_hair_", image_id=1, model_id=2)
        session.commit()

    with factory() as session:
        plan = repair_script.build_repair_plan(session)

    # model_id が異なるので統合しない。片方だけ整形更新。
    assert not plan.duplicate_deletions
    assert len(plan.updates) == 1


def test_build_repair_plan_flags_empty_normalization(tmp_path: Path) -> None:
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="___")
        session.commit()

    with factory() as session:
        plan = repair_script.build_repair_plan(session)

    assert len(plan.empty_deletions) == 1
    assert plan.empty_deletions[0].old_tag == "___"


def test_pick_survivor_prefers_manual_edit(tmp_path: Path) -> None:
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue hair", image_id=1, model_id=1, is_edited_manually=False)
        _add_tag(session, tag="blue_hair_", image_id=1, model_id=1, is_edited_manually=True)
        session.commit()

    with factory() as session:
        plan = repair_script.build_repair_plan(session)
        # 手動編集行が生存し、非手動行が削除される
        deleted = plan.duplicate_deletions[0]
        survivor = session.get(Tag, deleted.survivor_row_id)
        assert survivor is not None
        assert survivor.is_edited_manually is True


def test_repair_database_dry_run_does_not_write(tmp_path: Path) -> None:
    db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue_hair_")
        session.commit()

    plan = repair_script.repair_database(db_path, apply=False)
    assert len(plan.updates) == 1

    # DB は変更されていない
    with factory() as session:
        tags = list(session.execute(select(Tag.tag)).scalars())
    assert tags == ["blue_hair_"]


def test_repair_database_apply_writes_and_merges(tmp_path: Path) -> None:
    db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue hair", image_id=1, model_id=1)
        _add_tag(session, tag="blue_hair_", image_id=1, model_id=1)
        _add_tag(session, tag="_touhou", image_id=1, model_id=1)
        _add_tag(session, tag="___", image_id=1, model_id=1)
        session.commit()

    repair_script.repair_database(db_path, apply=True)

    with factory() as session:
        tags = sorted(session.execute(select(Tag.tag)).scalars())

    # 重複統合で "blue hair" は 1 行、"_touhou" は "touhou" に整形、"___" は削除
    assert tags == ["blue hair", "touhou"]


def test_repair_database_apply_creates_backup(tmp_path: Path) -> None:
    db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="blue_hair_")
        session.commit()

    repair_script.repair_database(db_path, apply=True, backup=True)

    backups = list(tmp_path.glob("image_database.db.bak-*"))
    assert len(backups) == 1


def test_repair_database_apply_no_changes_skips_backup(tmp_path: Path) -> None:
    db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="looking at viewer")
        session.commit()

    repair_script.repair_database(db_path, apply=True, backup=True)

    backups = list(tmp_path.glob("image_database.db.bak-*"))
    assert backups == []


def test_build_repair_plan_resolves_canonical_for_ai_tags(tmp_path: Path) -> None:
    """resolver があれば非手動タグを danbooru canonical へ更新する (ADR 0068 改訂)。"""
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="gray_hair", image_id=1, model_id=1)
        session.commit()

    def resolver(clean_tags: set[str]) -> dict[str, str]:
        return {"gray hair": "grey hair"}

    with factory() as session:
        plan = repair_script.build_repair_plan(session, resolver)

    assert len(plan.updates) == 1
    assert plan.updates[0].old_tag == "gray_hair"
    assert plan.updates[0].new_tag == "grey hair"


def test_build_repair_plan_keeps_manual_tag_clean_format(tmp_path: Path) -> None:
    """手動編集タグは canonical 化せず clean_format のみ適用する。"""
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="gray_hair", image_id=1, model_id=1, is_edited_manually=True)
        session.commit()

    def resolver(clean_tags: set[str]) -> dict[str, str]:
        # 手動タグは resolver の対象に含まれない想定だが、含まれても無視されること
        return {"gray hair": "grey hair"}

    with factory() as session:
        plan = repair_script.build_repair_plan(session, resolver)

    assert len(plan.updates) == 1
    # canonical 化されず clean_format のみ
    assert plan.updates[0].new_tag == "gray hair"


def test_build_repair_plan_canonical_merges_into_existing(tmp_path: Path) -> None:
    """canonical 解決で既存 canonical 行と衝突したら 1 行へ統合する。"""
    _db_path, factory = _make_db(tmp_path)
    with factory() as session:
        _add_tag(session, tag="grey hair", image_id=1, model_id=1)
        _add_tag(session, tag="gray_hair", image_id=1, model_id=1)
        session.commit()

    def resolver(clean_tags: set[str]) -> dict[str, str]:
        return {"gray hair": "grey hair", "grey hair": "grey hair"}

    with factory() as session:
        plan = repair_script.build_repair_plan(session, resolver)

    assert len(plan.duplicate_deletions) == 1
    assert plan.duplicate_deletions[0].new_tag == "grey hair"


def test_build_canonical_resolver_returns_none_without_reader() -> None:
    """reader が None なら resolver も None (clean_format のみへ縮退)。"""
    assert repair_script.build_canonical_resolver(None) is None


def test_build_canonical_resolver_excludes_deprecated(tmp_path: Path) -> None:
    """resolver は deprecated な解決結果を除外する。"""
    from unittest.mock import Mock

    reader = Mock()
    reader.search_tags_bulk.return_value = {
        "old tag": {"tag": "new tag", "tag_id": 1, "deprecated": True},
        "gray hair": {"tag": "grey hair", "tag_id": 2, "deprecated": False},
    }
    resolver = repair_script.build_canonical_resolver(reader)
    assert resolver is not None

    result = resolver({"old tag", "gray hair"})
    assert result == {"gray hair": "grey hair"}


def test_get_canonical_reader_initializes_tag_db_before_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_get_canonical_reader` は get_default_reader 前に ensure_tag_db_initialized を呼ぶ。

    base DB パス未設定だと get_default_reader が失敗するため、初期化順序が重要 (実 DB 修復時の回帰)。
    """
    from unittest.mock import Mock

    calls: list[str] = []
    ensure_mock = Mock(side_effect=lambda: calls.append("ensure"))
    reader = Mock()
    get_reader_mock = Mock(side_effect=lambda: (calls.append("get_reader"), reader)[1])
    monkeypatch.setattr(repair_script, "ensure_tag_db_initialized", ensure_mock)
    monkeypatch.setattr(repair_script, "get_default_reader", get_reader_mock)

    result = _ORIGINAL_GET_CANONICAL_READER()

    assert result is reader
    assert calls == ["ensure", "get_reader"]


def test_get_canonical_reader_returns_none_on_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """初期化失敗時は None を返し clean_format のみへ縮退する。"""
    from unittest.mock import Mock

    monkeypatch.setattr(
        repair_script,
        "ensure_tag_db_initialized",
        Mock(side_effect=RuntimeError("Tag database initialization failed")),
    )

    assert _ORIGINAL_GET_CANONICAL_READER() is None


def test_resolve_db_path_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        repair_script._resolve_db_path(tmp_path / "does_not_exist.db")
