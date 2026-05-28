"""models CLI command tests."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.commands.models import ModelCategoryFilter, ModelTypeFilter, _build_rows_from_infos
from lorairo.cli.main import app


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #245: Rich Table が Provider/Litellm ID 列を加えても全列が描画される
    十分な幅を CLI テスト環境で確保する。デフォルト 80 col では表示列が
    truncate される or Model 列が改行を挿入して substring 検証が壊れる。
    """
    monkeypatch.setenv("COLUMNS", "200")


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
    # Issue #245: models list 出力に Provider / Litellm ID 列を追加した
    provider: str | None = None
    litellm_model_id: str | None = None


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
    mock_container.annotator_library.refresh_available_models.assert_called_once_with()
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
    assert "Type" in result.stdout
    assert "local" in result.stdout
    assert "webapi" in result.stdout
    # Issue #270: default では active だけの Status 列を出さない
    assert "Status" not in result.stdout
    assert "active" not in result.stdout
    # 件数
    assert "5 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_shows_rating_models_section(mock_get_container) -> None:
    """models list default 出力では rating model を dedicated section でも表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(
            name="omni-moderation-latest",
            model_type="rating",
            is_local=False,
            is_api=True,
            provider="openai",
            litellm_model_id="openai/omni-moderation-latest",
        )
    ]
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = lambda section, key, default="": (
        "sk-test" if key == "openai_key" else default
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "Available Models" in result.stdout
    assert "Rating Models" in result.stdout
    assert "openai/omni-moderation-latest" in result.stdout


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
    """--type webapi は WebAPI モデルのみを簡潔な列で表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "webapi"])

    assert result.exit_code == 0
    assert "gpt-4o" in result.stdout
    assert "claude-3-5-sonnet" in result.stdout
    assert "wd-v1-4-tagger" not in result.stdout
    assert "Model ID" in result.stdout
    assert "Type" not in result.stdout
    assert "Category" not in result.stdout
    assert "Status" not in result.stdout
    assert "2 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_webapi_shows_gemini_when_google_key_configured(mock_get_container) -> None:
    """LiteLLM discovery の provider=Gemini は google key 設定済みなら表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(
            name="gemini/gemini-2.5-pro",
            model_type="vision",
            is_local=False,
            is_api=True,
            provider="Gemini",
            litellm_model_id="gemini/gemini-2.5-pro",
        ),
    ]
    mock_container.annotator_library.is_model_deprecated.return_value = False

    def get_setting(section: str, key: str, default: str = "") -> str:
        values = {
            ("api", "google_key"): "configured-google-key",
            ("model_selection", "route_preference"): "auto",
        }
        return values.get((section, key), default)

    mock_container.config_service.get_setting.side_effect = get_setting
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "webapi"])

    assert result.exit_code == 0
    assert "google" in result.stdout
    assert "gemini/gemini-2.5-pro" in result.stdout
    assert "missing_key" not in result.stdout
    assert "1 model(s)" in result.stdout


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
def test_models_list_filter_category_rating(mock_get_container) -> None:
    """--category rating は rating 専用モデルのみ表示する。"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(
            name="anime_rating_mobilenetv3_sce_dist",
            model_type="rating",
            is_local=True,
            is_api=False,
            device="cuda",
        ),
        _FakeAnnotatorInfo(
            name="wd-v1-4-tagger",
            model_type="tagger",
            is_local=True,
            is_api=False,
            device="cuda",
        ),
    ]
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--category", "rating"])

    assert result.exit_code == 0
    assert "anime_rating_mobilenetv3_sce_dist" in result.stdout
    assert "wd-v1-4-tagger" not in result.stdout
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
def test_models_list_include_deprecated_shows_availability(mock_get_container) -> None:
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
    assert "Availability" in result.stdout
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
    assert "active" not in result.stdout
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


# --- Issue #241: --route option / route 畳み込み ---


def _make_duplicate_route_infos() -> list[_FakeAnnotatorInfo]:
    """同一 canonical_key (gpt-4o) を direct / openrouter 2 経路で持つテスト用 infos。"""
    return [
        _FakeAnnotatorInfo(
            name="gpt-4o",
            model_type="vision",
            is_local=False,
            is_api=True,
            provider="openai",
            litellm_model_id="openai/gpt-4o",
        ),
        _FakeAnnotatorInfo(
            name="gpt-4o",
            model_type="vision",
            is_local=False,
            is_api=True,
            provider="openrouter",
            litellm_model_id="openrouter/openai/gpt-4o",
        ),
    ]


def _api_key_lookup(keys: dict[str, str]):
    """ConfigurationService.get_setting 互換 side_effect (api section のみ反応)。"""

    def _lookup(section: str, key: str, default: str = "") -> str:
        if section != "api":
            return default
        return keys.get(key, default)

    return _lookup


def _config_lookup(api_keys: dict[str, str], route_preference: str = "auto"):
    """Issue #249: api section + model_selection section の両方に反応する side_effect。"""

    def _lookup(section: str, key: str, default: str = "") -> str:
        if section == "api":
            return api_keys.get(key, default)
        if section == "model_selection" and key == "route_preference":
            return route_preference
        return default

    return _lookup


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_auto_collapses_duplicate_to_direct(mock_get_container) -> None:
    """--route auto: openai key 設定済み環境では direct route のみ表示 (1 行畳み込み)"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openai_key": "sk-openai"})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])  # default --route=auto

    assert result.exit_code == 0
    # 2 経路あったが auto で 1 行に畳まれる
    assert "1 model(s)" in result.stdout
    assert "preference=auto" in result.stdout
    # direct route が選ばれた (Route 列)
    assert "direct" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    # openrouter route の litellm_id は表示されない
    assert "openrouter/openai/gpt-4o" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_auto_falls_back_to_openrouter_when_only_openrouter_key(
    mock_get_container,
) -> None:
    """openrouter key のみ設定環境では openrouter route が preferred になる"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openrouter_key": "sk-or-x"})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "1 model(s)" in result.stdout
    # openrouter route が選ばれる
    assert "openrouter/openai/gpt-4o" in result.stdout
    assert "openrouter" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_all_expands_both_routes(mock_get_container) -> None:
    """--route all は各 candidate を 1 行ずつ展開する。

    Issue #249: 両方の key が設定済みでなければ available=False で filter される。
    本テストでは route 展開挙動のみ検証するため両 key を mock に持たせる。
    """
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup(
        {"openai_key": "sk-1", "openrouter_key": "sk-or"}
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--route", "all"])

    assert result.exit_code == 0
    assert "2 model(s)" in result.stdout
    assert "preference=all" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    assert "openrouter/openai/gpt-4o" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_direct_filters_to_direct_only(mock_get_container) -> None:
    """--route direct は direct route のみ表示。

    Issue #249: openai_key を設定しないと available=False で行が消えるため、
    direct route の表示挙動を検証するために key を入れる。
    """
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openai_key": "sk-1"})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--route", "direct"])

    assert result.exit_code == 0
    assert "1 model(s)" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    assert "openrouter/openai/gpt-4o" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_openrouter_filters_to_openrouter_only(mock_get_container) -> None:
    """--route openrouter は openrouter route のみ表示。

    Issue #249: openrouter_key を設定しないと available=False で行が消えるため、
    openrouter route の表示挙動を検証するために key を入れる。
    """
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openrouter_key": "sk-or"})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--route", "openrouter"])

    assert result.exit_code == 0
    assert "1 model(s)" in result.stdout
    assert "openrouter/openai/gpt-4o" in result.stdout


# --- Issue #249: --show-unavailable / config 由来 default ---


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_show_unavailable_displays_missing_key_rows(mock_get_container) -> None:
    """--show-unavailable は API key 未設定の行を Availability で表示する"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--show-unavailable"])

    assert result.exit_code == 0
    # 全 row が disabled でも表示される
    assert "1 model(s)" in result.stdout
    assert "Availability" in result.stdout
    assert "missing_key" in result.stdout
    assert "unavailable=1" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_show_unavailable_with_route_all(mock_get_container) -> None:
    """--show-unavailable + --route all で全 candidate を missing_key 状態で表示"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--route", "all", "--show-unavailable"])

    assert result.exit_code == 0
    assert "2 model(s)" in result.stdout
    assert "missing_key" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    assert "openrouter/openai/gpt-4o" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_default_reads_from_config(mock_get_container) -> None:
    """--route 未指定時は config の model_selection.route_preference を default として使う"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    # config に "direct" を入れる、両方の key を available にして filter で消えないようにする
    mock_container.config_service.get_setting.side_effect = _config_lookup(
        {"openai_key": "sk-1", "openrouter_key": "sk-or"},
        route_preference="direct",
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])  # --route 未指定

    assert result.exit_code == 0
    # config 値 "direct" が default として効く
    assert "preference=direct from config" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    # openrouter route は preference=direct で除外される
    assert "openrouter/openai/gpt-4o" not in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_explicit_route_overrides_config(mock_get_container) -> None:
    """--route 明示指定は config 値を上書きする (preference_source=explicit)"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _config_lookup(
        {"openai_key": "sk-1"},
        route_preference="openrouter",  # config では openrouter
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--route", "direct"])

    assert result.exit_code == 0
    # 明示指定 "direct" が config 値 "openrouter" を上書き
    assert "preference=direct from explicit" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_route_invalid_config_falls_back_to_auto(mock_get_container) -> None:
    """config の route_preference が不正値の場合 'auto' に fallback"""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _config_lookup(
        {"openai_key": "sk-1"},
        route_preference="bogus_value",
    )
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    # 不正値は auto fallback
    assert "preference=auto from config" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_long_model_names_keep_columns_visible(mock_get_container) -> None:
    """長いモデル ID でも主要カラムが collapse されない (Issue #220/#270 regression)."""
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

    # Issue #249: webapi モデルの provider が None だと available=False で filter される。
    # 本テストは表示列の collapse 防止 (Issue #220) を検証するため --show-unavailable で
    # 表示自体を保証する。
    result = runner.invoke(app, ["models", "list", "--show-unavailable"])

    assert result.exit_code == 0
    # 主要列が空 collapse せずに描画されること
    assert "Provider" in result.stdout
    assert "Route" in result.stdout
    assert "Model ID" in result.stdout
    assert "Availability" in result.stdout
    # Type 値 (webapi/local) が空 collapse せずに描画されること
    assert "webapi" in result.stdout
    assert "local" in result.stdout
    # Category 値 (vision/tagger) が空 collapse せずに描画されること
    assert "vision" in result.stdout
    assert "tagger" in result.stdout
    # ローカルモデルは ready、webapi は key 未設定で missing_key 表示
    assert "ready" in result.stdout
    assert "missing_key" in result.stdout
    assert "2 model(s)" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
def test_models_list_rows_use_shared_identity_for_display_metadata() -> None:
    """CLI row 生成も GUI と同じ identity 解析を使う。"""
    infos = [
        _FakeAnnotatorInfo(
            name="GPT-4o Vision",
            model_type="vision",
            is_local=False,
            is_api=True,
            provider="openai",
            litellm_model_id="gpt-4o",
        ),
        _FakeAnnotatorInfo(
            name="some/very/deep/namespace/local-tagger",
            model_type="tagger",
            is_local=True,
            is_api=False,
            device="cuda",
        ),
    ]
    annotator = MagicMock()
    annotator.is_model_deprecated.return_value = False

    rows = _build_rows_from_infos(
        infos=infos,
        type_filter=ModelTypeFilter.all,
        category=ModelCategoryFilter.all,
        include_deprecated=False,
        annotator=annotator,
        available_providers={"openai"},
    )

    assert rows[0]["display_name"] == "GPT-4o Vision"
    assert rows[0]["display_family"] == "OpenAI"
    assert rows[0]["required_provider"] == "openai"
    assert rows[0]["available"] is True
    assert rows[1]["display_name"] == "some/very/deep/namespace/local-tagger"
    assert rows[1]["display_family"] == "local"
    assert rows[1]["required_provider"] == "local"
    assert rows[1]["available"] is True


# --- Issue #253: 0 件 hint + DEBUG diagnostic ---


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_zero_count_hint_when_no_api_keys_loaded(mock_get_container) -> None:
    """Issue #253 シナリオ A: API key 全空 + show_unavailable 無で 0 件 → 中立 hint を出す."""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "webapi", "--route", "auto"])

    assert result.exit_code == 0
    assert "0 model(s)" in result.stdout
    # 中立的な文言: "No API keys are configured" のような断定ではない
    assert "No API keys were loaded from config" in result.stdout
    assert "--show-unavailable" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_zero_count_hint_when_filters_eliminate_all(mock_get_container) -> None:
    """Issue #253 シナリオ B: API key 設定済みだが filter で 0 件 → 'No models matched' hint."""
    # ローカルモデルのみ。--type webapi で 0 件
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = [
        _FakeAnnotatorInfo(
            name="wd-v1-4-tagger", model_type="tagger", is_local=True, is_api=False, device="cuda"
        ),
    ]
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openai_key": "sk-openai"})
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--type", "webapi"])

    assert result.exit_code == 0
    assert "0 model(s)" in result.stdout
    assert "No models matched the current filters" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_zero_count_hint_with_show_unavailable_empty_registry(mock_get_container) -> None:
    """Issue #253 シナリオ C: show_unavailable=True でも 0 件 → 'No entries in registry' hint."""
    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = []
    mock_get_container.return_value = mock_container

    result = runner.invoke(app, ["models", "list", "--show-unavailable"])

    assert result.exit_code == 0
    assert "0 model(s)" in result.stdout
    assert "No entries in the registry" in result.stdout
    assert "models refresh" in result.stdout


@pytest.mark.unit
@pytest.mark.cli
@patch("lorairo.cli.commands.models.get_service_container")
def test_models_list_diagnostic_log_includes_config_and_key_status(mock_get_container) -> None:
    """Issue #253: DEBUG diagnostic に config_path + per-provider key loaded 状況が含まれる.

    loguru sink を StringIO に追加して capture する (conftest にブリッジ helper が
    無いため、本 test 内で自己完結する方式を採用)。
    """
    from io import StringIO

    from loguru import logger as loguru_logger

    mock_container = MagicMock()
    mock_container.annotator_library.list_annotator_info.return_value = _make_duplicate_route_infos()
    mock_container.annotator_library.is_model_deprecated.return_value = False
    mock_container.config_service.get_setting.side_effect = _api_key_lookup({"openai_key": "sk-openai"})
    # MagicMock では _config_path が無いので DEFAULT_CONFIG_PATH fallback (<default: ...>) になる前提
    mock_get_container.return_value = mock_container

    buffer = StringIO()
    handler_id = loguru_logger.add(buffer, format="{message}", level="DEBUG")
    try:
        result = runner.invoke(app, ["models", "list", "--show-unavailable"])
    finally:
        loguru_logger.remove(handler_id)

    assert result.exit_code == 0
    log_output = buffer.getvalue()
    assert "models list diagnostic" in log_output
    assert "config_path=" in log_output
    assert "openai_key_loaded': True" in log_output or "openai_key_loaded=True" in log_output
    assert "claude_key_loaded': False" in log_output or "claude_key_loaded=False" in log_output
    # key 値そのものは出ていないこと (security 要件)
    assert "sk-openai" not in log_output
