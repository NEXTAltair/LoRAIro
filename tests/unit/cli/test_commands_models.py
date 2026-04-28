"""models CLI command tests."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_refresh_updates_registry(mock_get_container) -> None:
    """models refresh は registry refresh とDB同期を実行する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.refresh_available_models.return_value = [
        "openai/gpt-4.1-mini",
        "google/gemini-2.5-pro",
    ]
    mock_container.model_sync_service.sync_available_models.return_value.summary = (
        "同期完了: ライブラリモデル 2件"
    )
    mock_container.model_sync_service.sync_available_models.return_value.errors = []
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "refresh"])

    assert result.exit_code == 0
    mock_container.annotator_library.refresh_available_models.assert_called_once_with(force_refresh=True)
    mock_container.model_sync_service.sync_available_models.assert_called_once()
    assert "Model registry refreshed" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_excludes_deprecated_by_default(mock_get_container) -> None:
    """models list はデフォルトで active モデルだけを表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_available_models.return_value = ["openai/gpt-4.1-mini"]
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    mock_container.annotator_library.list_available_models.assert_called_once_with(include_deprecated=False)
    assert "openai/gpt-4.1-mini" in result.stdout
    assert "active" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_include_deprecated_shows_status(mock_get_container) -> None:
    """--include-deprecated は廃止済みモデルも表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_available_models.return_value = [
        "openai/gpt-4.1-mini",
        "openai/gpt-4-vision-preview",
    ]
    mock_container.annotator_library.is_model_deprecated.side_effect = lambda model_name: (
        model_name == "openai/gpt-4-vision-preview"
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--include-deprecated"])

    assert result.exit_code == 0
    mock_container.annotator_library.list_available_models.assert_called_once_with(include_deprecated=True)
    assert "openai/gpt-4-vision-preview" in result.stdout
    assert "deprecated" in result.stdout
