"""sd-scripts 用の TOML (データセット設定・学習設定) の書き出し。"""

from dataclasses import dataclass
from pathlib import Path

import toml

TomlValue = str | int | float | bool | list[str]


@dataclass(frozen=True)
class SubsetSpec:
    """データセット設定の 1 サブセット (画像フォルダ 1 つ)。

    Attributes:
        image_dir: 画像フォルダ。
        num_repeats: 繰り返し回数。
        caption_extension: 学習テキストの拡張子 (例: ".txt")。
    """

    image_dir: Path
    num_repeats: int
    caption_extension: str


def render_dataset_config(subsets: list[SubsetSpec]) -> str:
    """--dataset_config 用の TOML を生成する。

    caption_extension は sd-scripts の既定 (.caption) に任せず必ず明示する。
    sd-scripts (cb70b96) の library/config_util.py では resolution / batch_size /
    enable_bucket は未指定時に引数側 (argparse) の値で補われるため、ここでは出力しない。

    Args:
        subsets: サブセットの一覧。

    Returns:
        TOML 文字列。

    Raises:
        ValueError: subsets が空の場合。
    """
    if not subsets:
        raise ValueError("subsets must not be empty")
    config: dict[str, dict[str, str] | list[dict[str, list[dict[str, str | int]]]]] = {
        "general": {"caption_extension": subsets[0].caption_extension},
        "datasets": [
            {
                "subsets": [
                    {
                        "image_dir": str(spec.image_dir),
                        "num_repeats": spec.num_repeats,
                        "caption_extension": spec.caption_extension,
                    }
                    for spec in subsets
                ]
            }
        ],
    }
    dumped: str = toml.dumps(config)
    return dumped


def render_training_config(
    normalized: dict[str, TomlValue],
    path_overrides: dict[str, Path],
) -> str:
    """--config_file 用のフラットな TOML を生成する。

    path_overrides のキーは値を文字列のパスに置き換える。reg_data_dir は
    normalized か path_overrides に無ければ出力しない。

    Args:
        normalized: 正規化済みの学習設定。
        path_overrides: 上書きするパス (train_data_dir, output_dir, logging_dir など)。

    Returns:
        TOML 文字列。
    """
    config: dict[str, TomlValue] = dict(normalized)
    for key, path in path_overrides.items():
        config[key] = str(path)
    dumped: str = toml.dumps(config)
    return dumped
