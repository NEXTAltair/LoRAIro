# 設計判断（ADR 0001–0079）の Wireframe への影響メモ

最終更新: 2026-06-27
対象: `LoRAIro Wireframe.html`（Search / Annotate / Jobs / Errors / Results / Export）

> **⚠ 2026-06-27 実装確認の追記（このメモの前提は実装前のもの）**
> 本メモ本文は「次の改訂時の論点リスト」として**実装前**に書かれており、「未実装の疑い」を含む。
> その後、実コード (`NEXTAltair/LoRAIro@main` commit `b8f59ff`) を直接確認したところ、
> v12 背骨の4ギャップは**すべて実装済み**だった（誤って「未実装」と読まないこと）:
> - **Jobs = 監視専用台帳**: `ProviderBatchJobWidget` は GroupBox 名「バッチジョブ状態 (監視専用)」＋
>   `labelMonitorOnlyHint`「作成は Annotate タブから」。モデルピッカー / Submit / `comboBoxTaskType` は**実体に無い**（ADR 0076 / PR #884・#896）。
> - **async batch = 選択モデル集合の dispatch 射影**: `services/dispatch_projection_service.py` の
>   `project_async_batch_dispatch()` が discovery ∩ 選択集合 → 非対応混在は `DispatchProjectionError` 拒否 →
>   batch-capable 1モデル = 1 `DispatchEntry`（ADR 0076 §2）。
> - **INFERENCE LEDGER**: `gui/widgets/inference_ledger_widget.py` が SYNC / PROVIDER BATCH 2バンド。
>   ラベルは「推論回数合計」へ是正済み（ADR 0075 follow-up 反映済み）。
> - **rating preflight = 自動ゲート**: 同期は `AnnotationWorker(rating_gate=True)`、async は preflight 未完了で
>   fail-closed（ADR 0070 / 0077）。Jobs UI から task_type combo は撤去済み。
>
> **GUI 挙動は ADR ではなく Issue で駆動されていた**点に注意（#803 / #754 / #805）。その後 ADR 化された:
> - **ADR 0077** RunOptions 実行契約（dry-run 短絡・rating ゲート / refusal filter 分離。#803・PR #915/#916） — 本メモが「残課題」とした #803 は決定＋実装済み。
> - **ADR 0078** Model installer の明示ジョブ化（#754・ADR 0066 §5）。
> - **ADR 0079** Jobs ステージ別 progress + サマリ帯（#805）。サマリ帯の正準 = running / queued / completed_7d / **api_usage=「—」（データソース無し・捏造禁止）**。
>
> → 下の §6「足す価値が高い」は **1〜3・5 が実装完了済み**、残るのは登録/インポート画面（#9・ADR 0061・現状ワイヤー外）程度。本文は履歴として残置。

> **2026-06-05 追記:** 旧 §6 の優先項目はすべて **`Wireframes v11` に反映済み**。
> v11 = 統一品質ティア / per-scorer score_labels / canonical rating 正規化 / rating preflight ゲート /
> 環境ファースト・モデルピッカー / 非同期 Provider Batch / ステージング集合 Export / worker lifecycle 語彙 +
> 新フレーム 07 Export。

> **2026-06-27 全面改訂（ADR 0056–0076 を反映）:** v11 以降に、ワイヤーフレームの**背骨を組み替える**
> 決定が4本入った。以下はすべて「Accepted のまま責務/所在を更新」する性質の改訂で、相互に依存する:
> 1. **ADR 0066 Unified Jobs Lifecycle View** — Jobs を「実行中 / キュー / 履歴」の統一ライフサイクル台帳に。
> 2. **ADR 0074 StagingStateManager hoist** — ステージング集合の SSoT を `StagingWidget` から中立の
>    `StagingStateManager` へ。`DatasetStateManager` ではなくこれが対象集合の正本。
> 3. **ADR 0075 アノテーションパイプライン構成ドメインモデル** — **ADR 0030（環境ファースト二段フィルタ）を
>    Superseded**。per-stage ピッカー + 「SSoT = 選択モデル集合 / ステージ表示は派生ビュー」へ。
> 4. **ADR 0076 Submit を Annotate の dispatch 射影へ** — **Jobs から作成入口（モデルピッカー・Submit
>    フォーム）を撤去**し、Jobs は純粋な監視台帳に確定。submit は Annotate の dispatch 射影として再 home 化。
>
> この4本で、v12 の背骨は「**構成は Annotate・監視は Jobs・対象集合は StagingStateManager**」の一文に収束する。

リポジトリ `docs/decisions/` を読み込んで把握した内容。各項目に「現状」「ADR の決定」「対応方針」を併記。

---

## 0. 全体に効く背骨（v12）

- **ステージング集合（Staging set）が全フローの中心 SSoT**（ADR 0055 / 0074 / 0043 / 0041）。
  - 「選択中」という不可視概念ではなく、**有界（MAX 500枚）・可視・名前付きの集合**＝ステージングが、
    Annotate / Batch API / Export すべての対象解決の単一ソース。
  - **SSoT の所在は `StagingStateManager`（ADR 0074）**。旧来 `StagingWidget` が OrderedDict を所有し
    `connect_shared_staging` で双方向 sync する hack だったが、中立な `gui/state/StagingStateManager`
    （QObject + `staged_images_changed` Signal）へ hoist。`StagingWidget` は view へ降格。
    **対象集合の正本は `DatasetStateManager` ではなく `StagingStateManager`**（後者がメタ解決のため前者を注入）。
  - Export 対象も「フィルタ結果の直エクスポート」ではなく **ステージング集合のみ**。フィルタ結果は
    「ステージングへ投入」という明示操作を経て初めて対象化（21k 件誤エクスポート事故の構造的防止＝ADR 0019）。
  - Search の「📥 Stage」がこの概念。**この棒を Annotate だけでなく Export の入口にもつなぐ**のが正。

- **Jobs = 純粋な監視台帳 / 構成は Annotate に一本化**（ADR 0066 / 0076）。
  - Jobs は「実行中 / キュー / 履歴」の3状態で**同期ジョブ + 非同期 Provider Batch を1ビューに統合**（0066）。
  - **Jobs から作成入口（モデルピッカー・Submit フォーム・staging 投入コントロール）を撤去**（0076）。
    Jobs に残る操作は lifecycle / 事故復旧のみ（`状態を確認` / `キャンセル` / 二次的な `fetch` / `import`）。
  - submit は **Annotate の dispatch 射影**へ移る。同期/非同期は authoring の違いではなく dispatch（実行経路）
    の違いなので、入口は Annotate 1つでよい。

- **Web API バッチ（非同期 Provider Batch）= 選択モデル集合の dispatch 射影**（ADR 0038 / 0041 / 0076）。
  - 「submit → 後で状態確認 → 完了なら自動 fetch+import」という非同期ライフサイクル。
  - 「1 submit = 1 model」は**手動単一選択の制約ではなく、射影の出力不変条件**（0076）。選択モデル集合を
    route 分割し、batch-capable な1モデル＝`provider_batch_jobs` 1行を生成する。

---

## 1. Annotate / モデルピッカー（Frame 2A / 2B）★全面更新（ADR 0030 → 0075 で Superseded）

### 1-1. モデル選択は「選択モデル集合」を SSoT とする per-stage ドメインモデル（ADR 0075）★影響大
- **旧（ADR 0030 / v11）**: 「① 実行環境（API/local）→ ② タスク → ③ モデル一覧」の二段フィルタ。
  環境は未選択状態を持たず常に `api | local`。
- **新（ADR 0075、0030 を Superseded）**:
  - UI は per-stage ピッカー（`StageModelPickerDialog` + `PipelineStageTableWidget`）へ全面移行。
  - **SSoT は「選択されたモデルの集合」**。ステージへの割り当ては SSoT ではなく、選択集合から**毎回作り直す
    派生ビュー**。「どのモデルをどのステージに置いたか」は出力にもコストにも影響しない。
  - アノテーション種類は `tags / caption / score / rating` の4つ。逐次工程ではなく**1推論が並列に埋めうる
    出力の種類**。各モデルがどれを出せるかは capability（`fill_stages()`）で決まる。
  - **実行環境セグメントは3値 `すべて(all) / APIのみ(api) / ローカルのみ(local)`、既定 `all`**
    （ADR 0030 の「環境未選択を持たない」を**上書き**）。環境は絞り込みの1軸に降格。
- **対応方針**: ピッカーを per-stage テーブル + 環境/種類/provider の絞り込み軸で再構成。左レールの
  「環境ファースト」前提は撤去。現在の選択モデル集合を主表示にする。

### 1-2. multimodal の固定スキーマと RATING の出どころ（ADR 0075）
- multimodal WebAPI モデルの1推論は **`{tags, captions, score}` を固定で返す**。**multimodal は rating を出さない**。
- `rating` は別経路から得る: ① rating 対応モデルの出力、② 送信前 moderation プリフライト（ADR 0070）。
- **派生チップ（`↝ DerivedChip`）は read-only**。multimodal を1ステージに主割当すると、同一推論が埋める
  他種類は派生チップで表示され、compose で外せない（**派生出力は既定で採用**。表示と実体の乖離を避ける）。
  - 事後除外は非対称: `tags/caption` は Results の soft-reject（ADR 0065）で per-row に外せるが、
    `score` は per-row reject 経路が現状なく、派生 score は残る。

### 1-3. 推論回数 = ユニークモデル数 × ステージング枚数（ADR 0075）
- 課金単位＝推論アイテム数は **ユニークモデル数 × ステージング枚数**。同一モデルを複数種類に充当しても
  `litellm_model_id` で dedupe され増えない（`InferenceLedger`）。
- **dispatch 前に全ジョブ・全推論回数をプレビュー**する（INFERENCE LEDGER）。暗黙の fan-out / 隠れコストを作らない。

### 1-4. Annotate が dispatch mode（同期 / async Batch API）を所有する（ADR 0076）★新フロー
- Annotate に**「送信方式 = 同期 / Batch API」の選択（run settings の dispatch mode）**を設けるのが、Jobs から
  Submit を撤去する前提。async dispatch は選択モデル集合の射影として `provider_batch_jobs` を生成。
- 射影契約に運ぶもの: `litellm_model_id` + DB `Model.id`、`prompt_profile` / `description`、
  **processed/resized 画像パス（ADR 0064）**、batch-capable 判定（`list_batch_capable_models()` ∩ helper）。
- **非 batch-capable な選択を黙って落とさない** — 部分射影を拒否するか、別経路へ回す/ledger 報告を必須に。
- async dispatch の submit ループは **worker thread + busy/再入ガード**（ADR 0044）を引き継ぐ。

### 1-5. Web API モデル名の表示（ADR 0030 #343 / 0048）
- `openrouter/...` などの経路込み ID を前面に出さない。表示は canonical 名、`litellm_model_id` は実行用に保持、
  raw route / provider は tooltip。OpenRouter 経由は route ID から導出した canonical identity を使う。

### 1-6. WebAPI 候補は3軸でフィルタ（ADR 0048）
- annotation 候補の Web API モデルは「① endpoint 実行可能（`mode=chat`）」「② tool/function calling 実在」
  「③ 用途適性 denylist（TTS / computer-use / deep-research 等を除外）」を満たすもの。

### 1-7. 初回表示で自動 reconcile（ADR 0052）/ ローカル ML config 所有権（ADR 0040）
- ピッカー初回生成時、提供終了 Web API モデルを落とす非同期 sync を1回自動実行（起動直後の短い更新スピナー）。
- ローカルモデルの config 所有は ADR 0040 に整理。ピッカーのローカル側メタ表示の根拠。

### 1-8. 原画像はアノテーション対象外（ADR 0064）
- GUI は元々 `image_dataset/original_images/` の原画像を直接アノテーションさせない。CLI 側もこのガードを追加
  （processed/resized 画像レコードのみ対象）。**射影は staged の processed パスを運ぶ**（巨大 original の誤送信防止）。

---

## 2. Results（Frame 5）— 品質トリアージ

### 2-1. 統一品質ティアが raw スコアの上位概念（ADR 0029）★影響大
- 検索・表示・Export の語彙は **統一品質ティア**:
  `masterpiece / best quality / good quality / normal quality / low quality / worst quality / no score / unknown`。
  - raw scores / score_labels は**不変**。ティアはその上の derived view（mapping 版管理 `quality-tier-v1`）。
  - 複数 scorer の vote を **中央値 + is_unanimous** で集約。`no score`（未採点）と `unknown`（mapping 未定義）は**分離**。
- **対応方針**: Results の score 列を「品質ティア badge」中心に。`no score` / `unknown` の状態も描く。

### 2-2. score_labels は per-scorer pill で並列表示（ADR 0028）
- scorer ごとに `[model] label` の pill を並べ、判定不一致（UC-C）を一目で。多数決フィルタ（`min_consensus_count`）が
  Export/Search 側の絞り込み軸。

### 2-3. AI レーティングは canonical へ正規化（ADR 0031）★影響大
- model-native rating → canonical `PG / PG-13 / R / X / XXX` に LoRAIro 側で mapping。`r15 → R`、
  通常 mapper は `XXX` を自動生成しない。**1 モデル = 1 rating 行**（最高 confidence）。mapping 不能は**保存せず skip + warning**。

### 2-4. OpenAI Moderations による rating preflight（ADR 0070、旧 0042-openai-moderation）★更新
- annotation API に送る**前**に OpenAI Moderations Batch で rating を判定し、**`X / XXX` は送らない**
  （`PG/PG-13/R` は送る。`violence/graphic` は R 止まり）。`task_type = "rating_preflight"`、`omni-moderation-latest`。
- **これはユーザー操作ではなく自動の安全ゲート**（ADR 0076 / 0075）。射影は**画像の rating / 送信可否から
  preflight 要否を決める**（RATING ステージ選択の有無では決めない）。Jobs の task-type combo からは**撤去**。
  - 注: omni-moderation は Moderation API 経由で**無料**のため、未評価画像への送信ゲート自動挿入はコスト中立。

### 2-5. Tag/Caption の soft-reject と Export 解決（ADR 0065）★新概念
- `tags` / `captions` に nullable `rejected_at`。`NULL`=採用 / 非`NULL`=soft-reject（採用読みと export から除外）。
  - 物理削除しない。再アノテーションで復活しない（同一 image/model/content の upsert は reject を revive しない）。
  - **Export は採用タグを string union + 重複除去で解決。手動編集タグが衝突時に勝つ**。caption は1行に解決
    （手動編集優先、なければ最新の採用行）。
- **対応方針**: Results トリアージに「このタグ/captionを reject」操作を追加。`rejected_at IS NULL` を既定フィルタに。

### 2-6. タグ正規化は保存時に danbooru canonical を焼き込む（ADR 0068）
- 表示の未整形タグ（`_touhou`, `Grey hair`, `bad_id` 等）の原因はタグ canonical 化の境界欠如だった。
- **非手動タグは保存時に danbooru の preferred を `search_tags_bulk(resolve_preferred=True)` で焼き込む**
  （1画像=1 bulk lookup）。**手動編集タグ（`is_edited_manually=True`）は canonical 化せずユーザー表記を保持**。
  - **GUI 詳細表示は verbatim**（表示時変換は実 DB で遅すぎたため撤回）。管理メタタグ（`type=meta`）は export 時のみ除外。
- **対応方針**: Results のタグ表示は「保存済み canonical（手動編集は整形済み）」。手動編集タグは別表記として描き分け可。

---

## 3. Jobs / Errors（Frame 3 / 4）★全面更新（ADR 0066 / 0076）

### 3-1. 統一 Jobs ライフサイクルビュー（ADR 0066）★影響大
- **3状態**「実行中 / キュー / 履歴」で**同期ジョブ + Provider Batch を1ビューに統合**。空状態でも履歴テーブル枠は残す
  （Jobs の半分は台帳）。
- **永続性の非対称**: 同期ジョブ履歴は **in-memory（セッションスコープ、再起動で消える）**、Provider Batch は
  既存 `provider_batch_jobs` テーブルで**永続**（非同期で再起動を跨ぐ必然があるため）。
- **ジョブ粒度 = Pipeline / Operation レベル**（ADR 0034）。検索/サムネ等の UI 応答 Worker は**載せない**（firehose 化防止）。
- **キューは実セマンティクスを持つ**: **ローカル GPU 推論ジョブは同時1件（直列キュー、VRAM 競合を構造的に防ぐ）**、
  API 系は並列許容。
- **進捗ポップアップは Phase 7 で廃止**。実行開始時に Jobs へ自動遷移しない（statusbar 通知 + 完了時 Results 自動着地）。

### 3-2. Jobs は作成入口を持たない監視台帳（ADR 0076）★影響大
- **Jobs から撤去**: モデルピッカー（単一選択）・Submit フォーム・submit 専用の staging/対象選択コントロール・
  rating_preflight の task-type combo 露出。
- **Jobs に残す**: 主操作 `状態を確認` / `キャンセル`、二次的な復旧 `fetch` / `import`。
- レイアウトは「監視カードのみ」（v12 の `.pbatch` 帯は primary=`状態を確認`, 副=`キャンセル`、ピッカー/Submit 無し）。
- **対応方針**: Jobs を監視専用に描き、submit 導線は §1-4（Annotate dispatch mode）へ移設。

### 3-3. Worker / Operation / Pipeline の3層ライフサイクル（ADR 0034）
- 「現在の操作の失敗」「置換された古い worker の失敗」「明示キャンセル後の timeout」を区別する3層境界。
  Errors / Jobs の状態語彙（CANCELED / TERMINATED / UNRESPONSIVE / superseded）の根拠。

### 3-4. SQLite 並行性とロックエラー分類（ADR 0067）★新
- `busy_timeout` 設定 + ロックエラーの分類。Jobs/Errors の並列実行時（API 並列・GPU 直列）の失敗表示と
  「リトライ可否」分類に効く。一時的ロック（リトライ可）と恒久エラーを区別。

### 3-5. バッチ保存は atomic、I/O 分離（ADR 0012 / 0042 / 0033）
- バッチタグ保存は atomic transaction。DB save I/O は分離（ADR 0042 batch-annotation-db-save-io）。worker のバッチ実行契約（0033）。
  「部分失敗時の見せ方」の制約。

### 3-6. ログ運用（ADR 0045 / 0046 / 0047）
- 大量検索結果のログレベル、loguru placeholder、per-item 診断の trace レベル。Errors の「技術詳細」粒度設計に間接的に効く。

---

## 4. Search（Frame 1）

### 4-1. 品質ティア・フィルタ（ADR 0029）
- 検索フィルタは raw scorer 値ではなく **ティア**を主 interface に:
  `品質: good quality 以上 / 一致条件: 1件以上・過半数・全件 / 未採点: 除外・含める・未採点のみ`。

### 4-2. AI レーティング・フィルタ（ADR 0031 / 0015）
- canonical rating（PG/PG-13/R/X/XXX）で絞り込み。manual rating（MANUAL_EDIT）と AI rating は分離・優先。
  「AIレーティング未設定のみ」を抽出可（mapping 不能で未保存のものは対象に戻らない）。

### 4-3. ステージング投入が Search → Annotate / Export の唯一の橋（ADR 0055 / 0074）
- フィルタ結果 → サムネ確認 → **「ステージングへ投入」** → 対象化。**唯一の選択ソースは `StagingStateManager`**
  （ADR 0074。旧メモの `DatasetStateManager` 記述から更新）。

### 4-4. 大量 ID 集合ガード / count-first（ADR 0056 / 0060）★新
- exact-set selector の大量 ID 集合に対し count-only の軽量化と上限ガード（ADR 0056）。CLI は bounded pagination /
  count-first 契約（ADR 0060、1回500枚上限と整合）。Search の件数表示は重い全件取得を避け count を先に出す。

### 4-5. 登録パイプライン: pHash 候補の重複/別版分類（ADR 0061）★新概念（登録/インポート側）
- **pHash 完全一致は「重複確定」ではなく「候補」**。`width / height / has_alpha / is_grayscale_like` を比較し、
  **重複** か **別版**（カラー/グレー版・解像度違い・透過有無）かを分類。別版は新規 `images` 行を作る。
  - ハミング距離の近似重複検知は導入しない（完全一致のみ起点）。`phash` カラムは unique 化せず候補検索キー。
  - 保存は分類後（重複なら保存しない＝孤児ファイルを残さない）。副作用（`.txt`/`.caption` 取込・alias 登録・統計）は
    分類結果駆動で GUI/API/direct 全経路統一。
- **対応方針**: 登録/インポート画面（現状ワイヤー外）に「重複 vs 別版」の確認・分類結果表示を将来追加する論点。

---

## 5. Export（Frame 7）

### 5-1. フィルタ必須・全件禁止（ADR 0019）
- Export はフィルタ条件必須。GUI は「ステージング集合＝暗黙フィルタ」。全件エクスポートは存在しない。

### 5-2. 対象＝ステージング集合（ADR 0055 / 0074）★スタブを実画面化する根拠
- Export 入口はツールバー常設＋サムネグリッド下部バー。対象は常に staged 集合（SSoT=`StagingStateManager`）。
- `ImageFilterCriteria.image_ids` は **exact-set selector**（NSFW 除外等を bypass、明示ステージングした NSFW を黙って
  落とさない）。大量 ID は count-only ガード（ADR 0056）。changed-since フィルタはダイアログ内 post-filter。

### 5-3. Export 解決ルール（ADR 0065 / 0068）★新
- 採用タグ（`rejected_at IS NULL`）を **string union + 重複除去**、手動編集タグ優先。caption は1行に解決。
- target format 出し分けは export 時に danbooru→target 変換（基準 danbooru、ADR 0068）。管理メタタグ（`type=meta`）は export 時に除外。
- **対応方針**: Export スタブを「ステージング集合を学習フォーマットに書き出す」実画面に昇格。format 選択 + meta 除外を描く。

---

## 6. 「足す価値が高い」もの（優先度順・2026-06-27 更新）

1. **Jobs を監視専用台帳に確定 ＋ Submit を Annotate へ移設**（ADR 0066 / 0076）— v12 背骨。最優先。
2. **モデルピッカー: per-stage + 選択モデル集合 SSoT へ刷新（環境ファースト撤去）**（ADR 0075、0030 Superseded）。
3. **Annotate に dispatch mode（同期 / async Batch API）+ INFERENCE LEDGER プレビュー**（ADR 0076 / 0075）。
4. **Results: raw スコア → 統一品質ティア badge + soft-reject 操作**（ADR 0029 / 0028 / 0065）。
5. **rating preflight を「自動ゲート」として描く（ユーザー操作面から撤去）**（ADR 0070 / 0076）。
6. **対象集合 SSoT を StagingStateManager に統一表記**（ADR 0074）— メモ/ワイヤーの用語を揃える。
7. **Export スタブ → ステージング集合ベースの実画面（解決ルール込み）**（ADR 0055 / 0019 / 0065 / 0068）。
8. **Search: 品質ティア / canonical rating facet + count-first**（ADR 0029 / 0031 / 0056 / 0060）。
9. **登録/インポート画面に「重複 vs 別版」分類**（ADR 0061）— 現状ワイヤー外の新フレーム候補。

---

## 7. 用語の対応表（ADR → ワイヤーで使うべき言葉）

| 概念 | ADR | ワイヤーでの扱い |
|---|---|---|
| Staging set（有界・可視・名前付き、SSoT=StagingStateManager） | 0074 / 0055 / 0043 / 0041 | 「📥 Stage」を全フローの対象 SSoT に |
| Jobs = 監視専用ライフサイクル台帳（作成入口なし） | 0066 / 0076 | Jobs から picker/Submit 撤去、状態確認/キャンセル/復旧のみ |
| Submit = Annotate の dispatch 射影 | 0076 / 0075 | submit 導線は Annotate の dispatch mode へ |
| 選択モデル集合（SSoT）/ ステージ表示は派生ビュー | 0075（0030 を Superseded） | per-stage ピッカー、環境は絞り込み1軸 |
| INFERENCE LEDGER（推論回数 = ユニークモデル × 枚数） | 0075 | dispatch 前の全ジョブ/推論回数プレビュー |
| 品質ティア（masterpiece…worst / no score / unknown） | 0029 | Results / Search の品質表現 |
| score_labels per-scorer pill | 0028 / 0027 | Results の score 不一致表示 |
| Tag/Caption soft-reject（`rejected_at`） | 0065 | Results トリアージの reject 操作 / Export 解決 |
| タグ canonical（保存時 danbooru 焼き込み、手動は保持） | 0068 | Results のタグ表示（verbatim） |
| canonical rating（PG/PG-13/R/X/XXX） | 0031 / 0015 | rating 表示・不一致・フィルタ |
| rating preflight（Moderations, X/XXX 非送信、自動ゲート） | 0070 / 0076 | Annotate→Jobs の自動ゲート（ユーザー操作面に出さない） |
| Provider Batch（非同期 submit→確認→自動 import、選択集合の射影） | 0038 / 0041 / 0076 | Jobs の非同期ジョブ行 |
| WebAPI 3軸候補フィルタ | 0048 | ピッカーの Web API 母集団 |
| 大量 ID count-first / bounded pagination | 0056 / 0060 | Search/Export の件数表示 |
| pHash 重複/別版分類 | 0061 | 登録/インポート画面（新フレーム候補） |
| SQLite ロックエラー分類（busy_timeout） | 0067 | Errors の「リトライ可否」分類 |
| Export = フィルタ必須・staging 集合・解決ルール | 0019 / 0055 / 0065 / 0068 | Export 画面 |

> 注: 本メモは「ワイヤーをどう直すか」の決定ではなく、**次の改訂時の論点リスト**。実際の反映は別途相談のうえ
> Tweaks / 新フレームとして段階的に入れる想定。CLI 専用 ADR（0057/0058/0059/0060/0063）は GUI 影響が薄く、
> ここでは count-first（0056/0060）と原画像ガード（0064）のみ GUI 観点で拾った。
