import toml
from typing import Dict, Any, TypedDict

class ConfigDict(TypedDict):
    api: Dict[str, str]
    huggingface: Dict[str, str]
    directories: Dict[str, str]
    image_processing: Dict[str, Any]
    generation: Dict[str, bool]
    options: Dict[str, bool]
    prompts: Dict[str, str]
    image_extensions: list[str]
    text_extensions: list[str]
    preferred_resolutions: list[tuple[int, int]]
    log: Dict[str, str]

def load_config(config_file: str = 'processing.toml') -> ConfigDict:
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
        required_sections = ['directories', 'image_processing']
        for section in required_sections:
            if section not in config:
                raise KeyError(f"必須の設定セクション '{section}' が見つかりません。")
        return config

    except FileNotFoundError:
        raise ValueError(f"設定ファイル '{config_file}' が見つかりません。")
    except toml.TomlDecodeError as e:
        raise ValueError(f"設定ファイルの解析エラー: {str(e)}")

# 設定のデフォルト値
DEFAULT_CONFIG: ConfigDict = {
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
    ],
    'log': {
        'level': 'INFO',
        'file': 'app.log'
    }
}

def get_config(config_file: str = 'processing.toml') -> ConfigDict:
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
            print(f"セクション '{section}' が見つかりません。デフォルト値を使用します。")
            config[section] = values
        elif isinstance(values, dict):
            for key, value in values.items():
                if key not in config[section]:
                    print(f"  項目 '{section}.{key}' が見つかりません。デフォルト値 '{value}' を使用します。")
                    config[section][key] = value
        else:
            if not config[section]:
                print(f"  セクション '{section}' の値が空です。デフォルト値 '{values}' を使用します。")
                config[section] = values


    # データセットディレクトリのチェック
    if not config['directories']['dataset']:
        raise ValueError("'dataset' ディレクトリは設定ファイルで指定する必要があります。")
    return config

# 設定の使用例
if __name__ == "__main__":
    try:
        config = get_config()
        print(config)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"設定エラー processing.tomlを確認: {e}")