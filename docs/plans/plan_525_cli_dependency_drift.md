# Plan: Issue #525 — LoRAIro CLI 起動失敗 (typer / griffe / pydantic-ai dependency drift)

- **対象 Issue**: [#525](https://github.com/NEXTAltair/LoRAIro/issues/525)
- **関連 Issue**: #518 (本問題により実 CLI smoke が実施不能), #222 (並列 uv sync による venv 破損)
- **関連 ADR**: 0023 (PydanticAI/LiteLLM 境界), 0025 (uv.lock 運用), 0026 (On-Demand Runtime Validation)
- **関連 Rule**: `.claude/rules/dependency-management.md`, `.claude/rules/parallel-execution.md`

---

## 1. ultrathink 設計プロセス

Issue 報告では Symptom 1 (griffe) と Symptom 2 (typer-slim) の 2 つが並列で示されたが、現状調査の結果、両者は性質が異なることが判明した。

| Symptom | 報告 | 現状 (uv.lock + .venv 実測) | 根本原因 |
|---|---|---|---|
| 1: griffe top-level export 欠落 | `griffelib 2.0.2` install → `from griffe import Docstring` fail | uv.lock では `griffelib 2.0.2` 単独 resolve、`.venv` に `griffe 1.15.0` (uv.lock 外) が手動 install 残留 | pydantic-ai 1.100.0 upstream bug — `pydantic_ai/_griffe.py` が `griffe<2` の top-level API に依存 |
| 2: `module 'typer' has no attribute 'Typer'` | `typer-slim 0.20.1` install と推定 | uv.lock では `typer 0.25.1` (full) 正しく resolve / `.venv/lib/.../typer-0.25.1.dist-info` 存在。しかし `typer/` ディレクトリ実体は `.agents/skills/typer/SKILL.md` のみで `__init__.py` 等の本体ファイル全消失 | **venv 部分破損**。Issue #222 の並列 uv sync 破損か、最近 `typer 0.25.1` wheel に同梱された `.agents/skills/typer/SKILL.md` install 中に他ファイルが上書き失敗した可能性 |

**重要な再解釈**: Issue 報告時点では typer-slim が実際に install されていたが、その後 `uv lock` 更新で typer 0.25.1 に解決され直した。lock 自体は健全だが、venv のディスク状態が壊れている。つまり Symptom 2 は **lock 問題ではなく venv 状態問題** に変質した。

griffe 問題は依然として残る (lock では griffelib 単独で pydantic-ai が壊れる)。これは direct dep pin で固定する必要がある。

### pydantic-ai upstream の現状 (調査結果)

PyPI 直接確認 (2026-05-28 時点):

| version | release | 備考 |
|---|---|---|
| 1.94.0 | 2026-05-12 | mistralai quarantine 回避の最低 pin |
| 1.100.0 | 2026-05-21 | 現在 uv.lock で resolved (中間版) |
| 1.103.0 | 2026-05-27 | **最新安定版** (本 plan 策定時点) |
| 2.0.0b1〜b3 | 2026-05-21〜23 | beta — "harness-first" redesign、`openai:` prefix が Responses API 強制切替等の breaking change |

GitHub `v1.103.0` tag の `pydantic_ai_slim/pydantic_ai/_griffe.py` 直接確認結果:

```python
from griffe import Docstring, DocstringSectionKind, GoogleOptions, Object as GriffeObject
```

→ **1.103.0 でも依然として古い griffe 1.x top-level API を使用**。release notes に griffe 関連の言及なし。**pydantic-ai を bump しても griffe 問題は解決しない**ことが確定。

### スコープ判断: 本 Issue では griffe pin のみ

- **pydantic-ai 1.103.0 への bump は本 Issue スコープ外** (CLI 起動失敗の解決には不要)
- 2.0.0 beta は ADR 0023 同期経路と非互換 (`openai:` prefix Responses API 強制切替) のため不採用
- pydantic-ai bump は別 Issue / 月次 dependency review で評価する

### 設計判断のキーポイント

1. **dependency-management.md は AI SDK の upper bound を禁止しているが、`griffe` は AI SDK ではない** — pydantic-ai が依存する transitive dep。direct dep pin で `griffe>=1.15,<2.0` を追加するのは方針違反ではない。むしろ「下位互換性破壊が確認された minor / major release に対する一時 upper bound」の例外運用に該当する。
2. **typer は既に direct dep でlower bound のみ pin (`>=0.12.0`)**。lock では 0.25.1。これは正しい状態。問題は venv の物理破損なので `make venv-rebuild` で解決可能。
3. **upstream pydantic-ai bug は LoRAIro 側で根本解決不可**。pydantic-ai 1.100 → griffe 2.0 系 (griffelib) へ migration が未完了。LoRAIro 側ではワークアラウンド pin を入れ、upstream 修正が来たら外す。
4. **`/v1/chat/completions` Batch annotation (#518) は実 CLI smoke が #525 ブロックで未実施**。本 Issue を解決すれば #518 の closing 条件である実 CLI smoke が実施可能になる連鎖関係。

---

## 2. 要件・制約整理

### 成功基準

- [ ] `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv .venv/bin/python -m lorairo.cli.main --help` が成功
- [ ] `uv run lorairo --help` が成功
- [ ] 全 CLI subcommand (`project` / `images` / `annotate` / `export` / `models` / `batch`) が `--help` で import 成功
- [ ] `pydantic_ai._griffe` import が `griffelib` 環境ではなく `griffe 1.x` で成功し続ける
- [ ] `pyproject.toml` / `uv.lock` の整合 (ADR 0025)
- [ ] CI-equivalent filter test に regression なし (`testing.md`)
- [ ] make `venv-rebuild` 後も成功

### 制約条件

- **dependency-management.md**: AI SDK (pydantic-ai / openai / anthropic / google-genai / litellm / transformers / huggingface-hub / torch) は最新追従、upper bound 禁止。griffe / typer は対象外。
- **ADR 0025**: `uv.lock` は git commit 対象、direct dep 変更時に同時更新必須。
- **parallel-execution.md**: `uv sync` / `uv lock` は直列実行。並列実行で venv 破損 (Issue #222) を再発させない。
- **submodule pin 更新を含まないため CI-equivalent filter は推奨レベル** (本 Issue は submodule 非変更)。ただし regression 検出のため実施する。

### スコープ外

- pydantic-ai 1.100 upstream bug 自体の修正 (upstream PR は別タスク)
- griffelib 2.0 系への完全移行 (pydantic-ai が対応するまで待つ)
- venv 破損の根本原因追跡 (本計画では再構築で対症療法、再発時に Issue #222 系の調査をリオープン)

---

## 3. 現状・ギャップ分析

### 現状

**uv.lock**:
- `typer 0.25.1` (full, `typer.Typer` 提供) — ✅ 正常
- `griffelib 2.0.2` + `griffecli 2.0.2` (新 griffe 2.0 系、`_internal` ベース) — ❌ pydantic-ai 互換性なし
- `griffe` (旧 1.x 系、top-level API 提供) — lock 未記載 ❌

**.venv 実態**:
- `griffe 1.15.0` — 手動 `uv pip install 'griffe<2'` で install 済み (Issue 報告の workaround 痕跡)
- `typer 0.25.1` dist-info — ✅ 存在
- `typer/` ディレクトリ実体 — ❌ `__init__.py` 等全消失、`.agents/skills/typer/SKILL.md` のみ残存
- `pydantic-ai 1.100.0` — ✅ 正常 import (griffe 1.15.0 によりワークアラウンド成立)

**pyproject.toml**:
- `typer>=0.12.0` — 既に direct dep ✅
- `pydantic-ai>=1.94.0` — 既に direct dep ✅
- `griffe` — direct dep に未記載 ❌

### ギャップ

1. **lock 上の griffe missing**: 次回 `uv sync` で griffe 1.15.0 が剥がれて `griffelib` 単独になり、pydantic-ai が import 失敗するリスク。
2. **venv 内 typer 本体消失**: 現状で CLI 起動失敗。lock の `typer 0.25.1` が正しく venv に展開されていない。
3. **griffe pin の方針未文書化**: 一時 upper bound として `<2.0` を入れる場合、解除条件と監視タイミングが必要。

---

## 4. 複数ソリューション比較

### アプローチ A: 最小修正 (direct dep に griffe<2 追加 + venv 再構築)

**変更内容**:
- `pyproject.toml` dependencies に `"griffe>=1.15.0,<2.0",  # pydantic-ai 1.100 upstream bug workaround (#525)` を追加
- `uv lock --upgrade-package griffe` → `make venv-rebuild`

**Pros**:
- 変更最小、コメントで理由明示
- dependency-management.md の例外運用 (下位互換性破壊が確認された major release に対する一時 upper bound) に該当して正当
- 既存 typer pin はそのまま (`>=0.12.0`)、venv 再構築で本体ファイル復元

**Cons**:
- pydantic-ai 1.100 upstream bug への対症療法
- pydantic-ai が griffelib に migration 完了したら手動で `griffe<2` pin を外す必要 (月次 dependency review で確認)

**リスク**:
- 月次 review で外し忘れると pydantic-ai 新 version の griffelib 経路がブロックされる (低)

### アプローチ B: pydantic-ai を 1.93 以下に pin

**変更内容**:
- `pyproject.toml` の `pydantic-ai>=1.94.0` を `pydantic-ai>=1.94.0,<1.100` に変更

**Pros**:
- griffe 問題が直接消える (pydantic-ai 1.99 以下は griffelib 不要)

**Cons**:
- **dependency-management.md の "AI 推論 SDK は常に最新追従" 方針に正面違反**
- pydantic-ai 1.100 で導入された機能 (新 model 対応 / refusal handling 改善等) を全て放棄
- ADR 0023 (PydanticAI 採用) との整合性悪化
- mistralai quarantine 回避 pin (1.94.0+) との二重 pin で混乱

**リスク**:
- 新 model 対応で再 bump 必要、運用負担増 (高)
- LoRAIro #275 (claude-haiku-4-5 KeyError) と同じ "古い SDK が新 model に対応できない" 失敗パターン再来

### アプローチ C: 局所 reinstall のみ (venv 再構築なし)

**変更内容**:
- `uv sync --reinstall-package typer --reinstall-package griffe`
- `pyproject.toml` に griffe pin を追加
- `make venv-rebuild` は実施しない

**Pros**:
- 重い依存 (torch / tensorflow) の再ダウンロード回避、所要時間短い

**Cons**:
- venv 部分破損の根本原因が typer 単独なのか他にも波及しているか不明
- 他の壊れたパッケージが残留する可能性 (`.agents/skills/*/SKILL.md` 同梱パッケージは他にも存在する可能性)
- Issue #222 系の構造的問題に対する確実性が低い

**リスク**:
- 「直したと思ったら別パッケージで再発」する隠れ破損 (中)

### 推奨: アプローチ A

**選択理由**:
1. **修正範囲が最小で安全**: pyproject.toml に 1 行追加 + lock 更新 + venv 再構築のみ
2. **dependency-management.md の例外運用に該当**: griffe は AI SDK ではない transitive dep であり、upstream bug 回避の一時 upper bound は明示的に許容される (rule 内 "下位互換性破壊が確認された minor / major release のみ一時 upper bound 追加、追従修正 PR で外す")
3. **venv 再構築で他の隠れ破損も同時解消**: アプローチ C より確実性高い (再ダウンロード時間は許容範囲)
4. **upstream 修正が来た時に解除しやすい**: コメントで理由・解除条件を明示するため、月次 review で自動的に検出可能

---

## 5. アーキテクチャ設計

本 Issue はアーキテクチャ変更を伴わない (依存解決と venv 状態の修復のみ)。既存パターンに従う。

### pyproject.toml 配置

`dependencies` 配列の末尾、`litellm` の直後に追加し、コメントで関連付けを明示:

```toml
dependencies = [
    # ... 既存項目 ...
    "pydantic-ai>=1.94.0",
    "litellm>=1.84.0",
    # 2026-05-28: pydantic-ai (1.100 / 1.103 いずれも) の `pydantic_ai/_griffe.py` が
    # `from griffe import Docstring` 等の旧 griffe 1.x top-level API を期待するが、
    # universal lock では `griffelib 2.0.2` (top-level export を `_internal` に移動)
    # が resolve される。結果として pydantic-ai が import error になる (Issue #525)。
    # upstream pydantic-ai が griffelib API に追従するまでの workaround として
    # griffe 1.x の direct dep を明示する。pydantic-ai bump 時に解除可否を確認すること
    # (https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/_griffe.py)。
    "griffe>=1.15.0,<2.0",
]
```

**注**: pydantic-ai は `>=1.94.0` のまま据え置く。最新は 1.103.0 だが、bump しても griffe 問題は解決しない (上記 Section 1 で確認済み) ため、本 Issue では触らない。pydantic-ai 追従は別 PR で行う。

### 解除条件 (将来の参照用)

以下 **すべて** 満たした場合に `griffe` direct dep を削除する:
1. pydantic-ai upstream で `_griffe.py` が griffelib 2.0+ API (`griffe._internal` 経路) に移行
2. 新 pydantic-ai version の release notes で migration 完了が宣言
3. `uv sync` (griffe pin 外し) 後の `python -c "import pydantic_ai"` が成功
4. CI-equivalent filter test pass

月次 dependency review で本セクションを確認する。

---

## 6. 実装計画

### Phase 1: ブランチ & worktree 作成 (5 分)

```bash
# git-workflow.md に従い /tmp/worktrees/ 配下に作成
git worktree add /tmp/worktrees/fix-issue-525 -b fix/issue-525-cli-deps
cd /tmp/worktrees/fix-issue-525
```

### Phase 2: pyproject.toml 修正 (5 分)

- `dependencies` に `griffe>=1.15.0,<2.0` を追加 (理由コメント付き)
- typer pin は `>=0.12.0` のまま (現状で問題なし)

### Phase 3: lock 更新 (10 分)

```bash
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv lock --upgrade-package griffe
# 検証
grep -A 3 "^name = \"griffe\"" uv.lock   # griffe 1.x が登録されているか確認
grep "griffe" uv.lock | head -20         # griffelib との関係を確認
```

期待結果:
- `griffe 1.15.0+` が `[[package]]` として正式登録
- LoRAIro `[package.metadata]` の `requires-dist` に `griffe>=1.15.0,<2.0` が記録
- `griffelib 2.0.2` は pydantic-ai-slim transitive として共存 (LoRAIro が `griffe` 経路を上書き)

### Phase 4: venv 再構築 (10〜20 分、torch 再 DL 含む)

```bash
cd /workspaces/LoRAIro
make venv-rebuild
# = rm -rf .venv && uv sync --dev
```

注意:
- 実行中は他の `uv` コマンドを並行させない (parallel-execution.md)
- tensorflow / torch / transformers の再 DL で数分〜十数分
- 完了後 `.venv/bin/python -c "import typer; print(typer.Typer)"` で復元確認

### Phase 5: 動作確認 (10 分)

```bash
cd /workspaces/LoRAIro

# 1. 基本 import
UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv .venv/bin/python -c "
import pydantic_ai
import griffe; from griffe import Docstring
import typer; assert typer.Typer is not None
print('All imports OK')
"

# 2. CLI 起動 — 全 subcommand
.venv/bin/python -m lorairo.cli.main --help
.venv/bin/python -m lorairo.cli.main project --help
.venv/bin/python -m lorairo.cli.main images --help
.venv/bin/python -m lorairo.cli.main annotate --help
.venv/bin/python -m lorairo.cli.main export --help
.venv/bin/python -m lorairo.cli.main models --help
.venv/bin/python -m lorairo.cli.main batch --help

# 3. uv run 経路
uv run lorairo --help

# 4. CI-equivalent filter (testing.md)
.venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```

### Phase 6: PR 起票 (10 分)

```bash
cd /tmp/worktrees/fix-issue-525
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
fix: pin griffe<2 to work around pydantic-ai 1.100 upstream bug (#525)

pydantic-ai 1.100.0 の _griffe.py が `from griffe import Docstring`
等の旧 griffe 1.x top-level API を期待するが、universal lock では
griffelib 2.0.2 (top-level export を _internal に移動) が resolve され、
LoRAIro CLI 起動時に ImportError になっていた。

direct dep に `griffe>=1.15.0,<2.0` を追加してワークアラウンド。
pydantic-ai upstream が griffelib に追従したら本 pin を解除する。

合わせて venv 再構築で typer 0.25.1 の本体ファイル消失を修復。
これにより Issue #518 の実 CLI smoke も実施可能になる。

Refs: #525, #518
EOF
)"

git push -u origin fix/issue-525-cli-deps
gh pr create --title "fix: pin griffe<2 for CLI startup (#525)" --body "$(cat <<'EOF'
## Summary

- pydantic-ai 1.100.0 が古い griffe 1.x top-level API を期待するため `griffe>=1.15.0,<2.0` を direct dep に追加
- venv 再構築で typer 0.25.1 本体ファイル消失を修復
- Issue #518 の実 CLI smoke 実施を unblock

## Test plan

- [x] `python -c "from griffe import Docstring; import typer; assert typer.Typer"` 成功
- [x] `uv run lorairo --help` 成功
- [x] 全 CLI subcommand (project/images/annotate/export/models/batch) `--help` 成功
- [x] CI-equivalent filter pytest pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 7. テスト戦略

### 自動テスト

- **CI-equivalent filter** (testing.md):
  ```bash
  .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
  ```
- 既存 CLI test (`tests/unit/cli/...`) で typer.Typer 経由の subcommand 定義が collect 成功するか確認

### 手動 smoke test

- 全 CLI subcommand `--help` 表示
- `uv run lorairo --help` (project script 経由)
- pydantic-ai インスタンス化を伴う `lorairo annotate --help` (`_griffe` import path 確認)

### iam-lib との連携確認

- `make test-iam-lib` (LoRAIro root .venv 共有、ADR 0024 amended) で iam-lib 側 pytest pass を確認
- iam-lib 内の pydantic-ai 経路が griffe 1.x で動作することの間接確認

### Regression watchpoints

- Issue #275 系 (claude-haiku-4-5 KeyError): pydantic-ai 1.100 維持で SDK 最新追従、新 model 対応保持
- Issue #222 系 (並列 uv sync 破損): venv 再構築中の他 uv コマンド並行禁止、parallel-execution.md 遵守

---

## 8. リスク・対策

| リスク | 影響 | 確率 | 対策 |
|---|---|---|---|
| `make venv-rebuild` で他依存破損が顕在化 | 中 | 低 | 再構築後 `uv run pytest` で集中検証、破損依存があれば個別 reinstall |
| pydantic-ai 次 bump で griffe pin が解除不能 | 低 | 中 | コメントで解除条件明示、月次 review で確認 |
| typer 0.25.1 で B008 (`typer.Option` in defaults) 警告が増える | 低 | 低 | pyproject.toml `[tool.ruff.lint] ignore` に既に `B008` 追加済み |
| venv 再構築中 (10〜20分) の作業ブロック | 低 | 確実 | 他独立タスクと並行、終了通知で再開 |
| griffe 1.15.0 と griffelib 2.0.2 並存で Python が griffe 1.x を優先する保証なし | 中 | 低 | site-packages の `griffe/` ディレクトリは `griffe 1.x` wheel 由来。`griffelib` は別パッケージで Python module 名 衝突なし。実測で `pydantic_ai._griffe` が成功している (現状確認済み) |

---

## 9. LoRAIro 固有考慮事項

- **サービス層への影響**: なし (依存修復のみ)
- **DB スキーマ変更**: なし
- **GUI 影響**: なし (CLI 経路の修復のみ、GUI は別 entry point)
- **設定ファイル (config/lorairo.toml)**: 変更なし
- **AI 統合**: pydantic-ai 1.100.0 維持、annotation provider 動作維持
- **submodule pin**: 変更なし (iam-lib / genai-tag-db-tools いずれも触らない)

### CI-equivalent filter 適用判断

本 PR は submodule pin 変更を含まないため、hook gate (`hook_pre_pr_submodule_check.py`) の強制対象外。ただし依存変更によるregression リスクがあるため、推奨レベルで CI-equivalent filter を実施する。

---

## 10. 次ステップ (implement フェーズへの引き継ぎ)

### 実装着手前チェックリスト

- [x] Issue #525 内容把握
- [x] 関連 ADR (0023, 0025, 0026) 確認
- [x] dependency-management.md / parallel-execution.md / testing.md 確認
- [x] 現状 venv / uv.lock 実測
- [x] 3 アプローチ比較とトレードオフ評価
- [ ] **ユーザー承認** ← この plan の review

### `/implement` で実行する内容

1. worktree 作成 (`fix/issue-525-cli-deps`)
2. `pyproject.toml` に `griffe>=1.15.0,<2.0` 追加 (理由コメント付き)
3. `uv lock --upgrade-package griffe` で lock 更新
4. `make venv-rebuild` で venv 再構築
5. 動作確認 (CLI 全 subcommand `--help`)
6. CI-equivalent filter test pass 確認
7. commit + PR 起票

### 完了後アクション

- Issue #525 close (PR merge 時)
- Issue #518 の実 CLI smoke 実施 (本 Issue 解決により unblock)
- **メモリ保存**: dependency-management.md の例外運用ケースとして OpenClaw LTM に記録 (`griffe pin` の解除条件と monitoring 方針)
- **lessons-learned.md 追記候補**: "AI SDK が古い transitive API を期待する upstream bug への対処 = direct dep の `<X.Y` 一時 pin が正当な workaround"

### フォローアップ Issue 候補 (本 Issue スコープ外)

- **pydantic-ai 1.103.0 追従**: 現在 1.100.0 resolved。月次 dependency review で `uv lock --upgrade-package pydantic-ai` を実施。bump 時に `_griffe.py` の griffe API が変わっていれば griffe pin 解除を同時評価。
- **pydantic-ai 2.0 stable 評価**: 2.0 stable release 後、`openai:` prefix Responses API 強制切替 (ADR 0023 同期経路と非互換) の migration 計画を別 ADR で策定。

---

## Appendix: 調査で確認した事実

### A.1. pydantic-ai 1.100.0 の griffe import 経路

```python
# /workspaces/LoRAIro/.venv/lib/python3.13/site-packages/pydantic_ai/_griffe.py
from griffe import Docstring, DocstringSectionKind, GoogleOptions, Object as GriffeObject
```

これらは griffe 1.x の top-level export。griffelib 2.0.2 は `griffe/_internal/` のみで top-level export を提供しないため `ImportError`。

### A.2. .venv 内パッケージ実態 (調査時点)

```
griffe-1.15.0.dist-info/      ← 手動 install (Issue 内 workaround の痕跡、uv.lock 未記載)
griffe/                       ← 1.15.0 の本体ファイル一式 (正常)
griffecli-2.0.2.dist-info/    ← griffelib 2.0 系の CLI フロントエンド
griffecli/                    ← 同上
griffelib-2.0.2.dist-info/    ← pydantic-ai-slim transitive
griffelib モジュールパッケージ実態は uv.lock の RECORD 通り (本問題と無関係)

typer-0.25.1.dist-info/       ← 正常
typer/                        ← `.agents/skills/typer/SKILL.md` のみ、本体ファイル消失 (破損)
```

### A.3. uv.lock 内 typer / griffe / pydantic-ai

| パッケージ | uv.lock version | 状態 |
|---|---|---|
| `typer` | 0.25.1 | full typer (`Typer` クラス提供) |
| `griffelib` | 2.0.2 | pydantic-ai-slim transitive、新 griffe 2.0 系 |
| `griffe` | 未記載 | direct dep 追加で 1.15.0+ が登録される予定 |
| `pydantic-ai` | 1.100.0 | mistralai quarantine 回避 pin (≥1.94) |
| `pydantic-ai-slim` | 1.100.0 | griffelib transitive 依存 |

### A.4. typer wheel 内の `.agents/skills/typer/SKILL.md`

typer 0.25.1 (2026-04-30 release) wheel に同梱されている公式 Anthropic Claude skill。`META: name: typer, description: Typer best practices...`。venv 内で唯一残存しているのがこの skill ファイル単独であることから、wheel の partial extraction (file overwrite 中断 / 並列 uv sync race) が疑われるが、venv 再構築で復旧可能。

---

**End of Plan**
