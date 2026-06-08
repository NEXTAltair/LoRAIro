# tags add/remove/replace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lorairo-cli tags add/remove/replace` コマンドを追加し、エージェントがカンマ区切り image_ids に対してタグ操作を安全に実行できるようにする (Issue #695)

**Architecture:** 案A準拠。`AnnotationRepository` に `remove_tag_from_images_batch` / `replace_tag_for_images_batch` を追加し、新規 `tags.py` コマンドファイルから呼び出す。デフォルト dry-run、`--apply` のみ書き込み。

**Tech Stack:** Typer, SQLAlchemy, typer.testing.CliRunner, pytest

---

## ファイル構成

| 操作 | ファイル |
|---|---|
| Create | `src/lorairo/cli/commands/tags.py` |
| Modify | `src/lorairo/database/repository/annotation_record.py` (メソッド追加) |
| Modify | `src/lorairo/cli/main.py` (タググループ登録) |
| Create | `tests/unit/cli/test_commands_tags.py` |
| Create | `tests/unit/database/repository/test_tags_batch_ops.py` |

---

### Task 1: AnnotationRepository に `remove_tag_from_images_batch` を追加

**Files:**
- Modify: `src/lorairo/database/repository/annotation_record.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/database/repository/test_tags_batch_ops.py` を新規作成:

```python
"""AnnotationRepository タグ削除・置換バッチ操作のユニットテスト。"""
from unittest.mock import MagicMock

import pytest

from lorairo.database.repository.annotation_record import AnnotationRepository


@pytest.fixture
def mock_session():
    """SQLAlchemy セッションのモック。"""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture
def repo(mock_session):
    """セッションファクトリをモックした AnnotationRepository。"""
    repo = AnnotationRepository.__new__(AnnotationRepository)
    repo.session_factory = MagicMock(return_value=mock_session)
    return repo


@pytest.mark.unit
class TestRemoveTagFromImagesBatch:
    """remove_tag_from_images_batch のテスト。"""

    def test_removes_existing_tag_returns_per_item_results(self, repo, mock_session):
        """タグが存在する画像から削除し、per-item 結果リストを返す。"""
        repo._build_existing_tags_map = MagicMock(
            return_value={123: {"bad_tag"}, 456: {"bad_tag"}}
        )
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert results == [(123, "changed"), (456, "changed")]
        mock_session.commit.assert_called_once()

    def test_skips_images_without_tag(self, repo, mock_session):
        """対象タグが存在しない画像は skipped になる。"""
        repo._build_existing_tags_map = MagicMock(
            return_value={123: {"other_tag"}, 456: {"bad_tag"}}
        )
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert (123, "skipped") in results
        assert (456, "changed") in results

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        """空の image_ids リストは (False, []) を返す。"""
        ok, results = repo.remove_tag_from_images_batch([], "bad_tag")
        assert ok is False
        assert results == []

    def test_empty_tag_returns_false(self, repo, mock_session):
        """空のタグ文字列は (False, []) を返す。"""
        ok, results = repo.remove_tag_from_images_batch([123], "")
        assert ok is False
        assert results == []
```

- [ ] **Step 2: テストを実行して失敗確認**

```bash
uv run pytest tests/unit/database/repository/test_tags_batch_ops.py::TestRemoveTagFromImagesBatch -v
```

期待: `AttributeError: type object 'AnnotationRepository' has no attribute 'remove_tag_from_images_batch'`

- [ ] **Step 3: `remove_tag_from_images_batch` を実装**

`annotation_record.py` の `add_tag_to_images_batch` メソッド直後（約400行目付近）に追加:

```python
def remove_tag_from_images_batch(
    self,
    image_ids: list[int],
    tag: str,
) -> tuple[bool, list[tuple[int, str]]]:
    """複数画像から1つのタグを原子的に削除する。

    単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

    Args:
        image_ids: 対象画像のIDリスト
        tag: 削除するタグ

    Returns:
        (成功フラグ, [(image_id, "changed"|"skipped"), ...])

    Raises:
        SQLAlchemyError: データベースエラー時(ロールバック後に再送出)
    """
    if not image_ids:
        logger.warning("Empty image_ids list for batch tag remove")
        return (False, [])

    if not tag.strip():
        logger.warning("Empty tag for batch remove")
        return (False, [])

    normalized_tag = tag.strip().lower()
    per_item: list[tuple[int, str]] = []

    with self.session_factory() as session:
        try:
            existing_tags_by_image = self._build_existing_tags_map(session, image_ids)

            for image_id in image_ids:
                existing_tags = existing_tags_by_image.get(image_id, set())
                if normalized_tag not in existing_tags:
                    logger.debug(
                        f"Tag '{normalized_tag}' not found for image_id {image_id}, skipping",
                    )
                    per_item.append((image_id, "skipped"))
                    continue

                session.execute(
                    delete(Tag).where(
                        Tag.image_id == image_id,
                        Tag.tag == normalized_tag,
                    )
                )
                per_item.append((image_id, "changed"))

            session.commit()
            changed = sum(1 for _, s in per_item if s == "changed")
            logger.info(
                f"Atomic batch tag remove completed: tag='{normalized_tag}', "
                f"processed={len(image_ids)}, removed={changed}",
            )
            return (True, per_item)

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Atomic batch tag remove failed, rolled back: {e}", exc_info=True)
            raise
```

`annotation_record.py` の import に `delete` を追加（既存の `from sqlalchemy import ...` 行を確認して追加）:

```python
from sqlalchemy import delete, select  # delete が未 import なら追加
```

- [ ] **Step 4: テストを実行して通過確認**

```bash
uv run pytest tests/unit/database/repository/test_tags_batch_ops.py::TestRemoveTagFromImagesBatch -v
```

期待: 全テスト PASSED

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/database/repository/annotation_record.py tests/unit/database/repository/test_tags_batch_ops.py
git commit -m "feat(repo): add remove_tag_from_images_batch to AnnotationRepository (#695)"
```

---

### Task 2: AnnotationRepository に `replace_tag_for_images_batch` を追加

**Files:**
- Modify: `src/lorairo/database/repository/annotation_record.py`
- Modify: `tests/unit/database/repository/test_tags_batch_ops.py`

- [ ] **Step 1: 失敗するテストを追加**

`tests/unit/database/repository/test_tags_batch_ops.py` に追加:

```python
@pytest.mark.unit
class TestReplaceTagForImagesBatch:
    """replace_tag_for_images_batch のテスト。"""

    def test_replaces_tag_changed(self, repo, mock_session):
        """変換元あり・変換先なし → 変換元削除 + 変換先追加、status=changed。"""
        repo._build_existing_tags_map = MagicMock(
            return_value={123: {"bad_tag"}}
        )
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())
        mock_session.add = MagicMock()

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]
        mock_session.commit.assert_called_once()

    def test_replaces_tag_to_already_exists(self, repo, mock_session):
        """変換元あり・変換先あり → 変換元削除のみ、status=changed。"""
        repo._build_existing_tags_map = MagicMock(
            return_value={123: {"bad_tag", "good_tag"}}
        )
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]

    def test_skips_when_from_tag_not_found(self, repo, mock_session):
        """変換元なし → status=skipped。"""
        repo._build_existing_tags_map = MagicMock(
            return_value={123: {"other_tag"}}
        )

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "skipped")]

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        """空の image_ids リストは (False, []) を返す。"""
        ok, results = repo.replace_tag_for_images_batch([], "bad_tag", "good_tag")
        assert ok is False
        assert results == []
```

- [ ] **Step 2: テストを実行して失敗確認**

```bash
uv run pytest tests/unit/database/repository/test_tags_batch_ops.py::TestReplaceTagForImagesBatch -v
```

期待: `AttributeError: type object 'AnnotationRepository' has no attribute 'replace_tag_for_images_batch'`

- [ ] **Step 3: `replace_tag_for_images_batch` を実装**

`remove_tag_from_images_batch` 直後に追加:

```python
def replace_tag_for_images_batch(
    self,
    image_ids: list[int],
    from_tag: str,
    to_tag: str,
) -> tuple[bool, list[tuple[int, str]]]:
    """複数画像のタグを原子的に置換する。

    変換元タグが存在する画像のみ処理。変換先タグが既に存在する場合は
    変換元を削除のみ行い（重複させない）、ステータスは changed 扱い。

    Args:
        image_ids: 対象画像のIDリスト
        from_tag: 置換元タグ
        to_tag: 置換先タグ

    Returns:
        (成功フラグ, [(image_id, "changed"|"skipped"), ...])

    Raises:
        SQLAlchemyError: データベースエラー時(ロールバック後に再送出)
    """
    if not image_ids:
        logger.warning("Empty image_ids list for batch tag replace")
        return (False, [])

    if not from_tag.strip() or not to_tag.strip():
        logger.warning("Empty from_tag or to_tag for batch replace")
        return (False, [])

    normalized_from = from_tag.strip().lower()
    normalized_to = to_tag.strip().lower()
    per_item: list[tuple[int, str]] = []

    with self.session_factory() as session:
        try:
            existing_tags_by_image = self._build_existing_tags_map(session, image_ids)
            to_tag_external_id: int | None = None

            for image_id in image_ids:
                existing_tags = existing_tags_by_image.get(image_id, set())
                if normalized_from not in existing_tags:
                    logger.debug(
                        f"from_tag '{normalized_from}' not found for image_id {image_id}, skipping",
                    )
                    per_item.append((image_id, "skipped"))
                    continue

                # 変換元を削除
                session.execute(
                    delete(Tag).where(
                        Tag.image_id == image_id,
                        Tag.tag == normalized_from,
                    )
                )

                # 変換先が既に存在しない場合のみ追加
                if normalized_to not in existing_tags:
                    if to_tag_external_id is None:
                        to_tag_external_id = self._get_or_create_tag_id_external(
                            session, normalized_to
                        )
                    new_tag = Tag(
                        image_id=image_id,
                        model_id=None,
                        tag=normalized_to,
                        tag_id=to_tag_external_id,
                        confidence_score=None,
                        existing=False,
                        is_edited_manually=True,
                    )
                    session.add(new_tag)

                per_item.append((image_id, "changed"))

            session.commit()
            changed = sum(1 for _, s in per_item if s == "changed")
            logger.info(
                f"Atomic batch tag replace completed: '{normalized_from}' -> '{normalized_to}', "
                f"processed={len(image_ids)}, changed={changed}",
            )
            return (True, per_item)

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Atomic batch tag replace failed, rolled back: {e}", exc_info=True)
            raise
```

- [ ] **Step 4: テストを実行して通過確認**

```bash
uv run pytest tests/unit/database/repository/test_tags_batch_ops.py -v
```

期待: 全テスト PASSED

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/database/repository/annotation_record.py tests/unit/database/repository/test_tags_batch_ops.py
git commit -m "feat(repo): add replace_tag_for_images_batch to AnnotationRepository (#695)"
```

---

### Task 3: `tags.py` コマンドファイルを作成（`add` / `remove` / `replace`）

**Files:**
- Create: `src/lorairo/cli/commands/tags.py`

- [ ] **Step 1: 失敗するCLIテストを書く**

`tests/unit/cli/test_commands_tags.py` を新規作成:

```python
"""tags コマンド群のユニットテスト。"""
import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _make_container(*, image_exists: bool = True, changed: int = 1, removed: int = 1) -> MagicMock:
    """テスト用 ServiceContainer モックを生成する。"""
    container = MagicMock()

    # image_repo: 存在確認
    image_meta = MagicMock() if image_exists else None
    container.db_manager.image_repo.get_image_metadata.return_value = image_meta

    # get_images_by_filter: 指定 IDs が全件返る (存在確認用)
    mock_records = [{"id": 1}, {"id": 2}] if image_exists else []
    container.db_manager.image_repo.get_images_by_filter.return_value = (mock_records, len(mock_records))

    # annotation_repo
    container.db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, changed)
    container.db_manager.annotation_repo.remove_tag_from_images_batch.return_value = (True, removed)
    container.db_manager.annotation_repo.replace_tag_for_images_batch.return_value = (True, changed)

    return container


@pytest.fixture
def mock_project_and_container(monkeypatch):
    """プロジェクト確認と ServiceContainer をモックする。"""
    container = _make_container()
    monkeypatch.setattr("lorairo.cli.commands.tags.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("lorairo.cli.commands.tags.get_service_container", MagicMock(return_value=container))
    return container


@pytest.mark.unit
class TestTagsAdd:
    def test_add_dry_run_default_does_not_write(self, mock_project_and_container):
        """dry-run (デフォルト) では annotation_repo.add_tag_to_images_batch が呼ばれない。"""
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_not_called()

    def test_add_apply_writes_to_db(self, mock_project_and_container):
        """--apply では annotation_repo.add_tag_to_images_batch が呼ばれる。"""
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_called()

    def test_add_json_output_has_result_row(self, mock_project_and_container):
        """--json 出力に kind=result 行が含まれる。"""
        result = runner.invoke(
            app,
            ["--json", "tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat", "--apply"],
        )
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().splitlines() if l.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False


@pytest.mark.unit
class TestTagsRemove:
    def test_remove_dry_run_does_not_write(self, mock_project_and_container):
        """dry-run では remove_tag_from_images_batch が呼ばれない。"""
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_not_called()

    def test_remove_apply_writes(self, mock_project_and_container):
        """--apply では remove_tag_from_images_batch が呼ばれる。"""
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_called()


@pytest.mark.unit
class TestTagsReplace:
    def test_replace_dry_run_does_not_write(self, mock_project_and_container):
        """dry-run では replace_tag_for_images_batch が呼ばれない。"""
        result = runner.invoke(
            app,
            ["tags", "replace", "--project", "proj", "--image-ids", "1,2",
             "--from", "bad", "--to", "good"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_not_called()

    def test_replace_apply_writes(self, mock_project_and_container):
        """--apply では replace_tag_for_images_batch が呼ばれる。"""
        result = runner.invoke(
            app,
            ["tags", "replace", "--project", "proj", "--image-ids", "1,2",
             "--from", "bad", "--to", "good", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_called()

    def test_replace_json_item_rows(self, mock_project_and_container):
        """--json 出力に kind=item 行と kind=result 行が含まれる。"""
        result = runner.invoke(
            app,
            ["--json", "tags", "replace", "--project", "proj", "--image-ids", "1,2",
             "--from", "bad", "--to", "good", "--apply"],
        )
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().splitlines() if l.strip()]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 2
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False
```

- [ ] **Step 2: テストを実行して失敗確認**

```bash
uv run pytest tests/unit/cli/test_commands_tags.py -v 2>&1 | head -30
```

期待: `No such command 'tags'` 系のエラー

- [ ] **Step 3: `tags.py` を実装**

`src/lorairo/cli/commands/tags.py` を新規作成:

```python
"""Tag editing commands.

カンマ区切り image_ids に対してタグを追加・削除・置換するコマンド群。
エージェントが判断した操作を安全に実行するための CLI インターフェース。

デフォルトは dry-run (DB 非更新)。--apply を付けた場合のみ書き込む。
出力は ADR 0057/0058 に従う: --json 時は stdout に JSONL (item/result)。
"""

from __future__ import annotations

import click
import typer

from lorairo.api.project import get_project as api_get_project
from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.cli._glyphs import OK
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.service_container import get_service_container

app = typer.Typer(help="Tag editing commands (agent-friendly)")
console = make_console()

MAX_IMAGE_IDS = 500


def _parse_image_ids(image_ids_csv: str) -> list[int]:
    """カンマ区切り文字列を int リストに変換。不正値は UsageError。"""
    try:
        return [int(x.strip()) for x in image_ids_csv.split(",") if x.strip()]
    except ValueError as e:
        raise click.UsageError(f"--image-ids には整数のみ指定可: {e}") from e


def _validate_image_ids_exist(container, project: str, image_ids: list[int]) -> None:
    """全 image_id が DB に存在するか確認。存在しないものがあれば ImageNotFoundError を送出。"""
    from lorairo.api.exceptions import ImageNotFoundError

    criteria = ImageFilterCriteria(image_ids=image_ids, include_nsfw=True)
    records, _ = container.db_manager.image_repo.get_images_by_filter(criteria)
    found_ids = {int(r["id"]) for r in records}
    missing = [i for i in image_ids if i not in found_ids]
    if missing:
        raise ImageNotFoundError(missing[0])


@app.command("add")
def add(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    tags_csv: str = typer.Option(..., "--tags", help="Comma-separated tags to add"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Add tags to images.

    指定した image_ids に対してタグを追加します。
    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags add --project proj --image-ids 1,2,3 --tags "cat,dog" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if len(image_ids) > MAX_IMAGE_IDS:
            raise click.UsageError(f"--image-ids は最大 {MAX_IMAGE_IDS} 件まで。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, project, image_ids)

        total_added = 0
        dry_run = not apply

        if not dry_run:
            for tag in tag_list:
                _, added = container.db_manager.annotation_repo.add_tag_to_images_batch(
                    image_ids, tag, None
                )
                total_added += added

        if is_json_mode():
            for image_id in image_ids:
                emit_item({
                    "image_id": image_id,
                    "action": "add",
                    "tags": tag_list,
                    "status": "dry_run" if dry_run else "changed",
                })
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Added tags to {len(image_ids)} image(s)",
                target_images=len(image_ids),
                tags=tag_list,
                added=total_added,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(f"{prefix}{OK} {len(image_ids)} 件の画像に {tag_list} を追加{'予定' if dry_run else '完了'}")


@app.command("remove")
def remove(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    tags_csv: str = typer.Option(..., "--tags", help="Comma-separated tags to remove"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Remove tags from images.

    指定した image_ids からタグを削除します。
    対象タグが存在しない画像はスキップします（エラーにしません）。
    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags remove --project proj --image-ids 1,2,3 --tags "bad_tag" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")

        tag_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if not tag_list:
            raise click.UsageError("--tags に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, project, image_ids)

        dry_run = not apply
        per_item_results: list[tuple[int, str]] = []
        total_removed = 0

        if not dry_run:
            for tag in tag_list:
                _, item_results = container.db_manager.annotation_repo.remove_tag_from_images_batch(
                    image_ids, tag
                )
                per_item_results = item_results  # 最後のタグの結果を per-item として使用
                total_removed += sum(1 for _, s in item_results if s == "changed")

        if is_json_mode():
            for image_id in image_ids:
                status = "dry_run" if dry_run else next(
                    (s for iid, s in per_item_results if iid == image_id), "unknown"
                )
                emit_item({
                    "image_id": image_id,
                    "action": "remove",
                    "tags": tag_list,
                    "status": status,
                })
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Removed tags from {len(image_ids)} image(s)",
                target_images=len(image_ids),
                tags=tag_list,
                removed=total_removed,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(f"{prefix}{OK} {len(image_ids)} 件の画像から {tag_list} を削除{'予定' if dry_run else '完了'}")


@app.command("replace")
def replace(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    image_ids_csv: str = typer.Option(..., "--image-ids", help="Comma-separated image IDs"),
    from_tag: str = typer.Option(..., "--from", help="Tag to replace (変換元)"),
    to_tag: str = typer.Option(..., "--to", help="Replacement tag (変換先)"),
    apply: bool = typer.Option(False, "--apply", help="Write to DB (default: dry-run)"),
) -> None:
    """Replace a tag with another tag across images.

    指定した image_ids の変換元タグを変換先タグに置換します。
    - 変換元タグが存在しない画像はスキップします。
    - 変換先タグが既に存在する場合は変換元のみ削除します（重複しません）。
    デフォルトは dry-run です。--apply を付けると DB に書き込みます。

    Example:
        lorairo-cli tags replace --project proj --image-ids 1,2,3 \\
            --from "bad tag" --to "good_tag" --apply
    """
    with command_boundary():
        api_get_project(project)
        image_ids = _parse_image_ids(image_ids_csv)
        if not image_ids:
            raise click.UsageError("--image-ids に有効な値がありません。")
        if not from_tag.strip():
            raise click.UsageError("--from に有効な値がありません。")
        if not to_tag.strip():
            raise click.UsageError("--to に有効な値がありません。")

        container = get_service_container()
        container.set_active_project(project)
        _validate_image_ids_exist(container, project, image_ids)

        dry_run = not apply
        per_item_results: list[tuple[int, str]] = []

        if not dry_run:
            _, per_item_results = container.db_manager.annotation_repo.replace_tag_for_images_batch(
                image_ids, from_tag, to_tag
            )

        changed = sum(1 for _, s in per_item_results if s == "changed")
        skipped = sum(1 for _, s in per_item_results if s == "skipped")

        if is_json_mode():
            for image_id in image_ids:
                status = "dry_run" if dry_run else next(
                    (s for iid, s in per_item_results if iid == image_id), "unknown"
                )
                item: dict = {
                    "image_id": image_id,
                    "action": "replace",
                    "from": from_tag.strip().lower(),
                    "to": to_tag.strip().lower(),
                    "status": status,
                }
                if status == "skipped":
                    item["reason"] = "from_tag_not_found"
                emit_item(item)
            emit_result(
                f"{'[dry-run] ' if dry_run else ''}Replaced tags in {len(image_ids)} image(s)",
                target_images=len(image_ids),
                changed=changed,
                skipped=skipped,
                errors=0,
                dry_run=dry_run,
            )
        else:
            prefix = "[dry-run] " if dry_run else ""
            console.print(
                f"{prefix}{OK} {len(image_ids)} 件対象: '{from_tag}' → '{to_tag}' "
                f"({'予定' if dry_run else f'変更={changed}, スキップ={skipped}'})"
            )
```

- [ ] **Step 4: `main.py` に `tags` グループを登録**

`src/lorairo/cli/main.py` の `# ===== サブコマンドグループ登録 =====` セクションに追加:

```python
from lorairo.cli.commands import annotate, batch, export, images, models, project, tags  # tags を追加
# ...
app.add_typer(tags.app, name="tags", help="Tag editing commands (agent-friendly)")
```

- [ ] **Step 5: テストを実行して通過確認**

```bash
uv run pytest tests/unit/cli/test_commands_tags.py -v
```

期待: 全テスト PASSED

- [ ] **Step 6: コミット**

```bash
git add src/lorairo/cli/commands/tags.py src/lorairo/cli/main.py tests/unit/cli/test_commands_tags.py
git commit -m "feat(cli): add tags add/remove/replace commands (Issue #695)"
```

---

### Task 4: CI-equivalent filter 実行 & PR 起票

- [ ] **Step 1: フォーマット・型チェック**

```bash
uv run ruff format src/lorairo/cli/commands/tags.py src/lorairo/database/repository/annotation_record.py
uv run ruff check src/lorairo/cli/commands/tags.py src/lorairo/database/repository/annotation_record.py --fix
uv run mypy -p lorairo 2>&1 | tail -20
```

期待: エラーなし

- [ ] **Step 2: CI-equivalent filter 実行**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60 -q 2>&1 | tail -20
```

期待: 全テスト PASSED (既存テストに regression なし)

- [ ] **Step 3: worktree から push して PR 起票**

```bash
git push -u origin HEAD
gh pr create \
  --title "feat(cli): tags add/remove/replace コマンドを追加 (Issue #695)" \
  --body "$(cat <<'EOF'
## Summary
- `lorairo-cli tags add/remove/replace` コマンドを追加
- `AnnotationRepository` に `remove_tag_from_images_batch` / `replace_tag_for_images_batch` を追加
- デフォルト dry-run、`--apply` のみ書き込み
- `--json` で image_id ごとの item 行 + result 行を出力

## Test plan
- [ ] `uv run pytest tests/unit/cli/test_commands_tags.py -v`
- [ ] `uv run pytest tests/unit/database/repository/test_tags_batch_ops.py -v`
- [ ] CI-equivalent filter 全 PASS 確認

Closes #695
EOF
)"
```
