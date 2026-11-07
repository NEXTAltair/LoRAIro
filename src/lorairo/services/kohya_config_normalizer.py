"""Kohya_ss GUI の設定 json を sd-scripts の引数名と型へ正規化する。

変換規則は Kohya_ss (コミット 45088f0) の以下を根拠にする。
- kohya_gui/common_gui.py: `resolve_lr_warmup_steps` (lr_warmup の比率 % と lr_warmup_steps の優先順位)、
  `update_my_data` (`use_wandb` -> `log_with="wandb"`、`lora_network_weights` -> `network_weights`)
- kohya_gui/lora_gui.py: `train_model` の LoCon 用 `network_args` の組み立てと、
  GUI 引数から sd-scripts 引数への改名 (`optimizer` -> `optimizer_type` など)、
  `config_toml_data` 組み立て後の「"" / False / 0 を出力しない」フィルタ

epoch 指定の学習長 (dataset_config が無く max_train_steps / max_train_epochs が 0) は、GUI が画像数から
steps を計算するため正規化では再現できない。近似せず自動変換を保留し、`epoch` を unmapped に残す。

対象範囲は LoRA_type が Standard / LyCORIS/LoCon の SDXL / SD1.5 のみ。flux / sd3 / hunyuan /
anima / lumina 系のキーと、その他の LoRA_type 用のキーは変換せず unmapped に残す (計画の範囲外)。
"""

import json
from dataclasses import dataclass

from lorairo.services.sd_scripts_arg_table import SD_SCRIPTS_ARG_TYPES

NormalizedValue = str | int | float | bool | list[str]
UnmappedValue = str | int | float | bool | list[str] | None

# 起動ツール (accelerate) 用の引数。sd-scripts の学習設定には入らない
_LAUNCHER_KEYS = frozenset(
    {
        "extra_accelerate_launch_args",
        "gpu_ids",
        "main_process_port",
        "multi_gpu",
        "num_cpu_threads_per_process",
        "num_machines",
        "num_processes",
    }
)

# GUI の引数名 -> sd-scripts の引数名
_RENAMES: dict[str, str] = {
    "optimizer": "optimizer_type",
    "sdxl_cache_text_encoder_outputs": "cache_text_encoder_outputs",
    "sdxl_no_half_vae": "no_half_vae",
    "lora_network_weights": "network_weights",
    "max_resolution": "resolution",
}

# lora_gui.py の LoCon 用 network_args の並び (use_tucker が 2 回あるのも元のまま)
_LOCON_ARG_KEYS: tuple[str, ...] = (
    "LyCORIS_preset",
    "conv_dim",
    "conv_alpha",
    "use_tucker",
    "rank_dropout",
    "bypass_mode",
    "dora_wd",
    "module_dropout",
    "use_tucker",
    "use_scalar",
    "rank_dropout_scale",
)
# network_args の key= 側の名前 (GUI 変数 LyCORIS_preset は preset= で渡される)
_LOCON_ARG_NAMES: dict[str, str] = {"LyCORIS_preset": "preset"}
_LOCON_TRAIN_NORM_KEY = "train_norm"
_LOCON_TYPES = frozenset({"LyCORIS/LoCon", "LoCon"})

# sd-scripts で nargs="*" のキー。GUI は文字列を `str(v).replace('"', "").split()` でリスト化する
_SPLIT_LIST_KEYS = frozenset({"optimizer_args", "lr_scheduler_args"})

# noise_offset_type ごとに有効なキー (GUI は選択された側だけ出力する)
_ORIGINAL_NOISE_KEYS = frozenset({"noise_offset", "noise_offset_random_strength", "adaptive_noise_scale"})
_MULTIRES_NOISE_KEYS = frozenset({"multires_noise_iterations", "multires_noise_discount"})

# GUI のフィルタ (`value not in ["", False, None]`) の後で追加されるため 0 でも出力するキー
_KEEP_ZERO_KEYS = frozenset({"max_data_loader_n_workers"})

# Standard の network_args に入るキー (train_model の引数順。lora_gui.py の kohya_lora_var_list)
_STANDARD_ARG_KEYS: tuple[str, ...] = (
    "down_lr_weight",
    "mid_lr_weight",
    "up_lr_weight",
    "block_lr_zero_threshold",
    "block_dims",
    "block_alphas",
    "conv_block_dims",
    "conv_block_alphas",
    "rank_dropout",
    "module_dropout",
)
# append_loraplus_network_args の順序 (真のときだけ追加)
_LORAPLUS_ARG_KEYS: tuple[str, ...] = (
    "loraplus_lr_ratio",
    "loraplus_unet_lr_ratio",
    "loraplus_text_encoder_lr_ratio",
)

_SECRET_SUFFIXES = ("_api_key", "_token")
_TRUE_STRINGS = frozenset({"true", "1"})
_FALSE_STRINGS = frozenset({"false", "0"})


@dataclass(frozen=True)
class NormalizedConfig:
    """正規化した学習設定。

    Attributes:
        raw_content: 秘密の値を空にした元の設定 (json 文字列)。
        normalized: sd-scripts の引数名と型にそろえた設定。
        unmapped: 変換規則が未確認のキーと値。
        target_script: 対象スクリプト名。
        output_name: 出力名。
    """

    raw_content: str
    normalized: dict[str, NormalizedValue]
    unmapped: dict[str, UnmappedValue]
    target_script: str | None
    output_name: str | None


def _is_secret_key(key: str) -> bool:
    return key.lower().endswith(_SECRET_SUFFIXES)


def mask_secrets(config: dict[str, object]) -> dict[str, object]:
    """秘密キー (`*_api_key` / `*_token`) の値を空文字にした新しい dict を返す。

    Args:
        config: 元の設定。

    Returns:
        秘密キーの値を空にしたコピー。元の dict は変更しない。
    """
    return {key: ("" if _is_secret_key(key) else value) for key, value in config.items()}


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _is_truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return bool(value)


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _resolve_lr_warmup_steps(lr_warmup: object, lr_warmup_steps: object) -> int | float:
    """common_gui.resolve_lr_warmup_steps と同じ規則で lr_warmup_steps を決める。"""
    warmup = _to_float(lr_warmup) or 0.0
    steps = _to_float(lr_warmup_steps) or 0.0
    if steps > 0:
        return int(steps)
    if warmup != 0:
        return warmup / 100
    return 0


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        return None
    number = _to_float(value)
    return None if number is None else number != 0


def _coerce_int(value: object) -> int | None:
    number = _to_float(value)
    if number is None or number != int(number):
        return None
    return int(number)


def _coerce(value: object, type_name: str) -> NormalizedValue | None:
    """sd-scripts の引数型に値を合わせる。変換できないときは None。"""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if type_name == "bool":
        return _coerce_bool(value)
    if type_name == "int":
        return _coerce_int(value)
    if type_name == "float":
        return _to_float(value)
    return str(value)


def _to_unmapped(value: object) -> UnmappedValue:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _drop_inactive_noise_keys(data: dict[str, object]) -> None:
    """noise_offset_type で選ばれていない側のノイズ設定を取り除く。選択が無ければ何もしない。"""
    if "noise_offset_type" not in data:
        return
    noise_type = data["noise_offset_type"]
    active: frozenset[str] = frozenset()
    if noise_type == "Original":
        active = _ORIGINAL_NOISE_KEYS
    elif noise_type == "Multires":
        active = _MULTIRES_NOISE_KEYS
    for key in (_ORIGINAL_NOISE_KEYS | _MULTIRES_NOISE_KEYS) - active:
        data.pop(key, None)


def _derive_network_train_flags(data: dict[str, object], normalized: dict[str, NormalizedValue]) -> None:
    """text_encoder_lr / unet_lr から学習対象フラグを導く (lora_gui.py resolve_network_train_flags)。

    0 の学習率は後で取り除かれるため、その前に元の値で判定する。
    """
    text_encoder_lr = _to_float(data.get("text_encoder_lr")) or 0.0
    unet_lr = _to_float(data.get("unet_lr")) or 0.0
    if text_encoder_lr != 0 and unet_lr == 0:
        normalized["network_train_text_encoder_only"] = True
    elif text_encoder_lr == 0 and unet_lr != 0:
        normalized["network_train_unet_only"] = True


def _drop_sdxl_only_keys(data: dict[str, object], is_sdxl: bool) -> None:
    """GUI は sdxl が偽のとき sdxl 専用の項目を出力しない。"""
    if is_sdxl:
        return
    for key in ("sdxl_cache_text_encoder_outputs", "sdxl_no_half_vae"):
        data.pop(key, None)


def _drop_gui_falsy_values(normalized: dict[str, NormalizedValue]) -> None:
    """GUI の `value not in ["", False, None]` と同じく、False と数値 0 を取り除く。"""
    for key in list(normalized):
        value = normalized[key]
        if key in _KEEP_ZERO_KEYS or isinstance(value, list | str):
            continue
        if value is False or value == 0:
            del normalized[key]


def _apply_attention_selector(data: dict[str, object], normalized: dict[str, NormalizedValue]) -> None:
    """GUI の xformers 選択 ("xformers" / "sdpa" / "none") を backend フラグへ変換する。"""
    if "xformers" not in data:
        return
    selected = data.pop("xformers")
    if selected is True or selected == "xformers":
        normalized["xformers"] = True
    elif selected == "sdpa":
        normalized["sdpa"] = True


def _move_gui_only_keys(data: dict[str, object], unmapped: dict[str, UnmappedValue]) -> None:
    """sd-scripts の引数へそのまま渡せない GUI のキーを unmapped へ移す。

    - stop_text_encoder_training: GUI は「未対応」として 0 に上書きし出力しない。
    - sample_prompts: GUI は本文をファイルに書き、パスを出力する。本文は引数ではない。
    text_encoder_lr は含めない。保存された JSON はスカラー (数値または "1e-04" のような文字列)
    で、配列にするのは GUI がコマンドを組み立てるときだけ。sd-scripts もスカラーを受け付ける
    (train_network.py の backward compatibility 分岐) ので、float として通常どおり正規化する。
    """
    for key in ("stop_text_encoder_training", "sample_prompts"):
        if key in data:
            value = data.pop(key)
            if not (_to_float(value) == 0):
                unmapped[key] = _to_unmapped(value)


def _apply_gui_defaults(data: dict[str, object]) -> None:
    """GUI が空のときに補う既定値 (lr_scheduler_num_cycles = epoch、wandb_run_name = output_name)。"""
    if "lr_scheduler_num_cycles" not in data and "epoch" in data:
        data["lr_scheduler_num_cycles"] = data["epoch"]
    if "wandb_run_name" not in data and "output_name" in data:
        data["wandb_run_name"] = data["output_name"]


def _split_args(value: object) -> list[str]:
    """GUI と同じ規則 (二重引用符を除いて空白で分割) で引数文字列をリストにする。"""
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value).replace('"', "").split()


def _build_locon_network_args(data: dict[str, object]) -> list[str]:
    """lora_gui.py の LoCon 用 network_args と同じキー・順序の ["k=v", ...] を作る。"""
    args: list[str] = []
    for key in _LOCON_ARG_KEYS:
        if key in data:
            args.append(f"{_LOCON_ARG_NAMES.get(key, key)}={data[key]}")
    args.append("algo=locon")
    if _LOCON_TRAIN_NORM_KEY in data:
        args.append(f"{_LOCON_TRAIN_NORM_KEY}={data[_LOCON_TRAIN_NORM_KEY]}")
    return args


def _apply_lr_warmup(
    data: dict[str, object],
    normalized: dict[str, NormalizedValue],
    unmapped: dict[str, UnmappedValue],
) -> None:
    """lr_warmup (比率 %) と lr_warmup_steps (絶対値) を GUI と同じ規則で解決する。

    dataset_config がある場合、GUI は max_train_steps が正なら比率を絶対値 (round) に変換し、
    0 以下なら絶対値の上書きを捨てる (lora_gui.py train_model)。
    """
    if "lr_warmup" not in data and "lr_warmup_steps" not in data:
        return
    lr_warmup = data.pop("lr_warmup", None)
    lr_warmup_steps = data.pop("lr_warmup_steps", None)
    bad = [
        (key, val)
        for key, val in (("lr_warmup", lr_warmup), ("lr_warmup_steps", lr_warmup_steps))
        if not _is_empty(val) and _to_float(val) is None
    ]
    if bad:
        for key, val in bad:
            unmapped[key] = _to_unmapped(val)
        return
    if "dataset_config" in data:
        max_steps = _to_float(data.get("max_train_steps")) or 0.0
        override = _to_float(lr_warmup_steps) or 0.0
        percent = _to_float(lr_warmup) or 0.0
        if max_steps <= 0:
            lr_warmup_steps = 0
        elif override <= 0 and percent != 0:
            lr_warmup_steps = round(percent * int(max_steps) / 100)
            lr_warmup = 0
    resolved = _resolve_lr_warmup_steps(lr_warmup, lr_warmup_steps)
    if resolved:
        normalized["lr_warmup_steps"] = resolved


def _loraplus_args(data: dict[str, object]) -> list[str]:
    """append_loraplus_network_args と同じ順序で、真の値だけ "k=v" にする。"""
    return [f"{key}={data[key]}" for key in _LORAPLUS_ARG_KEYS if data.get(key)]


def _build_standard_network_args(data: dict[str, object]) -> list[str]:
    """lora_gui.py の Standard 用 network_args (真の値だけ。続けて loraplus) を作る。"""
    args = [f"{key}={data[key]}" for key in _STANDARD_ARG_KEYS if data.get(key)]
    return args + _loraplus_args(data)


def _apply_lora_type(
    data: dict[str, object],
    normalized: dict[str, NormalizedValue],
    unmapped: dict[str, UnmappedValue],
) -> set[str]:
    """LoRA_type から network_module / network_args を決める。network_args に使ったキーを返す。"""
    lora_type = data.pop("LoRA_type", None)
    if lora_type == "Standard":
        normalized["network_module"] = "networks.lora"
        args = _build_standard_network_args(data)
        if args:
            normalized["network_args"] = args
        return set(_STANDARD_ARG_KEYS) | set(_LORAPLUS_ARG_KEYS)
    if lora_type in _LOCON_TYPES:
        normalized["network_module"] = "lycoris.kohya"
        normalized["network_args"] = _build_locon_network_args(data) + _loraplus_args(data)
        return set(_LOCON_ARG_KEYS) | {_LOCON_TRAIN_NORM_KEY} | set(_LORAPLUS_ARG_KEYS)
    if lora_type is not None:
        unmapped["LoRA_type"] = _to_unmapped(lora_type)
    return set()


def normalize_kohya_gui_config(raw_text: str) -> NormalizedConfig:
    """Kohya_ss GUI の設定 json を正規化する。

    Args:
        raw_text: 設定 json の文字列。

    Returns:
        正規化結果。

    Raises:
        json.JSONDecodeError: json として読めない場合。
        ValueError: json の最上位がオブジェクトでない場合。
    """
    loaded = json.loads(raw_text)
    if not isinstance(loaded, dict):
        raise ValueError("設定 json の最上位はオブジェクトである必要があります")

    masked = mask_secrets(loaded)
    raw_content = json.dumps(masked, ensure_ascii=False, indent=2)

    # 空値・秘密キー・起動ツール引数を除いた作業用の辞書
    data: dict[str, object] = {
        key: value
        for key, value in masked.items()
        if not _is_empty(value) and key not in _LAUNCHER_KEYS and not _is_secret_key(key)
    }

    normalized: dict[str, NormalizedValue] = {}
    unmapped: dict[str, UnmappedValue] = {}

    is_sdxl = _is_truthy(data.pop("sdxl", False))
    target_script = "sdxl_train_network.py" if is_sdxl else "train_network.py"

    if _is_truthy(data.pop("use_wandb", False)):
        normalized["log_with"] = "wandb"

    _drop_inactive_noise_keys(data)
    _drop_sdxl_only_keys(data, is_sdxl)
    _derive_network_train_flags(data, normalized)
    _apply_attention_selector(data, normalized)
    _move_gui_only_keys(data, unmapped)
    if _is_truthy(data.get("train_inpainting", False)):
        # GUI は inpainting 学習時に latent キャッシュを無効にする
        data.pop("cache_latents", None)
        data.pop("cache_latents_to_disk", None)
    _apply_gui_defaults(data)
    _apply_lr_warmup(data, normalized, unmapped)
    locon_consumed = _apply_lora_type(data, normalized, unmapped)

    for key, value in data.items():
        if key in locon_consumed:
            continue
        if key in _SPLIT_LIST_KEYS:
            normalized[key] = _split_args(value)
            continue
        name = _RENAMES.get(key, key)
        type_name = SD_SCRIPTS_ARG_TYPES.get(name)
        if type_name is None:
            unmapped[key] = _to_unmapped(value)
            continue
        coerced = _coerce(value, type_name)
        if coerced is None:
            unmapped[key] = _to_unmapped(value)
        else:
            normalized[name] = coerced

    _drop_gui_falsy_values(normalized)
    output_name = normalized.get("output_name")
    return NormalizedConfig(
        raw_content=raw_content,
        normalized=normalized,
        unmapped=unmapped,
        target_script=target_script,
        output_name=output_name if isinstance(output_name, str) else None,
    )
