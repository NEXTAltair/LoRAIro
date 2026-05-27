# Plan: Issue #466 — Provider Batch API 利用条件と運用ガイド改訂

- **日付**: 2026-05-27
- **対象 Issue**: [NEXTAltair/LoRAIro#466](https://github.com/NEXTAltair/LoRAIro/issues/466)
- **対象成果物**: `docs/provider-batch-api.md` の改訂と関連ドキュメント (`docs/cli.md` / `docs/integrations.md` / `docs/services.md` / `docs/decisions/0038-*.md`) の整合確認
- **ステータス**: Draft (実装着手前の計画)

## 1. 設計プロセス (ultrathink)

Issue #466 は ADR 0038 「Provider Batch API Integration Strategy」が定めた user-facing 文書の最後の穴を埋める「Docs-only」タスクである。一見すると既存 `docs/provider-batch-api.md` (217 行) を実装完了状態に書き直すだけだが、4 つの並列 investigation で以下の **実装と ADR / Issue scope の三者乖離** が判明した。

| 項目 | Issue #466 scope | ADR 0038 contract | 現在の `origin/main` 実装 |
|---|---|---|---|
| OpenAI direct route | Setup checklist あり | Phase 1 MVP | **lib adapter 未実装、CLI/GUI のみ受付 → submit すると `unsupported_provider`** |
| Anthropic direct route | Setup checklist あり | Phase 2 | **完全実装、唯一の現用ルート** |
| Google Vertex AI | 対象外、その理由を明記 | Phase 3 | submit reject (CLI/GUI でも除外) |
| OpenRouter | 対象外、その理由を明記 | non-goal | submit reject (CLI/GUI でも除外) |
| `description` / `prompt_profile` 永続化 | (acceptance criteria に明記なし) | draft schema あり | **`BatchSubmitRequest` 引数のみ、DB に保存されない** |
| `raw_provider_payload` 保存 | (記載なし) | 「保存しない」と明記 | **Text カラムで保存する** |

ドキュメントは "設計の理想" でも "実装そのままのスナップショット" でもなく、**user が現時点で安全に使える境界線** を示す必要がある。よって以下の方針で書く。

- 「現時点で実用できるのは Anthropic direct route のみ」を冒頭に明示し、OpenAI は ADR 0038 Phase 1 MVP として「scope に含むが lib 側 adapter 未実装」と注記
- ADR と実装の差分は本ガイドの一節で列挙、ADR 0038 本体には触らない (ADR は historical decision、補正は別 ADR 起票か本ガイド側 caveat にする)
- CLI / GUI の運用手順は `origin/main` (PR #498/#499/#495) 基準で確定値を書く
- privacy 警告として `raw_provider_payload` カラムに provider 生 JSON が保存される事実を明記

## 2. 要件と制約

### Issue #466 受入条件 (原文ベース)

1. ユーザーが provider batch を使うべきケースと避けるべきケースを判断できる
2. OpenAI / Anthropic の setup checklist がある
3. Google Vertex AI / OpenRouter が Provider Batch API 対象外であることが明記されている
4. CLI / GUI の運用手順がある
5. cancel / failed / expired / retry の扱いが image-annotator-lib の Provider Batch API contract 前提で説明されている

### LoRAIro 側制約

- CLAUDE.md: NEVER 新規ドキュメント作成 (既存 `docs/provider-batch-api.md` を編集)
- `.claude/rules/coding-style.md`: 日本語コメント可、半角文字、108 文字行幅
- `.claude/rules/planning-memory.md`: ADR / lessons-learned 確認済み
- ローカル `main` が `origin/main` より 4 コミット遅れている (#495 #498 #499 #500) → 作業前に `git fetch origin && git merge origin/main` 必須

### 非ゴール

- ADR 0038 本体の修正 (本タスクでは追わない)
- ADR / 実装差分を解消するコード変更 (別 Issue 起票候補)
- 新規 ADR 起票
- 英語版 docs 作成
- screenshot / diagram の新規生成 (PNG / SVG は追加しない)

## 3. 現状とギャップ

### 現状の `docs/provider-batch-api.md` (217 行)

- 「2026-05-25 時点の `main` では... user が使う CLI / GUI の job 管理画面と provider adapter wiring はまだ実装途中」を **複数箇所で前提にしている** (4-7, 9-13, 112-117, 145-150)
- CLI / GUI 章は「実装後の想定」として書かれており、実 command 名 (`lorairo-cli batch submit` 等) や widget 名 (`ProviderBatchJobWidget`) が一切ない
- ADR と実装の差分 (description 永続化、raw_provider_payload 保存) は未記述
- privacy 警告は最後に短く 5 行のみ、`raw_provider_payload` への言及なし
- legacy `annotate import-batch` との切り分けは §「Legacy/manual OpenAI JSONL import との違い」(204-217) で既に書かれている — 改訂時は維持

### ギャップ (追記すべき項目)

| 項目 | 追記必要性 | 出典 |
|---|---|---|
| 「現時点で実用できるのは Anthropic direct route のみ」明示 | 必須 | lib-recon §1, §5 |
| CLI 実 command と引数 (`batch submit/list/status/cancel/fetch/import`) | 必須 | cli-recon §3, §4 |
| GUI 実 widget 名と画面遷移 (Provider Batch tab、index 2) | 必須 | gui-recon §1, §2 |
| `_DIRECT_PROVIDERS = {"openai", "anthropic"}` 制約 (CLI/GUI 両方) | 必須 | cli-recon §10, gui-recon §1 |
| `raw_provider_payload` カラムへの provider 生 JSON 保存 (privacy 警告) | 必須 | db-recon §5 |
| artifact 保存先 (`[directories].batch_results_dir`、default `batch_results/`、cwd 基準) | 必須 | db-recon §4 |
| 二重 import 防止 (`imported_at` チェック) | 必須 | db-recon §3 |
| Status transition graph (10 status、terminal status の定義) | 必須 | db-recon §3 |
| GUI が現在 GUI thread 同期実行 (submit/fetch 中フリーズ可能) | 注記 | gui-recon §3, §5 |
| GUI list view に `submitted_at / completed_at / imported_at` 欠落 (Detail 側にあり) | 注記 | gui-recon §1 |
| ADR と実装の差分 (`description` / `prompt_profile` 未保存、`raw_provider_payload` 保存) | 注記 | db-recon §6 |
| `fetch_batch_results` の `destination_dir` 引数が Anthropic で無視される | 注記 | lib-recon §5 |
| `list_batch_capable_models()` も Anthropic のみ返す現状 | 注記 | lib-recon §5 |
| Retry は別 job を新規 submit (legacy retry_count 削除済み) | 必須 | db-recon §5 |

## 4. 複数アプローチ比較

### Option A: 最小追記

`docs/provider-batch-api.md` の「まだ実装途中」表現を消し、CLI/GUI 章に command 名 / widget 名を埋める最小修正。

- 利点: 編集量最小、レビューしやすい
- 欠点: 「OpenAI は CLI/GUI で受け付けるが lib 未実装」の主要事実を transparent に書けない。受入条件 5 の「retry の扱いが image-annotator-lib の Provider Batch API contract 前提で説明されている」を満たすには不十分

### Option B: Anthropic-only 全面書き直し

OpenAI を「将来対応」扱いに引き下げ、Anthropic 専用ガイドとして全面書き直し。

- 利点: 現実と完全一致、user の誤投入を最小化
- 欠点: Issue #466 の受入条件 2 (「OpenAI / Anthropic の setup checklist がある」) と矛盾。ADR 0038 Phase 1 MVP の位置付けを軽視

### Option C: スコープ両対応 + 実装ステータスを明示 ← 推奨

Issue #466 受入条件通り OpenAI / Anthropic 両方の setup checklist を書きつつ、冒頭に「実装ステータス」セクションを設けて Anthropic only 現状を明示。OpenAI は ADR 0038 Phase 1 MVP として「lib adapter 完了後に有効化される」と注記。

- 利点: 受入条件 1-5 を全て満たし、user に「現時点で何が動くか」も「設計上の射程」も両方伝わる
- 欠点: 章構成がやや増える、メンテナンスで Anthropic と OpenAI 差分管理が必要

**選択理由**: Issue #466 はドキュメント作成 issue であり、実装契約は ADR 0038 が SSoT。docs は「ADR が示すゴール状態」と「現時点の実用範囲」の両方を提示するのが本筋。Option C なら OpenAI adapter 実装完了時に「実装ステータス」セクションを 1 行修正するだけで evergreen 化できる。

## 5. ドキュメント章構成 (推奨案)

`docs/provider-batch-api.md` を以下の構成で書き直す。**( ) 内の数字は概算行数、合計約 400 行**。

```
# Provider Batch API 利用条件と運用ガイド

1. 概要 (20)
   - 何のためのガイドか
   - 対象は OpenAI / Anthropic direct route のみ
   - ADR 0038 への link

2. 実装ステータス (NEW、25)
   - Anthropic direct route: 完全実装 (lib + Service + CLI + GUI)
   - OpenAI direct route: lib adapter 未実装 (CLI/GUI は受け付けるが lib dispatch で reject)
   - Google Vertex AI: ADR 0038 Phase 3、CLI/GUI で reject 実装あり
   - OpenRouter: ADR 0038 non-goal、CLI/GUI で reject 実装あり
   - 関連 PR / Issue (#463 #483 #495 #498 #499 NEXTAltair/image-annotator-lib#102 #103)

3. 使うべきケース / 避けるべきケース (30)
   - 既存 §「使うべきケース」を維持しつつ、Anthropic only 現状で書き直す
   - 「OpenAI direct API key を持っている」→「Anthropic direct API key を持っている」に補正
   - 「OpenAI MVP 実装後に使える」も追記

4. 対象 provider (60)
   - Anthropic direct route
     - Setup checklist (5 項目、既存維持 + API key 環境変数 `ANTHROPIC_API_KEY` or config/lorairo.toml 明示)
     - Message Batches 制約 (50% pricing, 24h expiration, 29 day result availability, ZDR 対象外, 100k requests, 256 MB)
     - 同期 vs batch の選択基準 (request 数, 遅延許容度)
   - OpenAI direct route
     - Setup checklist (将来形で記載 + 「lib adapter 完了まで `lorairo-cli batch submit --provider openai` は失敗する」明記)
     - Batch API 制約 (50% discount, 24h completion, 50k requests, 200 MB, streaming 非対応)
   - 対象外 provider
     - Google Vertex AI: GCS/BQ/region/IAM 設定が必要、ADR 0038 Phase 3
     - OpenRouter: provider-native job lifecycle なし、ADR 0038 non-goal

5. LoRAIro と image-annotator-lib の責務境界 (35)
   - 表形式で 9 項目 (custom_id 生成、DB 永続化、payload 構築、HTTP retry、parse、UI lifecycle 等)
   - 出典: lib-recon §4

6. CLI 運用 (90)
   - 前提: `lorairo-cli` group 構成 (top-level `batch`)
   - submit / list / status / cancel / fetch / import の 6 subcommand
   - 各 subcommand に「構文 / 引数 / オプション / 例 / 出力例」セクション (docs/cli.md パターン準拠)
   - Anthropic submit の完全例
   - OpenAI submit の「将来形例」 + 現在の失敗メッセージ
   - Google / OpenRouter / discontinued / ambiguous model 指定時のエラー
   - exit code (1: ビジネスエラー、2: 想定外例外)

7. GUI 運用 (70)
   - main_window の「Provider Batch」tab (index 2) を開く
   - Submit groupBox の入力フィールド (Model / Image IDs / Prompt / Description)
   - Jobs テーブル (5 列: ID/Provider/Status/Provider Status/Requests)
   - Detail/Items 領域の 17 フィールド表示と item filter (all/failed/expired/canceled)
   - 操作ボタン (Refresh / Refresh Status / Cancel / Fetch / Import) の挙動
   - 「Use Selected」でワークスペースタブ選択画像の流し込み
   - 注記: 現在 GUI thread 同期実行、submit/fetch 中ブロック
   - 注記: Jobs テーブルには `submitted_at / completed_at / imported_at` を表示しない、Detail 領域で確認
   - 注記: Google は GUI から silent excluded、「not configured」表示は出ない

8. Status mapping と retry (40)
   - 10 status の意味表 (既存 §「Status と retry」維持しつつ、`provider_status` カラムが生 status を保持する旨を追記)
   - Transition graph (succinct な箇条書き or matrix)
   - retry は「別 job を新規 submit」(自動 retry なし、legacy `error_records.retry_count` 削除済み)
   - 二重 import 防止 (`imported_at` 検査) の挙動

9. Artifact と保存先 (NEW、25)
   - 保存先設定 (`[directories].batch_results_dir` config キー、default `batch_results/`、cwd 基準で解決)
   - artifact_type ∈ {input, output, error}
   - sha256 / provider_file_id の用途
   - LoRAIro 側自動削除なし — operator が手動 purge

10. Privacy / retention (30)
    - 既存 §「Privacy / retention」を拡張
    - **重要追加**: `provider_batch_jobs.raw_provider_payload` カラムに provider 生 JSON が saved される事実
    - Anthropic ZDR 対象外、29 日結果保持
    - OpenAI 結果 retention (実装後)
    - secret / 公開不可画像を batch に投入しない

11. Legacy/manual OpenAI JSONL import との違い (15)
    - 既存 §「Legacy/manual OpenAI JSONL import との違い」維持
    - `lorairo-cli annotate import-batch` は手動ダウンロード済み JSONL の import 専用、`provider_batch_*` テーブルに書かない
    - 新規運用は `lorairo-cli batch ...` (top-level group)

12. ADR と実装の差分 (NEW、20)
    - `provider_batch_jobs.description` / `prompt_profile`: dataclass 引数のみ、DB 未保存
    - `raw_provider_payload`: ADR は「保存しない」、実装は保存する
    - `provider_batch_items.task_type` / `raw_request` / `raw_response`: ADR draft にないカラムあり
    - `BatchFetchResult.artifacts`: lib 型に存在しない (LoRAIro `ProviderBatchFetchResult` のみ)
    - `fetch_batch_results(destination_dir)`: Anthropic では引数無視される
    - `list_batch_capable_models()`: 現在 Anthropic のみ返す
    - 注記: これらは将来 ADR amendment / 別 Issue で解消する候補

13. 関連 docs / ADR / Issue (10)
    - ADR 0038, ADR 0023, ADR 0033, ADR 0037
    - docs/cli.md, docs/integrations.md, docs/services.md
    - 関連 PR / Issue 一覧
```

## 6. 周辺ドキュメント更新

### `docs/cli.md` (現状 696 行)

- L551-559「Provider Batch API job 管理」セクション
  - 「2026-05-25 時点の `main` では user-facing CLI はまだ実装途中で...」を削除
  - top-level `batch` group の 6 subcommand 一覧へのリンクを `docs/provider-batch-api.md` § CLI 運用 に張る
  - 例として `lorairo-cli batch list --project myproject` 1 行のみ残す

### `docs/integrations.md` (現状 505 行)

- L335-347「Provider Batch API」セクション
  - 「`ProviderBatchAdapter` protocol と `ProviderBatchJobService` が存在しますが、OpenAI / Anthropic adapter wiring と user-facing CLI / GUI はまだ実装途中です」を削除
  - 「現在は Anthropic adapter 完全実装、OpenAI adapter 未実装、Google Phase 3」に書き直し
  - 詳細は `provider-batch-api.md` に委譲

### `docs/services.md` (現状 §ProviderBatchJobService / WorkflowService)

- 軽微: User Guide リンクは維持。`Operations` 一覧に `import_results` を追加 (現状欠落)

### `docs/decisions/0038-provider-batch-api-integration-strategy.md`

- **本タスクでは触らない**。ADR は historical decision として保持
- 実装差分は本ガイド § 12 と将来の ADR amendment で扱う (別 Issue 起票候補)

## 7. 実装計画 (タスク分解)

```
TASK-A: ローカル main を origin/main に同期
  → git fetch origin && git merge origin/main
  → ローカルに provider_batch CLI / GUI 実装を取得

TASK-B: docs/provider-batch-api.md を Option C 構成で全面書き直し
  → 既存 217 行を保持しつつ、§2 §9 §12 を新設
  → CLI 章 (§6) は docs/cli.md 形式 (構文/引数/オプション/例/出力例) で 6 subcommand 分書く
  → GUI 章 (§7) は画面遷移ベースで 9 ステップ書く

TASK-C: docs/cli.md L551-559 を更新
  → 「実装途中」表現を削除、top-level batch group を概要のみ示し詳細リンク

TASK-D: docs/integrations.md L335-347 を更新
  → Anthropic adapter 完全実装の現状を反映、詳細リンク

TASK-E: docs/services.md の ProviderBatchWorkflowService entry に
        `import_results` operation を追記

TASK-F: lint / preview 確認
  → markdown lint (用意があれば)
  → ローカルで MkDocs preview (もし MkDocs 構成があれば、なければ skip)
  → cross-link が壊れていないか確認

TASK-G: PR 起票
  → branch: docs/issue-466-provider-batch
  → Refs #466 / Closes #466
  → submodule 変更を含まないので CI-equivalent test 不要 (docs-only)
```

### タイムライン目安

| Task | 想定時間 |
|---|---|
| TASK-A | 5 分 |
| TASK-B | 90-120 分 (本タスクの主要部) |
| TASK-C | 10 分 |
| TASK-D | 10 分 |
| TASK-E | 5 分 |
| TASK-F | 15 分 |
| TASK-G | 10 分 |
| **合計** | **約 2.5-3 時間** |

### 実装順序

TASK-A → TASK-B → (TASK-C と TASK-D と TASK-E を並列) → TASK-F → TASK-G

## 8. 検証戦略

ドキュメントタスクなので pytest による検証はないが、以下を実施する。

### Markdown / リンク検証

- すべての ADR / Issue / Service / file:line リンクが解決することを目視確認
- `docs/cli.md` の Provider Batch API job 管理セクションから新規 `docs/provider-batch-api.md` への遷移が機能
- `docs/integrations.md` `docs/services.md` からの逆リンクが機能

### CLI / GUI 表記の事実検証

- `git show origin/main:src/lorairo/cli/commands/batch.py` を sed で開き、各 subcommand の引数名・default 値が docs と一致するか
- GUI 章記載の widget objectName が `provider_batch_job_widget.py` と一致するか
- 表示カラム名 / ボタンラベルが実装と一致するか

### 用語整合

- 「バッチ API」「Batch API」「Provider Batch API」「Provider Batch」「provider batch」の表記揺れを docs 全体で統一
  - 推奨統一: 「Provider Batch API」(API surface を指す場合) と「Provider Batch job」(job lifecycle を指す場合)
- ADR 0038 と本ガイドで status 名 (canceling vs cancelling 等) が一致

### Issue #466 受入条件チェックリスト

完了時に Issue #466 にコメントで以下を確認:

- [ ] 受入条件 1: 使うべき / 避けるべきケースの判断軸が明示されている (§3)
- [ ] 受入条件 2: OpenAI / Anthropic setup checklist が存在する (§4)
- [ ] 受入条件 3: Google Vertex AI / OpenRouter が対象外であること明記 (§2, §4)
- [ ] 受入条件 4: CLI / GUI 運用手順が記載されている (§6, §7)
- [ ] 受入条件 5: cancel / failed / expired / retry が lib contract 前提で説明されている (§8)

## 9. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| OpenAI lib adapter 完了時に docs を更新し忘れる | user 混乱 (実装ステータス章と乖離) | §12「ADR と実装の差分」と §2「実装ステータス」を同じ PR で更新する運用ルールを §13 末尾に記載 |
| 既存 217 行の有用な記述 (legacy import 切り分け等) を消す | regression | TASK-B は既存セクションを diff-friendly に保ち、新規追加部分を独立セクションにする |
| Anthropic / OpenAI / Google の用語混在で user 混乱 | minor | 用語整合チェックを TASK-F に組み込む |
| `raw_provider_payload` への生 JSON 保存を user が知らないまま運用 | privacy 事故 | §10 で太字 / 警告 callout で明示 |
| ローカル main が古いまま編集して、PR #498/#499 の CLI/GUI 表記が想像で書かれる | 事実誤り | TASK-A を必ず最初に実行 (precondition) |
| ADR 0038 本体に手を入れたくなる誘惑 | scope 拡大 | 本計画 §「非ゴール」を厳守、差分は §12 のみで扱う |
| ローカル `image-annotator-lib` submodule が dirty (`M`) で実装と乖離 | 事実誤り | git status を確認、必要なら submodule の HEAD を `origin/main` 期待値にリセット |

## 10. 次ステップ (implement 引き継ぎ)

`/implement` で本計画を実行する際の優先順序:

1. **TASK-A** で `git pull` 実行、`src/lorairo/gui/widgets/provider_batch_job_widget.py` と `src/lorairo/cli/commands/batch.py` が手元にあることを確認
2. **TASK-B (主要部)** を以下の章順で書く:
   - §1 概要 → §2 実装ステータス → §3 使うべき/避けるべき → §4 対象 provider → §5 責務境界 → §6 CLI → §7 GUI → §8 Status → §9 Artifact → §10 Privacy → §11 Legacy import → §12 ADR 差分 → §13 関連
   - CLI 例は `cli-recon` レポートの §4 例をそのまま転記可
   - GUI 例は `gui-recon` レポートの §「ドキュメントに記載すべき画面遷移」9 ステップをそのまま転記可
3. **TASK-C/D/E** は並列実行可、各 10 分以内
4. **TASK-F** で表記揺れと cross-link を最終チェック
5. **TASK-G** で PR 起票 (`docs/issue-466-provider-batch` branch、`Closes #466`)

### 参考実装報告 (本計画策定時の investigation 出典)

- `cli-recon`: PR #499 で `src/lorairo/cli/commands/batch.py` (333 行) 追加、top-level `batch` group、6 subcommand、Rich Table 出力
- `gui-recon`: PR #498 で `ProviderBatchJobWidget` (500 行) 追加、main_window tab index 2「Provider Batch」、3 つの groupBox 構成
- `lib-recon`: `image-annotator-lib` HEAD `e36aef5`、Anthropic adapter のみ実装、OpenAI/Google 未実装、`list_batch_capable_models()` も Anthropic のみ
- `db-recon`: migration `c6d7e8f9a0b1` で 3 テーブル追加、ADR と実装差分 5 件、artifact 保存先は `[directories].batch_results_dir` (default `batch_results/`)

## 関連

- ADR 0038: docs/decisions/0038-provider-batch-api-integration-strategy.md
- 親 Issue: NEXTAltair/LoRAIro#466
- 依存 PR (origin/main 既マージ): #495 #498 #499
- 関連 lib PR (image-annotator-lib): #102 #103 #116 #117
- 参考過去計画: docs/plans/plan_418_remaining_tasks_agentteams.md
