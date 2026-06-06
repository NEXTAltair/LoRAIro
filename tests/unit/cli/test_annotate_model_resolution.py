"""CLI モデル識別子の解決ロジック単体テスト (Issue #245)。

`_resolve_model_identifier()` が litellm_model_id / name / 曖昧 / 不明 の
4 パターンを正しく扱うことを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import click
import pytest

from lorairo.cli.commands.annotate import _resolve_model_identifier


def _fake_model(
    litellm_model_id: str, name: str, provider: str | None = None, *, available: bool = True
) -> SimpleNamespace:
    """`Model` 互換の軽量 fake。"""
    return SimpleNamespace(
        litellm_model_id=litellm_model_id,
        name=name,
        provider=provider,
        available=available,
    )


@pytest.fixture
def repository() -> Mock:
    """Mock リポジトリ (get_model_by_litellm_id / get_models_by_name のみ実装)"""
    return Mock()


class TestResolveModelIdentifier:
    """`_resolve_model_identifier()` の 4 パターン検証。"""

    def test_exact_litellm_id_match_returns_value(self, repository: Mock) -> None:
        """litellm_model_id 完全一致は最優先で採用される"""
        target = _fake_model("openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter")
        repository.get_model_by_litellm_id.return_value = target

        result = _resolve_model_identifier(repository, "openrouter/openai/gpt-4o")

        assert result == "openrouter/openai/gpt-4o"
        repository.get_model_by_litellm_id.assert_called_once_with("openrouter/openai/gpt-4o")
        # name lookup は呼ばれない
        repository.get_models_by_name.assert_not_called()

    def test_unique_name_match_returns_litellm_id(self, repository: Mock) -> None:
        """name 一致が単一行ならその行の litellm_model_id を返す (convenience)"""
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = [
            _fake_model("openai/gpt-4o-mini", "gpt-4o-mini", "openai"),
        ]

        result = _resolve_model_identifier(repository, "gpt-4o-mini")

        assert result == "openai/gpt-4o-mini"

    def test_ambiguous_name_match_aborts_with_candidate_list(self, repository: Mock) -> None:
        """同 name 複数 provider の曖昧マッチは UsageError で候補一覧を表示"""
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = [
            _fake_model("openai/gpt-4o", "openai/gpt-4o", "openai"),
            _fake_model("openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter"),
        ]

        with pytest.raises(click.UsageError) as excinfo:
            _resolve_model_identifier(repository, "openai/gpt-4o")

        out = excinfo.value.message
        assert "Ambiguous model 'openai/gpt-4o'" in out
        # 両方の候補が表示される
        assert "openai/gpt-4o (provider: openai)" in out
        assert "openrouter/openai/gpt-4o (provider: openrouter)" in out
        assert "lorairo-cli models list" in out

    def test_unknown_identifier_aborts_with_help(self, repository: Mock) -> None:
        """litellm_model_id / name どちらにも一致しない場合は UsageError + help"""
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = []

        with pytest.raises(click.UsageError) as excinfo:
            _resolve_model_identifier(repository, "totally-unknown-model")

        out = excinfo.value.message
        assert "Unknown model 'totally-unknown-model'" in out
        assert "lorairo-cli models list" in out

    def test_litellm_match_short_circuits_before_name_lookup(self, repository: Mock) -> None:
        """litellm_model_id 一致時は name lookup を skip する (パフォーマンス確認)"""
        target = _fake_model("openai/gpt-4o", "openai/gpt-4o", "openai")
        repository.get_model_by_litellm_id.return_value = target

        _resolve_model_identifier(repository, "openai/gpt-4o")

        repository.get_models_by_name.assert_not_called()

    def test_discontinued_litellm_match_aborts(self, repository: Mock) -> None:
        """de-list 済 (available=False) モデルは litellm_model_id 一致でも abort する (PR #590 review P2)。"""
        target = _fake_model(
            "openai/o4-mini-deep-research-2025-06-26",
            "openai/o4-mini-deep-research-2025-06-26",
            "openai",
            available=False,
        )
        repository.get_model_by_litellm_id.return_value = target

        with pytest.raises(click.UsageError) as excinfo:
            _resolve_model_identifier(repository, "openai/o4-mini-deep-research-2025-06-26")

        out = excinfo.value.message
        assert "openai/o4-mini-deep-research-2025-06-26" in out
        assert "discontinued" in out

    def test_discontinued_name_match_aborts(self, repository: Mock) -> None:
        """name 一致でも de-list 済モデルは abort する (PR #590 review P2)。"""
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = [
            _fake_model("openai/removed", "removed", "openai", available=False),
        ]

        with pytest.raises(click.UsageError) as excinfo:
            _resolve_model_identifier(repository, "removed")

        assert "discontinued" in excinfo.value.message
