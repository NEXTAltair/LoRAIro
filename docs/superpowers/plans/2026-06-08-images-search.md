# images search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lorairo-cli images search --query-file / --query -` コマンドを追加し、JSON 検索スキーマを受け取って read-only で画像を検索できるようにする (Issue #697)

**Architecture:** 案A準拠。`ImageFilterCriteria` にソートフィールドを追加し、`ImageRepository.get_images_by_filter` の ORDER BY を動的にする。JSON スキーマは Pydantic `ImageSearchQuery` モデルで定義し、`images.py` に `search` サブコマンドを追加。

**Tech Stack:** Typer, Pydantic v2, SQLAlchemy, typer.testing.CliRunner, pytest

---

## ファイル構成

| 操作 | ファイル |
|---|---|
| Modify | `src/lorairo/database/filter_criteria.py` (sort フィールド追加) |
| Modify | `src/lorairo/database/repository/image.py` (動的 ORDER BY) |
| Modify | `src/lorairo/cli/commands/images.py` (search コマンド + Pydantic モデル追加) |
| Create | `tests/unit/cli/test_commands_images_search.py` |

---

### Task 1: `ImageFilterCriteria` にソートフィールドを追加

**Files:**
- Modify: `src/lorairo/database/filter_criteria.py`

- [ ] **Step 1: `filter_criteria.py` にフィールドを追加**

`ImageFilterCriteria` の `image_ids` フィールドの直後に追加:

```python
# ソート条件 (ADR 0697: images search で使用)
sort_field: str = "image_id"    # "image_id" または "file_path"
sort_direction: str = "asc"     # "asc" または "desc"
```

`to_dict()` メソッドにも追加:

```python
"sort_field": self.sort_field,
"sort_direction": self.sort_direction,
```

- [ ] **Step 2: 既存テストが壊れていないか確認**

```bash
uv run pytest tests/unit/database/ -v -q 2>&1 | tail -20
```

期待: 全テスト PASSED (デフォルト値があるので既存テストへの影響なし)

- [ ] **Step 3: コミット**

```bash
git add src/lorairo/database/filter_criteria.py
git commit -m "feat(db): add sort_field/sort_direction to ImageFilterCriteria (#697)"
```

---

### Task 2: `ImageRepository.get_images_by_filter` に動的 ORDER BY を追加

**Files:**
- Modify: `src/lorairo/database/repository/image.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/cli/test_commands_images_search.py` に先にソートのユニットテストを追加（後の Task 3 でこのファイルを拡張する）:

```python
"""images search コマンドのユニットテスト。"""
import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.filter_criteria import ImageFilterCriteria

runner = CliRunner()


@pytest.mark.unit
class TestImageFilterCriteriaSort:
    """ImageFilterCriteria のソートフィールドテスト。"""

    def test_default_sort_is_image_id_asc(self):
        """デフォルトは image_id の asc ソート。"""
        criteria = ImageFilterCriteria()
        assert criteria.sort_field == "image_id"
        assert criteria.sort_direction == "asc"

    def test_sort_fields_can_be_set(self):
        """sort_field / sort_direction を設定できる。"""
        criteria = ImageFilterCriteria(sort_field="file_path", sort_direction="desc")
        assert criteria.sort_field == "file_path"
        assert criteria.sort_direction == "desc"
```

```bash
uv run pytest tests/unit/cli/test_commands_images_search.py::TestImageFilterCriteriaSort -v
```

期待: PASSED (filter_criteria.py を既に変更済みなので通過するはず)

- [ ] **Step 2: `image.py` の ORDER BY を動的に変更**

`src/lorairo/database/repository/image.py` の `get_images_by_filter` メソッド内、約2263行目付近の:

```python
paged_query = query.order_by(Image.id)
```

を以下に変更:

```python
# sort_field / sort_direction に従って ORDER BY を動的に決定
_sort_col = Image.filename if filter_criteria.sort_field == "file_path" else Image.id
if filter_criteria.sort_direction == "desc":
    paged_query = query.order_by(_sort_col.desc())
else:
    paged_query = query.order_by(_sort_col.asc())
```

- [ ] **Step 3: 既存テストが壊れていないか確認**

```bash
uv run pytest tests/unit/database/ -v -q 2>&1 | tail -20
```

期待: 全テスト PASSED

- [ ] **Step 4: コミット**

```bash
git add src/lorairo/database/repository/image.py
git commit -m "feat(repo): dynamic ORDER BY for get_images_by_filter (#697)"
```

---

### Task 3: `images.py` に `search` コマンドを追加

**Files:**
- Modify: `src/lorairo/cli/commands/images.py`
- Modify: `tests/unit/cli/test_commands_images_search.py`

- [ ] **Step 1: 失敗するテストを追加**

`tests/unit/cli/test_commands_images_search.py` に追加:

```python
def _make_container(records: list[dict]) -> MagicMock:
    container = MagicMock()
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.image_repo.get_images_count_only.return_value = len(records)
    return container


@pytest.fixture
def mock_search_context(tmp_path, monkeypatch):
    """project 確認と ServiceContainer をモック。検索結果 2 件を返す。"""
    records = [
        {"id": 1, "image_id": 1, "file_path": "a.webp"},
        {"id": 2, "image_id": 2, "file_path": "b.webp"},
    ]
    container = _make_container(records)
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container))
    return container, tmp_path


@pytest.mark.unit
class TestImagesSearch:
    def test_search_query_file(self, mock_search_context, tmp_path):
        """--query-file で JSON ファイルを渡すと JSONL を返す。"""
        container, _ = mock_search_context
        query_file = tmp_path / "search.json"
        query_file.write_text('{"tags": ["cat"], "limit": 10}')

        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().splitlines() if l.strip()]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 2
        assert result_row["ok"] is True
        assert "image_id" in items[0]
        assert "file_path" in items[0]

    def test_search_stdin(self, mock_search_context):
        """--query - で stdin から JSON を渡すと JSONL を返す。"""
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query", "-"],
            input='{"include_nsfw": true}',
        )
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().splitlines() if l.strip()]
        assert any(r.get("kind") == "result" for r in lines)

    def test_search_invalid_json_returns_invalid_input(self, mock_search_context):
        """不正な JSON は INVALID_INPUT (exit 2) で終了する。"""
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query", "-"],
            input="not json",
        )
        assert result.exit_code == 2

    def test_search_invalid_schema_returns_invalid_input(self, mock_search_context, tmp_path):
        """スキーマ違反 (limit=999) は INVALID_INPUT (exit 2) で終了する。"""
        query_file = tmp_path / "bad.json"
        query_file.write_text('{"limit": 999}')
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 2

    def test_search_with_sort(self, mock_search_context, tmp_path):
        """sort フィールドを含む JSON スキーマが受け付けられる。"""
        query_file = tmp_path / "sort.json"
        query_file.write_text('{"sort": [{"field": "file_path", "direction": "desc"}]}')
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0
```

- [ ] **Step 2: テストを実行して失敗確認**

```bash
uv run pytest tests/unit/cli/test_commands_images_search.py::TestImagesSearch -v 2>&1 | head -20
```

期待: `No such command 'search'` 系のエラー

- [ ] **Step 3: `images.py` に Pydantic モデルと `search` コマンドを追加**

`images.py` の先頭 import に追加:

```python
import json
import sys
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError
```

`app = typer.Typer(...)` の直後（定数定義の後）に Pydantic モデルを追加:

```python
class _SortSpec(BaseModel):
    field: Literal["image_id", "file_path"] = "image_id"
    direction: Literal["asc", "desc"] = "asc"


class ImageSearchQuery(BaseModel):
    """images search コマンドが受け付ける JSON 検索スキーマ。"""

    image_ids: list[int] | None = None
    tags: list[str] | None = None
    excluded_tags: list[str] | None = None
    caption: str | None = None
    manual_rating: str | None = None
    ai_rating: str | None = None
    score_min: float | None = None
    score_max: float | None = None
    only_unrated: bool = False
    missing_model: str | None = None
    include_nsfw: bool = False
    limit: int = Field(default=500, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort: list[_SortSpec] = Field(default_factory=lambda: [_SortSpec()])
```

`list_images` コマンドの後に `search` コマンドを追加:

```python
@app.command("search")
def search_images(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    query_file: str | None = typer.Option(
        None, "--query-file", help="Path to JSON search schema file"
    ),
    query: str | None = typer.Option(
        None, "--query", help="JSON search schema string or '-' for stdin"
    ),
) -> None:
    """Search images using a JSON search schema (read-only).

    JSON 検索スキーマを受け取り、条件に合う画像を返します（副作用なし）。

    スキーマは --query-file でファイルから、--query - で stdin から渡します。

    Examples:
        lorairo-cli images search --project proj --query-file search.json --json
        echo '{"tags":["cat"]}' | lorairo-cli images search --project proj --query - --json
    """
    with command_boundary():
        if query_file is None and query is None:
            raise click.UsageError("--query-file または --query - のいずれかを指定してください。")
        if query_file is not None and query is not None:
            raise click.UsageError("--query-file と --query は同時に指定できません。")

        # JSON 読み込み
        try:
            if query_file is not None:
                raw = Path(query_file).read_text(encoding="utf-8")
            else:
                raw = sys.stdin.read() if query == "-" else query or ""
            parsed = json.loads(raw)
        except (OSError, json.JSONDecodeError) as e:
            raise click.UsageError(f"JSON 読み込みエラー: {e}") from e

        # スキーマバリデーション
        try:
            q = ImageSearchQuery.model_validate(parsed)
        except ValidationError as e:
            raise click.UsageError(f"検索スキーマが無効です: {e}") from e

        api_get_project(project)
        container = get_service_container()
        container.set_active_project(project)

        # ImageFilterCriteria に変換
        criteria = ImageFilterCriteria(
            image_ids=q.image_ids,
            tags=q.tags,
            excluded_tags=q.excluded_tags,
            caption=q.caption,
            manual_rating_filter=q.manual_rating,
            ai_rating_filter=q.ai_rating,
            score_min=q.score_min,
            score_max=q.score_max,
            only_unrated=q.only_unrated,
            missing_model_litellm_id=q.missing_model,
            include_nsfw=q.include_nsfw,
            limit=q.limit,
            offset=q.offset,
            sort_field=q.sort[0].field if q.sort else "image_id",
            sort_direction=q.sort[0].direction if q.sort else "asc",
        )

        # count-first (ADR 0060)
        total_count = container.db_manager.image_repo.get_images_count_only(criteria)
        if total_count > MAX_IMAGE_LIST_FETCH and criteria.image_ids is None:
            from lorairo.api.exceptions import ResultSetTooLargeError
            raise ResultSetTooLargeError(matched=total_count, limit=MAX_IMAGE_LIST_FETCH)

        records, total = container.db_manager.image_repo.get_images_by_filter(criteria)
        count = len(records)
        has_more = q.offset + count < total

        if is_json_mode():
            for record in records:
                emit_item({
                    "image_id": record.get("id") or record.get("image_id"),
                    "file_path": record.get("file_path"),
                })
            emit_result(
                f"{count} image(s)",
                count=count,
                total=total,
                limit=q.limit,
                offset=q.offset,
                has_more=has_more,
            )
        else:
            for record in records:
                print(f"{record.get('id') or record.get('image_id')}\t{record.get('file_path')}")
```

- [ ] **Step 4: テストを実行して通過確認**

```bash
uv run pytest tests/unit/cli/test_commands_images_search.py -v
```

期待: 全テスト PASSED

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/cli/commands/images.py tests/unit/cli/test_commands_images_search.py
git commit -m "feat(cli): add images search command with JSON schema (#697)"
```

---

### Task 4: CI-equivalent filter 実行 & PR 起票

- [ ] **Step 1: フォーマット・型チェック**

```bash
uv run ruff format src/lorairo/cli/commands/images.py src/lorairo/database/filter_criteria.py src/lorairo/database/repository/image.py
uv run ruff check src/lorairo/cli/commands/images.py src/lorairo/database/filter_criteria.py src/lorairo/database/repository/image.py --fix
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
  --title "feat(cli): images search コマンドを追加 (Issue #697)" \
  --body "$(cat <<'EOF'
## Summary
- `lorairo-cli images search --query-file / --query -` コマンドを追加
- Pydantic `ImageSearchQuery` モデルで JSON 検索スキーマを定義
- `ImageFilterCriteria` に `sort_field` / `sort_direction` を追加
- `get_images_by_filter` の ORDER BY を動的化（image_id / file_path, asc/desc）
- read-only、ファイル出力なし

## Test plan
- [ ] `uv run pytest tests/unit/cli/test_commands_images_search.py -v`
- [ ] CI-equivalent filter 全 PASS 確認

Closes #697
EOF
)"
```
