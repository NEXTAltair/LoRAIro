"""CLI モデル識別子の解決ロジック単体テスト (Issue #245)。

`_resolve_model_identifier()` が litellm_model_id / name / 曖昧 / 不明 の
4 パターンを正しく扱うことを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import click
import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.commands.annotate import _resolve_model_identifier
from lorairo.cli.main import app
from lorairo.services.annotation_save_service import AnnotationSaveResult


def _fake_model(
    litellm_model_id: str,
    name: str,
    provider: str | None = None,
    *,
    available: bool = True,
    requires_api_key: bool | None = None,
) -> SimpleNamespace:
    """`Model` 互換の軽量 fake。"""
    return SimpleNamespace(
        litellm_model_id=litellm_model_id,
        name=name,
        provider=provider,
        requires_api_key=(provider or "").strip().lower() not in {"", "local"}
        if requires_api_key is None
        else requires_api_key,
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
            _fake_model("openai/gpt-4o", "gpt-4o", "openai"),
            _fake_model("openrouter/openai/gpt-4o", "gpt-4o", "openrouter"),
        ]

        with pytest.raises(click.UsageError) as excinfo:
            _resolve_model_identifier(repository, "gpt-4o")

        out = excinfo.value.message
        assert "Ambiguous model 'gpt-4o'" in out
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

    @pytest.mark.parametrize(
        "provider",
        ["openai", "anthropic", "google", "gemini", "vertex_ai", "openrouter", "vercel_ai_gateway"],
    )
    def test_explicit_provider_id_cannot_fall_back_to_name(self, repository, provider):
        identifier = f"{provider}/missing"
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = [
            _fake_model(f"openrouter/{identifier}", identifier, "openrouter")
        ]
        with pytest.raises(click.UsageError, match="must match exactly"):
            _resolve_model_identifier(repository, identifier)
        repository.get_models_by_name.assert_called_once_with(identifier)

    @pytest.mark.parametrize(
        "display_name", ["SmilingWolf/wd-tagger", "google/siglip-so400m", "openai/clip-vit-large-patch14"]
    )
    @pytest.mark.parametrize(
        "local_provider",
        [None, "", "local", "LOCAL", " local ", "SmilingWolf", "cafe", "xinntao", "esrgan"],
    )
    def test_local_namespace_display_name_still_resolves(self, repository, display_name, local_provider):
        repository.get_model_by_litellm_id.return_value = None
        repository.get_models_by_name.return_value = [
            _fake_model("local-classifier", display_name, local_provider, requires_api_key=False)
        ]
        assert _resolve_model_identifier(repository, display_name) == "local-classifier"


@pytest.fixture
def cli_route_flow(monkeypatch, tmp_path):
    """Exercise the real CLI run and image-loading paths with only DB/API calls mocked."""
    image_path = tmp_path / "processed.png"
    Image.new("RGB", (8, 8)).save(image_path)
    record = {"id": 1, "phash": "hash", "stored_image_path": str(image_path)}
    container = Mock()
    repo = container.db_manager.model_repo
    repo.get_model_by_litellm_id.return_value = None
    image_repo = container.db_manager.image_repo
    image_repo.get_existing_image_ids.return_value = [1]
    image_repo.get_candidate_image_ids.return_value = [1]
    image_repo.get_images_by_ids.return_value = [record]
    image_repo.get_images_by_filter.return_value = ([record], 1)
    container.config_service.get_setting.side_effect = lambda section, key, default="": (
        "mock-key" if key.endswith("key") else default
    )
    container.annotator_library.is_model_deprecated.return_value = False
    container.annotator_library.annotate.return_value = {"hash": {"result": {"tags": ["test"]}}}
    container.annotation_save_service.save_annotation_results.return_value = AnnotationSaveResult(
        success_count=1, error_count=0, skip_count=0, total_count=1
    )
    monkeypatch.setattr("lorairo.cli.commands.annotate.api_get_project", Mock())
    monkeypatch.setattr("lorairo.cli.commands.annotate.get_service_container", lambda: container)
    monkeypatch.setattr("lorairo.cli.commands.annotate.selection_includes_webapi_model", lambda *_: False)
    monkeypatch.setattr(
        "lorairo.services.model_registry_protocol.selection_includes_webapi_model", lambda *_: False
    )
    return container


@pytest.mark.parametrize("explicit_images", [False, True])
@pytest.mark.parametrize("identifier", ["openai/gpt-4o", "vercel_ai_gateway/openai/o1"])
@pytest.mark.parametrize("requires_api_key", [False, True])
def test_cli_explicit_missing_id_fails_before_image_or_api_calls(
    cli_route_flow, explicit_images, requires_api_key, identifier
):
    container = cli_route_flow
    container.db_manager.model_repo.get_models_by_name.return_value = [
        _fake_model("openrouter/openai/gpt-4o", identifier, "openrouter", requires_api_key=requires_api_key)
    ]
    args = ["annotate", "run", "--project", "mock-project", "--model", identifier]
    if explicit_images:
        args += ["--image-id", "1"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert "must match exactly" in " ".join(result.output.split())
    container.db_manager.image_repo.get_images_by_filter.assert_not_called()
    container.db_manager.image_repo.get_images_by_ids.assert_not_called()
    container.annotator_library.annotate.assert_not_called()
    container.annotation_save_service.save_annotation_results.assert_not_called()


@pytest.mark.parametrize(
    "identifier,resolved,provider,exact",
    [
        ("openrouter/openai/gpt-4o", "openrouter/openai/gpt-4o", "openrouter", True),
        ("gpt-4o", "openrouter/openai/gpt-4o", "openrouter", False),
        ("Curated/Caption Model", "openrouter/openai/gpt-4o", "openrouter", False),
        ("SmilingWolf/wd-tagger", "wd-tagger", "local", False),
        ("google/siglip-so400m", "local-siglip", "local", False),
        ("google/siglip-so400m", "local-siglip", None, False),
        ("google/siglip-so400m", "local-siglip", "", False),
        ("google/siglip-so400m", "local-siglip", "LOCAL", False),
        ("google/siglip-so400m", "local-siglip", " local ", False),
        ("openai/clip-vit-large-patch14", "local-clip", "local", False),
        ("vercel_ai_gateway/local-classifier", "local-classifier", "local", False),
    ],
)
def test_cli_resolves_legitimate_identifier_and_sends_exact_target(
    cli_route_flow, identifier, resolved, provider, exact
):
    container = cli_route_flow
    model = _fake_model(resolved, identifier, provider)
    container.db_manager.model_repo.get_model_by_litellm_id.side_effect = lambda mid: (
        model if mid == resolved and (exact or mid != identifier) else None
    )
    container.db_manager.model_repo.get_models_by_name.return_value = [model]
    result = CliRunner().invoke(
        app, ["annotate", "run", "--project", "mock-project", "--model", identifier, "--image-id", "1"]
    )
    assert result.exit_code == 0, result.output
    assert container.annotator_library.annotate.call_args.kwargs["litellm_model_ids"] == [resolved]
    container.annotation_save_service.save_annotation_results.assert_called_once()


@pytest.mark.parametrize(
    "identifier,resolved,provider",
    [
        ("wd-vit-large-tagger-v3", "wd-vit-large-tagger-v3", "SmilingWolf"),
        ("cafe_aesthetic", "cafe_aesthetic", "cafe"),
        ("classification_ViT-L-14_openai", "classification_ViT-L-14_openai", "openai"),
        ("openai/clip-vit-large-patch14", "classification_ViT-L-14_openai", "openai"),
        ("google/siglip-so400m", "google/siglip-so400m", None),
        ("openai/clip-vit-large-patch14", "openai/clip-vit-large-patch14", "local"),
        *[
            (identifier, "local-classifier", provider)
            for identifier in ("google/siglip-so400m", "openai/clip-vit-large-patch14")
            for provider in ("SmilingWolf", "cafe", "xinntao", "esrgan")
        ],
    ],
)
def test_cli_keyless_vendor_local_models_execute_without_any_api_key(
    cli_route_flow, identifier, resolved, provider
):
    container = cli_route_flow
    model = _fake_model(resolved, identifier, provider, requires_api_key=False)
    container.db_manager.model_repo.get_model_by_litellm_id.side_effect = lambda mid: (
        model if mid == resolved else None
    )
    container.db_manager.model_repo.get_models_by_name.return_value = [model]
    container.config_service.get_setting.side_effect = lambda section, key, default="": default
    result = CliRunner().invoke(
        app, ["annotate", "run", "--project", "mock-project", "--model", identifier, "--image-id", "1"]
    )
    assert result.exit_code == 0, result.output
    assert container.annotator_library.annotate.call_args.kwargs["litellm_model_ids"] == [resolved]
    container.annotation_save_service.save_annotation_results.assert_called_once()


@pytest.mark.parametrize("requires_api_key", [False, True])
def test_cli_qualified_cloud_model_still_requires_its_key_before_api_call(cli_route_flow, requires_api_key):
    container = cli_route_flow
    model_id = "openrouter/openai/gpt-4o"
    model = _fake_model(model_id, "gpt-4o", "openrouter", requires_api_key=requires_api_key)
    container.db_manager.model_repo.get_model_by_litellm_id.return_value = model
    container.config_service.get_setting.side_effect = lambda section, key, default="": default
    result = CliRunner().invoke(
        app, ["annotate", "run", "--project", "mock-project", "--model", model_id, "--image-id", "1"]
    )
    assert result.exit_code == 2, result.output
    assert "Missing API keys" in " ".join(result.output.split())
    container.annotator_library.annotate.assert_not_called()
    container.annotation_save_service.save_annotation_results.assert_not_called()


def test_cli_ambiguous_display_name_stops_before_api_call(cli_route_flow):
    container = cli_route_flow
    container.db_manager.model_repo.get_models_by_name.return_value = [
        _fake_model("openai/gpt-4o", "gpt-4o", "openai"),
        _fake_model("openrouter/openai/gpt-4o", "gpt-4o", "openrouter"),
    ]
    result = CliRunner().invoke(app, ["annotate", "run", "--project", "mock-project", "--model", "gpt-4o"])
    assert result.exit_code == 2
    assert "Ambiguous model" in result.output
    container.annotator_library.annotate.assert_not_called()


@pytest.mark.parametrize(
    "providers", [("local", "local"), ("local", "openrouter"), ("openai", "openrouter")]
)
def test_cli_provider_namespace_name_with_multiple_matches_stops_before_api_call(cli_route_flow, providers):
    container = cli_route_flow
    container.db_manager.model_repo.get_models_by_name.return_value = [
        _fake_model("first-target", "openai/gpt-4o", providers[0]),
        _fake_model("second-target", "openai/gpt-4o", providers[1]),
    ]
    result = CliRunner().invoke(
        app, ["annotate", "run", "--project", "mock-project", "--model", "openai/gpt-4o", "--image-id", "1"]
    )
    assert result.exit_code == 2
    assert "Ambiguous model" in result.output
    container.annotator_library.annotate.assert_not_called()
