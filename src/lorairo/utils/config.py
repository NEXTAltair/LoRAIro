import toml
from pathlib import Path
from typing import Any
from copy import deepcopy

# デフォルト設定
DEFAULT_CONFIG = {
    'directories': {
        'database': 'Image_database',
        'dataset': '',
        'output': 'output',
        'edited_output': 'edited_output',
        'response_file': 'response_file'
    },
    'image_processing': {
        'target_resolution': 1024,
        'realesrganer_upscale': False,
        'realesrgan_model': "RealESRGAN_x4plus_anime_6B.pth"
    },
    'generation': {
        'batch_jsonl': False,
        'start_batch': False,
        'single_image': True
    },
    'options': {
        'generate_meta_clean': False,
        'cleanup_existing_tags': False,
        'join_existing_txt': True
    },
    'prompts': {
        'main': "",
        'additional': ""
    },
    'text_extensions': ['.txt', '.caption'],
    'preferred_resolutions': [
        (512, 512), (768, 512), (512, 768),
        (1024, 1024), (1216, 832), (832, 1216)
    ],
    'image_database': 'image_database.db',
    'log': {
        'level': 'INFO',
        'file': 'app.log'
    }
}

def load_config(config_file: str = 'processing.toml') -> dict:
    try:
        # TOMLファイルの読み込み
        with open(config_file, 'r', encoding='utf-8') as f:
            load_parameters = toml.load(f)

        # 必須セクションのチェック
        for section in ['directories', 'image_processing']:
            if section not in load_parameters:
                raise KeyError(f"必須の設定セクション '{section}' が見つかりません。")

        # mainprompt.mdファイルの存在確認と読み込み
        prompt_file = Path('mainprompt.md')
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                load_parameters.setdefault('prompts', {})
                load_parameters['prompts']['main'] = f.read()
        else:
            load_parameters.setdefault('prompts', {})
            load_parameters['prompts']['main'] = ""  # デフォルト値として空文字列を設定

        return load_parameters
    except FileNotFoundError as exc:
        raise ValueError(f"設定ファイル '{config_file}' が見つかりません。") from exc
    except toml.TomlDecodeError as e:
        raise ValueError(f"設定ファイルの解析エラー: {str(e)}") from e

def deep_update(d: dict[str, Any], u: dict[str, Any]) -> dict[str, Any]:
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v)
        elif v != "":
            d[k] = v
    return d

def get_config(config_file = 'processing.toml') -> dict:
    final_config = deepcopy(DEFAULT_CONFIG)
    loaded_config = load_config(config_file)
    final_config = deep_update(final_config, loaded_config)
    return final_config

def write_config_file(config_data: dict[str, Any], file_name: str = "processing.toml"):
    """設定をファイルに保存します。"""
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            toml.dump(config_data, f)
    except Exception as e:
        print(f"設定ファイルの保存に失敗しました: {e}")

if __name__ == "__main__":
    try:
        config = get_config()
        print(config)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"設定エラー processing.tomlを確認: {e}")