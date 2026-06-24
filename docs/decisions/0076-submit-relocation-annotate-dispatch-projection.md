---
type: ADR
title: Submit を Annotate の dispatch 射影へ移し Jobs を純粋な監視台帳にする
status: Proposed
timestamp: 2026-06-24
tags: [gui, annotation, jobs, provider-batch, state]
---
# ADR 0076: Submit を Annotate の dispatch 射影へ移し Jobs を純粋な監視台帳にする

- **関連 Issue**: #884 (モデル選択 state の hoist / 複数→単一射影), #867 (epic: MainWindow 分解), #874 (JobsTabWidget 抽出)
- **一部改訂対象**: ADR 0041 (Provider Batch 実行 UI 統一) — submit のレイアウト条項を relocation, ADR 0066 (Unified Jobs Lifecycle View) — Jobs に submit 入口を持たせない旨を追補
- **関連 ADR**: 0030 (Batch Annotation Model Selection UI), 0034 (Worker / Operation / Pipeline Lifecycle Boundary), 0038 (Provider Batch API Integration Strategy), 0070 (OpenAI Moderation WebAPI Preflight), 0074 (StagingStateManager hoist), 0075 (アノテーションパイプライン構成ドメインモデル)

## Context

「アノテーションタブのモデル選択が Jobs タブに反映されない」(#884) の原因をコード確認で特定した。`ModelSelectionWidget` が独立に2インスタンス存在し、両者を繋ぐ配線が存在しない:

- Annotate (`tab/annotate_tab.py`): 複数選択。pipeline ステージ (TAGS/CAPTION/SCORE/RATING) へ割当。SSoT は選択モデル集合 (ADR 0075)。
- Jobs (`widgets/provider_batch_job_widget.py`): `set_single_selection_mode(True)`。batch-capable 単一選択 (ADR 0041「1 submit = 1 model」)。

これは回帰ではなく、ADR のマージ痕 (未調整の責務移動) である。経緯はコードと ADR から一意に追える:

1. **ADR 0038**: provider batch の submit は `submit_batch(request)` という request ベースの作成操作で、`refresh` / `cancel` / `fetch` の監視系とは別 Worker 群 (`BatchSubmitWorker` / `BatchPollWorker` / `BatchImportWorker`) に分離されている。submit と監視は元から別責務。
2. **ADR 0041**: Provider Batch が独立タブだった間は「staging + 単一ピッカー + Submit + 状態表示」を1ウィジェットに同居させるのが正しかった。
3. **ADR 0066**: そのウィジェットを丸ごと Jobs タブへ吸収し「Jobs = 同期 + async batch の lifecycle 台帳 (Jobs is the ledger)」と再定義した。このとき submit 面まで持ち込まれ、submit 責務を再 home 化しなかった。「Jobs = 台帳」と定義した瞬間に「台帳が実行入口を併せ持つ」矛盾が生じた。

証拠: wireframes v12 の `.pbatch` 帯は既に**監視カードしか描いていない** (primary ボタン = `状態を確認`, 副 = `キャンセル`。モデルピッカーも Submit フォームも無い)。ワイヤーは submit フォームを黙って落としたが、実装は ADR 0041 のまま submit を Jobs 側に残した。この乖離が #884 の正体である。

## Decision

### 1. 役割境界: 構成は Annotate・監視は Jobs

- **Annotate** = アノテーション構成の唯一の入口。選択モデル集合 (SSoT, ADR 0075)・pipeline ステージ割当・実行トリガー (同期/非同期の双方) を所有する。
- **Jobs** = 実行 lifecycle の純粋な監視台帳。実行中/キュー/履歴を表示する。操作は **lifecycle / 事故復旧系に限る**: 主操作 `状態を確認` / `キャンセル`、および ADR 0041 §7 が定める二次的な復旧操作 (`fetch` / `import` の再取得・再取り込み) は残す。Jobs から取り除くのは**作成入口 (モデルピッカー・Submit フォーム) だけ**であり、lifecycle/recovery 操作は保持する。

同期と非同期は authoring (構成) の違いではなく dispatch (実行経路) の違いなので、入口は Annotate 1つでよい。

### 2. async batch = 選択モデル集合の dispatch 射影

Provider Batch (async) を「Annotate の選択モデル集合からの dispatch 射影」として定義する:

- 選択モデル集合を route で分割し、batch-capable なモデル1台につき `provider_batch_jobs` を1行生成する。
- 「1 submit = 1 model」(ADR 0041 / 0038) は**手で1つ選ばせる制約ではなく、射影の出力不変条件**として守る。`provider_batch_workflow_service.submit_images(*, litellm_model_id: str, model_id: int | None, ...) -> int` は単一モデルで1ジョブを返すため、batch-capable モデルN台をループ呼び出しすれば N 行になる (service 改変ゼロ、各呼び出しは1モデル1ジョブのまま)。
- **射影は litellm_model_id だけでなく DB の `Model.id` (`model_id`) も各 submit に運ぶ**。`_validate_submit_task` は `task_type = "rating_preflight"` で `model_id` が `None` だと reject し、結果 import も DB model ID に依存する。射影 glue が `model_id` を省くと moderation batch が submit 前に失敗するため、選択/登録済み `Model.id` を射影の出力契約に含める。
- **moderation preflight は「送信ゲート」であって RATING 出力の派生ではない** (ADR 0070)。未評価画像に対する WebAPI 送信の事前判定 (fail-closed) なので、射影は **画像の rating / 送信可否から preflight 要否を決める**。RATING 出力ステージが選択されているか否かでは決めない (tags/caption/score のみ要求 + 未評価画像でも preflight を落とさない)。ただし ADR 0070 line 30 は **Provider Batch の自動2段オーケストレーションを対象外**とし manual `rating_preflight` batch を残す立場なので、async batch の自動 preflight 連鎖は本 ADR では契約 (model_id 同伴・送信ゲート由来) のみ定義し、自動2段の実装は ADR 0070 の deferral を引き継ぐフォローアップとする。

ADR 0041 が却下したのは「暗黙の fan-out + 隠れコスト」である。本案は INFERENCE LEDGER (ADR 0075) で dispatch 前に全ジョブ・全推論回数をプレビューするため、コストが暗黙に増える状況を作らない。0041 の意図を満たしたまま、選び方を「手動単一選択」から「集合の射影 + 事前プレビュー」へ置き換える。

### 3. 第2ピッカーの撤去と state hoist

- Jobs 側 (`provider_batch_job_widget.py`) の `ModelSelectionWidget` (単一選択) と Submit 導線を撤去する。
- モデル選択 state を `gui/state/` へ hoist する (#884, ADR 0074 の `StagingStateManager` に倣う)。canonical = 選択モデル集合。Annotate はこれを購読する唯一の view。Jobs は購読しない (監視のみ)。
- batch-capable フィルタ判定 (現 `ModelSelectionWidget` 内, ADR 0041 §B で移設済) は**削除せず射影レイヤへ転用**する。第2ピッカー撤去後も dispatch 射影がこの helper を要する。

## ADR 0041 / 0066 への影響

- **ADR 0041**: §1 統一レイアウトの「右上に単一選択ピッカー + Submit」条項を relocation する。staging = 共通対象集合 (ADR 0074) と「1 submit = 1 model」不変条件は不変。submit の **置き場**のみが Jobs タブから Annotate の dispatch 射影へ移る。
- **ADR 0066**: 「Jobs = lifecycle 台帳」は不変。本 ADR は「Jobs は作成入口 (submit) を持たない」を明文化し、submit 面の所在を Annotate に確定する追補である。lifecycle 状態 (実行中/キュー/履歴)・キューの実セマンティクス (GPU 直列 / API 並列) は不変。

両 ADR は Status を Accepted のまま、責務の所在のみ更新される。

## Rationale

### (1) 設定は Annotate に一本化 (縦割り維持を採らない)

- 縦割り維持 (同期=Annotate完結 / async=Jobs完結) は二重ピッカー・二重 state・#884 を「仕様」として永続化し、ADR 0066 の「Jobs is the ledger」を自ら取り消すことになる。
- (1) は v12 の背骨2本 (staging = 共通対象 SSoT / Jobs = 台帳) と一致し、「構成は Annotate・監視は Jobs」を一文で言える。

### 橋渡しでなく第2ピッカー撤去 (複数→単一の射影)

- 複数選択 (pipeline) と単一選択 (batch) を双方向同期させると、片方の意味をもう片方へ翻訳し続ける UX ノイズが残る。
- 射影として一方向に定義すれば、SSoT は選択モデル集合の1つだけになり、Jobs は派生すら持たず純粋な監視に徹せる。

## Consequences

**良い点**
- モデル選択 state が1箇所 (`gui/state/`) に集約され、#884 (反映されない) が構造的に解消する。
- 「設定 = Annotate / 監視 = Jobs」が一文で言え、役割境界が一意になる。
- service 層 (`submit_images`) は無改変。射影はループ呼び出しで成立する。

**悪い点 / トレードオフ**
- ADR 0041 のレイアウト条項を relocation するため、本 ADR の Accepted まで Jobs/Annotate のワイヤー反映・実装は保留する (既決の暗黙改変を避ける)。
- 射影レイヤ (route 分割 + batch-capable フィルタ + rating_preflight 分岐) という新コンポーネントが要る。`gui/state/` の選択 state manager と、dispatch を組み立てる service/glue の責務分担を実装 plan で確定する。

**フォローアップ**
- 選択モデル state manager (`gui/state/`) の新設可否を調査 (#884 進め方 2)。
- ワイヤー v12 反映: Annotate に route バッジ + INFERENCE LEDGER に async batch レーン + 単一ピッカー撤去 / Jobs `.pbatch` を監視専用に確定し「作成入口なし」を明示。
- #874 Jobs スコープに本決定を反映 (#884 が #874 着手の前提)。
