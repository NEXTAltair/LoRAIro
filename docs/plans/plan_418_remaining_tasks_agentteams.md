c# Tracking Issue #418 残タスク並行実装計画 (Agent Teams)

- **日付**: 2026-05-25
- **対象**: Tracking Issue #418 の残 4 タスク (#413 / #420 / #422 / #423)
- **戦略**: Agent Teams (worktree 分離) による 2 Wave 構成
- **前提**: ADR 0035 / 0036 / 0037 確定済、`.claude/rules/coding-style.md` Manager 層方針追記済

## 1. 残タスク総覧

| Issue | 種別 | スコープ | 確定済み設計指針 | 規模 |
|---|---|---|---|---|
| #413 | chore | GUI dead code 削除 3 ファイル候補 | (該当 ADR 無し、grep 再検証必要) | 小 |
| #420 | refactor | `FilterSearchPanel` (1,697 行) を sub-widget 化 | **ADR 0036** | 大 |
| #422 | refactor | `db_manager.py` (1,264 行) broad-except 統一 | **`.claude/rules/coding-style.md` Manager 層方針** | 中 |
| #423 | refactor | `db_repository.py` (3,942 行) を 5 Repository に分割 | **ADR 0035** (5 段階 PR) | 特大 |

### 残タスク以外の状況

- ADR 系 (#426/#427/#428/#429) は CLOSED 済 → 設計指針は確定
- 設計指針依存タスクは全て前提解消
- 並列ブロッカーは「同一ファイル編集の衝突」のみ

## 2. 事前調査で判明した重要事項

### 2.1 #413 の前提崩れ (dead code 疑いの再評価が必要)

Issue #413 が「dead code 疑い」と挙げた 3 ファイルを `grep -r` で再検証した結果:

| 対象 | 検出結果 | 判定 |
|---|---|---|
| `gui/widgets/file_picker.py` | `ConfigurationWindow_ui.py` で `FilePickerWidget` を import (UI 生成コード) | **削除不可** |
| `gui/workers/modern_progress_manager.py` | `gui/services/worker_service.py` で `ModernProgressManager` を使用中、`workers/__init__.py` で公開シンボル | **削除不可** |
| `gui/workers/manager.py` | production 内 import 検出されず、テスト `tests/unit/gui/workers/test_manager.py` のみ | **要詳細確認** |

→ #413 のタスクは「3 件削除」から「**詳細 grep → 削除可能なものだけ削除、残りは `# pragma: no cover` / `.coveragerc omit`**」に縮小される。

### 2.2 #422 と #423 の編集競合点

両 Issue とも `src/lorairo/database/db_manager.py` を編集する:

- **#422 が変更する部分**: `try / except Exception` ブロック内のロジック (21+ メソッド)
- **#423 が変更する部分**: `__init__` の Repository instantiation (1 個 → 5 個 composition)、各メソッドの `self.repository.xxx` → `self.image_repo.xxx` 等の呼び替え

両者は **同じメソッド本体に手を入れる** ため、Wave 内で並行すると merge conflict が広範囲発生する。
→ Wave 1 で #422 を完了 → Wave 2 で #423 が更新済み db_manager.py を基点に進める。

### 2.3 ADR 0035 の段階移行戦略

ADR 0035 §6 で `ImageRepository` 分割は **5 段階 PR** を明示:

1. `ModelRepository` (依存少)
2. `ProjectRepository`
3. `ErrorRecordRepository`
4. `ImageRepository`
5. `AnnotationRepository` (genai-tag-db-tools 連携、最複雑)

各段階で `db_manager.py` の import / 属性追加が必要。段階間で並行不可。

## 3. 並行戦略 (2 Wave 構成)

### Wave 1: 3 Team 並列実行

| Team | Issue | 担当ファイル境界 | 工数目安 | 依存 |
|---|---|---|---|---|
| **Team A** (chore-cleanup) | #413 | `gui/widgets/file_picker.py`, `gui/workers/manager.py`, `gui/workers/modern_progress_manager.py` 周辺 (削除 or pragma) | 1–2h | なし |
| **Team B** (gui-refactor) | #420 | `gui/widgets/filter_search_panel.py` + 新規 `gui/widgets/filter_search/` ディレクトリ | 6–10h | ADR 0036 |
| **Team C** (db-errors) | #422 | `database/db_manager.py` のみ | 4–6h | rule (Manager 層方針) |

#### Wave 1 ファイル境界マトリクス (衝突なしを確認)

| ファイル | Team A | Team B | Team C |
|---|---|---|---|
| `gui/widgets/file_picker.py` | △ (削除候補) | - | - |
| `gui/workers/manager.py` | △ (削除候補) | - | - |
| `gui/workers/modern_progress_manager.py` | △ (削除候補) | - | - |
| `gui/workers/__init__.py` | △ (`__all__` 整理) | - | - |
| `gui/widgets/filter_search_panel.py` | - | ◯ (mediator 化) | - |
| `gui/widgets/filter_search/*.py` | - | ◯ (新規) | - |
| `database/db_manager.py` | - | - | ◯ (except 統一) |
| テストファイル | △ (テスト削除) | ◯ (sub-widget test 追加) | ◯ (例外伝播 test 追加) |

**結論**: Wave 1 の 3 Team は **同一ファイルを編集しない** → 並行安全。

### Wave 2: 1 Team × 5 段階 PR

| Team | Issue | 段階 | 担当ファイル | 工数目安 |
|---|---|---|---|---|
| **Team D** (db-repo-split) | #423-1 | `ModelRepository` 抽出 | `database/repository/{base,model}.py` 新規 + `db_repository.py` re-export + `db_manager.py` import | 2–3h |
| | #423-2 | `ProjectRepository` 抽出 | `database/repository/project.py` 新規 + 同上 | 1–2h |
| | #423-3 | `ErrorRecordRepository` 抽出 | `database/repository/error_record.py` 新規 + 同上 | 1–2h |
| | #423-4 | `ImageRepository` 抽出 | `database/repository/image.py` 新規 + 同上 | 3–4h |
| | #423-5 | `AnnotationRepository` 抽出 + ファサード削除 | `database/repository/annotation.py` 新規 + genai-tag-db-tools 連携移設 + 旧 `db_repository.py` 削除 | 4–6h |

**Wave 2 を Wave 1 後に置く根拠:**

- ADR 0035 §3 で「Manager 畳み込みは本 ADR スコープ外、#422 の error handling 統一と同時に判断」と明記
- #422 で `db_manager.py` の except が安定化 → Team D の import 修正が小さな diff で済む
- Wave 1 の Team B (#420) が完了済なら GUI 側の Repository 呼び出し変更時に regression を検知しやすい

## 4. Worktree 構成

`.claude/rules/git-workflow.md` + `parallel-execution.md` 準拠で `/tmp/worktrees/` 配下に配置:

```
/tmp/worktrees/
├── cleanup-issue-413/       # Team A (Wave 1)
├── refactor-issue-420/      # Team B (Wave 1)
├── refactor-issue-422/      # Team C (Wave 1)
└── refactor-issue-423/      # Team D (Wave 2、段階 PR を同一 worktree で順次)
```

各 worktree は LoRAIro root の named volume `.venv` を共有 (ADR 0024 amended #291):
- テスト実行時は `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest` 経由
- 並列で `uv sync` / `uv run --active` は禁止 (Issue #222 教訓、Hook で機械的ブロック)

各 Team は実装着手時に独立 branch を切る:

```bash
# Wave 1 起動コマンド (3 並列)
git worktree add /tmp/worktrees/cleanup-issue-413  -b chore/issue-413-dead-code
git worktree add /tmp/worktrees/refactor-issue-420 -b refactor/issue-420-filter-panel
git worktree add /tmp/worktrees/refactor-issue-422 -b refactor/issue-422-db-manager-errors
```

## 5. Team 別実装ステップ

### Team A (#413): GUI dead code 詳細検証 + 削除 / pragma

1. `git worktree add /tmp/worktrees/cleanup-issue-413 -b chore/issue-413-dead-code`
2. **詳細 grep**: `find src tests -name "*.py" -print0 | xargs -0 grep -l <symbol>` で 3 ファイルの参照を完全列挙
3. 判定マトリクスを作成:
   - 真に未使用 → ファイル削除 + 対応テスト削除 + `__init__.py` `__all__` 更新
   - 部分使用 → `# pragma: no cover` (ファイル冒頭) または `.coveragerc` omit 追加
4. ローカルテスト: `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`
5. PR 起票: `chore: GUI dead code 削除 / pragma 適用 (#413)`

**事前判明している事項**: `file_picker.py` と `modern_progress_manager.py` は削除不可 → 主に pragma / omit 対応になる見込み。

### Team B (#420): FilterSearchPanel 分割 (ADR 0036 §6 準拠)

1. `git worktree add /tmp/worktrees/refactor-issue-420 -b refactor/issue-420-filter-panel`
2. `src/lorairo/gui/widgets/filter_search/` ディレクトリ作成
3. 4 コンポーネント抽出 (ADR 0036 §6 のテーブル通り):
   - `tag_suggestion.py`: `TagSuggestionWidget` + `_TagSuggestionTask`
   - `favorite_filter.py`: `FavoriteFilterPanel`
   - `count_estimate.py`: `CountEstimateWidget` + `_CountEstimateTask`
   - `pipeline_state.py`: `PipelineStateMachine` (Qt-free)
4. `filter_search_panel.py` を mediator として残し composition で持つ (import 互換)
5. 各 sub-widget の `qtbot` 独立テスト追加 (ADR 0036 §5)
6. `PipelineStateMachine` は unit test で完全検証 (Qt 非依存)
7. ローカル CI-equivalent filter で regression 確認
8. PR 起票: `refactor: FilterSearchPanel を sub-widget に分割 (#420)`

### Team C (#422): db_manager.py error handling 統一 (rule 準拠)

1. `git worktree add /tmp/worktrees/refactor-issue-422 -b refactor/issue-422-db-manager-errors`
2. 47 メソッドを分類:
   - **「not found 正常系」**: `return None / [] / 0` を維持 (e.g. `get_image` で未登録)
   - **「DB/IO 失敗」**: `except SQLAlchemyError` に絞り再 raise
   - **「二次エラー防止」**: `save_error_record` 等の sentinel return は docstring で理由明記
3. broad-except (`except Exception`) を 21+ 箇所から削除
4. テスト追加 (#414 で Top 5 ファイル test を一度通っているが、新しい raise 経路を unit test で固定)
5. Worker boundary / GUI boundary が新例外を吸収することを integration test で検証
6. ローカル CI-equivalent filter で regression 確認
7. PR 起票: `refactor: db_manager.py の broad-except を統一し silent failure を解消 (#422)`

**注意**: ADR 0033 (Worker 例外伝播契約) との整合を必ず確認。Worker layer で `error_occurred` signal に変換する責務が増える可能性。

### Team D (#423): db_repository.py 5 Repository 分割 (Wave 2、5 段階 PR)

各段階は独立 PR を起票し、main へ merge してから次の段階に進む:

#### 段階 1: ModelRepository 分割

1. `git worktree add /tmp/worktrees/refactor-issue-423 -b refactor/issue-423-1-model-repo` (main 最新を取得した状態)
2. `src/lorairo/database/repository/base.py` 新規 (BaseRepository + `BATCH_CHUNK_SIZE`)
3. `src/lorairo/database/repository/model.py` 新規 (Model 関連メソッド移設)
4. `db_repository.py` を re-export ファサード化 (ADR 0035 §5)
5. `db_manager.py` で `self.model_repo = ModelRepository(...)` 追加 (既存 `self.repository.get_model_*` 呼び出しを `self.model_repo.get_model_*` に置換)
6. ローカルテスト → PR 起票

#### 段階 2-5: 同パターンで Project / ErrorRecord / Image / Annotation を順次抽出

- 各段階の PR 起票前に CI-equivalent filter
- 段階 5 完了後、re-export ファサード削除 + `db_repository.py` 物理削除 (旧名残)

**段階 5 の特殊事項**: `MergedTagReader` / `TagRegisterService` の初期化を `AnnotationRepository` に移設 (ADR 0035 §4)。LoRAIro 起動コストへの影響をプロファイリングで確認。

## 6. テスト戦略

### 6.1 全 Team 共通

- **CI-equivalent filter** (`.claude/rules/testing.md` 必須):
  ```bash
  .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
  ```
- **カバレッジ**: 75% 以上維持 (`uv run pytest --cov=src --cov-report=xml`)
- **PR 起票前**: `make format && make mypy` で lint / type check 必須

### 6.2 Team 別追加要件

| Team | 追加テスト |
|---|---|
| Team A | 削除した dead code に対応するテストファイルも同時削除、pragma 適用箇所は coverage.xml で denominator 減を確認 |
| Team B | 各 sub-widget の `qtbot` 単独テスト、`PipelineStateMachine` の unit test (Qt-free)、mediator のシグナル流通 integration test |
| Team C | broad-except 削除前後の raise 経路を unit test で固定、Worker boundary が新例外を `error_occurred` に変換することを integration test で検証 |
| Team D | 各段階で Repository 単独 mock 化が機能することを確認 (`Mock(spec=ModelRepository)` 等)、ADR 0035 §5 のファサード経由 import が壊れていないことを確認 |

### 6.3 PR レビュー時の verification gate

`gh pr create` 時に `.claude/hooks/hook_pre_pr_submodule_check.py` が gate として動く可能性 (submodule 変更を含む PR の場合のみ)。本計画の 4 Issue は submodule 変更を伴わないため通常 gate のみ。

## 7. リスクと対策

| ID | リスク | 軽減策 |
|---|---|---|
| R1 | Wave 1 の 3 Team の PR レビュー / merge が滞り Team D が待つ | Wave 1 PR を Draft で並行起票し、レビューを並列化 |
| R2 | #413 の dead code 削除候補が実は使用中で削除不可 (一部既に判明) | 詳細 grep をタスク Step 2 として明示、pragma フォールバックを許容 |
| R3 | Team B の sub-widget 抽出で `filter_search_panel.py` の import 互換が壊れる | `filter_search/__init__.py` で旧シンボルを re-export、`from .widgets.filter_search_panel import FilterSearchPanel` の使用箇所を grep で確認 |
| R4 | Team C の例外 raise が GUI 側で吸収されず未捕捉例外で落ちる | Worker boundary / GUI event handler の境界層で `try/except` を追加するパッチを Team C の PR に含める |
| R5 | Team D 段階 5 (Annotation) で `MergedTagReader` 初期化タイミング変更が起動回帰 | 段階 5 PR では benchmark (`uv run lorairo --start-profile`) で startup time 比較を必須化 |
| R6 | 並列 `uv sync` で `.venv` 破損 (Issue #222 再発) | `parallel-execution.md` 準拠、`uv sync` は直列、`UV_PROJECT_ENVIRONMENT=root/.venv` で root venv を共有 |
| R7 | worktree 配下に bind mount で `.venv` 作成し test が遅くなる (#288) | worktree 内で `uv sync` せず root の named volume venv を使う |

## 8. PR 起票順序とマージ戦略

### Wave 1 (並列、Draft → Ready 順序自由)

- PR-A (#413): `chore: GUI dead code 削除 / pragma`
- PR-B (#420): `refactor: FilterSearchPanel sub-widget 分割`
- PR-C (#422): `refactor: db_manager.py error handling 統一`

3 PR は **互いに独立** → main にどの順序で merge しても conflict 無し。

### Wave 2 (順次)

Wave 1 全 merge 後に main をベースとして開始:

- PR-D1 (#423-1): `refactor: ModelRepository 抽出`
- PR-D2 (#423-2): `refactor: ProjectRepository 抽出`
- PR-D3 (#423-3): `refactor: ErrorRecordRepository 抽出`
- PR-D4 (#423-4): `refactor: ImageRepository 抽出`
- PR-D5 (#423-5): `refactor: AnnotationRepository 抽出 + ファサード削除`

各 PR-D は **前段階 merge 後** に開始。1 PR 単位で revert 可能な粒度。

## 9. Agent Teams 実装時の sub-agent 活用

各 Team が必要に応じて使う subagent:

| Team | 推奨 subagent | 用途 |
|---|---|---|
| Team A | `investigation` | `find ... | xargs grep` を絶対精度で実行 |
| Team B | `investigation` → `lorairo-qt-widget` skill | sub-widget 構造調査 → Qt 実装パターン適用 |
| Team C | `solutions` → `build-error-resolver` | 47 メソッドの分類検討 → except 削除後の test 失敗解消 |
| Team D | `db-schema-reviewer` → `query-analyzer` | Repository 分割後の整合性 → クエリ性能回帰 check |
| 全 Team | `test-runner` → `code-formatter` → `code-reviewer` | PR 起票前の verification gate |

## 10. 期待効果

- 全体カバレッジ: 79.34% → **88-90%** (ADR 0035/0036 分割後の独立テスト追加で底上げ)
- `db_manager.py` の silent failure 撲滅 (47 メソッド中 21+ → 0)
- `filter_search_panel.py` の 6 責務 → 4 sub-widget + 1 mediator
- `db_repository.py` の god class (3,942 行) → 5 Repository (各 ~800 行平均)
- Single Responsibility 原則違反の根本解消
- 将来の widget / repository 拡張時にも ADR 0035 / 0036 が指針として機能

## 11. 次ステップ

1. 本計画書をユーザーに確認してもらう
2. 承認後、`/implement` フェーズに移行
3. Wave 1 着手: 3 worktree を並列作成 → 3 Team で並行実装
4. Wave 1 全 PR merge → Wave 2 着手 (5 段階 PR を順次)

## 12. 関連

- **Tracking**: #418
- **ADR**: 0035 (Repository), 0036 (Widget), 0037 (api Facade、本計画では関係薄)
- **Rule**: `.claude/rules/coding-style.md` Manager 層エラーハンドリング方針
- **テストルール**: `.claude/rules/testing.md` (CI-equivalent filter)
- **並列実行ルール**: `.claude/rules/parallel-execution.md`
- **Worktree ルール**: `.claude/rules/git-workflow.md`
