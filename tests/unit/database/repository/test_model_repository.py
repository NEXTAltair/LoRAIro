"""ModelRepository 直接の単体テスト (ADR 0035 段階 1, Issue #423)。

`db_repository.py` から抽出した `ModelRepository` の責務境界を独立して検証する。
既存の `tests/unit/database/test_db_repository_litellm_lookup.py` 等は
`ImageRepository` の delegating facade 経由で同じ実装をカバーしているため、本ファイルでは
ModelRepository を直接 instantiate して以下を最小限カバーする:

- BaseRepository 継承 / session_factory 共有
- `_get_model_id` の基本動作 (found / not found)
- `insert_model` / `update_model` / `_get_or_create_manual_edit_model` の正常系
- `get_models_by_litellm_ids` の空入力ガード
- 削除されていないことを保証する smoke (ファサード経由でも同一クラス)
"""

from __future__ import annotations

import pytest

from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
from lorairo.database.schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    MANUAL_EDIT_PROVIDER,
)


@pytest.fixture
def model_repository(db_session_factory) -> ModelRepository:
    """In-memory SQLite に対する ModelRepository インスタンス。"""
    return ModelRepository(session_factory=db_session_factory)


@pytest.mark.unit
class TestModelRepositoryStructure:
    """ADR 0035 段階 1 で確立した抽出構造の sanity check。"""

    def test_inherits_base_repository(self) -> None:
        """ModelRepository は BaseRepository を継承する。"""
        assert issubclass(ModelRepository, BaseRepository)

    def test_holds_session_factory(self, db_session_factory) -> None:
        """`session_factory` を BaseRepository 経由で保持する。"""
        repo = ModelRepository(session_factory=db_session_factory)
        assert repo.session_factory is db_session_factory


@pytest.mark.unit
class TestGetModelId:
    """`_get_model_id` の基本動作。"""

    def test_returns_id_when_model_exists(self, model_repository: ModelRepository) -> None:
        """登録済み litellm_model_id で int の id が返る。"""
        new_id = model_repository.insert_model(
            name="gpt-test",
            provider="openai",
            model_types=["multimodal"],
            litellm_model_id="openai/test-get-id",
            requires_api_key=True,
        )

        result = model_repository._get_model_id("openai/test-get-id")

        assert result == new_id

    def test_returns_none_when_not_found(self, model_repository: ModelRepository) -> None:
        """未登録 litellm_model_id で None が返る (silent return せず警告ログのみ)。"""
        result = model_repository._get_model_id("openai/never-registered")
        assert result is None


@pytest.mark.unit
class TestInsertModel:
    """`insert_model` の正常系と model_types バリデーション。"""

    def test_inserts_with_all_fields(self, model_repository: ModelRepository) -> None:
        """全フィールド指定で登録できる。"""
        new_id = model_repository.insert_model(
            name="local-tagger",
            provider=None,
            model_types=["tags"],
            litellm_model_id="local-tagger-v1",
            estimated_size_gb=2.5,
            requires_api_key=False,
        )

        assert isinstance(new_id, int)
        model = model_repository.get_model_by_litellm_id("local-tagger-v1")
        assert model is not None
        assert model.name == "local-tagger"
        assert model.provider is None
        assert model.estimated_size_gb == pytest.approx(2.5)
        assert model.requires_api_key is False
        assert {mt.name for mt in model.model_types} == {"tags"}

    def test_invalid_model_type_raises_value_error(self, model_repository: ModelRepository) -> None:
        """存在しない model_type 名で ValueError が発生する。"""
        with pytest.raises(ValueError, match="Invalid model_type"):
            model_repository.insert_model(
                name="bad",
                provider="openai",
                model_types=["nonexistent_type"],
                litellm_model_id="openai/bad-type",
            )


@pytest.mark.unit
class TestUpdateModel:
    """`update_model` の差分検出。"""

    def test_updates_only_changed_fields(self, model_repository: ModelRepository) -> None:
        """変更されたフィールドのみ更新し True を返す。"""
        new_id = model_repository.insert_model(
            name="update-target",
            provider="openai",
            model_types=["multimodal"],
            litellm_model_id="openai/update-target",
        )

        changed = model_repository.update_model(model_id=new_id, provider="openrouter")

        assert changed is True
        model = model_repository.get_model_by_litellm_id("openai/update-target")
        assert model is not None
        assert model.provider == "openrouter"

    def test_no_changes_returns_false(self, model_repository: ModelRepository) -> None:
        """全引数 None の場合は差分なしで False を返す。"""
        new_id = model_repository.insert_model(
            name="no-change",
            provider="openai",
            model_types=["multimodal"],
            litellm_model_id="openai/no-change",
        )

        changed = model_repository.update_model(model_id=new_id)
        assert changed is False

    def test_raises_when_not_found(self, model_repository: ModelRepository) -> None:
        """存在しない model_id で ValueError が発生する。"""
        with pytest.raises(ValueError, match="Model not found"):
            model_repository.update_model(model_id=999999, provider="openai")


@pytest.mark.unit
class TestGetModelsByLitellmIds:
    """`get_models_by_litellm_ids` のバルクルックアップ。"""

    def test_empty_input_short_circuits(self, model_repository: ModelRepository) -> None:
        """空集合では DB アクセスせず空 dict を返す。"""
        result = model_repository.get_models_by_litellm_ids(set())
        assert result == {}

    def test_returns_only_found_keys(self, model_repository: ModelRepository) -> None:
        """見つかった key のみ dict に含まれる。"""
        model_repository.insert_model(
            name="bulk-1",
            provider="openai",
            model_types=["multimodal"],
            litellm_model_id="openai/bulk-1",
        )
        result = model_repository.get_models_by_litellm_ids({"openai/bulk-1", "openai/missing"})
        assert "openai/bulk-1" in result
        assert "openai/missing" not in result


@pytest.mark.unit
class TestGetOrCreateManualEditModel:
    """`_get_or_create_manual_edit_model` の MANUAL_EDIT sentinel 動作 (static method)。"""

    def test_creates_manual_edit_on_first_call(self, model_repository: ModelRepository) -> None:
        """初回呼び出しで MANUAL_EDIT モデルを作成する。"""
        with model_repository.session_factory() as session:
            model_id = ModelRepository._get_or_create_manual_edit_model(session)
            session.commit()

        manual_edit = model_repository.get_model_by_litellm_id(MANUAL_EDIT_LITELLM_ID)
        assert manual_edit is not None
        assert manual_edit.id == model_id
        assert manual_edit.name == MANUAL_EDIT_NAME
        assert manual_edit.provider == MANUAL_EDIT_PROVIDER

    def test_returns_existing_on_second_call(self, model_repository: ModelRepository) -> None:
        """2 回目以降は既存 MANUAL_EDIT を再利用する。"""
        with model_repository.session_factory() as session:
            first_id = ModelRepository._get_or_create_manual_edit_model(session)
            second_id = ModelRepository._get_or_create_manual_edit_model(session)
            session.commit()

        assert first_id == second_id


@pytest.mark.unit
class TestFacadeDelegation:
    """`ImageRepository` の delegating facade が `ModelRepository` を正しく呼ぶ。"""

    def test_image_repository_delegates_get_model_by_litellm_id(
        self, temp_db_repository: ImageRepository
    ) -> None:
        """ImageRepository.get_model_by_litellm_id は内部で ModelRepository を経由する。"""
        # delegating facade 経由でも同じ結果を得る
        temp_db_repository.insert_model(
            name="facade-test",
            provider="openai",
            model_types=["multimodal"],
            litellm_model_id="openai/facade-test",
        )
        via_facade = temp_db_repository.get_model_by_litellm_id("openai/facade-test")
        via_direct = temp_db_repository._model_repo.get_model_by_litellm_id("openai/facade-test")
        assert via_facade is not None
        assert via_direct is not None
        assert via_facade.id == via_direct.id

    def test_image_repository_exposes_model_repo_attribute(
        self, temp_db_repository: ImageRepository
    ) -> None:
        """ImageRepository は内部 `_model_repo` を保持する (段階移行中の hook)。"""
        assert isinstance(temp_db_repository._model_repo, ModelRepository)
        assert temp_db_repository._model_repo.session_factory is temp_db_repository.session_factory
