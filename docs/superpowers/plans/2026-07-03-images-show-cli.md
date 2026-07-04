# images show CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `lorairo-cli images show` command that returns an image's current tags, captions, scores, and ratings, so an agent has the material it needs to decide a tag-fix diff before calling the existing `tags add/remove/replace` commands.

**Architecture:** Extract the CSV `image_ids` parsing/validation logic that `tags.py` already has into a shared `_image_ids.py` helper module (removes duplication before adding a third caller). Add `images show` to `src/lorairo/cli/commands/images.py`, reusing the existing `ImageRepository.get_image_annotations()` method unchanged. Register the new command in `src/lorairo/cli/introspection.py` so `list-commands` / `describe` pick it up. Regenerate `docs/cli.md`.

**Tech Stack:** Python 3.13, Typer/Click CLI, Pydantic (introspection schemas), pytest + `typer.testing.CliRunner`.

## Global Constraints

- Implementation touches `src/` and `tests/` — per `.claude/rules/git-workflow.md` this MUST happen in a dedicated worktree (`.agents/worktree/<name>`) on a feature branch (`feat/images-show-cli`), not in the shared checkout on `main`.
- Design doc: `docs/superpowers/specs/2026-07-03-images-show-cli-design.md` — read it before starting; this plan implements it exactly (CSV batch input, no model-name resolution, reuse `get_image_annotations()` unchanged).
- Follow `.claude/rules/coding-style.md`: modern type hints (`list[int]`, `X | None`), Google-style docstrings, no `# type: ignore` / `# noqa`.
- Run `make format` and `uv run mypy -p lorairo` before each commit that touches `src/`.
- Before opening a PR, run the CI-equivalent filter from `.claude/rules/testing.md`:
  `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`.

---

### Task 1: Extract shared `_image_ids` helper and refactor `tags.py` to use it

**Files:**
- Create: `src/lorairo/cli/_image_ids.py`
- Create: `tests/unit/cli/test_image_ids_helper.py`
- Modify: `src/lorairo/cli/commands/tags.py` (remove duplicated `MAX_IMAGE_IDS` / `_parse_image_ids` / `_validate_image_ids_exist`, import from the new module instead)

**Interfaces:**
- Produces (used by Task 2 and by the refactored `tags.py`):
  - `MAX_IMAGE_IDS: int` (value `500`)
  - `parse_image_ids(image_ids_csv: str) -> list[int]` — raises `click.UsageError` on non-integer input
  - `validate_image_ids_exist(container: ServiceContainer, image_ids: list[int]) -> None` — raises `lorairo.public_api.exceptions.ImageNotFoundError` if any id is missing

This is a pure extraction (no behavior change): `tags.py` currently defines `MAX_IMAGE_IDS = 500` plus `_parse_image_ids` and `_validate_image_ids_exist` at `src/lorairo/cli/commands/tags.py:28-64`. `images.py` will need the identical logic for the new `show` command in Task 2, so the duplication is removed now rather than copy-pasted a third time.

- [ ] **Step 1: Write the failing test for the new helper module**

Create `tests/unit/cli/test_image_ids_helper.py`:

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

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/cli/test_image_ids_helper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lorairo.cli._image_ids'`

- [ ] **Step 3: Create `src/lorairo/cli/_image_ids.py`**

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

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/cli/test_image_ids_helper.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Refactor `tags.py` to use the shared helper**

In `src/lorairo/cli/commands/tags.py`, replace the import block (currently lines 9-21):

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

with:

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

Then delete the now-duplicated definitions (currently at `src/lorairo/cli/commands/tags.py:28-64`, right after `console = make_console()`):

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

Finally, in each of the three command functions (`add`, `remove`, `replace`), rename the two call sites each:
- `_parse_image_ids(image_ids_csv)` → `parse_image_ids(image_ids_csv)` (3 occurrences)
- `_validate_image_ids_exist(container, image_ids)` → `validate_image_ids_exist(container, image_ids)` (3 occurrences)

`MAX_IMAGE_IDS` is used as-is (same name, now imported instead of module-local).

- [ ] **Step 6: Run the full existing tags test suite to confirm no regression**

Run: `uv run pytest tests/unit/cli/test_commands_tags.py -v`
Expected: PASS (all 9 tests, same as before the refactor)

- [ ] **Step 7: Format, type-check, commit**

```bash
uv run ruff format src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py tests/unit/cli/test_image_ids_helper.py
uv run ruff check src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/_image_ids.py src/lorairo/cli/commands/tags.py tests/unit/cli/test_image_ids_helper.py
git commit -m "refactor(cli): extract shared image_ids CSV helper from tags.py"
```

---

### Task 2: Add `images show` command

**Files:**
- Modify: `src/lorairo/cli/commands/images.py`
- Create: `tests/unit/cli/test_commands_images_show.py`

**Interfaces:**
- Consumes: `parse_image_ids`, `validate_image_ids_exist`, `MAX_IMAGE_IDS` from `lorairo.cli._image_ids` (Task 1). `ImageRepository.get_image_annotations(image_id: int, *, include_rejected: bool = False) -> dict[str, Any]` (existing, unchanged, at `src/lorairo/database/repository/image.py:1217`) — returns a dict with keys `tags`, `captions`, `scores`, `score_labels`, `ratings`, `quality_summary`.
- Produces: CLI command `images show`, reachable via `lorairo-cli images show --project <name> --image-ids <csv> [--include-rejected] [--json]`. No new Python symbols consumed by later tasks (Task 3 references the command name as a string).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cli/test_commands_images_show.py`:

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

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/cli/test_commands_images_show.py -v`
Expected: FAIL — `show` is not a registered command (Typer/Click "No such command 'show'")

- [ ] **Step 3: Implement `images show`**

In `src/lorairo/cli/commands/images.py`, add the import (alongside the existing `from lorairo.database.filter_criteria import ImageFilterCriteria` line):

```python
from lorairo.cli._image_ids import MAX_IMAGE_IDS, parse_image_ids, validate_image_ids_exist
```

Then add the new command at the end of the file, after the existing `search_images` command:

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

    指定した image_ids の現行アノテーション（タグ/キャプション/スコア/レーティング）を
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/cli/test_commands_images_show.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full images + tags CLI test suite to confirm no regression**

Run: `uv run pytest tests/unit/cli/ -v`
Expected: PASS (all tests, including the pre-existing `test_commands_images.py`, `test_commands_images_search.py`, `test_commands_tags.py`)

- [ ] **Step 6: Format, type-check, commit**

```bash
uv run ruff format src/lorairo/cli/commands/images.py tests/unit/cli/test_commands_images_show.py
uv run ruff check src/lorairo/cli/commands/images.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/commands/images.py tests/unit/cli/test_commands_images_show.py
git commit -m "feat(cli): add images show command for reading current annotations"
```

---

### Task 3: Register `images show` in CLI introspection

**Files:**
- Modify: `src/lorairo/cli/introspection.py`
- Modify: `tests/unit/cli/test_introspection.py`

**Interfaces:**
- Consumes: nothing from earlier tasks besides the command existing (Task 2). Uses existing `_input`, `_output`, `_f`, `ERROR_MODEL`, `ToolSpec`, `ModelSpec`, `FieldSpec`, `TOOL_SPECS` helpers already defined in `introspection.py`.
- Produces: `ImagesShowInputSchema`, `ImagesShowItem`, `ImagesShowResult` Pydantic classes; a `"images show"` entry in `TOOL_SPECS`. These are internal to introspection and not consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/cli/test_introspection.py`:

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

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/cli/test_introspection.py -k images_show -v`
Expected: FAIL — `"images show" in by_path` is `False`; `describe "images show"` raises `ValueError: Unknown command path`

- [ ] **Step 3: Add the Pydantic schema classes**

In `src/lorairo/cli/introspection.py`, add after the `ImagesUpdateResult` class (which currently ends the `images update` section, just before `class ExportCreateInputSchema`):

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

- [ ] **Step 4: Register the `ToolSpec` entry**

In `src/lorairo/cli/introspection.py`, add a new entry to the `TOOL_SPECS` dict, immediately after the `"images search"` entry and before `"tags add"`:

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

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/cli/test_introspection.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 6: Format, type-check, commit**

```bash
uv run ruff format src/lorairo/cli/introspection.py tests/unit/cli/test_introspection.py
uv run ruff check src/lorairo/cli/introspection.py --fix
uv run mypy -p lorairo
git add src/lorairo/cli/introspection.py tests/unit/cli/test_introspection.py
git commit -m "feat(cli): register images show in CLI introspection"
```

---

### Task 4: Regenerate `docs/cli.md`

**Files:**
- Modify: `docs/cli.md` (generated, do not hand-edit)

**Interfaces:**
- Consumes: `TOOL_SPECS["images show"]` registered in Task 3.
- Produces: nothing consumed by later tasks (documentation-only, terminal task).

- [ ] **Step 1: Regenerate the docs**

Run: `uv run python scripts/generate_cli_docs.py`
Expected: exits 0, `docs/cli.md` is rewritten with an `### images show` section (alphabetically between `images register` and `images update`, matching the sorted `TOOL_SPECS` iteration order).

- [ ] **Step 2: Verify the new section is present**

Run: `grep -A 5 '### \`images show\`' docs/cli.md`
Expected output includes:
```
### `images show`

Show current tags, captions, scores, and ratings for images (read-only). Use as judgment material before tags add/remove/replace.
```

- [ ] **Step 3: Commit**

```bash
git add docs/cli.md
git commit -m "docs: regenerate CLI reference for images show"
```

---

### Task 5: Full local verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full CI-equivalent filter**

Run: `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`
Expected: all tests PASS, 0 failures (this is the exact filter the CI "LoRAIro Unit Tests" / "Integration Tests" jobs use — see `.claude/rules/testing.md`)

- [ ] **Step 2: Run mypy across the whole package**

Run: `uv run mypy -p lorairo`
Expected: `Success: no issues found`

- [ ] **Step 3: Manual smoke test against a real project**

Run (adjust `<project>` and `<image_id>` to a real project/image in `lorairo_data/`):
```bash
uv run lorairo-cli images show --project <project> --image-ids <image_id> --json
uv run lorairo-cli images show --project <project> --image-ids <image_id>
```
Expected: JSON mode emits one `kind:"item"` row with `tags`/`captions`/`scores`/`score_labels`/`ratings`/`quality_summary` matching what the GUI detail panel shows for that image, followed by a `kind:"result"` row with `ok:true`. Non-JSON mode prints a human-readable `Image <id>` block.

No commit for this task — it is the final gate before opening the PR (see `superpowers:finishing-a-development-branch` for PR creation, per `.claude/rules/git-workflow.md`).
