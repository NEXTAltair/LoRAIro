"""Alembic migration `d8e9f0a1b2c3` (ADR 0023 Phase 1.11) の data backfill 検証。

旧 schema のデータパターンを再現し、upgrade 後の状態 (`name` / `provider` /
`litellm_model_id` の正規化、UNIQUE NOT NULL 制約の付与、重複 dedup) を確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _make_alembic_config(db_path: Path) -> Config:
    """テスト用 Alembic Config を組み立てる (sqlalchemy.url を上書き)。"""
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _create_legacy_schema(db_path: Path) -> None:
    """`c4d5e6f7a8b9` (本 migration の直前 head) 相当の `models` テーブルを直接 CREATE する。

    旧 schema (`name UNIQUE`, `litellm_model_id` nullable) を再現し、
    Alembic version table も整える。
    """
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE models (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    provider VARCHAR,
                    discontinued_at TIMESTAMP,
                    litellm_model_id VARCHAR,
                    estimated_size_gb FLOAT,
                    requires_api_key BOOLEAN DEFAULT '0' NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    UNIQUE (name)
                )
                """
            )
        )
        # Alembic version table を直前 head に固定 (本 migration のみ流す)
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('c4d5e6f7a8b9')"))
    engine.dispose()


def _upgrade_to_head(db_path: Path) -> None:
    """対象 migration (本 PR で追加) を head まで流す。"""
    cfg = _make_alembic_config(db_path)
    command.upgrade(cfg, "head")


@pytest.mark.unit
class TestLitellmModelIdMigration:
    """Phase 1.11 migration の data backfill 検証。"""

    def test_manual_edit_gets_sentinel(self, tmp_path: Path) -> None:
        """MANUAL_EDIT 行は sentinel `__manual_edit__` に変換される。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('MANUAL_EDIT', 'user')"))
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, provider, litellm_model_id FROM models WHERE name = 'MANUAL_EDIT'")
            ).one()
            assert row.litellm_model_id == "__manual_edit__"
            assert row.provider == "user"
        engine.dispose()

    def test_slash_name_is_split_and_litellm_id_normalized_lowercase(self, tmp_path: Path) -> None:
        """`name='OpenAI/gpt-4o'` (大文字混入 slash) → 分離後 `litellm_model_id` も lowercase 化 (P2 指摘)。

        旧実装は slash 込み name を litellm_model_id に verbatim コピーしていたため
        `OpenAI/gpt-4o` のような大文字混入がそのまま `litellm_model_id` に残り、後の
        case-sensitive lookup で正規 `openai/gpt-4o` と一致せず重複登録が起きていた。
        修正後は Step 2 で name/provider を分離 + provider lowercase、Step 3 で
        正規化済み provider/name から litellm_model_id を再構築するため、常に LiteLLM 規約
        (lowercase prefix) の正規 ID が格納される。
        """
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('OpenAI/gpt-4o', 'OpenAI')"))
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, provider, litellm_model_id FROM models WHERE id = 1")
            ).one()
            assert row.name == "gpt-4o"
            assert row.provider == "openai"
            # P2 指摘: litellm_model_id は lowercase 化された正規 LiteLLM ID
            assert row.litellm_model_id == "openai/gpt-4o"
        engine.dispose()

    def test_openrouter_nested_slash_name_normalized(self, tmp_path: Path) -> None:
        """`name='openrouter/openai/gpt-4o'` → `provider='openrouter', name='openai/gpt-4o', litellm_model_id='openrouter/openai/gpt-4o'`。

        複数 `/` を含む OpenRouter 経由モデルも、最初の `/` で分離 + provider lowercase 化
        により正規 LiteLLM ID が構築される。
        """
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO models (name, provider) VALUES ('openrouter/openai/gpt-4o', 'openrouter')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, provider, litellm_model_id FROM models WHERE id = 1")
            ).one()
            assert row.name == "openai/gpt-4o"
            assert row.provider == "openrouter"
            assert row.litellm_model_id == "openrouter/openai/gpt-4o"
        engine.dispose()

    def test_bare_name_with_known_provider_is_normalized(self, tmp_path: Path) -> None:
        """`name='claude-3-5-sonnet-20241022', provider='Anthropic'` → `anthropic/<bare>`。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO models (name, provider) VALUES ('claude-3-5-sonnet-20241022', 'Anthropic')"
                )
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name, provider, litellm_model_id FROM models WHERE id = 1")
            ).one()
            assert row.name == "claude-3-5-sonnet-20241022"
            assert row.provider == "anthropic"
            assert row.litellm_model_id == "anthropic/claude-3-5-sonnet-20241022"
        engine.dispose()

    def test_google_provider_is_mapped_to_gemini(self, tmp_path: Path) -> None:
        """旧 `provider='Google'` は LiteLLM 規約の `gemini/` プレフィックスにマップされる。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('gemini-1.5-pro', 'Google')"))
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT provider, litellm_model_id FROM models WHERE id = 1")).one()
            assert row.provider == "gemini"
            assert row.litellm_model_id == "gemini/gemini-1.5-pro"
        engine.dispose()

    def test_unknown_provider_falls_back_to_legacy_sentinel(self, tmp_path: Path) -> None:
        """ローカル ML モデル (`provider=None`/`xinntao` 等) は `__legacy_<id>__` sentinel に落ちる。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('wd-vit-tagger-v3', NULL)"))
            conn.execute(
                text("INSERT INTO models (name, provider) VALUES ('RealESRGAN_x4plus', 'xinntao')")
            )
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row1 = conn.execute(
                text("SELECT litellm_model_id FROM models WHERE name = 'wd-vit-tagger-v3'")
            ).one()
            row2 = conn.execute(
                text("SELECT litellm_model_id FROM models WHERE name = 'RealESRGAN_x4plus'")
            ).one()
            assert row1.litellm_model_id.startswith("__legacy_")
            assert row2.litellm_model_id.startswith("__legacy_")
        engine.dispose()

    def test_duplicate_litellm_id_collision_is_resolved(self, tmp_path: Path) -> None:
        """旧 DB に slash 形式と bare 形式が共存していた場合の `litellm_model_id` 衝突解消 (P1 指摘)。

        `name='openai/gpt-4o'` (slash) と `name='gpt-4o', provider='openai'` (bare) が
        共存していた場合、Step 2/4 で両行が同じ `litellm_model_id='openai/gpt-4o'` を持つ。
        Step 5.5 (dedup) で最古 (id 最小) のみ正規 ID を保持し、残りは sentinel に変換される。
        """
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            # id=1 (slash 形式) と id=2 (bare 形式) を意図的に同じ provider/モデルで作る
            conn.execute(text("INSERT INTO models (id, name, provider) VALUES (1, 'openai/gpt-4o', NULL)"))
            conn.execute(text("INSERT INTO models (id, name, provider) VALUES (2, 'gpt-4o', 'openai')"))
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        with engine.connect() as conn:
            row1 = conn.execute(text("SELECT litellm_model_id FROM models WHERE id = 1")).one()
            row2 = conn.execute(text("SELECT litellm_model_id FROM models WHERE id = 2")).one()
            # id 最小 (id=1) が正規 ID、id=2 は __legacy_2__ sentinel
            assert row1.litellm_model_id == "openai/gpt-4o"
            assert row2.litellm_model_id == "__legacy_2__"
        engine.dispose()

    def test_upgrade_applies_unique_not_null_constraint(self, tmp_path: Path) -> None:
        """upgrade 後の schema が `litellm_model_id` UNIQUE NOT NULL になっている。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('gpt-4o', 'openai')"))
        engine.dispose()

        _upgrade_to_head(db)

        engine = create_engine(f"sqlite:///{db}")
        insp = inspect(engine)
        unique_constraints = insp.get_unique_constraints("models")
        # litellm_model_id に UNIQUE 制約が付いている
        assert any(uc["column_names"] == ["litellm_model_id"] for uc in unique_constraints)
        # name の UNIQUE 制約は削除されている
        assert not any(uc["column_names"] == ["name"] for uc in unique_constraints)

        # litellm_model_id は NOT NULL
        cols = {col["name"]: col for col in insp.get_columns("models")}
        assert cols["litellm_model_id"]["nullable"] is False

        # UNIQUE 制約違反テスト
        with engine.begin() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO models (name, provider, litellm_model_id) "
                        "VALUES ('duplicate', 'openai', 'openai/gpt-4o')"
                    )
                )
        engine.dispose()

    def test_downgrade_restores_name_unique(self, tmp_path: Path) -> None:
        """downgrade で `name` UNIQUE が復元、`litellm_model_id` が nullable に戻る。"""
        db = tmp_path / "test.db"
        _create_legacy_schema(db)
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO models (name, provider) VALUES ('gpt-4o', 'openai')"))
        engine.dispose()

        _upgrade_to_head(db)

        cfg = _make_alembic_config(db)
        command.downgrade(cfg, "c4d5e6f7a8b9")

        engine = create_engine(f"sqlite:///{db}")
        insp = inspect(engine)
        unique_constraints = insp.get_unique_constraints("models")
        assert any(uc["column_names"] == ["name"] for uc in unique_constraints)
        assert not any(uc["column_names"] == ["litellm_model_id"] for uc in unique_constraints)

        cols = {col["name"]: col for col in insp.get_columns("models")}
        assert cols["litellm_model_id"]["nullable"] is True
        engine.dispose()
