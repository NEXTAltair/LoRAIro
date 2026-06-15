import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import toml


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
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "lorairo.log"
DEFAULT_CLI_LOG_PATH = PROJECT_ROOT / "logs" / "lorairo-cli.log"

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


def get_config(config_file: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    final_config = deepcopy(DEFAULT_CONFIG)
    try:
        loaded_config = load_config(config_file)
        final_config = deep_update(final_config, loaded_config)
    except FileNotFoundError:
        # Missing files are handled without side effects; creation is explicit.
        pass
    return final_config


def write_config_file(config_data: dict[str, Any], file_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """設定をファイルに保存します。"""
    with open(file_path, "w", encoding="utf-8") as f:
        toml.dump(config_data, f)


def ensure_config_file(config_file: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Create a user-facing config file if needed and return effective config."""
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        write_config_file(create_user_config_defaults(), config_file)
    return get_config(config_file)


if __name__ == "__main__":
    try:
        config = get_config()
        print(config)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"設定エラー config/lorairo.tomlを確認: {e}")
