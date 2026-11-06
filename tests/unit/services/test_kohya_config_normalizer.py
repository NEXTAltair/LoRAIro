"""kohya_config_normalizer のテスト。"""

import json

import pytest

from lorairo.services.kohya_config_normalizer import (
    NormalizedConfig,
    mask_secrets,
    normalize_kohya_gui_config,
)


def _normalize(config: dict[str, object]) -> NormalizedConfig:
    return normalize_kohya_gui_config(json.dumps(config))


def test_empty_string_keys_are_dropped():
    result = _normalize({"reg_data_dir": "", "dataset_config": "", "unknown_none": None})
    assert result.normalized == {}
    assert result.unmapped == {}


def test_secret_value_is_masked_everywhere():
    result = _normalize({"wandb_api_key": "SECRET", "hf_token": "SECRET", "output_name": "x"})
    for text in (result.raw_content, str(result.normalized), str(result.unmapped)):
        assert "SECRET" not in text
    assert json.loads(result.raw_content)["wandb_api_key"] == ""
    assert "wandb_api_key" not in result.normalized
    assert "wandb_api_key" not in result.unmapped


def test_mask_secrets_returns_new_dict():
    original: dict[str, object] = {"wandb_api_key": "SECRET", "a": 1}
    masked = mask_secrets(original)
    assert masked == {"wandb_api_key": "", "a": 1}
    assert original["wandb_api_key"] == "SECRET"


def test_renames_and_wandb_mapping():
    result = _normalize({"optimizer": "AdamW8bit", "use_wandb": True, "max_resolution": "1024,1024"})
    assert result.normalized == {
        "optimizer_type": "AdamW8bit",
        "log_with": "wandb",
        "resolution": "1024,1024",
    }


def test_use_wandb_false_is_dropped_and_launcher_keys_removed():
    result = _normalize({"use_wandb": False, "num_processes": 1, "multi_gpu": False, "gpu_ids": "0"})
    assert result.normalized == {}
    assert result.unmapped == {}


def test_numeric_strings_are_coerced():
    result = _normalize(
        {"learning_rate": "0.0001", "max_data_loader_n_workers": "0", "cache_latents": "true"}
    )
    assert result.normalized["learning_rate"] == 0.0001
    assert isinstance(result.normalized["learning_rate"], float)
    assert result.normalized["max_data_loader_n_workers"] == 0
    assert isinstance(result.normalized["max_data_loader_n_workers"], int)
    assert result.normalized["cache_latents"] is True


def test_lr_warmup_percent_and_override_follow_kohya_rule():
    percent = _normalize({"lr_warmup": 10, "lr_warmup_steps": 0})
    assert percent.normalized["lr_warmup_steps"] == pytest.approx(0.1)
    override = _normalize({"lr_warmup": 10, "lr_warmup_steps": "100"})
    assert override.normalized["lr_warmup_steps"] == 100
    zero = _normalize({"lr_warmup": 0, "lr_warmup_steps": 0})
    assert "lr_warmup_steps" not in zero.normalized
    broken = _normalize({"lr_warmup": "abc"})
    assert broken.unmapped == {"lr_warmup": "abc"}


def test_sdxl_flag_selects_script():
    result = _normalize({"sdxl": True})
    assert result.target_script == "sdxl_train_network.py"
    assert "sdxl" not in result.normalized
    assert "sdxl" not in result.unmapped
    assert _normalize({}).target_script == "train_network.py"


def test_standard_lora_type_sets_network_module():
    result = _normalize({"LoRA_type": "Standard"})
    assert result.normalized["network_module"] == "networks.lora"
    assert "LoRA_type" not in result.unmapped


def test_locon_packs_network_args():
    result = _normalize(
        {"LoRA_type": "LyCORIS/LoCon", "conv_dim": 8, "conv_alpha": 1, "LyCORIS_preset": "full"}
    )
    assert result.normalized["network_module"] == "lycoris.kohya"
    assert result.normalized["network_args"] == ["preset=full", "conv_dim=8", "conv_alpha=1", "algo=locon"]
    assert "conv_dim" not in result.unmapped


def test_other_lora_type_goes_to_unmapped():
    result = _normalize({"LoRA_type": "LyCORIS/LoHa", "conv_dim": 4})
    assert result.unmapped["LoRA_type"] == "LyCORIS/LoHa"
    assert result.unmapped["conv_dim"] == 4
    assert "network_module" not in result.normalized


def test_output_name_is_extracted():
    result = _normalize({"output_name": "kariginu-XL"})
    assert result.output_name == "kariginu-XL"
    assert _normalize({}).output_name is None


def test_invalid_json_propagates():
    with pytest.raises(json.JSONDecodeError):
        normalize_kohya_gui_config("{not json")


def test_zero_means_unset_for_gui_zero_disabled_keys():
    result = _normalize(
        {
            "max_train_epochs": 0,
            "max_train_steps": "1600",
            "seed": "0",
            "clip_skip": 0,
            "save_every_n_steps": 0,
        }
    )
    assert result.normalized == {"max_train_steps": 1600}
    assert result.unmapped == {}


def test_nonzero_values_of_zero_disabled_keys_are_kept():
    result = _normalize({"max_train_epochs": 10, "seed": 42})
    assert result.normalized == {"max_train_epochs": 10, "seed": 42}


def test_optimizer_and_scheduler_args_are_split_into_lists():
    result = _normalize(
        {
            "optimizer_args": 'weight_decay=0.1 "betas=0.9,0.99"',
            "lr_scheduler_args": "T_max=10",
        }
    )
    assert result.normalized["optimizer_args"] == ["weight_decay=0.1", "betas=0.9,0.99"]
    assert result.normalized["lr_scheduler_args"] == ["T_max=10"]


def test_original_noise_type_drops_multires_settings():
    result = _normalize(
        {
            "noise_offset_type": "Original",
            "noise_offset": 0.1,
            "adaptive_noise_scale": 0.05,
            "multires_noise_iterations": 6,
            "multires_noise_discount": 0.3,
        }
    )
    assert result.normalized == {"noise_offset": 0.1, "adaptive_noise_scale": 0.05}
    assert result.unmapped == {"noise_offset_type": "Original"}


def test_multires_noise_type_drops_offset_settings():
    result = _normalize(
        {
            "noise_offset_type": "Multires",
            "noise_offset": 0.1,
            "noise_offset_random_strength": True,
            "adaptive_noise_scale": 0.05,
            "multires_noise_iterations": 6,
            "multires_noise_discount": 0.3,
        }
    )
    assert result.normalized == {"multires_noise_iterations": 6, "multires_noise_discount": 0.3}


def test_unknown_noise_type_drops_both_groups_and_missing_type_keeps_values():
    other = _normalize({"noise_offset_type": "None", "noise_offset": 0.1, "multires_noise_iterations": 6})
    assert other.normalized == {}
    missing = _normalize({"noise_offset": 0.1})
    assert missing.normalized == {"noise_offset": 0.1}


def test_text_encoder_only_flag_is_derived_before_zero_unet_lr_is_dropped():
    result = _normalize({"learning_rate": 0.0001, "text_encoder_lr": 0.00005, "unet_lr": 0})
    assert result.normalized["network_train_text_encoder_only"] is True
    assert "network_train_unet_only" not in result.normalized
    assert "unet_lr" not in result.normalized


def test_unet_only_flag_is_derived_when_text_encoder_lr_is_zero():
    result = _normalize({"learning_rate": "0.0001", "text_encoder_lr": "0", "unet_lr": "0.0002"})
    assert result.normalized["network_train_unet_only"] is True
    assert "network_train_text_encoder_only" not in result.normalized
    assert result.normalized["unet_lr"] == 0.0002


def test_no_train_flag_when_both_or_neither_lr_is_set():
    both = _normalize({"text_encoder_lr": 0.1, "unet_lr": 0.2})
    neither = _normalize({"text_encoder_lr": 0, "unet_lr": 0})
    for result in (both, neither):
        assert "network_train_unet_only" not in result.normalized
        assert "network_train_text_encoder_only" not in result.normalized


def test_sdxl_only_flags_are_dropped_unless_sdxl():
    off = _normalize({"sdxl_cache_text_encoder_outputs": True, "sdxl_no_half_vae": True})
    assert off.normalized == {}
    on = _normalize({"sdxl": True, "sdxl_cache_text_encoder_outputs": True, "sdxl_no_half_vae": True})
    assert on.normalized == {"cache_text_encoder_outputs": True, "no_half_vae": True}
