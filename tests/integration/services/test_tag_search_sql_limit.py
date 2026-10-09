"""大量のタグ候補がある検索でも翻訳解決・サジェストが縮退しないことを検証する。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from genai_tag_db_tools.db.overlay_reader import OverlayTagReader
from genai_tag_db_tools.db.repository import MergedTagReader, TagReader
from genai_tag_db_tools.db.schema import (
    Base,
    Tag,
    TagFormat,
    TagStatus,
    TagTranslation,
    TagTypeFormatMapping,
    TagTypeName,
    UserOverlayBase,
    UserTagTranslationPatch,
)
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import sessionmaker

from lorairo.services.search_criteria_processor import resolve_tag_search_targets
from lorairo.services.tag_suggestion_service import TagSuggestionService

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def large_tag_reader() -> Iterator[MergedTagReader]:
    """表示上限20件でも、その前段の候補数がSQLiteの変数上限を超えるDB。"""
    base_engine = create_engine("sqlite://")
    overlay_engine = create_engine("sqlite://")

    @event.listens_for(overlay_engine, "connect")
    def limit_variables(connection: sqlite3.Connection, _record: object) -> None:
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)

    try:
        Base.metadata.create_all(base_engine)
        Base.metadata.create_all(overlay_engine)
        UserOverlayBase.metadata.create_all(overlay_engine)
        base_sessions = sessionmaker(bind=base_engine)
        overlay_sessions = sessionmaker(bind=overlay_engine)
        with base_sessions() as session:
            session.add(TagFormat(format_id=1, format_name="test"))
            session.add(TagTypeName(type_name_id=1, type_name="general"))
            session.flush()
            session.add(TagTypeFormatMapping(format_id=1, type_id=0, type_name_id=1))
            session.execute(
                insert(Tag),
                [
                    {"tag_id": tag_id, "source_tag": f"fa{tag_id:04}", "tag": f"fa{tag_id:04}"}
                    for tag_id in range(1, 1006)
                ],
            )
            session.execute(
                insert(TagStatus),
                [
                    {
                        "tag_id": tag_id,
                        "format_id": 1,
                        "type_id": 0,
                        "alias": False,
                        "preferred_tag_id": tag_id,
                        "deprecated": False,
                    }
                    for tag_id in range(1, 1006)
                ],
            )
            session.execute(
                insert(TagTranslation),
                [
                    {"tag_id": tag_id, "language": "ja", "translation": f"顔{tag_id:04}"}
                    for tag_id in range(1, 1006)
                ],
            )
            session.commit()
        with overlay_sessions() as session:
            session.add_all(
                [
                    UserTagTranslationPatch(
                        target_scope="base",
                        target_tag_id=tag_id,
                        language="ja",
                        translation=f"追加の顔{tag_id:04}",
                    )
                    for tag_id in (1, 1005)
                ]
            )
            session.commit()

        yield MergedTagReader(TagReader(base_sessions), OverlayTagReader(overlay_sessions))
    finally:
        overlay_engine.dispose()
        base_engine.dispose()


def test_translation_resolution_with_many_matches(large_tag_reader: MergedTagReader) -> None:
    """SQL例外を握りつぶして元の検索語だけになる退行を防ぐ。"""
    resolved = resolve_tag_search_targets(large_tag_reader, ["顔"])

    assert resolved == ["顔", *(f"fa{tag_id:04}" for tag_id in range(1, 21))]


def test_tag_suggestions_with_many_matches(large_tag_reader: MergedTagReader) -> None:
    """短い検索語でも、SQL例外による空候補ではなく上限までの候補を返す。"""
    suggestions = TagSuggestionService(large_tag_reader).get_suggestions("fa")

    assert suggestions == [f"fa{tag_id:04}" for tag_id in range(1, 21)]
