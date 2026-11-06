"""sd_scripts_toml のテスト。"""

from pathlib import Path

import pytest
import toml

from lorairo.services.sd_scripts_toml import (
    SubsetSpec,
    render_dataset_config,
    render_training_config,
)


@pytest.mark.unit
def test_dataset_config_has_explicit_caption_extension() -> None:
    text = render_dataset_config([SubsetSpec(Path("/d/a"), 3, ".txt")])
    data = toml.loads(text)
    assert data["general"]["caption_extension"] == ".txt"
    assert data["datasets"][0]["subsets"][0]["caption_extension"] == ".txt"


@pytest.mark.unit
def test_dataset_config_subsets() -> None:
    specs = [SubsetSpec(Path("/d/a"), 3, ".txt"), SubsetSpec(Path("/d/b"), 5, ".txt")]
    data = toml.loads(render_dataset_config(specs))
    subsets = data["datasets"][0]["subsets"]
    assert len(subsets) == 2
    assert [s["num_repeats"] for s in subsets] == [3, 5]
    assert [Path(s["image_dir"]) for s in subsets] == [Path("/d/a"), Path("/d/b")]


@pytest.mark.unit
def test_dataset_config_empty_raises() -> None:
    with pytest.raises(ValueError):
        render_dataset_config([])


@pytest.mark.unit
def test_training_config_is_flat_and_overrides_paths() -> None:
    text = render_training_config(
        {"train_data_dir": "/old", "learning_rate": 0.0001, "flip_aug": True, "tags": ["a", "b"]},
        {"train_data_dir": Path("/new")},
    )
    data = toml.loads(text)
    assert data["train_data_dir"] == "/new"
    assert data["learning_rate"] == 0.0001
    assert all(not isinstance(v, dict) for v in data.values())
    assert not any(line.startswith("[") for line in text.splitlines())


@pytest.mark.unit
def test_training_config_omits_reg_data_dir_unless_given() -> None:
    assert "reg_data_dir" not in toml.loads(render_training_config({"epochs": 1}, {}))
    data = toml.loads(render_training_config({"epochs": 1}, {"reg_data_dir": Path("/reg")}))
    assert data["reg_data_dir"] == "/reg"
