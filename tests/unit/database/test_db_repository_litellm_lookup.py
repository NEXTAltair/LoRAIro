"""ADR 0023 Phase 1.11 (LoRAIro Issue #238) — `litellm_model_id` ベースの lookup API 検証。

`get_model_by_litellm_id` / `get_models_by_litellm_ids` / `_get_or_create_manual_edit_model`
の挙動を、実 in-memory SQLite に対する統合的な単体テストで確認する。
"""

from __future__ import annotations

import pytest

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    MANUAL_EDIT_PROVIDER,
)


@pytest.mark.unit
class TestGetModelByLitellmId:
    """`get_model_by_litellm_id` (Phase 1.11) の境界条件検証。"""

    def test_returns_model_when_found(self, temp_db_repository: ImageRepository) -> None:
        """登録済み `litellm_model_id` で Model が返る。"""
        temp_db_repository.insert_model(
            name="gpt-4o",
            provider="openai",
            model_types=["llm", "captioner"],
            litellm_model_id="openai/phase111-gpt-4o",
            requires_api_key=True,
        )

        model = temp_db_repository.get_model_by_litellm_id("openai/phase111-gpt-4o")

        assert model is not None
        assert model.name == "gpt-4o"
        assert model.provider == "openai"
        assert model.litellm_model_id == "openai/phase111-gpt-4o"

    def test_returns_none_when_not_found(self, temp_db_repository: ImageRepository) -> None:
        """未登録 `litellm_model_id` で None が返る。"""
        result = temp_db_repository.get_model_by_litellm_id("openai/nonexistent")
        assert result is None

    def test_distinguishes_routes_for_same_model(self, temp_db_repository: ImageRepository) -> None:
        """同名モデルでも経路 (直接 vs OpenRouter) が異なれば別エントリとして取得できる。"""
        temp_db_repository.insert_model(
            name="claude-3-5-sonnet-20241022",
            provider="anthropic",
            model_types=["llm", "captioner"],
            litellm_model_id="anthropic/claude-3-5-sonnet-20241022",
            requires_api_key=True,
        )
        temp_db_repository.insert_model(
            name="anthropic/claude-3-5-sonnet-20241022",
            provider="openrouter",
            model_types=["llm", "captioner"],
            litellm_model_id="openrouter/anthropic/claude-3-5-sonnet-20241022",
            requires_api_key=True,
        )

        direct = temp_db_repository.get_model_by_litellm_id("anthropic/claude-3-5-sonnet-20241022")
        openrouter = temp_db_repository.get_model_by_litellm_id(
            "openrouter/anthropic/claude-3-5-sonnet-20241022"
        )

        assert direct is not None and direct.provider == "anthropic"
        assert openrouter is not None and openrouter.provider == "openrouter"
        assert direct.id != openrouter.id


@pytest.mark.unit
class TestGetModelsByLitellmIds:
    """`get_models_by_litellm_ids` (Phase 1.11) の境界条件検証。"""

    def test_empty_set_returns_empty_dict(self, temp_db_repository: ImageRepository) -> None:
        """空セットは空 dict を返す (DB アクセスなし)。"""
        assert temp_db_repository.get_models_by_litellm_ids(set()) == {}

    def test_returns_partial_match(self, temp_db_repository: ImageRepository) -> None:
        """存在する key だけが結果 dict に含まれる。"""
        temp_db_repository.insert_model(
            name="gpt-4o",
            provider="openai",
            model_types=["llm"],
            litellm_model_id="openai/phase111-gpt-4o",
            requires_api_key=True,
        )

        result = temp_db_repository.get_models_by_litellm_ids({"openai/phase111-gpt-4o", "missing/model"})

        assert "openai/phase111-gpt-4o" in result
        assert "missing/model" not in result


@pytest.mark.unit
class TestManualEditModelSentinel:
    """`_get_or_create_manual_edit_model` の sentinel 動作 (Phase 1.11)。"""

    def test_creates_with_sentinel_litellm_id(
        self, temp_db_repository: ImageRepository, db_session_factory
    ) -> None:
        """初回呼び出しで sentinel `__manual_edit__` の MANUAL_EDIT 行が作成される。"""
        with db_session_factory() as session:
            model_id = temp_db_repository._get_or_create_manual_edit_model(session)
            session.commit()

        with db_session_factory() as session:
            from lorairo.database.schema import Model

            model = session.query(Model).filter_by(litellm_model_id=MANUAL_EDIT_LITELLM_ID).first()
            assert model is not None
            assert model.id == model_id
            assert model.name == MANUAL_EDIT_NAME
            assert model.provider == MANUAL_EDIT_PROVIDER
            assert model.litellm_model_id == MANUAL_EDIT_LITELLM_ID

    def test_returns_existing_when_already_present(
        self, temp_db_repository: ImageRepository, db_session_factory
    ) -> None:
        """2 回目以降は既存の MANUAL_EDIT 行 ID を返す (重複作成しない)。"""
        with db_session_factory() as session:
            first_id = temp_db_repository._get_or_create_manual_edit_model(session)
            session.commit()

        with db_session_factory() as session:
            second_id = temp_db_repository._get_or_create_manual_edit_model(session)
            session.commit()

        assert first_id == second_id

    def test_unique_constraint_holds(self, temp_db_repository: ImageRepository, db_session_factory) -> None:
        """sentinel `__manual_edit__` は他の `litellm_model_id` と衝突しない (UNIQUE)。"""
        with db_session_factory() as session:
            temp_db_repository._get_or_create_manual_edit_model(session)
            session.commit()

        from lorairo.database.schema import Model

        with db_session_factory() as session:
            count = session.query(Model).filter_by(litellm_model_id=MANUAL_EDIT_LITELLM_ID).count()
            assert count == 1
