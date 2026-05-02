"""models CLI command tests."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


@dataclass(frozen=True)
class _FakeAnnotatorInfo:
    """テスト用 AnnotatorInfo ダミー (実体と同等のフィールドを持つ frozen dataclass)。"""

    name: str
    model_type: str
    is_local: bool
    is_api: bool
    capabilities: frozenset = field(default_factory=frozenset)
    device: str | None = None


def _make_infos() -> list[_FakeAnnotatorInfo]:
    """ローカル / WebAPI / 各 model_type を網羅したテスト用モデル群。"""
    return [
        _FakeAnnotatorInfo(
            name="wd-v1-4-tagger", model_type="tagger", is_local=True, is_api=False, device="cuda"
        ),
        _FakeAnnotatorInfo(
            name="aesthetic-predictor", model_type="scorer", is_local=True, is_api=False, device="cuda"
        ),
        _FakeAnnotatorInfo(
            name="blip-large", model_type="captioner", is_local=True, is_api=False, device="cpu"
        ),
        _FakeAnnotatorInfo(name="gpt-4o", model_type="vision", is_local=False, is_api=True),
        _FakeAnnotatorInfo(name="claude-3-5-sonnet", model_type="vision", is_local=False, is_api=True),
    ]


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
def test_models_refresh_fails_when_db_sync_reports_errors(mock_get_container) -> None:
    """models refresh はDB同期エラー時に非ゼロ終了する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.refresh_available_models.return_value = ["openai/gpt-4.1-mini"]
    mock_container.model_sync_service.sync_available_models.return_value.summary = (
        "同期完了: ライブラリモデル 1件, エラー 1件"
    )
    mock_container.model_sync_service.sync_available_models.return_value.errors = [
        "failed to update model table"
    ]
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "refresh"])

    assert result.exit_code == 1
    assert "DB sync failed" in result.stdout
    assert "failed to update model table" in result.stdout
    assert "Model registry refreshed." not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_shows_local_and_webapi_with_type_column(mock_get_container) -> None:
    """models list はローカルと WebAPI 両方を表示し、Type カラムで区別する (Issue #220)."""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    mock_container.annotator_library.list_annotator_info.assert_called_once_with()
    # ローカルモデルが表示されること (Issue #220 の主要要求)
    assert "wd-v1-4-tagger" in result.stdout
    assert "aesthetic-predictor" in result.stdout
    # WebAPI モデルも表示されること
    assert "gpt-4o" in result.stdout
    assert "claude-3-5-sonnet" in result.stdout
    # Type カラムの値
    assert "local" in result.stdout
    assert "webapi" in result.stdout
    # 件数
    assert "5 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_filter_type_local_only(mock_get_container) -> None:
    """--type local はローカルモデルのみ表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "local"])

    assert result.exit_code == 0
    assert "wd-v1-4-tagger" in result.stdout
    assert "aesthetic-predictor" in result.stdout
    assert "blip-large" in result.stdout
    assert "gpt-4o" not in result.stdout
    assert "claude-3-5-sonnet" not in result.stdout
    assert "3 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_filter_type_webapi_only(mock_get_container) -> None:
    """--type webapi は WebAPI モデルのみ表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "webapi"])

    assert result.exit_code == 0
    assert "gpt-4o" in result.stdout
    assert "claude-3-5-sonnet" in result.stdout
    assert "wd-v1-4-tagger" not in result.stdout
    assert "2 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_filter_category_tagger(mock_get_container) -> None:
    """--category tagger は tagger モデルのみ表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--category", "tagger"])

    assert result.exit_code == 0
    assert "wd-v1-4-tagger" in result.stdout
    assert "aesthetic-predictor" not in result.stdout
    assert "gpt-4o" not in result.stdout
    assert "1 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_filter_combines_type_and_category(mock_get_container) -> None:
    """--type local --category scorer はローカル scorer のみ表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "local", "--category", "scorer"])

    assert result.exit_code == 0
    assert "aesthetic-predictor" in result.stdout
    assert "wd-v1-4-tagger" not in result.stdout
    assert "gpt-4o" not in result.stdout
    assert "1 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_excludes_deprecated_by_default(mock_get_container) -> None:
    """デフォルトでは deprecated モデルを除外する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(name="gpt-4o", model_type="vision", is_local=False, is_api=True),
        _FakeAnnotatorInfo(name="gpt-4-vision-preview", model_type="vision", is_local=False, is_api=True),
    ]
    mock_container.annotator_library.is_model_deprecated.side_effect = lambda model_name: (
        model_name == "gpt-4-vision-preview"
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "gpt-4o" in result.stdout
    assert "gpt-4-vision-preview" not in result.stdout
    assert "1 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_include_deprecated_shows_status(mock_get_container) -> None:
    """--include-deprecated は廃止済みモデルも表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(name="gpt-4o", model_type="vision", is_local=False, is_api=True),
        _FakeAnnotatorInfo(name="gpt-4-vision-preview", model_type="vision", is_local=False, is_api=True),
    ]
    mock_container.annotator_library.is_model_deprecated.side_effect = lambda model_name: (
        model_name == "gpt-4-vision-preview"
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--include-deprecated"])

    assert result.exit_code == 0
    assert "gpt-4o" in result.stdout
    assert "gpt-4-vision-preview" in result.stdout
    assert "deprecated" in result.stdout
    assert "2 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_invalid_type_exits_with_error(mock_get_container) -> None:
    """--type に不正値を指定すると typer が exit_code=2 で拒否する。"""
    mock_get_container.return_value = MagicMock()

    result = runner.invoke(app, ["models", "list", "--type", "bogus"])

    assert result.exit_code == 2
    mock_get_container.return_value.annotator_library.list_annotator_info.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_handles_deprecated_check_failure(mock_get_container) -> None:
    """is_model_deprecated 例外時は deprecated=False として継続する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(name="gpt-4o", model_type="vision", is_local=False, is_api=True),
    ]
    mock_container.annotator_library.is_model_deprecated.side_effect = RuntimeError("network down")
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "gpt-4o" in result.stdout
    assert "active" in result.stdout
    assert "1 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_empty_registry_returns_zero(mock_get_container) -> None:
    """registry が空のとき 0件で正常終了する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = []
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "0 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_long_model_names_keep_columns_visible(mock_get_container) -> None:
    """長いモデル名でも Type/Category/Status カラムが collapse されない (Issue #220 表示バグ regression)."""
    long_infos = [
        _FakeAnnotatorInfo(
            name="vercel_ai_gateway/openai/o1-very-long-model-name-2025-04-16",
            model_type="vision",
            is_local=False,
            is_api=True,
        ),
        _FakeAnnotatorInfo(
            name="some/very/deep/namespace/local-tagger-with-extremely-long-identifier-v3.5.2",
            model_type="tagger",
            is_local=True,
            is_api=False,
            device="cuda",
        ),
    ]
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = long_infos
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    # Type 値 (webapi/local) が空 collapse せずに描画されること
    assert "webapi" in result.stdout
    assert "local" in result.stdout
    # Category 値 (vision/tagger) が空 collapse せずに描画されること
    assert "vision" in result.stdout
    assert "tagger" in result.stdout
    # Status 値 (active) が空 collapse せずに描画されること
    assert "active" in result.stdout
    assert "2 model(s)" in result.stdout
