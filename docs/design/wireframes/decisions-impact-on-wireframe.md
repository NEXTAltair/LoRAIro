# 設計判断（ADR 0001–0055）の Wireframe v10 への影響メモ

最終更新: 2026-06-05
対象: `Wireframes v10.html`（Search / Annotate / Jobs / Errors / Results / Export）

> **2026-06-05 追記:** 本メモ §6 の優先項目はすべて **`Wireframes v11.html` に反映済み**。
> v11 = 統一品質ティア / per-scorer score_labels / canonical rating 正規化 / rating preflight ゲート /
> 環境ファースト・モデルピッカー / 非同期 Provider Batch / ステージング集合 Export / worker lifecycle 語彙 +
> 新フレーム **07 Export**。 v10 は履歴として残置。

リポジトリ `docs/decisions/` を読み込んで把握した内容。**v10 を描いた後に確定した決定**のうち、
ワイヤーフレームに食い違い・追記が必要な箇所を整理する。各項目に「v10 の現状」「ADR の決定」
「対応方針」を併記。

---

## 0. 全体に効く新しい背骨

- **ステージング集合（Staging set）が全フローの中心 SSoT になった**（ADR 0055 / 0043 / 0041）。
  - 「選択中」という不可視概念ではなく、**有界（MAX 500枚）・可視・名前付きの集合**＝ステージングが、
    Annotate / Batch API / Export すべての対象解決の単一ソース。
  - Export 対象も「フィルタ結果の直エクスポート」ではなく **ステージング集合のみ**。フィルタ結果は
    「ステージングへ投入」という明示操作を経て初めて対象化（21k 件誤エクスポート事故の構造的防止＝ADR 0019）。
  - v10 では Search の「📥 Stage 9」がこの概念に当たる。**この棒を Annotate だけでなく Export の入口にも**
    つなげるのが新しい正。

- **Web API バッチ（非同期 Provider Batch）が一級市民になった**（ADR 0038 / 0041 / 0033）。
  - v10 の Jobs は「ローカル同期実行の進捗」中心。実際には **OpenAI / Anthropic の非同期 Batch ジョブ**
    （submit → 後で状態確認 → 完了なら自動 fetch+import）という別ライフサイクルが加わっている。

---

## 1. Annotate / モデルピッカー（Frame 2A / 2B）

### 1-1. モデル選択は「環境ファースト」の二段フィルタ（ADR 0030, amended #585）

> **⚠️ Superseded by ADR 0075（2026-06-23、#885/#887/#889）**: この「環境 → タスク」二段フィルタ案は
> per-stage ピッカー（`StageModelPickerDialog`、#741/#839/#845）へ移行済みで、ADR 0030 は Superseded。
> 現行の正準は **ADR 0075**: SSoT は選択モデル集合、ステージ表示は派生ビュー、実行環境は
> `すべて / APIのみ / ローカルのみ` の3値（既定 `すべて`）＝絞り込みの1軸（環境未選択を持たない、という
> 0030 の規定は撤回）。以下は移行前の設計記録として残す。

- **v10 の現状**: ピッカーは CAPTION ステージから開く task ドリブン。左レールはモデル種別。
  `Model.type ∈ {multimodal}` で事前絞り込み。
- **ADR の決定**: フィルタは **① 実行環境（Web API / ローカル）→ ② タスク（Caption/Tags/Scores/すべて）→
  ③ モデル一覧** の順。`environment = "api" | "local"` を常にどちらか選択（未選択状態を持たない）。
  - `executionEnvCombo` のような二重の環境フィルタは**廃止**。入力源はひとつ。
  - 「すべて」は空配列ではなく明示的な値。空＝全件補完の暗黙挙動は廃止。
  - capability 絞り込みは**ローカル選択時のみ操作可能**。Web API 選択時は同じ場所に Web API モデル一覧を
    出す（#585 で placeholder 案は撤回）。
  - **upscaler 等の除外は表示名文字列でなく構造化 model type / capability で行う**（v10 の UPSCALE 行の扱いに影響）。
- **対応方針**: ピッカー上部に「環境 → タスク」の二段を明示し、現在の適用条件を
  `Web API / Tags` のように1行表示。左レールを「環境＋タスク」に組み替える。

### 1-2. Web API モデル名の表示（ADR 0030 #343 / 0048）
- `openrouter/...` などの経路込み ID を前面に出さない。表示は canonical 名、`litellm_model_id` は実行用に保持、
  raw route / provider は tooltip。OpenRouter 経由の provider/family は route ID から導出した canonical identity を使う。

### 1-3. WebAPI 候補は3軸でフィルタされる（ADR 0048）
- annotation 候補に出る Web API モデルは「① endpoint 実行可能（現状 `mode=chat` のみ）」「② tool/function calling
  実在」「③ 用途適性 denylist（TTS / computer-use / deep-research 等を除外）」を満たすもの。
  - ピッカーに出る Web API モデルの母集団がこれで決まる、という注記をデザインメモに足すと良い。

### 1-4. 初回表示で自動 reconcile（ADR 0052）
- ピッカー初回生成時、提供終了した Web API モデルを落とすため非同期 sync を1回自動実行。
  - 「起動直後に短い更新スピナーが出ることがある／手動『更新』も残る」を反映できる。

### 1-5. ローカル ML モデル設定の所有権（ADR 0040）
- ローカルモデルの config 所有が整理されている（詳細は 0040）。ピッカーのローカル側メタ表示の根拠。

---

## 2. Results（Frame 5）— 品質トリアージ

### 2-1. 統一品質ティアが raw スコアの上位概念（ADR 0029）★影響大
- **v10 の現状**: 各行に `aesthetic 7.8` のような **raw スコア**を表示。
- **ADR の決定**: 検索・表示・Export の語彙は **統一品質ティア**:
  `masterpiece / best quality / good quality / normal quality / low quality / worst quality / no score / unknown`。
  - raw scores / score_labels は**不変**。ティアはその上の derived view（mapping 版管理 `quality-tier-v1`）。
  - 複数 scorer の vote を **中央値 + is_unanimous** で集約。
  - `no score`（未採点）と `unknown`（mapping 未定義）は**明確に分離**。
- **対応方針**: Results の score 列を「品質ティア badge」中心に。例:
  `品質: best quality (2 scorer · 全一致)` ／ raw は副表示。`no score` / `unknown` の状態も1ケース描く。

### 2-2. score_labels は per-scorer pill で並列表示（ADR 0028）
- scorer ごとに `[model] label` の pill を並べ、**判定不一致（UC-C）を一目で**。
  - v10 の rating 不一致カードと同じ思想を score にも適用。「scorer 間の不一致」も issue 化候補。
- 多数決フィルタ（`min_consensus_count`）が Export/Search 側の絞り込み軸。

### 2-3. AI レーティングは canonical へ正規化（ADR 0031）★影響大
- **v10 の現状**: `wd-rater R ↔ gpt-4o PG` のようなモデル間不一致を CRIT 表示（思想は正しい）。
- **ADR の決定**: model-native rating → canonical `PG / PG-13 / R / X / XXX` に LoRAIro 側で mapping。
  - `r15 → R`、通常 mapper は `XXX` を自動生成しない（手動 or openai_moderation のみ）。
  - **1 モデル = 1 rating 行**（最高 confidence の1件）。mapping 不能は**保存せず skip + warning**（未判定として残す）。
  - rating 専用モデルは `model_type="rating"`、tagger 兼用は `["tags","ratings"]`。
- **対応方針**: 不一致表示は canonical 値同士の比較である点を明記。`X/XXX` が混ざるケース、
  「mapping 不能で未判定」のケースを Results に追加できる。

### 2-4. OpenAI Moderations による rating preflight（ADR 0031 amend / 0070-openai-moderation）★新概念
- annotation API に送る**前**に OpenAI Moderations Batch で rating を判定し、
  **`X / XXX` は annotation API に送らない**（`PG/PG-13/R` は送る。`violence/graphic` は R 止まり）。
  - これは Annotate → Jobs の間に挟まる**ゲート**。v10 には無い。Annotate の「送信前プリフライト」または
    Jobs の前段として描く価値がある。`task_type = "rating_preflight"`、`omni-moderation-latest`。

---

## 3. Jobs / Errors（Frame 3 / 4）

### 3-1. Provider Batch（非同期）ライフサイクルの UI 統一（ADR 0041 / 0038）★影響大
- **v10 の現状**: Jobs は同期実行の進捗バー中心。履歴テーブルあり。
- **ADR の決定**:
  - **1 submit = 1 batch job / 1 provider / 1 model**（モデルは単一選択。複数は submit を複数回）。
  - 主操作は **「状態を確認」だけ**に集約。完了していれば **fetch + import を自動**。
    `更新`（ローカル再読込）と `状態更新`（provider 問い合わせ）を別ボタンで並べない。
    `取得`／`取り込み`は通常フローの主ボタンから外し、復旧用の二次操作に。
  - task_type × provider × endpoint の対応表（annotation→openai `/v1/chat/completions` or anthropic `/v1/messages`、
    rating_preflight→openai `/v1/moderations`）。
  - レイアウトは個別実行と同形（左=ステージング／右上=実行／右下=ジョブ状態）。
- **対応方針**: Jobs に **非同期 Batch ジョブの行**（submitted / validating / in_progress / completed→auto-imported）を
  追加。「状態を確認」一個に主操作を集約した見せ方に。

### 3-2. Worker / Operation / Pipeline の3層ライフサイクル（ADR 0034）
- 「現在の操作の失敗」「置換された古い worker の失敗」「明示キャンセル後の timeout」などを区別する3層境界。
  - Errors / Jobs の状態語彙（CANCELED / TERMINATED / UNRESPONSIVE / superseded）を正確化する根拠。
  - v10 Errors の「リトライ可否」分類と整合させられる。

### 3-3. バッチ保存は atomic、I/O 分離（ADR 0012 / 0042-batch-annotation-db-save-io / 0033）
- バッチタグ保存は atomic transaction。DB save I/O は分離。worker のバッチ実行契約（0033）。
  - 「部分失敗時の見せ方」をデザインする際の制約。

### 3-4. ログ運用（ADR 0045 / 0046 / 0047）
- 大量検索結果のログレベル、loguru placeholder、per-item 診断の trace レベルなど。
  Errors 画面の「技術詳細」表示の粒度設計に間接的に効く（直接の UI 変更要求は薄い）。

---

## 4. Search（Frame 1）

### 4-1. 品質ティア・フィルタ（ADR 0029）
- 検索フィルタは raw scorer 値ではなく **ティア**を主 interface に:
  `品質: good quality 以上 / 一致条件: 1件以上・過半数・全件 / 未採点: 除外・含める・未採点のみ`。
- **対応方針**: Search の facet に品質ティアの3コントロールを追加。

### 4-2. AI レーティング・フィルタ（ADR 0031 / 0015）
- canonical rating（PG/PG-13/R/X/XXX）で絞り込み。manual rating（MANUAL_EDIT）と AI rating は分離・優先。
- 「AIレーティング未設定のみ」を抽出できる（mapping 不能で未保存のものが対象に戻らない）。

### 4-3. ステージング投入が Search → Annotate / Export の唯一の橋（ADR 0055 / 0043）
- フィルタ結果 → サムネ確認 → **「ステージングへ投入」** → 対象化。`DatasetStateManager` が唯一の選択ソース。

---

## 5. Export（Frame 7 / 現状スタブ）

### 5-1. フィルタ必須・全件禁止（ADR 0019）
- Export はフィルタ条件必須。GUI は「ステージング集合＝暗黙フィルタ」。全件エクスポートは存在しない。

### 5-2. 対象＝ステージング集合（ADR 0055）★スタブを実画面化する根拠
- Export 入口はツールバー常設＋サムネグリッド下部バー。対象は常に `StagingWidget.get_image_ids()`。
- 件数表示は staged 件数。`ImageFilterCriteria.image_ids` は **exact-set selector**（NSFW 除外等を bypass、
  明示ステージングした NSFW を黙って落とさない）。changed-since フィルタはダイアログ内 post-filter。
- **対応方針**: Export スタブを「ステージング集合を学習フォーマットに書き出す」実画面に昇格できる。

---

## 6. v10 に「足す価値が高い」もの（優先度順）

1. **Results: raw スコア → 統一品質ティア badge**（ADR 0029 / 0028） — 影響最大、思想の核。
2. **モデルピッカー: per-stage ピッカー**（ADR 0075、旧 0030 の二段フィルタを supersede）— v10 と明確に食い違う。
3. **Annotate↔Jobs 間に rating preflight（Moderations）ゲート**（ADR 0031）— 新フロー段。
4. **Jobs: 非同期 Provider Batch 行 ＋「状態を確認」集約**（ADR 0041 / 0038）— Jobs の見せ方を更新。
5. **Export スタブ → ステージング集合ベースの実画面**（ADR 0055 / 0019）。
6. **Search: 品質ティア / canonical rating facet**（ADR 0029 / 0031）。
7. **Rating 正規化の明示（canonical・1モデル1行・未判定 skip）**（ADR 0031）。

---

## 7. 用語の対応表（ADR → v10 で使うべき言葉）

| 概念 | ADR | v10 での扱い |
|---|---|---|
| Staging set（有界・可視・名前付き） | 0055 / 0043 / 0041 | 「📥 Stage 9」を全フローの対象 SSoT に |
| 品質ティア（masterpiece…worst / no score / unknown） | 0029 | Results / Search の品質表現 |
| score_labels per-scorer pill | 0028 / 0027 | Results の score 不一致表示 |
| canonical rating（PG/PG-13/R/X/XXX） | 0031 / 0015 | rating 表示・不一致・フィルタ |
| rating preflight（Moderations, X/XXX 非送信） | 0031 / 0042 | Annotate→Jobs のゲート |
| Provider Batch（非同期 submit→確認→自動 import） | 0038 / 0041 | Jobs の非同期ジョブ |
| per-stage ピッカー（環境=絞り込み1軸、選択モデル集合 SSoT） | 0075（旧 0030） | モデルピッカー |
| WebAPI 3軸候補フィルタ | 0048 | ピッカーの Web API 母集団 |
| Export = フィルタ必須・staging 集合 | 0019 / 0055 | Export 画面 |

> 注: 本メモは「v10 をどう直すか」の決定ではなく、**次の改訂時の論点リスト**。実際の反映は別途相談のうえ
> Tweaks / 新フレームとして段階的に入れる想定。
