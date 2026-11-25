# `src/lorairo` ディレクトリ・モジュール改名 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/lorairo/` 配下の 4 ディレクトリ(および一部モジュール・クラス)を、実態に即した説明的な名前へ機械的に改名する。ロジックの変更は一切行わない。

**Architecture:** ハードリネーム方式(`git mv` で履歴を温存し、インポートを一括置換する。deprecation shim は置かない)を採用する。1 ディレクトリにつき 1 サブ PR とし、優先度順に直列で実装・検証・マージする。各サブ PR は直前のサブ PR がマージされた後の `origin/main` からワークツリーを作成するため、リベースは不要である。

**Tech Stack:** Python 3.13、uv、GNU sed(`\b` 対応)、pytest、mypy、git worktree

## 全体制約

- **実行モデル:** 並列 Agent Teams は採用せず、リード単独で直列に実行する。前のサブ PR をマージしてから次のサブ PR のワークツリーを作成する。
- **ワークツリー運用:** 各サブ PR は `origin/main` から分岐した専用ワークツリー(`.agents/worktree/issue-717-<name>`)で作業する。共有 venv(`/workspaces/LoRAIro/.venv`)を使用し、ワークツリー内に `.venv` を作成しない。
- **検証方針:** CI 相当フィルタ(`-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`)と `uv run mypy -p lorairo` を実行する。ワークツリーでのローカル検証は editable install の都合でメインチェックアウトを参照する可能性があるため、**最終的な正否はプッシュ後の CI を信頼源(SSoT)とする**。
- **sed の置換対象:** `src/`、`tests/`、および live docs 5 ファイル(`docs/conftest_template.py`、`docs/integrations.md`、`docs/decisions/0037-api-facade-wiring-policy.md`、`docs/decisions/0059-cli-command-introspection.md`、`docs/specs/core/filesystem_management.md`)に限定する。設計・計画ドキュメント内の改名前記述を壊さないため、**`docs/superpowers/specs/` と `docs/superpowers/plans/` は除外する**。
- **相対インポートの置換(Task 2 の教訓):** `lorairo.<old>` の絶対インポートだけでなく、`from ..<old>` や `from ...<old>` の相対インポートも必ず置換する。相対インポートの漏れは mypy をすり抜け、実行時に `ModuleNotFoundError` を引き起こす。各タスクの sed に相対インポート置換を含め、取りこぼし確認にも `from \.+<old>\b` を加える。
- **平坦化時の相対インポート調整(Task 4 の教訓):** サブパッケージからトップレベルモジュールへ平坦化する場合、移動したファイル自身の相対インポートのドットを 1 つ減らす必要がある。たとえば `storage/file_system.py`(`.` が `storage`、`..` が `lorairo`)を `filesystem.py`(`.` が `lorairo`)へ移すと、ファイル内の `from ..utils.log` や `from ..database.db_core` が「attempted relative import beyond top-level package」エラーになるため、`from .X` へ修正する。インポートが壊れると mypy が依存シンボルを `Any` 扱いして `no-any-return` などの二次エラーを出すが、インポート修正で連鎖的に解消する。
- **`validate_docs.py` 連動ゲート:** 「Validate Agent Harness」は `CLAUDE.md`、`docs/services.md`、`docs/integrations.md`、`docs/testing.md` 内のファイルパス参照の存在を検証する。ディレクトリ・モジュール改名時は `CLAUDE.md` のパス参照と `scripts/validate_docs.py` の `integration_files` リストも追従させ、非必須チェックも含めて常に通る状態を保つ。
- **PR リンクとコミット規約:** サブ PR 1〜3 は `Refs #717`、最後のサブ PR 4 のみ `Closes #717` を記載する。リポジトリ規約に従い、コミット末尾に `Co-Authored-By` と `Claude-Session` を付与する。

**置換スコープのヘルパ変数(各タスクで使用):**
```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
```

---

### Task 1: `api/` → `public_api/`(優先度: 高 / 影響 35 ファイル)

**Files:**
- Rename dir: `src/lorairo/api/` → `src/lorairo/public_api/`
- Rename dir: `tests/unit/api/` → `tests/unit/public_api/`
- Modify: `src/lorairo/api.*` をインポートする全ファイル(`lorairo.api` → `lorairo.public_api`)
- 内部ファサードモジュール(`images.py`、`tags.py`、`project.py`、`export.py`、`batch_import.py`、`types.py`、`exceptions.py`、`annotations.py`)は据え置く。

**Interfaces:**
- 依存(Consumes): なし(最初のタスク)。
- 提供(Produces): 公開パスが `lorairo.public_api.*` になる。後続タスクは `lorairo.api` を参照しない前提とする。

- [ ] **Step 1: ワークツリーを作成する**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-public-api -b refactor/issue-717-public-api origin/main
cd .agents/worktree/issue-717-public-api
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリを `git mv` で改名する**

```bash
git mv src/lorairo/api src/lorairo/public_api
git mv tests/unit/api tests/unit/public_api
```

- [ ] **Step 3: インポートパスを一括置換する**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
grep -rlE 'lorairo\.api\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.api\b/lorairo.public_api/g'
```

- [ ] **Step 4: 取りこぼしがないことを確認する**

```bash
grep -rnE 'lorairo\.api\b' src/ tests/ $SCOPE_DOCS 2>/dev/null
```
期待結果: 出力なし(全件置換済み)。

- [ ] **Step 5: mypy で検証する**

実行コマンド: `uv run mypy -p lorairo`
期待結果: 改名前と同じ結果であり、新規エラーがない。

- [ ] **Step 6: CI 相当フィルタで pytest を検証する**

実行コマンド:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
期待結果: 収集エラーがなく、改名前と同じ件数で全テストが通る。

- [ ] **Step 7: コミットする**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): api/ を public_api/ へ改名 (Refs #717)\n\nHTTP/REST API との混同を避けるため公開インターフェース層を明示。\n内部 facade モジュールは説明的なので据え置き。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: プッシュして PR を起票する**

```bash
git push -u origin refactor/issue-717-public-api
gh pr create --title "refactor(structure): api/ → public_api/ (Refs #717)" \
  --body "$(printf '## 概要\n`src/lorairo/api/` を `public_api/` へ改名(Issue #717 サブPR1/4)。\n\nHTTP/REST API との混同を避けるため公開インターフェース層であることを明示。内部 facade モジュールは説明的なので据え置き。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ(import パスのみ)\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI と bot レビューの安全性を確認してスカッシュマージする**

CI が通り、非同期の Codex レビューに問題がないことを確認してからマージする。本 PR は機械的な改名のみであり、dry-run・課金・DB 系の危険箇所がないことを確認する。

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: ワークツリーを削除する**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-public-api
```

---

### Task 2: `editor/` → `image_transforms/`(優先度: 中 / 影響 7 ファイル)

**Files:**
- Rename dir: `src/lorairo/editor/` → `src/lorairo/image_transforms/`
- Modify: `lorairo.editor` をインポートする全ファイル(`patch.dict("sys.modules", {"lorairo.editor.image_processor"...})` の文字列参照も含む)
- `autocrop.py`(`AutoCrop`)、`upscaler.py`(`Upscaler`)、`image_processor.py`(`ImageProcessingManager`、`ImageProcessor`)は据え置く。
- `tests/` 配下に `editor` のミラーディレクトリはない(関連テストはフラット配置)。

**Interfaces:**
- 依存(Consumes): Task 1 完了後の `origin/main`(`public_api/` 適用済み)。
- 提供(Produces): 公開パスが `lorairo.image_transforms.*` になる。

- [ ] **Step 1: ワークツリーを作成する**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-image-transforms -b refactor/issue-717-image-transforms origin/main
cd .agents/worktree/issue-717-image-transforms
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリを `git mv` で改名する**

```bash
git mv src/lorairo/editor src/lorairo/image_transforms
```

- [ ] **Step 3: インポートパスを一括置換する**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
grep -rlE 'lorairo\.editor\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.editor\b/lorairo.image_transforms/g'
```

- [ ] **Step 4: 取りこぼしがないことを確認する**

```bash
grep -rnE 'lorairo\.editor\b' src/ tests/ $SCOPE_DOCS 2>/dev/null
```
期待結果: 出力なし。

- [ ] **Step 5: mypy で検証する**

実行コマンド: `uv run mypy -p lorairo`
期待結果: 新規エラーがない。

- [ ] **Step 6: CI 相当フィルタで pytest を検証する**

実行コマンド:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
期待結果: 全テストが通る。

- [ ] **Step 7: コミットする**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): editor/ を image_transforms/ へ改名 (Refs #717)\n\nautocrop/upscale/image_processor の実態(画像変換処理)を反映。\nテキスト/GUI エディタとの混同を排除。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: プッシュして PR を起票する**

```bash
git push -u origin refactor/issue-717-image-transforms
gh pr create --title "refactor(structure): editor/ → image_transforms/ (Refs #717)" \
  --body "$(printf '## 概要\n`src/lorairo/editor/` を `image_transforms/` へ改名(Issue #717 サブPR2/4)。\n\n実態は autocrop/upscale/image_processor による画像変換処理。\n内部モジュール/クラス名は据え置き。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI と bot レビューの安全性を確認してスカッシュマージする**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: ワークツリーを削除する**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-image-transforms
```

---

### Task 3: `annotations/` → `annotation/` とモジュール・クラス改名(優先度: 低 / 影響 12 ファイル)

**Files:**
- Rename dir: `src/lorairo/annotations/` → `src/lorairo/annotation/`
- Rename module: `annotation/annotation_logic.py` → `annotation/annotation_runner.py`(クラス `AnnotationLogic` → `AnnotationRunner`)
- Rename module: `annotation/existing_file_reader.py` → `annotation/sidecar_reader.py`(クラス `ExistingFileReader` → `SidecarAnnotationReader`)
- 据え置き: `annotator_adapter.py`(`AnnotatorLibraryAdapter`)
- Rename dir: `tests/unit/annotations/` → `tests/unit/annotation/`
- Rename test: `tests/unit/annotation/test_annotation_logic.py` → `test_annotation_runner.py`

**Interfaces:**
- 依存(Consumes): Task 2 完了後の `origin/main`。
- 提供(Produces): `lorairo.annotation.annotation_runner.AnnotationRunner`、`lorairo.annotation.sidecar_reader.SidecarAnnotationReader`、`lorairo.annotation.annotator_adapter.AnnotatorLibraryAdapter`。

- [ ] **Step 1: ワークツリーを作成する**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-annotation -b refactor/issue-717-annotation origin/main
cd .agents/worktree/issue-717-annotation
git submodule update --init --recursive
```

- [ ] **Step 2: ディレクトリとモジュールを `git mv` で改名する**

```bash
git mv src/lorairo/annotations src/lorairo/annotation
git mv src/lorairo/annotation/annotation_logic.py src/lorairo/annotation/annotation_runner.py
git mv src/lorairo/annotation/existing_file_reader.py src/lorairo/annotation/sidecar_reader.py
git mv tests/unit/annotations tests/unit/annotation
git mv tests/unit/annotation/test_annotation_logic.py tests/unit/annotation/test_annotation_runner.py
```

- [ ] **Step 3: インポートパス、モジュール名、クラス名を一括置換する**

ディレクトリ、モジュール、クラスの順に置換する。各トークンは一意であるため衝突しない。

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
# dir パス・絶対import(lorairo.annotations → lorairo.annotation。facade の lorairo.public_api.annotations は非マッチ)
grep -rlE 'lorairo\.annotations\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.annotations\b/lorairo.annotation/g'
# 相対import(from ..annotations / ...annotations 等、先頭ドット温存)← Task2で取りこぼし発覚した必須ステップ
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

- [ ] **Step 4: 取りこぼしがないことを確認する**

```bash
grep -rnE 'lorairo\.annotations\b|from \.+annotations\b|annotation_logic|existing_file_reader|AnnotationLogic|ExistingFileReader' src/ tests/ scripts/ $SCOPE_DOCS 2>/dev/null
```
期待結果: 出力なし。

- [ ] **Step 5: mypy で検証する**

実行コマンド: `uv run mypy -p lorairo`
期待結果: 新規エラーがない。

- [ ] **Step 6: CI 相当フィルタで pytest を検証する**

実行コマンド:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
期待結果: 全テストが通る(特にアノテーション系テストの収集成功を確認する)。

- [ ] **Step 7: コミットする**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): annotations/ を annotation/ へ改名しモジュール名を明確化 (Refs #717)\n\n- annotations/ → annotation/(単数形で database/domain と整合)\n- annotation_logic.py → annotation_runner.py(AnnotationLogic → AnnotationRunner)\n- existing_file_reader.py → sidecar_reader.py(ExistingFileReader → SidecarAnnotationReader)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: プッシュして PR を起票する**

```bash
git push -u origin refactor/issue-717-annotation
gh pr create --title "refactor(structure): annotations/ → annotation/ + module 明確化 (Refs #717)" \
  --body "$(printf '## 概要\nIssue #717 サブPR3/4。\n\n- `annotations/` → `annotation/`(単数形)\n- `annotation_logic.py`/`AnnotationLogic` → `annotation_runner.py`/`AnnotationRunner`(実行統括ランナー、ノイズ語 logic 排除)\n- `existing_file_reader.py`/`ExistingFileReader` → `sidecar_reader.py`/`SidecarAnnotationReader`(.txt/.caption サイドカー読取を明示)\n- `annotator_adapter.py` は据え置き\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nRefs #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI と bot レビューの安全性を確認してスカッシュマージする**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: ワークツリーを削除する**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-annotation
```

---

### Task 4: `storage/` → `filesystem.py` 平坦化(優先度: 低 / 影響 24 ファイル / 最終)

**Files:**
- Move: `src/lorairo/storage/file_system.py` → `src/lorairo/filesystem.py`
- Delete: 空の `src/lorairo/storage/__init__.py` および空になった `storage/` ディレクトリ
- Modify: `lorairo.storage.file_system` をインポートする全ファイル(実形は `.file_system` のみで `__init__` による再エクスポートはない)
- 据え置き: クラス `FileSystemManager`
- Rename dir: `tests/unit/storage/` → `tests/unit/filesystem/`(`test_file_system_manager.py` は据え置く)

**Interfaces:**
- 依存(Consumes): Task 3 完了後の `origin/main`。
- 提供(Produces): `lorairo.filesystem.FileSystemManager`(パッケージではなく単一モジュール)。

- [ ] **Step 1: ワークツリーを作成する**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/issue-717-filesystem -b refactor/issue-717-filesystem origin/main
cd .agents/worktree/issue-717-filesystem
git submodule update --init --recursive
```

- [ ] **Step 2: ファイルを平坦化し、テストディレクトリを改名する**

```bash
git mv src/lorairo/storage/file_system.py src/lorairo/filesystem.py
git rm src/lorairo/storage/__init__.py
git mv tests/unit/storage tests/unit/filesystem
```

- [ ] **Step 3: インポートパスを一括置換する**

```bash
SCOPE_DOCS="docs/conftest_template.py docs/integrations.md docs/decisions/0037-api-facade-wiring-policy.md docs/decisions/0059-cli-command-introspection.md docs/specs/core/filesystem_management.md"
# 絶対import
grep -rlE 'lorairo\.storage\.file_system\b' src/ tests/ $SCOPE_DOCS 2>/dev/null \
  | xargs -r sed -i -E 's/lorairo\.storage\.file_system\b/lorairo.filesystem/g'
# 相対import(from ..storage.file_system / ...storage.file_system 等、先頭ドット温存)← Task2教訓の必須ステップ
grep -rlE 'from \.+storage\.file_system\b' src/ tests/ scripts/ 2>/dev/null \
  | xargs -r sed -i -E 's/(from \.+)storage\.file_system\b/\1filesystem/g'
```

- [ ] **Step 4: 取りこぼしがないことを確認する(`lorairo.storage` と相対 `storage` の残存ゼロ)**

```bash
grep -rnE 'lorairo\.storage\b|from \.+storage\b' src/ tests/ scripts/ $SCOPE_DOCS 2>/dev/null
```
期待結果: 出力なし。

- [ ] **Step 5: mypy で検証する**

実行コマンド: `uv run mypy -p lorairo`
期待結果: 新規エラーがない。

- [ ] **Step 6: CI 相当フィルタで pytest を検証する**

実行コマンド:
```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```
期待結果: 全テストが通る(`FileSystemManager` 利用テストの収集成功を確認する)。

- [ ] **Step 7: コミットする**

```bash
git add -A
git commit -m "$(printf 'refactor(structure): storage/ を filesystem.py へ平坦化 (Closes #717)\n\n1ファイル(file_system.py)のみのディレクトリを単一モジュールへ平坦化。\nlorairo.filesystem.FileSystemManager。FileSystemManager クラス名は維持。\n\nIssue #717 完了(全4サブPR)。\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01GZuJm4xB1aKbtYh6pUHoyu')"
```

- [ ] **Step 8: プッシュして PR を起票する(`Closes` で Issue をクローズ)**

```bash
git push -u origin refactor/issue-717-filesystem
gh pr create --title "refactor(structure): storage/ → filesystem.py 平坦化 (Closes #717)" \
  --body "$(printf '## 概要\nIssue #717 サブPR4/4(最終)。\n\n`storage/file_system.py`(1ファイルのみ)を単一モジュール `filesystem.py` へ平坦化。`from lorairo.filesystem import FileSystemManager`。クラス名は維持。\n\nこのPRで Issue #717 の全4サブPR完了。\n\n## 検証\n- mypy / CI-equivalent filter 全 pass\n- ロジック変更ゼロ\n\nCloses #717\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)')"
```

- [ ] **Step 9: CI と bot レビューの安全性を確認してスカッシュマージする**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 10: ワークツリーを削除し、最終確認を行う**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/issue-717-filesystem
git fetch origin
gh issue view 717 --json state --jq .state   # CLOSED を期待
```

---

## 完了の定義

- 4 つのサブ PR がすべてスカッシュマージ済みであること。
- `src/lorairo/` 配下に `api/`、`editor/`、`annotations/`、`storage/` が存在しないこと。
- `lorairo.public_api`、`lorairo.image_transforms`、`lorairo.annotation`、`lorairo.filesystem` としてインポートできること。
- Issue #717 が `CLOSED` になっていること。
- すべてのワークツリーが削除済みであること。
