"""OS user overrides never rewrite a shared bind-mounted project config."""

from pathlib import Path

import pytest
import toml
from platformdirs import user_config_path, user_log_path

from lorairo.services.configuration_service import ConfigurationService
from lorairo.utils import config


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    shared = tmp_path / "checkout" / "config" / "lorairo.toml"
    user = tmp_path / "windows-user" / "lorairo.toml"
    shared.parent.mkdir(parents=True)
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", shared)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", user)
    return shared, user


def write_settings(path: Path, **settings):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(toml.dumps({"directories": {}, **settings}), encoding="utf-8")


def test_project_user_precedence_and_explicit_file_isolation(isolated_paths):
    shared, user = isolated_paths
    write_settings(shared, log={"level": "DEBUG"}, annotation_review={"n_gpu_layers": 4})
    write_settings(user, annotation_review={"n_gpu_layers": 12, "server_path": "C:/local/llama.exe"})
    before = shared.read_bytes()

    merged = config.get_config()
    assert merged["log"]["level"] == "DEBUG"
    assert merged["annotation_review"]["n_gpu_layers"] == 12
    assert merged["annotation_review"]["server_path"] == "C:/local/llama.exe"
    assert config.get_config(shared)["annotation_review"]["n_gpu_layers"] == 4
    assert config.get_config(shared)["annotation_review"]["server_path"] == ""
    assert shared.read_bytes() == before


def test_first_run_and_repeated_save_leave_project_and_other_os_user_untouched(
    isolated_paths, tmp_path, monkeypatch
):
    shared, windows_user = isolated_paths
    write_settings(shared, log={"level": "DEBUG"})
    before = shared.read_bytes()
    windows = ConfigurationService()
    assert windows.get_setting("log", "level") == "DEBUG"
    assert toml.load(windows_user) == {"directories": {}}
    windows.update_setting("annotation_review", "server_path", "C:/local/llama.exe")
    assert windows.save_settings()
    windows_saved = windows_user.read_bytes()

    linux_user = tmp_path / "linux-user" / "lorairo.toml"
    monkeypatch.setattr(config, "USER_CONFIG_PATH", linux_user)
    linux = ConfigurationService()
    assert linux.get_setting("annotation_review", "server_path") == ""
    linux.update_setting("annotation_review", "server_path", "/usr/local/bin/llama-server")
    assert linux.save_settings()
    assert ConfigurationService().get_setting("annotation_review", "server_path") == (
        "/usr/local/bin/llama-server"
    )
    assert windows_user.read_bytes() == windows_saved
    assert shared.read_bytes() == before


@pytest.mark.parametrize(
    "absolute_path", ["H:/models/private-model", "/opt/private-model", "\\\\host\\share\\model"]
)
def test_legacy_absolute_shared_paths_require_explicit_migration(isolated_paths, absolute_path):
    shared, user = isolated_paths
    write_settings(
        shared,
        annotation_review={"model_path": absolute_path, "n_gpu_layers": 3},
        upscaler_models=[{"name": "legacy", "path": absolute_path, "scale": 4.0}],
    )
    before = shared.read_bytes()
    with pytest.warns(RuntimeWarning, match="Move OS-specific settings explicitly") as warnings:
        settings = config.get_config()
    assert absolute_path not in str(warnings[0].message)
    assert settings["annotation_review"]["model_path"] == ""
    assert settings["annotation_review"]["n_gpu_layers"] == 3
    assert settings["upscaler_models"] == config.DEFAULT_CONFIG["upscaler_models"]
    assert config.get_config(shared)["annotation_review"]["model_path"] == absolute_path
    assert not user.exists()
    assert shared.read_bytes() == before


def test_explicit_service_path_preserves_portable_api(isolated_paths, tmp_path):
    shared, user = isolated_paths
    explicit = tmp_path / "portable" / "lorairo.toml"
    service = ConfigurationService(config_path=explicit)
    service.update_setting("annotation_review", "model_path", "H:/models/user-model")
    assert service.save_settings()
    assert toml.load(explicit)["annotation_review"]["model_path"] == "H:/models/user-model"
    assert not shared.exists()
    assert not user.exists()


def test_default_config_writers_use_user_path_and_preserve_shared_defaults(isolated_paths):
    shared, user = isolated_paths
    write_settings(shared, log={"level": "DEBUG"})
    before = shared.read_bytes()
    assert config.ensure_config_file()["log"]["level"] == "DEBUG"
    assert toml.load(user) == {"directories": {}}
    config.write_config_file({"directories": {}, "log": {"level": "ERROR"}})
    assert config.ensure_config_file()["log"]["level"] == "ERROR"
    assert shared.read_bytes() == before


def test_default_paths_use_platformdirs_outside_the_checkout():
    assert config.DEFAULT_LOG_PATH == user_log_path("LoRAIro", appauthor=False) / "lorairo.log"
    assert config.DEFAULT_CLI_LOG_PATH.parent == config.DEFAULT_LOG_PATH.parent
    assert not config.DEFAULT_LOG_PATH.is_relative_to(config.PROJECT_ROOT)
    assert user_config_path("LoRAIro", appauthor=False).is_absolute()


def test_workspace_uses_local_preferences_without_importing_user_data_directories(isolated_paths, tmp_path):
    _, user = isolated_paths
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(
        toml.dumps(
            {
                "directories": {"database_base_dir": "H:/private/real-data"},
                "annotation_review": {"n_gpu_layers": 99},
                "api": {"openai_key": "local-test-key"},
            }
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    runtime = config.resolve_runtime_configuration(workspace, None)
    with config.runtime_configuration_scope(runtime):
        service = ConfigurationService()
        assert service.get_setting("annotation_review", "n_gpu_layers") == 99
        assert service.get_setting("api", "openai_key") == "local-test-key"
        assert Path(service.get_setting("directories", "database_base_dir")) == workspace / "lorairo_data"
        assert service._config_path == workspace / "config" / "lorairo.toml"
    assert not (workspace / "config").exists()


def test_explicit_runtime_config_remains_independent_of_user_preferences(isolated_paths, tmp_path):
    _, user = isolated_paths
    write_settings(user, api={"openai_key": "local-test-key"}, annotation_review={"n_gpu_layers": 99})
    explicit = tmp_path / "portable.toml"
    write_settings(explicit, annotation_review={"n_gpu_layers": 2})
    runtime = config.resolve_runtime_configuration(tmp_path / "workspace", explicit)
    with config.runtime_configuration_scope(runtime):
        service = ConfigurationService()
        assert service.get_setting("annotation_review", "n_gpu_layers") == 2
        assert service.get_setting("api", "openai_key") == ""
