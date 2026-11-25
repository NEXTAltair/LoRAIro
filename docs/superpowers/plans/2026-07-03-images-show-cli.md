# `images show` CLI 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 画像の現行タグ、キャプション、スコア、レーティングを返す読み取り専用の `lorairo-cli images show` コマンドを追加する。これにより、エージェントが既存の `tags add/remove/replace` コマンドを呼ぶ前に、タグ修正の差分を判断するための材料を取得できるようにする。

**Architecture:** `tags.py` がすでに持つ CSV 形式 `image_ids` のパース・検証ロジックを共有ヘルパーモジュール `_image_ids.py` へ抽出し、3 箇所目の呼び出し元を増やす前に重複を解消する。続いて `src/lorairo/cli/commands/images.py` に `images show` を追加し、既存の `ImageRepository.get_image_annotations()` を無変更で再利用する。さらに `src/lorairo/cli/introspection.py` に新コマンドを登録して `list-commands` と `describe` へ反映し、`docs/cli.md` を再生成する。

**Tech Stack:** Python 3.13、Typer/Click CLI、Pydantic(イントロスペクション用スキーマ)、pytest および `typer.testing.CliRunner`

## 全体制約

- 本実装は `src/` と `tests/` を変更するため、`.claude/rules/git-workflow.md` に従い `main` の共有チェックアウトではなく専用ワークツリー(`.agents/worktree/<name>`)のフィーチャーブランチ(`feat/images-show-cli`)で作業する。
- 着手前に設計書 `docs/superpowers/specs/2026-07-03-images-show-cli-design.md` を読む。本計画は設計書どおり(CSV バッチ入力、モデル名解決なし、`get_image_annotations()` を無変更で再利用)に実装する。
- `.claude/rules/coding-style.md` に従い、モダンな型ヒント(`list[int]`、`X | None`)と Google スタイルの docstring を用い、`# type: ignore` および `# noqa` は禁止する。
- `src/` を変更したコミットの前に、必ず `make format` と `uv run mypy -p lorairo` を実行する。
- PR 作成前に、`.claude/rules/testing.md` の CI 相当フィルタ `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` を実行する。

---

### Task 1: 共有ヘルパー `_image_ids` を抽出し、`tags.py` をリファクタリングする

**Files:**
- Create: `src/lorairo/cli/_image_ids.py`
- Create: `tests/unit/cli/test_image_ids_helper.py`
- Modify: `src/lorairo/cli/commands/tags.py`(重複する `MAX_IMAGE_IDS`、`_parse_image_ids`、`_validate_image_ids_exist` を削除し、新モジュールからインポートする)

**Interfaces:**
- 提供(Produces、Task 2 およびリファクタ後の `tags.py` が利用):
  - `MAX_IMAGE_IDS: int`(値は `500`)
  - `parse_image_ids(image_ids_csv: str) -> list[int]`(整数以外の入力で `click.UsageError` を送出)
  - `validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None`(存在しない ID があれば `lorairo.public_api.exceptions.ImageNotFoundError` を送出)

本タスクは振る舞いを変えない純粋な抽出である。現在 `tags.py`(`src/lorairo/cli/commands/tags.py:28-64`)が `MAX_IMAGE_IDS = 500`、`_parse_image_ids`、`_validate_image_ids_exist` を定義している。Task 2 の `images show` でも同一ロジックが必要になるため、コピーペーストせずこの段階で共通化する。

- [ ] **Step 1: 新ヘルパーモジュールの失敗するテストを書く**

`tests/unit/cli/test_image_ids_helper.py` を作成する。

```python
"""_image_ids 共有ヘルパーのユニットテスト。"""

from unittest.mock import MagicMock

import click
import pytest

from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.public_api.exceptions import ImageNotFoundError


@pytest.mark.unit
class TestParseImageIds:
    def test_parses_comma_separated_ints(self) -> None:
        assert parse_image_ids("1,2,3") == [1, 2, 3]

    def test_strips_whitespace(self) -> None:
        assert parse_image_ids(" 1 , 2 ") == [1, 2]

    def test_ignores_empty_segments(self) -> None:
        assert parse_image_ids("1,,2,") == [1, 2]

    def test_raises_usage_error_on_non_integer(self) -> None:
        with pytest.raises(click.UsageError):
            parse_image_ids("1,abc")

    def test_max_image_ids_constant_is_500(self) -> None:
        assert MAX_IMAGE_IDS == 500


@pytest.mark.unit
class TestValidateImageIdsExist:
    def test_passes_when_all_ids_found(self) -> None:
        container = MagicMock()
        container.db_manager.image_repo.get_images_by_filter.return_value = (
            [{"id": 1}, {"id": 2}],
            2,
        )
        validate_image_ids_exist(container, [1, 2])  # does not raise

    def test_raises_image_not_found_for_missing_id(self) -> None:
        container = MagicMock()
        container.db_manager.image_repo.get_images_by_filter.return_value = ([{"id": 1}], 1)
        with pytest.raises(ImageNotFoundError) as exc_info:
            validate_image_ids_exist(container, [1, 2])
        assert exc_info.value.image_id == 2
```

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_image_ids_helper.py -v`
期待結果: `ModuleNotFoundError: No module named 'lorairo.cli._image_ids'` で失敗する。

- [ ] **Step 3: `src/lorairo/cli/_image_ids.py` を作成する**

```python
"""Shared image_id CSV parsing/validation for agent-facing CLI commands.

``tags add/remove/replace`` (write) and ``images show`` (read) all accept the
same ``--image-ids`` comma-separated form with the same 500-id cap and the
same "does this image exist" check. Centralized here so both call sites stay
in sync.
"""

from __future__ import annotations

import click

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.services.service_container import ServiceContainer

MAX_IMAGE_IDS = 500


def parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換する。

    Args:
        image_ids_csv: カンマ区切りの画像 ID 文字列。

    Returns:
        画像 ID の整数リスト。

    Raises:
        click.UsageError: 整数に変換できない値が含まれていた場合。
    """
    try:
        return [int(x.strip()) for x in image_ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--image-ids には整数のみ指定可: {e}") from e


def validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None:
    """全 image_id が DB に存在するか確認する。

    Args:
        container: サービスコンテナ。
        image_ids: 存在確認する画像 ID のリスト。

    Raises:
        ImageNotFoundError: リスト内に存在しない画像 ID があった場合。
    """
    criteria = ImageFilterCriteria(image_ids=image_ids, include_nsfw=True)
    records, _ = container.db_manager.image_repo.get_images_by_filter(criteria)
    found_ids = {int(r["id"]) for r in records}
    missing = [i for i in image_ids if i not in found_ids]
    if missing:
        raise ImageNotFoundError(missing[0])
```

- [ ] **Step 4: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_image_ids_helper.py -v`
期待結果: 6 件すべて通る。

- [ ] **Step 5: `tags.py` を共有ヘルパー利用へリファクタリングする**

`src/lorairo/cli/commands/tags.py` のインポートブロック(現行 9–21 行目)を置き換える。

変更前:
```python
from __future__ import annotations

import click
import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.public_api.exceptions import ImageNotFoundError
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import ServiceContainer, get_service_container
```

変更後:
```python
from __future__ import annotations

import click
import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._glyphs import OK
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container
```

続いて、重複した定義(現行 `src/lorairo/cli/commands/tags.py:28-64`、`console = make_console()` の直後)を削除する。

```python
MAX_IMAGE_IDS = 500


def _parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換。不正値は UsageError。
    ...
    """
    try:
        return [int(x.strip()) for x in image_ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--image-ids には整数のみ指定可: {e}") from e


def _validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None:
    """全 image_id が DB に存在するか確認。存在しなければ ImageNotFoundError。
    ...
    """
    criteria = ImageFilterCriteria(image_ids=image_ids, include_nsfw=True)
    records, _ = container.db_manager.image_repo.get_images_by_filter(criteria)
    found_ids = {int(r["id"]) for r in records}
    missing = [i for i in image_ids if i not in found_ids]
    if missing:
        raise ImageNotFoundError(missing[0])
```

最後に、3 つのコマンド関数(`add`、`remove`、`replace`)内の呼び出しをそれぞれ改名する。
- `_parse_image_ids(image_ids_csv)` → `parse_image_ids(image_ids_csv)`(3 箇所)
- `_validate_image_ids_exist(container, image_ids)` → `validate_image_ids_exist(container, image_ids)`(3 箇所)

`MAX_IMAGE_IDS` は名称が変わらないためそのまま使用する。

- [ ] **Step 6: 既存の `tags` テストスイートを実行してリグレッションがないことを確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_commands_tags.py -v`
期待結果: リファクタ前と同様に 9 件すべて通る。

- [ ] **Step 7: フォーマット、型チェック、コミットを実行する**

```bash
uv run ruff format src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py tests/unit/cli/test_image_ids_helper.py
uv run ruff check src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py tests/unit/cli/test_image_ids_helper.py
git commit -m "refactor(cli): extract shared image_ids CSV helper from tags.py"
```

---

### Task 2: `images show` コマンドを追加する

**Files:**
- Modify: `src/lorairo/cli/commands/images.py`
- Create: `tests/unit/cli/test_commands_images_show.py`

**Interfaces:**
- 依存(Consumes): Task 1 の `lorairo.cli._image_ids`(`parse_image_ids`、`validate_image_ids_exist`、`MAX_IMAGE_IDS`)、および既存の `ImageRepository.get_image_annotations(image_id: int, *, include_rejected: bool = False) -> dict[str, Any]`(`src/lorairo/database/repository/image.py:1217`、無変更)。戻り値の辞書は `tags`、`captions`、`scores`、`score_labels`、`ratings`、`quality_summary` キーを持つ。
- 提供(Produces): `lorairo-cli images show --project <name> --image-ids <csv> [--include-rejected] [--json]` で呼び出せる CLI コマンド。後続タスクから参照される新規 Python シンボルはない(Task 3 はコマンド名を文字列で参照する)。

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/cli/test_commands_images_show.py` を作成する。

```python
"""images show コマンドのユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _annotations_for(image_id: int) -> dict:
    return {
        "tags": [
            {
                "id": 1,
                "tag": f"tag-{image_id}",
                "tag_id": 10,
                "model_id": 3,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
                "rejected_at": None,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        "captions": [],
        "scores": [],
        "score_labels": [],
        "ratings": [],
        "quality_summary": {},
    }


def _make_container(image_ids: list[int]) -> MagicMock:
    container = MagicMock()
    records = [{"id": i} for i in image_ids]
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.image_repo.get_image_annotations.side_effect = (
        lambda image_id, include_rejected=False: _annotations_for(image_id)
    )
    return container


@pytest.fixture
def mock_show_context(monkeypatch: pytest.MonkeyPatch):
    container = _make_container([42, 57])
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestImagesShow:
    def test_show_single_image_json(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 1
        assert items[0]["image_id"] == 42
        assert items[0]["tags"][0]["tag"] == "tag-42"
        assert result_row["ok"] is True
        assert result_row["target_images"] == 1

    def test_show_batch_csv(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42,57"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        assert {row["image_id"] for row in items} == {42, 57}

    def test_show_passes_include_rejected_flag(self, mock_show_context: MagicMock) -> None:
        runner.invoke(
            app,
            [
                "--json",
                "images",
                "show",
                "--project",
                "proj",
                "--image-ids",
                "42",
                "--include-rejected",
            ],
        )
        mock_show_context.db_manager.image_repo.get_image_annotations.assert_any_call(
            42, include_rejected=True
        )

    def test_show_missing_image_id_errors(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "999"],
        )
        assert result.exit_code != 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        error_row = next(r for r in lines if r.get("kind") == "error")
        assert error_row["code"] == "NOT_FOUND"

    def test_show_over_500_ids_rejected(self, mock_show_context: MagicMock) -> None:
        csv_ids = ",".join(str(i) for i in range(1, 502))
        result = runner.invoke(
            app,
            ["images", "show", "--project", "proj", "--image-ids", csv_ids],
        )
        assert result.exit_code != 0
```

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_commands_images_show.py -v`
期待結果: `show` コマンドが未登録のため、Typer/Click の `No such command 'show'` で失敗する。

- [ ] **Step 3: `images show` を実装する**

`src/lorairo/cli/commands/images.py` の既存 `from lorairo.database.filter_criteria import ImageFilterCriteria` の近くにインポートを追加する。

```python
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
```

続いて、ファイル末尾(既存の `search_images` コマンドの後)に新コマンドを追加する。

```python
@app.command("show")
def show(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    include_rejected: bool = typer.Option(
        False,
        "--include-rejected",
        help="Include soft-rejected tags/captions in the output.",
    ),
) -> None:
    """Show current tags, captions, scores, and ratings for images (read-only).

    指定した image_ids の現行アノテーション(タグ/キャプション/スコア/レーティング)を
    表示します。タグ修正の判断材料として使うためのコマンドで、書き込みは行いません。

    Example:
        lorairo-cli images show --project proj --image-ids 42,57 --json
    """
    with command_boundary():
        api_get_project(project)
        image_ids = parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        container = get_service_container()
        container.set_active_project(project)
        validate_image_ids_exist(container, image_ids)

        image_repo = container.db_manager.image_repo
        annotations_by_id = {
            image_id: image_repo.get_image_annotations(image_id, include_rejected=include_rejected)
            for image_id in image_ids
        }

        if is_json_mode():
            for image_id in image_ids:
                annotations = annotations_by_id[image_id]
                emit_item(
                    {
                        "image_id": image_id,
                        "tags": annotations["tags"],
                        "captions": annotations["captions"],
                        "scores": annotations["scores"],
                        "score_labels": annotations["score_labels"],
                        "ratings": annotations["ratings"],
                        "quality_summary": annotations["quality_summary"],
                    }
                )
            emit_result(f"{len(image_ids)} image(s)", target_images=len(image_ids))
        else:
            for image_id in image_ids:
                annotations = annotations_by_id[image_id]
                tag_names = [t["tag"] for t in annotations["tags"]]
                caption_texts = [c["caption"] for c in annotations["captions"]]
                console.print(f"\n[bold]Image {image_id}[/bold]")
                console.print(f"  tags: {', '.join(tag_names) if tag_names else '(none)'}")
                console.print(
                    f"  captions: {' | '.join(caption_texts) if caption_texts else '(none)'}"
                )
```

- [ ] **Step 4: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_commands_images_show.py -v`
期待結果: 5 件すべて通る。

- [ ] **Step 5: CLI テスト全体を実行してリグレッションがないことを確認する**

実行コマンド: `uv run pytest tests/unit/cli/ -v`
期待結果: 既存の `test_commands_images.py`、`test_commands_images_search.py`、`test_commands_tags.py` を含め、すべて通る。

- [ ] **Step 6: フォーマット、型チェック、コミットを実行する**

```bash
uv run ruff format src/lorairo/cli/commands/images.py tests/unit/cli/test_commands_images_show.py
uv run ruff check src/lorairo/cli/commands/images.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/commands/images.py tests/unit/cli/test_commands_images_show.py
git commit -m "feat(cli): add images show command for reading current annotations"
```

---

### Task 3: `images show` を CLI イントロスペクションへ登録する

**Files:**
- Modify: `src/lorairo/cli/introspection.py`
- Modify: `tests/unit/cli/test_introspection.py`

**Interfaces:**
- 依存(Consumes): Task 2 で追加したコマンドの存在、および `introspection.py` に既存の `_input`、`_output`、`_f`、`ERROR_MODEL`、`ToolSpec`、`ModelSpec`、`FieldSpec`、`TOOL_SPECS`。
- 提供(Produces): Pydantic クラス `ImagesShowInputSchema`、`ImagesShowItem`、`ImagesShowResult`、および `TOOL_SPECS` 内の `"images show"` エントリ(イントロスペクション内部向けであり、後続タスクから直接参照されない)。

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/cli/test_introspection.py` の末尾に以下を追記する。

```python
def test_list_commands_includes_images_show() -> None:
    """images show が list-commands に現れ read-only である。"""
    result = runner.invoke(app, ["--json", "list-commands"])

    assert result.exit_code == 0
    items = [row for row in _jsonl(result.stdout) if row["kind"] == "item"]
    by_path = {row["path"]: row for row in items}

    assert "images show" in by_path
    assert by_path["images show"]["read_only"] is True
    assert by_path["images show"]["side_effects"] == ["db_read"]


def test_describe_images_show_exposes_required_fields() -> None:
    """describe images show が project / image_ids 必須フィールドを返す。"""
    result = runner.invoke(app, ["--json", "describe", "images show"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    assert rows[0]["path"] == "images show"

    input_row = next(
        row for row in rows if row.get("type") == "model" and row["name"] == "ImagesShowInput"
    )
    fields = {f["name"]: f for f in input_row["fields"]}
    assert fields["project"]["required"] is True
    assert fields["image_ids"]["required"] is True
    assert fields["include_rejected"]["default"] is False


def test_describe_images_show_json_schema_includes_item_and_result() -> None:
    """images show --schema json_schema が Input/Item/Result スキーマを返す。"""
    result = runner.invoke(app, ["--json", "describe", "images show", "--schema", "json_schema"])

    assert result.exit_code == 0
    rows = _jsonl(result.stdout)
    schema_names = {row["name"] for row in rows if row.get("type") == "schema"}
    assert "ImagesShowInput" in schema_names
    assert "ImagesShowItem" in schema_names
    assert "ImagesShowResult" in schema_names

    item_schema = next(row for row in rows if row.get("name") == "ImagesShowItem")
    item_props = set(item_schema["schema"]["properties"])
    assert {"image_id", "tags", "captions", "scores", "score_labels", "ratings", "quality_summary"} <= (
        item_props
    )
```

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_introspection.py -k images_show -v`
期待結果: `"images show" in by_path` が `False` となり、`describe "images show"` で `ValueError: Unknown command path` が発生して失敗する。

- [ ] **Step 3: Pydantic スキーマクラスを追加する**

`src/lorairo/cli/introspection.py` の `ImagesUpdateResult` クラスの直後(`class ExportCreateInputSchema` の直前)に以下を追加する。

```python
class ImagesShowInputSchema(BaseModel):
    """Implemented options surface accepted by ``images show``."""

    project: str
    image_ids: str = Field(description="Comma-separated image IDs, max 500.")
    include_rejected: bool = False

    model_config = ConfigDict(title="ImagesShowInput")


class ImagesShowItem(BaseModel):
    """JSONL item payload emitted per image by ``images show --json``."""

    image_id: int
    tags: list[dict[str, Any]]
    captions: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    score_labels: list[dict[str, Any]]
    ratings: list[dict[str, Any]]
    quality_summary: dict[str, Any]

    model_config = ConfigDict(title="ImagesShowItem")


class ImagesShowResult(BaseModel):
    """JSONL result payload emitted by ``images show --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    target_images: int

    model_config = ConfigDict(title="ImagesShowResult")
```

- [ ] **Step 4: `ToolSpec` エントリを登録する**

`src/lorairo/cli/introspection.py` の `TOOL_SPECS` 辞書内で、`"images search"` の直後かつ `"tags add"` の直前に以下を追加する。

```python
    "images show": ToolSpec(
        name="images show",
        path="images show",
        summary=(
            "Show current tags, captions, scores, and ratings for images (read-only). "
            "Use as judgment material before tags add/remove/replace."
        ),
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ImagesShowInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, max 500.",
                    ),
                    _f(
                        "include_rejected",
                        "bool",
                        default=False,
                        description="Include soft-rejected tags/captions in the output.",
                    ),
                ),
                schema=ImagesShowInputSchema,
            ),
        ),
        outputs=(
            _output(
                "ImagesShowItem",
                (
                    _f("image_id", "int"),
                    _f("tags", "list[dict]"),
                    _f("captions", "list[dict]"),
                    _f("scores", "list[dict]"),
                    _f("score_labels", "list[dict]"),
                    _f("ratings", "list[dict]"),
                    _f("quality_summary", "dict"),
                ),
                schema=ImagesShowItem,
            ),
            _output(
                "ImagesShowResult",
                (_f("target_images", "int"),),
                schema=ImagesShowResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
```

- [ ] **Step 5: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/cli/test_introspection.py -v`
期待結果: 新規 3 件を含めすべて通る。

- [ ] **Step 6: フォーマット、型チェック、コミットを実行する**

```bash
uv run ruff format src/lorairo/cli/introspection.py tests/unit/cli/test_introspection.py
uv run ruff check src/lorairo/cli/introspection.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/introspection.py tests/unit/cli/test_introspection.py
git commit -m "feat(cli): register images show in CLI introspection"
```

---

### Task 4: `docs/cli.md` を再生成する

**Files:**
- Modify: `docs/cli.md`(自動生成物のため手編集しない)

**Interfaces:**
- 依存(Consumes): Task 3 で登録した `TOOL_SPECS["images show"]`。
- 提供(Produces): なし(ドキュメント生成のみの最終タスク)。

- [ ] **Step 1: ドキュメントを再生成する**

実行コマンド: `uv run python scripts/generate_cli_docs.py`
期待結果: 終了コード 0 で完了し、`docs/cli.md` に `### images show` セクションが出力される(ソート済みの `TOOL_SPECS` 順に従い、`images register` と `images update` の間に配置される)。

- [ ] **Step 2: 新セクションの出力を確認する**

実行コマンド: `grep -A 5 '### \`images show\`' docs/cli.md`
期待される出力例:
```
### `images show`

Show current tags, captions, scores, and ratings for images (read-only). Use as judgment material before tags add/remove/replace.
```

- [ ] **Step 3: コミットする**

```bash
git add docs/cli.md
git commit -m "docs: regenerate CLI reference for images show"
```

---

### Task 5: ローカル全体検証

**Files:** なし(検証のみ)

- [ ] **Step 1: CI 相当フィルタで全テストを実行する**

実行コマンド: `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`
期待結果: 失敗ゼロで全テストが通る(CI の「LoRAIro Unit Tests」および「Integration Tests」ジョブと同一フィルタ。`.claude/rules/testing.md` を参照)。

- [ ] **Step 2: パッケージ全体の mypy を実行する**

実行コマンド: `uv run mypy -p lorairo`
期待結果: `Success: no issues found` が出力される。

- [ ] **Step 3: 実プロジェクトで手動スモークテストを行う**

`lorairo_data/` 内の実プロジェクト名と画像 ID に置き換えて以下を実行する。
```bash
uv run lorairo-cli images show --project <project> --image-ids <image_id> --json
uv run lorairo-cli images show --project <project> --image-ids <image_id>
```
期待結果: JSON モードでは、GUI 詳細パネルの表示内容と一致する `tags`、`captions`、`scores`、`score_labels`、`ratings`、`quality_summary` を持つ `kind:"item"` 行が 1 行出力され、続いて `ok:true` の `kind:"result"` 行が出力される。非 JSON モードでは人間可読な `Image <id>` ブロックが表示される。

本タスクは PR 作成前の最終ゲートであるためコミットは行わない(PR 作成は `.claude/rules/git-workflow.md` に従い `superpowers:finishing-a-development-branch` を参照)。
