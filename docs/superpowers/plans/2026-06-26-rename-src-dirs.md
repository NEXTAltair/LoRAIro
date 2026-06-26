# src/lorairo ディレクトリ/モジュール改名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/lorairo/` の4ディレクトリ（+ 一部モジュール/クラス）を実態に即した説明的な名前へ機械的に改名する。ロジック変更ゼロ。

**Architecture:** ハードリネーム（`git mv` で履歴温存 + import 一括置換、deprecation shim なし）。1ディレクトリ=1サブPR、優先度順に直列で実装・検証・merge する。各サブPR は前サブPR merge 後の `origin/main` から worktree を切るため rebase 不要。

**Tech Stack:** Python 3.13 / uv / GNU sed（`\b` 対応）/ pytest / mypy / git worktree

## Global Constraints

- 実行モデルは**直列・リード単独**（並列 Agent Teams は不採用）。前サブPR を merge してから次サブPR の worktree を切る。
- 各サブPR は専用 worktree（`.agents/worktree/issue-717-<name>`）で作業。`origin/main` から分岐。共有 venv (`/workspaces/LoRAIro/.venv`) を使い worktree 内に `.venv` を作らない。
- 検証は CI-equivalent filter（`-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`）+ `uv run mypy -p lorairo`。worktree のローカル検証は editable install の都合で main checkout を見る可能性があるため、**真偽は push 後 CI が SSoT**。
- sed の置換対象は `src/` `tests/` + live docs 5ファイル（`docs/conftest_template.py` `docs/integrations.md` `docs/decisions/0037-api-facade-wiring-policy.md` `docs/decisions/0059-cli-command-introspection.md` `docs/specs/core/filesystem_management.md`）に限定。**`docs/superpowers/specs/` `docs/superpowers/plans/` は除外**（設計/計画ドキュメント自身の "before" 記述を壊さないため）。
- **相対 import を必ず置換する**（Task2 で発覚した教訓）。`lorairo.<old>` の絶対 import だけでなく、`from ..<old>` / `from ...<old>` の**相対 import** も置換対象。後者は mypy をすり抜け runtime で `ModuleNotFoundError` を起こす（外部パッケージから消えたディレクトリへ相対参照するため）。各タスクの sed に相対 import 置換ステップを含め、取りこぼし確認も `from \.+<old>\b` を含める。
- **平坦化（サブパッケージ → トップレベルモジュール）では移動したファイル自身の相対 import のドットを1つ減らす**（Task4 で発覚した教訓）。`storage/file_system.py`（`.`=storage, `..`=lorairo）を `filesystem.py`（`.`=lorairo）へ移すと、ファイル内の `from ..utils.log` / `from ..database.db_core` が「attempted relative import beyond top-level package」になる。`from ..X` → `from .X` へ修正する。副作用として import が壊れると mypy が依存シンボルを `Any` 扱いし `no-any-return` 等の二次エラーも出る（import を直すと連鎖的に解消）。
- **validate_docs.py 連動ゲート**（"Validate Agent Harness"）は `CLAUDE.md` / `docs/services.md` / `docs/integrations.md` / `docs/testing.md` のファイルパス参照存在を検証する。ディレクトリ/モジュール改名時は `CLAUDE.md` のパス参照も追従させる（非必須チェックだが green を保つ）。`scripts/validate_docs.py` の `integration_files` リストのパス文字列も同様。
- PR リンク: サブPR1〜3 は `Refs #717`、最後のサブPR4 のみ `Closes #717`。
- commit 末尾に Co-Authored-By / Claude-Session を付与（リポジトリ規約）。

**置換スコープのヘルパ変数（各タスクで使用）:**
```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
```

---

### Task 1: `api/` → `public_api/`（優先度: 高 / 影響 35 files）

**Files:**
- Rename dir: `src/lorairo/api/` → `src/lorairo/public_api/`
- Rename dir: `tests/unit/api/` → `tests/unit/public_api/`
- Modify: `src/lorairo/api.*` を import する全ファイル（`lorairo.api` → `lorairo.public_api`）
- 内部 facade モジュール（`images.py`/`tags.py`/`project.py`/`export.py`/`batch_import.py`/`types.py`/`exceptions.py`/`annotations.py`）は据え置き

**Interfaces:**
- Consumes: なし（最初のタスク）
- Produces: 公開パスが `lorairo.public_api.*` になる。後続タスクは `lorairo.api` を参照しない前提。

- [ ] **Step 1: worktree 作成**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-public-api -b refactor/issue-717-public-api origin/main
cd .agents/worktree/issue-717-public-api
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリを git mv**

```bash
git mv src/lorairo/api src/lorairo/public_api
git mv tests/unit/api tests/unit/public_api
```

- [ ] **Step 3: import パスを一括置換**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
grep -rlE 'lorairo\.api\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.api\b/lorairo.public_api/g'
```

- [ ] **Step 4: 取りこぼし確認（残存ゼロを期待）**

```bash
grep -rnE 'lorairo\.api\b' src/ tests/ $SCOPE_DOCS 2>/dev/null
```
Expected: 出力なし（全件置換済み）

- [ ] **Step 5: mypy 検証**

Run: `uv run mypy -p lorairo`
Expected: 改名前と同じ結果（新規エラーなし）

- [ ] **Step 6: CI-equivalent filter で pytest 検証**

Run:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
Expected: PASS（collection エラーなし、改名前と同じ pass 数）

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): api/ を public_api/ へ改名 (Refs #717)\n\nHTTP/REST API との混同を避けるため公開インターフェース層を明示。\n内部 facade モジュールは説明的なので据え置き。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: push & PR 起票**

```bash
git push -u origin refactor/issue-717-public-api
gh pr create --title "refactor(structure): api/ → public_api/ (Refs #717)" \
  --body "$(printf '## 概要\n`src/lorairo/api/` を `public_api/` へ改名（Issue #717 サブPR1/4）。\n\nHTTP/REST API との混同を避けるため公開インターフェース層であることを明示。内部 facade モジュールは説明的なので据え置き。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ（import パスのみ）\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI green + bot レビュー safe を確認して squash merge**

CI green と Codex レビュー（非同期）の確認後に merge。dry-run/課金/DB 系の footgun が無いことを確認（本PRは純機械改名なので低リスク）。

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: worktree 削除**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-public-api
```

---

### Task 2: `editor/` → `image_transforms/`（優先度: 中 / 影響 7 files）

**Files:**
- Rename dir: `src/lorairo/editor/` → `src/lorairo/image_transforms/`
- Modify: `lorairo.editor` を import する全ファイル（`patch.dict("sys.modules", {"lorairo.editor.image_processor"...})` の文字列も含む）
- `autocrop.py`(AutoCrop) / `upscaler.py`(Upscaler) / `image_processor.py`(ImageProcessingManager, ImageProcessor) は据え置き
- tests に `editor` ミラーディレクトリは無い（editor テストはフラット）

**Interfaces:**
- Consumes: Task 1 完了後の `origin/main`（`public_api/` 済み）
- Produces: 公開パスが `lorairo.image_transforms.*` になる。

- [ ] **Step 1: worktree 作成**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-image-transforms -b refactor/issue-717-image-transforms origin/main
cd .agents/worktree/issue-717-image-transforms
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリを git mv**

```bash
git mv src/lorairo/editor src/lorairo/image_transforms
```

- [ ] **Step 3: import パスを一括置換**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
grep -rlE 'lorairo\.editor\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.editor\b/lorairo.image_transforms/g'
```

- [ ] **Step 4: 取りこぼし確認**

```bash
grep -rnE 'lorairo\.editor\b' src/ tests/ $SCOPE_DOCS 2>/dev/null
```
Expected: 出力なし

- [ ] **Step 5: mypy 検証**

Run: `uv run mypy -p lorairo`
Expected: 新規エラーなし

- [ ] **Step 6: CI-equivalent filter で pytest 検証**

Run:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
Expected: PASS

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): editor/ を image_transforms/ へ改名 (Refs #717)\n\nautocrop/upscale/image_processor の実態（画像変換処理）を反映。\nテキスト/GUI エディタとの混同を排除。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: push & PR 起票**

```bash
git push -u origin refactor/issue-717-image-transforms
gh pr create --title "refactor(structure): editor/ → image_transforms/ (Refs #717)" \
  --body "$(printf '## 概要\n`src/lorairo/editor/` を `image_transforms/` へ改名（Issue #717 サブPR2/4）。\n\n実態は autocrop/upscale/image_processor による画像変換処理。\n内部モジュール/クラス名は据え置き。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI green + bot レビュー safe を確認して squash merge**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: worktree 削除**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-image-transforms
```

---

### Task 3: `annotations/` → `annotation/` + モジュール/クラス改名（優先度: 低 / 影響 12 files）

**Files:**
- Rename dir: `src/lorairo/annotations/` → `src/lorairo/annotation/`
- Rename module: `annotation/annotation_logic.py` → `annotation/annotation_runner.py`（class `AnnotationLogic` → `AnnotationRunner`）
- Rename module: `annotation/existing_file_reader.py` → `annotation/sidecar_reader.py`（class `ExistingFileReader` → `SidecarAnnotationReader`）
- 据え置き: `annotator_adapter.py`(AnnotatorLibraryAdapter)
- Rename dir: `tests/unit/annotations/` → `tests/unit/annotation/`
- Rename test: `tests/unit/annotation/test_annotation_logic.py` → `test_annotation_runner.py`

**Interfaces:**
- Consumes: Task 2 完了後の `origin/main`
- Produces: `lorairo.annotation.annotation_runner.AnnotationRunner` / `lorairo.annotation.sidecar_reader.SidecarAnnotationReader` / `lorairo.annotation.annotator_adapter.AnnotatorLibraryAdapter`

- [ ] **Step 1: worktree 作成**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-annotation -b refactor/issue-717-annotation origin/main
cd .agents/worktree/issue-717-annotation
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリ/モジュールを git mv**

```bash
git mv src/lorairo/annotations src/lorairo/annotation
git mv src/lorairo/annotation/annotation_logic.py src/lorairo/annotation/annotation_runner.py
git mv src/lorairo/annotation/existing_file_reader.py src/lorairo/annotation/sidecar_reader.py
git mv tests/unit/annotations tests/unit/annotation
git mv tests/unit/annotation/test_annotation_logic.py tests/unit/annotation/test_annotation_runner.py
```

- [ ] **Step 3: import パス + モジュール名 + クラス名を一括置換**

順序に注意（dir → module → class）。各トークンは一意なので衝突しない。

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
# dir パス・絶対import（lorairo.annotations → lorairo.annotation。facade の lorairo.public_api.annotations は非マッチ）
grep -rlE 'lorairo\.annotations\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.annotations\b/lorairo.annotation/g'
# 相対import（from ..annotations / ...annotations 等、先頭ドット温存）← Task2で取りこぼし発覚した必須ステップ
grep -rlE 'from \.+annotations\b' src/ tests/ scripts/ 2>/dev/null \
  | xargs -r sed -i -E 's/(from \.+)annotations\b/\1annotation/g'
# モジュール名
grep -rl 'annotation_logic' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i 's/annotation_logic/annotation_runner/g'
grep -rl 'existing_file_reader' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i 's/existing_file_reader/sidecar_reader/g'
# クラス名
grep -rl 'AnnotationLogic' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i 's/AnnotationLogic/AnnotationRunner/g'
grep -rl 'ExistingFileReader' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i 's/ExistingFileReader/SidecarAnnotationReader/g'
```

- [ ] **Step 4: 取りこぼし確認**

```bash
grep -rnE 'lorairo\.annotations\b|from \.+annotations\b|annotation_logic|existing_file_reader|AnnotationLogic|ExistingFileReader' src/ tests/ scripts/ $SCOPE_DOCS 2>/dev/null
```
Expected: 出力なし

- [ ] **Step 5: mypy 検証**

Run: `uv run mypy -p lorairo`
Expected: 新規エラーなし

- [ ] **Step 6: CI-equivalent filter で pytest 検証**

Run:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
Expected: PASS（特にアノテーション系テストの collection 成功を確認）

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): annotations/ を annotation/ へ改名しモジュール名を明確化 (Refs #717)\n\n- annotations/ → annotation/（単数形で database/domain と整合）\n- annotation_logic.py → annotation_runner.py（AnnotationLogic → AnnotationRunner）\n- existing_file_reader.py → sidecar_reader.py（ExistingFileReader → SidecarAnnotationReader）\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: push & PR 起票**

```bash
git push -u origin refactor/issue-717-annotation
gh pr create --title "refactor(structure): annotations/ → annotation/ + module 明確化 (Refs #717)" \
  --body "$(printf '## 概要\nIssue #717 サブPR3/4。\n\n- `annotations/` → `annotation/`（単数形）\n- `annotation_logic.py`/`AnnotationLogic` → `annotation_runner.py`/`AnnotationRunner`（実行統括ランナー、ノイズ語 logic 排除）\n- `existing_file_reader.py`/`ExistingFileReader` → `sidecar_reader.py`/`SidecarAnnotationReader`（.txt/.caption サイドカー読取を明示）\n- `annotator_adapter.py` は据え置き\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI green + bot レビュー safe を確認して squash merge**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: worktree 削除**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-annotation
```

---

### Task 4: `storage/` → `filesystem.py` 平坦化（優先度: 低 / 影響 24 files / 最後）

**Files:**
- Move: `src/lorairo/storage/file_system.py` → `src/lorairo/filesystem.py`
- Delete: `src/lorairo/storage/__init__.py`（空）+ 空になった `storage/` ディレクトリ
- Modify: `lorairo.storage.file_system` を import する全ファイル（実形は `.file_system` のみ、`__init__` re-export なし）
- 据え置き: class `FileSystemManager`
- Rename dir: `tests/unit/storage/` → `tests/unit/filesystem/`（`test_file_system_manager.py` はそのまま）

**Interfaces:**
- Consumes: Task 3 完了後の `origin/main`
- Produces: `lorairo.filesystem.FileSystemManager`（単一モジュール、パッケージではない）

- [ ] **Step 1: worktree 作成**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-filesystem -b refactor/issue-717-filesystem origin/main
cd .agents/worktree/issue-717-filesystem
git submodule update --init --recursive
```

- [ ] **Step 2: ファイル平坦化 + テストディレクトリ改名**

```bash
git mv src/lorairo/storage/file_system.py src/lorairo/filesystem.py
git rm src/lorairo/storage/__init__.py
git mv tests/unit/storage tests/unit/filesystem
```

- [ ] **Step 3: import パスを一括置換**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
# 絶対import
grep -rlE 'lorairo\.storage\.file_system\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.storage\.file_system\b/lorairo.filesystem/g'
# 相対import（from ..storage.file_system / ...storage.file_system 等、先頭ドット温存）← Task2教訓の必須ステップ
grep -rlE 'from \.+storage\.file_system\b' src/ tests/ scripts/ 2>/dev/null \
  | xargs -r sed -i -E 's/(from \.+)storage\.file_system\b/\1filesystem/g'
```

- [ ] **Step 4: 取りこぼし確認（`lorairo.storage` / 相対 storage 残存ゼロ）**

```bash
grep -rnE 'lorairo\.storage\b|from \.+storage\b' src/ tests/ scripts/ $SCOPE_DOCS 2>/dev/null
```
Expected: 出力なし

- [ ] **Step 5: mypy 検証**

Run: `uv run mypy -p lorairo`
Expected: 新規エラーなし

- [ ] **Step 6: CI-equivalent filter で pytest 検証**

Run:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
Expected: PASS（FileSystemManager 利用テストの collection 成功を確認）

- [ ] **Step 7: commit**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): storage/ を filesystem.py へ平坦化 (Closes #717)\n\n1ファイル（file_system.py）のみのディレクトリを単一モジュールへ平坦化。\nlorairo.filesystem.FileSystemManager。FileSystemManager クラス名は維持。\n\nIssue #717 完了（全4サブPR）。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: push & PR 起票（Closes で Issue クローズ）**

```bash
git push -u origin refactor/issue-717-filesystem
gh pr create --title "refactor(structure): storage/ → filesystem.py 平坦化 (Closes #717)" \
  --body "$(printf '## 概要\nIssue #717 サブPR4/4（最終）。\n\n`storage/file_system.py`（1ファイルのみ）を単一モジュール `filesystem.py` へ平坦化。`from lorairo.filesystem import FileSystemManager`。クラス名は維持。\n\nこのPRで Issue #717 の全4サブPR完了。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nCloses #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI green + bot レビュー safe を確認して squash merge**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: worktree 削除 + 最終確認**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-filesystem
git fetch origin
gh issue view 717 --json state --jq .state   # CLOSED を期待
```

---

## 完了の定義

- 4サブPR すべて squash merge 済み
- `src/lorairo/` 配下に `api/` `editor/` `annotations/` `storage/` が存在しない
- `lorairo.public_api` / `lorairo.image_transforms` / `lorairo.annotation` / `lorairo.filesystem` で import できる
- Issue #717 が CLOSED
- 全 worktree 削除済み
