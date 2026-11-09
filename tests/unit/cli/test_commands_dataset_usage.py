"""`lorairo-cli dataset usage` コマンドのユニットテスト (Issue #1461)。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.repository.dataset import ImageDatasetUsage, LearningTextSnapshot

pytestmark = pytest.mark.unit

runner = CliRunner()


def _sample_usages() -> list[ImageDatasetUsage]:
    return [
        ImageDatasetUsage(
            image_id=42,
            dataset_id=1,
            dataset_name="kariginu",
            version_id=10,
            version_name="v01",
            parent_version_id=None,
            folder_id=100,
            dir_name="10_kariginu",
            folder_name="kariginu",
            num_repeats=10,
            trigger_word="Kariginu",
            file_stem="img_a",
            texts=[
                LearningTextSnapshot(
                    id=1000,
                    extension=".txt",
                    raw_text="Kariginu, [bracket], (tag:1.2)",
                    elements=["Kariginu", "[bracket]", "(tag:1.2)"],
                    is_edited=False,
                )
            ],
        ),
        ImageDatasetUsage(
            image_id=42,
            dataset_id=1,
            dataset_name="kariginu",
            version_id=10,
            version_name="v01",
            parent_version_id=None,
            folder_id=101,
            dir_name="5_style",
            folder_name="style",
            num_repeats=5,
            trigger_word=None,
            file_stem="img_a_style",
            texts=[
                LearningTextSnapshot(
                    id=1001,
                    extension=".txt",
                    raw_text="style, long_sleeves",
                    elements=["style", "long_sleeves"],
                    is_edited=True,
                )
            ],
        ),
        ImageDatasetUsage(
            image_id=42,
            dataset_id=1,
            dataset_name="kariginu",
            version_id=11,
            version_name="v02",
            parent_version_id=10,
            folder_id=102,
            dir_name="10_kariginu",
            folder_name="kariginu",
            num_repeats=10,
            trigger_word="Kariginu",
            file_stem="img_a",
            texts=[
                LearningTextSnapshot(
                    id=1002,
                    extension=".txt",
                    raw_text="Kariginu, smile",
                    elements=["Kariginu", "smile"],
                    is_edited=False,
                )
            ],
        ),
    ]


@pytest.fixture
def mock_dataset_repo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    repo = MagicMock()
    usages_by_id = {42: _sample_usages()}
    repo.list_image_usage.side_effect = lambda image_id: usages_by_id.get(image_id, [])
    monkeypatch.setattr("lorairo.cli.commands.dataset._build_repository", MagicMock(return_value=repo))
    return repo


def test_usage_json_with_image_id_option(mock_dataset_repo: MagicMock) -> None:
    """`--image-id` 指定で複数版・複数フォルダの所属と学習テキストを JSONL で返す。"""
    result = runner.invoke(app, ["--json", "dataset", "usage", "--image-id", "42", "-p", "proj"])

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    items = [r for r in rows if r["kind"] == "item"]
    summary = rows[-1]

    assert len(items) == 3
    assert [
        (item["dataset"], item["version"], item["dir_name"], item["texts"][0]["raw_text"]) for item in items
    ] == [
        ("kariginu", "v01", "10_kariginu", "Kariginu, [bracket], (tag:1.2)"),
        ("kariginu", "v01", "5_style", "style, long_sleeves"),
        ("kariginu", "v02", "10_kariginu", "Kariginu, smile"),
    ]
    assert items[0]["trigger_word"] == "Kariginu"
    assert items[1]["trigger_word"] is None
    assert items[1]["texts"][0]["is_edited"] is True
    assert items[2]["parent_version_id"] == 10
    assert summary["kind"] == "result"
    assert summary["ok"] is True
    assert summary["image_id"] == 42
    assert (summary["usages"], summary["datasets"], summary["versions"], summary["folders"]) == (
        3,
        1,
        2,
        3,
    )
    mock_dataset_repo.list_image_usage.assert_called_once_with(42)


def test_usage_positional_image_id_rich_output_preserves_brackets(mock_dataset_repo: MagicMock) -> None:
    """位置引数でも指定でき、人間向け出力で `[]` が Rich markup に潰されない。"""
    result = runner.invoke(app, ["dataset", "usage", "42", "-p", "proj"])

    assert result.exit_code == 0, result.output
    assert "image_id: 42" in result.stdout
    assert (
        "kariginu / v01 (version_id=10)  10_kariginu/img_a  repeats=10  trigger=Kariginu" in result.stdout
    )
    assert "  .txt: Kariginu, [bracket], (tag:1.2)" in result.stdout
    assert "kariginu / v01 (version_id=10)  5_style/img_a_style  repeats=5  trigger=-" in result.stdout
    assert "total: 3 usage(s)" in result.stdout


def test_usage_unused_image_returns_empty_without_error(mock_dataset_repo: MagicMock) -> None:
    """使われていない画像は JSON・人間向けのどちらでも空の一覧を返し終了コード 0 になる。"""
    json_res = runner.invoke(app, ["--json", "dataset", "usage", "--image-id", "999", "-p", "proj"])
    assert json_res.exit_code == 0, json_res.output
    rows = [json.loads(line) for line in json_res.stdout.splitlines() if line.strip()]
    assert [r for r in rows if r["kind"] == "item"] == []
    assert rows[-1]["kind"] == "result"
    assert rows[-1]["ok"] is True
    assert rows[-1]["image_id"] == 999
    assert (rows[-1]["usages"], rows[-1]["datasets"], rows[-1]["versions"], rows[-1]["folders"]) == (
        0,
        0,
        0,
        0,
    )

    text_res = runner.invoke(app, ["dataset", "usage", "999", "-p", "proj"])
    assert text_res.exit_code == 0, text_res.output
    assert "image_id: 999" in text_res.stdout
    assert "total: 0 usage(s)" in text_res.stdout


@pytest.mark.parametrize(
    "extra_args",
    [
        [],
        ["42", "--image-id", "57"],
        ["--image-id", "0"],
    ],
)
def test_usage_invalid_image_id_arguments_exit_2(
    mock_dataset_repo: MagicMock, extra_args: list[str]
) -> None:
    result = runner.invoke(app, ["--json", "dataset", "usage", *extra_args, "-p", "proj"])

    assert result.exit_code == 2
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert rows[-1]["kind"] == "error"
    assert rows[-1]["code"] == "INVALID_INPUT"
    mock_dataset_repo.list_image_usage.assert_not_called()
