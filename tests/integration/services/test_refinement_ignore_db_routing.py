"""refinement ignore の保存先 DB 追従テスト (#978)。

``ServiceContainer.create_refinement_service`` に注入した session factory の DB へ ignore が
保存され、別 DB には保存されないこと (保存先 DB の差) を実 SQLite で検証する。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.refinement_ignore import RefinementIgnoreRepository
from lorairo.database.schema import Base
from lorairo.services.service_container import ServiceContainer

pytestmark = pytest.mark.integration


def _make_factory() -> tuple[sessionmaker, object]:
    """スキーマ作成済みの独立 in-memory SQLite と session factory を生成する。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine), engine


def test_create_refinement_service_persists_ignore_to_given_db() -> None:
    """注入 factory の DB にだけ ignore が保存され、別 DB には残らない (#978)。"""
    ServiceContainer.reset_for_testing()
    try:
        container = ServiceContainer()
        factory_a, engine_a = _make_factory()
        factory_b, engine_b = _make_factory()

        service = container.create_refinement_service(factory_a)
        service.ignore("blue_eyes", "broad_single_word")

        repo_a = RefinementIgnoreRepository(session_factory=factory_a)
        repo_b = RefinementIgnoreRepository(session_factory=factory_b)
        assert repo_a.list_ignored() == {("blue_eyes", "broad_single_word")}
        assert repo_b.list_ignored() == set()

        engine_a.dispose()
        engine_b.dispose()
    finally:
        ServiceContainer.reset_for_testing()
