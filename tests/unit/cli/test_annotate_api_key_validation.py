"""Issue #241: CLI annotate run の API key validation 単体テスト。

`_validate_required_api_keys()` が provider 別の不足検出と Rich console 出力 +
``typer.Exit(1)`` を正しく実行することを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer

from lorairo.cli.commands.annotate import _validate_required_api_keys


def _fake_config(api_keys: dict[str, str]) -> Mock:
    """ConfigurationService 互換の Mock。``get_setting(section, key, default)`` のみ実装。"""
    config = Mock()
    config.get_setting.side_effect = lambda section, key, default="": api_keys.get(key, default)
    return config


def _fake_model(provider: str | None) -> SimpleNamespace:
    return SimpleNamespace(provider=provider)


@pytest.mark.unit
@pytest.mark.cli
class TestValidateRequiredApiKeys:
    def test_all_keys_present_returns_without_exit(self) -> None:
        """全 key 揃っていれば正常終了 (typer.Exit を出さない)"""
        repository = Mock()
        repository.get_model_by_litellm_id.return_value = _fake_model("openai")
        config = _fake_config(
            {
                "openai_key": "sk-a",
                "claude_key": "sk-c",
                "google_key": "sk-g",
                "openrouter_key": "sk-or",
            }
        )

        _validate_required_api_keys(repository, config, ["openai/gpt-4o"])
        # 例外が出なければ OK

    def test_missing_openrouter_exits_with_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Issue #241 主要シナリオ: openai key のみ環境で openrouter モデル選択 -> exit 1"""
        repository = Mock()
        repository.get_model_by_litellm_id.return_value = _fake_model("openrouter")
        config = _fake_config({"openai_key": "sk-a"})

        with pytest.raises(typer.Exit) as excinfo:
            _validate_required_api_keys(repository, config, ["openrouter/openai/gpt-4o"])

        assert excinfo.value.exit_code == 1
        out = capsys.readouterr().out
        assert "Missing API keys" in out
        assert "openrouter: required for openrouter/openai/gpt-4o" in out
        assert "[api] section" in out

    def test_local_model_passes(self) -> None:
        """ローカル ML モデルは API key 要求しない"""
        repository = Mock()
        repository.get_model_by_litellm_id.return_value = _fake_model("local")
        config = _fake_config({})

        _validate_required_api_keys(repository, config, ["wd-v1-4-tagger"])
        # 例外が出なければ OK

    def test_uses_db_provider_as_hint_for_migration_case(self) -> None:
        """`Model.provider` を hint として渡し、prefix と食い違う migration 経由ケースを救済。

        Phase 1.11 migration 経由で `name='openai/gpt-4o', provider='openrouter',
        litellm_model_id='openrouter/openai/gpt-4o'` の行が存在しうる。CLI 入力
        `openrouter/openai/gpt-4o` (litellm_model_id) なので prefix だけでも
        openrouter required と判定できるが、hint で `Model.provider="openrouter"`
        が渡ることで判定の SSoT が DB 側に揃う。
        """
        repository = Mock()
        repository.get_model_by_litellm_id.return_value = _fake_model("openrouter")
        config = _fake_config({"openrouter_key": "sk-or"})

        _validate_required_api_keys(repository, config, ["openrouter/openai/gpt-4o"])

    def test_multiple_models_with_multiple_missing_providers(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """複数モデルで複数 provider 不足のケースは全件列挙"""
        repository = Mock()
        # 各 litellm_id ごとに異なる Model.provider を返す
        provider_map = {
            "openai/gpt-4o": _fake_model("openai"),
            "anthropic/claude-3-5": _fake_model("anthropic"),
        }
        repository.get_model_by_litellm_id.side_effect = lambda lid: provider_map.get(lid)
        config = _fake_config({})  # 全 key 空

        with pytest.raises(typer.Exit) as excinfo:
            _validate_required_api_keys(repository, config, ["openai/gpt-4o", "anthropic/claude-3-5"])

        assert excinfo.value.exit_code == 1
        out = capsys.readouterr().out
        assert "openai: required for openai/gpt-4o" in out
        assert "anthropic: required for anthropic/claude-3-5" in out

    def test_handles_model_not_found_in_db(self) -> None:
        """DB に未登録の litellm_id でも prefix から required_provider を判定できる"""
        repository = Mock()
        repository.get_model_by_litellm_id.return_value = None
        config = _fake_config({"openai_key": "sk-a"})

        # openai/gpt-4o は openai key 有り -> 不足なし
        _validate_required_api_keys(repository, config, ["openai/gpt-4o"])
