# Plan: Issue #535 CLI/GUI DX エピック (Agent Teams 並列実装)

- **対象 Issue**: [#535](https://github.com/NEXTAltair/LoRAIro/issues/535) (epic) / サブ [#539](https://github.com/NEXTAltair/LoRAIro/issues/539) [#540](https://github.com/NEXTAltair/LoRAIro/issues/540) [#541](https://github.com/NEXTAltair/LoRAIro/issues/541)
- **作成日**: 2026-05-29
- **戦略**: 2-track 並列（Track A=#539+#540 同一オーナー / Track B=#541 独立）

---

## 1. 要件・成功基準

### #540 — meta コマンドの annotator registry 遅延ロード
`lorairo-cli --help` 実測 **~2.2s**（registry/model discovery が走る）。annotation を実行しない meta コマンドは registry を初期化すべきでない。
- **成功基準**: `--help` / `version` が image-annotator-lib annotator を初期化しない。`models list` 等 registry が必要なコマンドは従来どおり初期化。import-level smoke test で help/version の軽量性を証明。

### #539 — CLI ログレベル設定可能化
`cli/main.py` の `main()` で log level が `WARNING` 固定 → 運用者向け INFO 進捗が `logs/lorairo-cli.log` に残らない（#531 の診断性ギャップの原因）。
- **成功基準**: 既定 `INFO` で phase 遷移・最終サマリーを記録。`--log-level LEVEL` で上書き可能（`WARNING` で INFO 抑制）。実 annotation を呼ばずにテスト。

### #541 — `lorairo --help` から `lorairo-cli` へ誘導
GUI launcher (`src/lorairo/main.py`, argparse) の help が `lorairo-cli` に触れていない。
- **成功基準**: `lorairo --help` に batch/annotation/dataset 操作は `lorairo-cli --help` を案内する行を追加。既存 launcher option は不変。

---

## 2. 現状分析（調査結果）

| 項目 | 現状 |
|---|---|
| CLI logging | `cli/main.py:144` `main()` で `initialize_logging({"level": "WARNING", ...})` 固定。`app()` の**前**に呼ばれる |
| meta コマンド起動コスト | `cli.main` import 時に command モジュール → `service_container` → annotator adapter → image-annotator-lib の chain が transitive に重い import を引く（~2.2s）。command モジュールは `get_service_container()` を**関数内で遅延呼び出し**しており、重さは import-time chain 由来 |
| GUI launcher help | `src/lorairo/main.py:167` `argparse.ArgumentParser(epilog=...)`。`使用例` のみで CLI 言及なし |
| 既存 lazy import 方針 | ADR 0010（torch/tensorflow/onnxruntime をモジュールレベル import せず関数内 lazy import）。skill `lazy-import-refactor` あり |

### #539 / #540 の相乗効果
ログ初期化を Typer `@app.callback` に移すと、`--help` は callback を実行せず短絡終了するため重い初期化も走らない。両者は `cli/main.py` の同じ初期化フローに関わるため**同一オーナーが直列実装**するのが安全（別オーナー並列だと `cli/main.py` で衝突）。

---

## 3. アプローチとトレードオフ

| 案 | 並列性 | 衝突 | 採否 |
|---|---|---|---|
| 2-track: A=#539+#540 / B=#541 | 高（A=bulk / B=独立 `lorairo/main.py`） | A 内は直列で衝突なし、B は別ファイルで衝突なし | **採用** |
| 3-track: #539/#540/#541 個別 | 最大 | #539 と #540 が `cli/main.py` で衝突 | 不採用 |
| 単独セッション順次 | なし | なし | 代替可（規模小なら） |

---

## 4. 実装方針

### Track A — #540 → #539（この順、同一オーナー、`cli/main.py` 中心）

**#540 lazy import（先に構造を確立）** — skill `lazy-import-refactor` を使用:
1. `-X importtime` で `import lorairo.cli.main` の重い import 源を pinpoint（image-annotator-lib / litellm / torch 系）。
2. ADR 0010 に倣い、重い import を関数内/遅延化。具体的には `cli/main.py` の module-top `from lorairo.cli.commands import ...` / `from lorairo.services.service_container import get_service_container` 経由で transitive に走る重い import を切る。候補:
   - command モジュール（annotate/models 等）が import 時に annotator adapter / image-annotator-lib を引く箇所を関数内 import へ。
   - `service_container` の重い import を lazy 化（`importlib.import_module` or 関数内 import）。
3. `models list` 等 registry 必須コマンドは従来どおり動くことを保証。
4. **import-level smoke test**: subprocess で `lorairo-cli --help` / `version` 実行後に `image_annotator_lib` が `sys.modules` に**入っていない**ことを assert（conftest のグローバルモックに影響されない subprocess 方式）。

**#539 log level**:
1. ログ初期化を `@app.callback()` へ移し、`--log-level LEVEL`（既定 `INFO`）option を追加。`main()` の hard-coded `WARNING` 初期化を整理。
2. INFO に phase 遷移・最終サマリー、per-item は DEBUG（`.claude/rules/logging.md` 準拠）。`--log-level WARNING` で INFO 抑制。
3. `--help` で callback 非実行＝ログ初期化も走らない（#540 と整合）。
4. テスト: `CliRunner` + `initialize_logging` を mock/spy し、`--log-level` 値が反映されることを検証（実 annotation 不要）。

**Track A ファイル所有**: `src/lorairo/cli/main.py`、必要に応じ `src/lorairo/cli/commands/*.py` / `src/lorairo/services/service_container.py` の import 行、`tests/unit/cli/test_*`（log-level テスト + import-lightness smoke test、別ファイル新規）。

### Track B — #541（独立、`src/lorairo/main.py`）
1. `parse_arguments()` の `epilog`（または description）に `lorairo-cli --help` への誘導行を追加（GUI option は不変、CLI コマンドツリーは複製しない）。
2. テスト: `lorairo --help` 出力（argparse help text）に `lorairo-cli` が含まれることを assert。

**Track B ファイル所有**: `src/lorairo/main.py`、`tests/unit/...`（launcher help テスト）。

> 競合回避: Track A と Track B は**別ファイル**（`cli/main.py` vs `main.py`）。worktree 分離 + 別テストファイルで衝突ゼロ。

---

## 5. テスト戦略

| Issue | テスト |
|---|---|
| #540 | subprocess smoke: `--help`/`version` 後に `image_annotator_lib` 未ロードを検証。`models list` は registry 初期化されること |
| #539 | `--log-level` 反映（mock `initialize_logging`）、既定 INFO、`WARNING` で INFO 抑制 |
| #541 | `lorairo --help` 出力に `lorairo-cli` 誘導行 |
| 回帰 | 既存 `tests/unit/cli/` 全 pass、CI-equivalent filter |

CI-equivalent (LoRAIro Unit): `-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`。

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| #540 の重い import 源特定漏れ | `-X importtime` で実測 pinpoint、skill `lazy-import-refactor` で test 副作用予測 |
| lazy 化で `models list` 等が壊れる | registry 必須コマンドの回帰テスト必須 |
| #539/#540 の `cli/main.py` 衝突 | 同一オーナー（Track A）が #540→#539 順で直列実装 |
| callback 移行で既存コマンドのログ初期化漏れ | callback が全 subcommand で走ることを確認、既存 CLI テスト回帰 |
| 並列 `uv sync` venv 破損 (#222) | worktree で `PYTHONPATH=<wt>/src .venv/bin/pytest`（読み取りのみ）検証 |

---

## 7. チーム編成

| ロール | 担当 | worktree |
|---|---|---|
| Team Lead | 統合・CI-equiv・PR | — |
| Track A | #540 + #539 | `wt-535a` (`feat/issue-539-540-cli`) |
| Track B | #541 | `wt-535b` (`feat/issue-541-gui-help`) |

統合: A → B を別ファイルで結合（衝突なし想定）。完了でエピック #535 クローズ。

---

## 8. 次ステップ
1. 本計画承認後、worktree 2 つ作成。
2. Track A（skill `lazy-import-refactor` 使用）/ Track B を並列 dispatch。
3. 統合 → CI-equivalent 検証 → PR（`Closes #539 #540 #541` / `Refs #535`）。

## 参照
- ADR 0010 (Torch Import Design) / `.claude/rules/logging.md` / `.claude/rules/testing.md`
- skill `lazy-import-refactor`
- `src/lorairo/cli/main.py` / `src/lorairo/main.py` / `src/lorairo/services/service_container.py`
