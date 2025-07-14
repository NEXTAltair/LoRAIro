from copy import deepcopy
from pathlib import Path
from typing import Any

import toml

PROJECT_ROOT = Path.cwd()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "lorairo.toml"
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "lorairo.log"

# デフォルト設定
DEFAULT_CONFIG = {
    "api": {
        "openai_key": "",
        "claude_key": "",
        "google_key": "",
    },
    "directories": {
        "database_dir": "",  # 空文字列 = 自動生成 (日付+連番プロジェクト)
        "database_base_dir": "lorairo_data",  # 自動生成時のベースディレクトリ名
        "database_project_name": "main_dataset",  # 自動生成時のデフォルトプロジェクト名
        "export_dir": "export",  # 学習用データセットの出力先（.txt/.captionファイル等）
        "batch_results_dir": "batch_results",  # OpenAI Batch API結果JSONLファイルの保存先
    },
    "huggingface": {
        "hf_username": "",
        "repo_name": "",
        "token": "",
    },
    "image_processing": {
        "target_resolution": 1024,
        "realesrgan_upscale": False,
        "realesrgan_model": "RealESRGAN_x4plus_anime_6B.pth",
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
    "generation": {"batch_jsonl": False, "start_batch": False, "single_image": True},
    "options": {"generate_meta_clean": False, "cleanup_existing_tags": False, "join_existing_txt": True},
    "prompts": {"main": "", "additional": ""},
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
        "tag_db_package": "genai_tag_db_tools.data",  # タグDBのインポート元パッケージ名
        "tag_db_filename": "tags_v4.db",  # タグDBのファイル名
    },
    "log": {"level": "INFO", "file_path": str(DEFAULT_LOG_PATH), "rotation": "25 MB", "levels": {}},
}


def load_config(config_file: Path = DEFAULT_CONFIG_PATH) -> dict:
    try:
        # TOMLファイルの読み込み
        with open(config_file, encoding="utf-8") as f:
            load_parameters = toml.load(f)

        # 必須セクションのチェック
        for section in ["directories", "image_processing"]:
            if section not in load_parameters:
                raise KeyError(f"必須の設定セクション '{section}' が見つかりません。")

        # mainprompt.mdファイルの存在確認と読み込み
        prompt_file = Path("mainprompt.md")
        if prompt_file.exists():
            with open(prompt_file, encoding="utf-8") as f:
                load_parameters.setdefault("prompts", {})
                load_parameters["prompts"]["main"] = f.read()
        else:
            load_parameters.setdefault("prompts", {})
            load_parameters["prompts"]["main"] = ""  # デフォルト値として空文字列を設定

        return load_parameters
    except FileNotFoundError:
        # 上位関数で処理されるのでそのまま再発生
        raise
    except toml.TomlDecodeError as e:
        raise ValueError(f"設定ファイルの解析エラー: {e!s}") from e


def deep_update(d: dict[str, Any], u: dict[str, Any]) -> dict[str, Any]:
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v)
        elif v != "":
            d[k] = v
    return d


def get_config(config_file: Path = DEFAULT_CONFIG_PATH) -> dict:
    final_config = deepcopy(DEFAULT_CONFIG)
    try:
        loaded_config = load_config(config_file)
        final_config = deep_update(final_config, loaded_config)
    except FileNotFoundError:
        # ファイルがない場合はデフォルト設定のみ返す（自動作成される）
        pass
    return final_config


def write_config_file(config_data: dict[str, Any], file_path: Path = DEFAULT_CONFIG_PATH):
    """設定をファイルに保存します。"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            toml.dump(config_data, f)
    except Exception as e:
        print(f"設定ファイルの保存に失敗しました: {e}")


if __name__ == "__main__":
    try:
        config = get_config()
        print(config)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"設定エラー config/lorairo.tomlを確認: {e}")
