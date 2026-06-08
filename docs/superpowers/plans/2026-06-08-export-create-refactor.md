# export create Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `export create` から検索責務を完全に分離し、`--image-ids` を必須とし常に全形式（タグtxt・キャプションtxt・JSON）を出力するシンプルなコマンドに整理する (Issue #698)

**Architecture:** 案A準拠。`export.py` から検索ヘルパー・検索オプション・`--format` を削除し、`--image-ids` を必須オプションとして追加。export service の `export_dataset_txt_format` と `export_dataset_json_format` を両方呼び出す。

**Tech Stack:** Typer, typer.testing.CliRunner, pytest

---

## ファイル構成

| 操作 | ファイル |
|---|---|
| Modify | `src/lorairo/cli/commands/export.py` (大幅簡略化) |
| Modify | `tests/unit/cli/test_commands_export.py` (既存テスト更新 + 新規追加) |

---

### Task 1: `export.py` を書き直し

**Files:**
- Modify: `src/lorairo/cli/commands/export.py`

- [ ] **Step 1: 既存 export テストを確認**

```bash
uv run pytest tests/unit/cli/test_commands_export.py -v 2>&1 | head -40
```

現在のテストの構造とどれが変更の影響を受けるかを確認する。

- [ ] **Step 2: `export.py` を新しいシンプルな実装に書き直す**

`src/lorairo/cli/commands/export.py` の全内容を以下に置き換える:

```python
"""Dataset export commands.

データセット エクスポート コマンド。
image_ids を受け取り、タグ txt / キャプション txt / JSON の全形式を出力する。
検索責務は ``lorairo-cli images search`` に委譲する (Issue #698)。
"""

from pathlib import Path

import typer

from lorairo.api.project import get_project as api_get_project
from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.services.service_container import get_service_container

import click

app = typer.Typer(help="Dataset export commands")
console = make_console()


def _parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換。不正値は UsageError。"""
    try:
        return [int(x.strip()) for x in image_ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--image-ids には整数のみ指定可: {e}") from e


@app.command("create")
def create(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    image_ids_csv: str = typer.Option(
        ...,
        "--image-ids",
        help="Comma-separated image IDs to export",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for exported dataset",
    ),
    resolution: int = typer.Option(
        512,
        "--resolution",
        "-r",
        help="Target resolution for processed images",
    ),
) -> None:
    """Create a dataset export from a list of image IDs.

    指定した image_ids からデータセットをエクスポートします。
    タグ txt、キャプション txt、JSON の全形式を出力します。

    画像の検索には ``lorairo-cli images search`` を使用してください。

    Example:
        # まず検索で image_ids を取得
        lorairo-cli images search --project proj --query-file search.json --json \\
          | jq -r 'select(.kind=="item")|.image_id' | paste -sd, > ids.txt

        # 取得した ids でエクスポート
        lorairo-cli export create --project proj --image-ids $(cat ids.txt) --output /tmp/out
    """
    with command_boundary():
        api_get_project(project)

        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)

        export_service = container.dataset_export_service
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        rich = not is_json_mode()
        if rich:
            console.print(f"[cyan]Exporting {len(image_ids)} image(s) to {output}[/cyan]")

        # タグ txt + キャプション txt
        txt_path = export_service.export_dataset_txt_format(image_ids, output_path, resolution)
        # JSON メタデータ
        json_path = export_service.export_dataset_json_format(image_ids, output_path, resolution)

        if is_json_mode():
            emit_result(
                "Export completed successfully.",
                output_path=str(txt_path),
                total_images=len(image_ids),
                resolution=resolution,
            )
        else:
            from rich.table import Table
            table = Table()
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Images", str(len(image_ids)))
            table.add_row("Resolution", f"{resolution}px")
            table.add_row("Output Path", str(txt_path))
            console.print(table)
            console.print("\n[green]Export completed successfully![/green]")
```

- [ ] **Step 3: 影響を受ける既存テストを更新**

`tests/unit/cli/test_commands_export.py` を開き、以下の変更を行う:

1. `--tags`, `--manual-rating` などの旧オプションを使うテストを削除または更新
2. `--image-ids` を使う新しいテストを追加

既存テストファイルの冒頭に以下の新しいテストを追加（既存テストは削除）:

```python
"""export create コマンドのユニットテスト。"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _make_export_container(tmp_path: Path) -> MagicMock:
    """export テスト用 ServiceContainer モックを生成する。"""
    container = MagicMock()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    container.dataset_export_service.export_dataset_txt_format.return_value = out_dir
    container.dataset_export_service.export_dataset_json_format.return_value = out_dir
    return container


@pytest.fixture
def mock_export_context(tmp_path, monkeypatch):
    """project 確認と ServiceContainer をモック。"""
    container = _make_export_container(tmp_path)
    monkeypatch.setattr(
        "lorairo.cli.commands.export.api_get_project", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "lorairo.cli.commands.export.get_service_container", MagicMock(return_value=container)
    )
    return container, tmp_path


@pytest.mark.unit
class TestExportCreate:
    def test_create_with_image_ids_calls_both_exporters(self, mock_export_context, tmp_path):
        """--image-ids 指定時に txt と json 両エクスポーターが呼ばれる。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "export", "create",
                "--project", "proj",
                "--image-ids", "1,2,3",
                "--output", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        container.dataset_export_service.export_dataset_txt_format.assert_called_once()
        container.dataset_export_service.export_dataset_json_format.assert_called_once()

    def test_create_without_image_ids_fails(self, mock_export_context, tmp_path):
        """--image-ids なしは exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export", "create",
                "--project", "proj",
                "--output", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_json_output_has_result_row(self, mock_export_context, tmp_path):
        """--json 出力に kind=result 行が含まれる。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "--json",
                "export", "create",
                "--project", "proj",
                "--image-ids", "1,2,3",
                "--output", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().splitlines() if l.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["total_images"] == 3

    def test_create_invalid_image_ids_fails(self, mock_export_context, tmp_path):
        """非整数の --image-ids は exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export", "create",
                "--project", "proj",
                "--image-ids", "abc,def",
                "--output", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_resolution_passed_to_exporters(self, mock_export_context, tmp_path):
        """--resolution が両エクスポーターに渡される。"""
        container, _ = mock_export_context
        runner.invoke(
            app,
            [
                "export", "create",
                "--project", "proj",
                "--image-ids", "1",
                "--output", str(tmp_path / "out"),
                "--resolution", "1024",
            ],
        )
        _, kwargs_txt = container.dataset_export_service.export_dataset_txt_format.call_args
        _, kwargs_json = container.dataset_export_service.export_dataset_json_format.call_args
        # resolution は positional arg として渡される
        call_args_txt = container.dataset_export_service.export_dataset_txt_format.call_args[0]
        call_args_json = container.dataset_export_service.export_dataset_json_format.call_args[0]
        assert 1024 in call_args_txt or call_args_txt[2] == 1024
        assert 1024 in call_args_json or call_args_json[2] == 1024
```

- [ ] **Step 4: テストを実行して通過確認**

```bash
uv run pytest tests/unit/cli/test_commands_export.py -v
```

期待: 全テスト PASSED

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/cli/commands/export.py tests/unit/cli/test_commands_export.py
git commit -m "feat(cli): simplify export create to --image-ids only, always all formats (Issue #698)"
```

---

### Task 2: CI-equivalent filter 実行 & PR 起票

- [ ] **Step 1: フォーマット・型チェック**

```bash
uv run ruff format src/lorairo/cli/commands/export.py
uv run ruff check src/lorairo/cli/commands/export.py --fix
uv run mypy -p lorairo 2>&1 | tail -20
```

期待: エラーなし

- [ ] **Step 2: CI-equivalent filter 実行**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q 2>&1 | tail -20
```

期待: 全テスト PASSED (既存テストに regression なし)

- [ ] **Step 3: push して PR 起票**

```bash
git push -u origin HEAD
gh pr create \
  --title "feat(cli): export create を --image-ids 専用に整理 (Issue #698)" \
  --body "$(cat <<'EOF'
## Summary
- `export create` から検索オプション（--tags / --manual-rating 等）を完全削除
- `--image-ids` を必須オプションとして追加
- `--format` を削除し常にタグ txt・キャプション txt・JSON の全形式を出力
- 検索責務は `images search` に分離

## Test plan
- [ ] `uv run pytest tests/unit/cli/test_commands_export.py -v`
- [ ] CI-equivalent filter 全 PASS 確認

Closes #698
EOF
)"
```
