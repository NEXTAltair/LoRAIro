import os
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import toml
from platformdirs import user_config_path, user_log_path


# Test isolation: Use temp directory for tests, actual project root otherwise
def get_project_root() -> Path:
    """Get project root path, with test isolation support."""
    # Check if we're running in pytest environment
    if "PYTEST_CURRENT_TEST" in os.environ:
        # Use a temp directory for tests to avoid creating files in src/
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "lorairo_test"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

    # For normal execution, use the actual project root (parent of src directory)
    current_file = Path(__file__)  # src/lorairo/utils/config.py
    project_root = current_file.parent.parent.parent.parent  # Go up 4 levels to project root
    return project_root


PROJECT_ROOT = get_project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "lorairo.toml"
# Project configuration is a portable, read-only layer. Mutable preferences and
# logs belong to the current OS user, outside a bind-mounted checkout.
USER_CONFIG_PATH = (
    Path(os.environ["LORAIRO_CONFIG_HOME"]).expanduser().resolve()
    if os.environ.get("LORAIRO_CONFIG_HOME")
    else user_config_path("LoRAIro", appauthor=False)
) / "lorairo.toml"
DEFAULT_LOG_PATH = user_log_path("LoRAIro", appauthor=False) / "lorairo.log"
DEFAULT_CLI_LOG_PATH = DEFAULT_LOG_PATH.with_name("lorairo-cli.log")


def get_user_config_path() -> Path:
    """Return the mutable OS user config; never migrate shared legacy files implicitly."""
    return USER_CONFIG_PATH


# Runtime defaults used after merging user configuration.
# Keep this as the single source of truth for default configuration values.
# The first-run config file is generated from a user-facing subset of this dict.
DEFAULT_CONFIG = {
    "api": {
        "openai_key": "",
        "claude_key": "",
        "google_key": "",
        "openrouter_key": "",
    },
    "directories": {
        "database_dir": "",  # 空文字列 = 自動生成 (日付+連番プロジェクト)
        "database_base_dir": "lorairo_data",  # 自動生成時のベースディレクトリ名
        "database_project_name": "main_dataset",  # 自動生成時のデフォルトプロジェクト名
        "export_dir": "export",  # 学習用データセットの出力先（.txt/.captionファイル等）
        "batch_results_dir": "batch_results",  # OpenAI Batch API結果JSONLファイルの保存先
    },
    "image_processing": {
        "upscaler": "RealESRGAN_x4plus",  # デフォルトアップスケーラー名
    },
    "upscaler_models": [
        {
            "name": "RealESRGAN_x4plus",
            "path": "models/RealESRGAN/RealESRGAN_x4plus.pth",
            "scale": 4.0,
        },
        {
            "name": "RealESRGAN_x4plus_anime_6B",
            "path": "models/RealESRGAN/RealESRGAN_x4plus_anime_6B.pth",
            "scale": 4.0,
        },
    ],
    "prompts": {"additional": ""},
    "annotation_review": {
        "model": "clef-flash",
        "server_path": "",
        "model_path": "",
        "mmproj_path": "",
        "n_gpu_layers": 10,
        "context_size": 4096,
        # Probability the candidate is supported by the image; warning iff p < threshold.
        "warning_threshold": 0.2,
        # Candidate suggestions are actionable iff p >= this threshold.
        "suggestion_threshold": 0.8,
        "timeout": 300.0,
    },
    "text_extensions": [".txt", ".caption"],
    "preferred_resolutions": [
        # 512 Base
        (336, 784),  # 9:21
        (384, 680),  # 9:16
        (416, 624),  # 2:3
        (440, 592),  # 3:4
        (456, 576),  # 4:5
        (512, 512),  # 1:1
        (576, 456),  # 5:4
        (592, 440),  # 4:3
        (624, 416),  # 3:2
        (680, 384),  # 16:9
        (784, 336),  # 21:9
        # 768 Base
        (504, 1176),  # 9:21
        (576, 1024),  # 9:16
        (624, 944),  # 2:3
        (664, 888),  # 3:4
        (688, 856),  # 4:5
        (768, 768),  # 1:1
        (856, 688),  # 5:4
        (888, 664),  # 4:3
        (944, 624),  # 3:2
        (1024, 576),  # 16:9
        (1176, 504),  # 21:9
        # 1024 Base
        (672, 1568),  # 9:21
        (768, 1368),  # 9:16
        (840, 1256),  # 2:3
        (888, 1184),  # 3:4
        (912, 1144),  # 4:5
        (1024, 1024),  # 1:1
        (1144, 912),  # 5:4
        (1184, 888),  # 4:3
        (1256, 840),  # 3:2
        (1368, 768),  # 16:9
        (1568, 672),  # 21:9
    ],
    "database": {
        "image_db_filename": "image_database.db",  # 画像データベースのファイル名
        # SQLite 書き込みロック競合時の最大待機時間 (ミリ秒)。GUI/CLI を同じプロジェクト
        # DB に併用すると一時的な書き込み競合が起こり得るため、即時失敗せず一定時間
        # リトライ待機する (PRAGMA busy_timeout / Issue #767)。
        "busy_timeout_ms": 30000,
        # Note: tag_db_package and tag_db_filename were removed (2026-01-02)
        # Tag databases are now managed via genai-tag-db-tools public API (initialize_databases)
    },
    "log": {"level": "INFO", "file_path": str(DEFAULT_LOG_PATH), "rotation": "25 MB", "levels": {}},
    "model_selection": {
        # Issue #249: route preference の永続化。
        # auto | direct | openrouter (GUI dropdown で選択可)
        # all は CLI 専用 (--route all): GUI checkbox UI は preferred 1 行のみ描画する設計と
        # 整合しないため GUI dropdown では未提供。手動で "all" を書いた場合 GUI 起動時に
        # warning log + auto 表示にフォールバックする (configuration_window.py 参照)。
        "route_preference": "auto",
    },
}

LEGACY_BLANK_AS_DEFAULT_KEYS = {
    ("directories", "database_base_dir"),
    ("directories", "database_project_name"),
    ("directories", "export_dir"),
    ("directories", "batch_results_dir"),
    ("database", "image_db_filename"),
    ("log", "file_path"),
}


def create_user_config_defaults() -> dict[str, Any]:
    """Return the user-facing defaults written to a new config file.

    Runtime-only defaults stay in DEFAULT_CONFIG and are applied by get_config().
    """
    user_config = deepcopy(DEFAULT_CONFIG)
    user_config.pop("qt", None)
    log_config = user_config.get("log")
    if isinstance(log_config, dict):
        log_config.pop("file_path", None)
    return user_config


def _should_keep_default_for_blank(path: tuple[str, ...], value: Any) -> bool:
    """Return whether a legacy blank placeholder should keep DEFAULT_CONFIG."""
    return value == "" and path in LEGACY_BLANK_AS_DEFAULT_KEYS


def load_config(config_file: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    try:
        # TOMLファイルの読み込み
        with open(config_file, encoding="utf-8") as f:
            load_parameters = toml.load(f)

        # 必須セクションのチェック
        for section in ["directories"]:
            if section not in load_parameters:
                raise KeyError(f"必須の設定セクション '{section}' が見つかりません。")

        return load_parameters
    except FileNotFoundError:
        # 上位関数で処理されるのでそのまま再発生
        raise
    except toml.TomlDecodeError as e:
        raise ValueError(f"設定ファイルの解析エラー: {e!s}") from e


def deep_update(d: dict[str, Any], u: dict[str, Any], path: tuple[str, ...] = ()) -> dict[str, Any]:
    for k, v in u.items():
        current_path = (*path, k)
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v, current_path)
        elif _should_keep_default_for_blank(current_path, v):
            continue
        else:
            d[k] = v
    return d


def get_config(config_file: Path | None = None) -> dict[str, Any]:
    runtime = get_runtime_configuration()
    if config_file is None and runtime is not None:
        return deepcopy(runtime.settings)
    final_config = deepcopy(DEFAULT_CONFIG)
    paths = [config_file] if config_file is not None else [DEFAULT_CONFIG_PATH, get_user_config_path()]
    for path in paths:
        try:
            loaded_config = load_config(path)
            if config_file is None and path == DEFAULT_CONFIG_PATH:
                loaded_config = _portable_project_config(loaded_config)
            final_config = deep_update(final_config, loaded_config)
        except FileNotFoundError:
            # Missing files are handled without side effects; creation is explicit.
            pass
    return final_config


def _portable_project_config(settings: dict[str, Any]) -> dict[str, Any]:
    """Ignore absolute machine paths in the implicit shared project layer.

    Both path dialects are checked so a Windows legacy file cannot configure a
    Linux process. Explicit config files and OS user preferences are unchanged.
    No setting values are included in the diagnostic.
    """
    rejected: list[str] = []

    def portable(value: Any, location: tuple[str, ...]) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                is_path = key == "path" or key.endswith(("_path", "_dir"))
                if (
                    is_path
                    and isinstance(item, str)
                    and (PureWindowsPath(item).is_absolute() or PurePosixPath(item).is_absolute())
                ):
                    rejected.append(".".join((*location, key)))
                    continue
                rejected_before = len(rejected)
                candidate = portable(item, (*location, key))
                # A partially stripped model definition has no usable path.
                # Keep the code default for an entire affected list instead.
                if not (isinstance(item, list) and len(rejected) > rejected_before):
                    result[key] = candidate
            return result
        if isinstance(value, list):
            return [portable(item, (*location, str(index))) for index, item in enumerate(value)]
        return value

    result: dict[str, Any] = portable(settings, ())
    if rejected:
        warnings.warn(
            "Absolute paths in shared project config were ignored: "
            + ", ".join(rejected)
            + f". Move OS-specific settings explicitly to {get_user_config_path()}.",
            RuntimeWarning,
            stacklevel=3,
        )
    return result


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Explicit CLI path selection, scoped to one invocation without changing CWD."""

    workspace: Path
    config_path: Path
    settings: dict[str, Any]


_RUNTIME_CONFIGURATION: ContextVar[RuntimeConfiguration | None] = ContextVar(
    "lorairo_runtime_configuration", default=None
)


def get_runtime_configuration() -> RuntimeConfiguration | None:
    return _RUNTIME_CONFIGURATION.get()


def resolve_runtime_configuration(workspace: Path | None, config_path: Path | None) -> RuntimeConfiguration:
    """Resolve explicit CLI paths; a specified config must exist and parse successfully.

    CLI paths are relative to invocation CWD. Relative configured directories use
    workspace, or the explicit config's parent when workspace is omitted.
    """
    selected_config = config_path.expanduser().resolve() if config_path is not None else None
    if selected_config is not None and not selected_config.is_file():
        raise ValueError(f"Config file does not exist or is not a file: {selected_config}")
    root = (
        workspace.expanduser().resolve()
        if workspace is not None
        else selected_config.parent
        if selected_config
        else Path.cwd()
    )
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")
    selected_config = selected_config or root / "config" / "lorairo.toml"
    settings = (
        deep_update(deepcopy(DEFAULT_CONFIG), load_config(selected_config))
        if config_path is not None
        else get_config(selected_config)
    )
    if config_path is None:
        try:
            preferences = load_config(get_user_config_path())
        except FileNotFoundError:
            preferences = {}
        # --workspace selects data directories, while credentials and executable
        # preferences still belong to the OS user. An explicit --config stays
        # fully independent from user preferences for portable invocations.
        preferences.pop("directories", None)
        settings = deep_update(settings, preferences)
    if not isinstance(settings["directories"], dict):
        raise ValueError("Config [directories] must be a table")
    for key, value in settings["directories"].items():
        if key.endswith("_dir"):
            if not isinstance(value, str):
                raise ValueError(f"Config directories.{key} must be a path string")
            if value:
                directory = Path(value).expanduser()
                settings["directories"][key] = str((root / directory).resolve())
    return RuntimeConfiguration(root, selected_config, settings)


@contextmanager
def runtime_configuration_scope(configuration: RuntimeConfiguration) -> Iterator[None]:
    token = _RUNTIME_CONFIGURATION.set(configuration)
    try:
        yield
    finally:
        _RUNTIME_CONFIGURATION.reset(token)


def write_config_file(config_data: dict[str, Any], file_path: Path | None = None) -> None:
    """Save preferences to the OS user path unless a file is explicitly selected."""
    if file_path is None:
        file_path = get_user_config_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        toml.dump(config_data, f)


def ensure_config_file(config_file: Path | None = None) -> dict[str, Any]:
    """Create an OS user override or an explicitly selected portable config."""
    use_user_config = config_file is None
    config_file = config_file or get_user_config_path()
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        initial_config = {"directories": {}} if use_user_config else create_user_config_defaults()
        write_config_file(initial_config, config_file)
    return get_config() if use_user_config else get_config(config_file)


if __name__ == "__main__":
    try:
        config = get_config()
        print(config)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"設定エラー config/lorairo.tomlを確認: {e}")
