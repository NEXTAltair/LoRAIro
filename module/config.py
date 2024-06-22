import toml
from typing import Dict, Any
from pathlib import Path

def load_config(config_file: str = 'processing.toml') -> Dict[str, Any]:
    """
    設定ファイルを読み込む

    Args:
        config_file (str): 設定ファイルのパス

    Returns:
        Dict[str, Any]: 設定項目を含む辞書
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = toml.load(f)
        # 必須の設定項目の存在チェック
        required_sections = ['directories', 'image_processing', 'generation', 'options', 'prompts']
        for section in required_sections:
            if section not in config:
                raise KeyError(f"必須の設定セクション '{section}' が見つかりません。")
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"設定ファイル '{config_file}' が見つかりません。")
    except toml.TomlDecodeError as e:
        raise ValueError(f"設定ファイルの解析エラー: {str(e)}")

# 設定のデフォルト値
DEFAULT_CONFIG = {
    'directories': {
        'dataset': '',
        'output': 'output',
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
    'image_extensions': ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'],
    'text_extensions': ['.txt', '.caption'],
    'preferred_resolutions': [
        (512, 512), (768, 512), (512, 768),
        (1024, 1024), (1216, 832), (832, 1216)
    ]
}

def get_config(config_file: str = 'processing.toml') -> Dict[str, Any]:
    """
    設定を取得し、デフォルト値で補完する

    Args:
        config_file (str): 設定ファイルのパス

    Returns:
        Dict[str, Any]: 完全な設定辞書
    """
    config = load_config(config_file)
    # デフォルト値で設定を補完
    for section, values in DEFAULT_CONFIG.items():
        if section not in config:
            config[section] = values
        elif isinstance(values, dict):
            for key, value in values.items():
                if key not in config[section]:
                    config[section][key] = value
        else:
            if section not in config:
                config[section] = values

    # 空の文字列をデフォルト値に置き換え
    if config['directories']['dataset'] == '':
        config['directories']['dataset'] = str(Path.cwd() / 'dataset')
    if config['directories']['output'] == '':
        config['directories']['output'] = str(Path.cwd() / 'output')
    if config['directories']['response_file'] == '':
        config['directories']['response_file'] = str(Path.cwd() / 'response_file')

    return config

# 設定の使用例
if __name__ == "__main__":
    config = get_config()
    print(config)