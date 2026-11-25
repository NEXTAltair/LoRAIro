# 設計判断(ADR 0001–0079)の Wireframe への影響メモ

- 最終更新: 2026-06-27
- 対象: `LoRAIro Wireframe.html`(Search / Annotate / Jobs / Errors / Results / Export)

---

## 改訂履歴と実装確認の追記

### 2026-06-27 実装確認の追記(本文の前提は実装前)

本メモの本文は「次の改訂時の論点リスト」として **実装前** に書かれており、「未実装の疑い」を含む。その後、実コード(`NEXTAltair/LoRAIro@main`、commit `b8f59ff`)を直接確認したところ、v12 背骨の 4 つのギャップは **すべて実装済み** であった(誤って「未実装」と読まないこと)。

- **Jobs = 監視専用台帳**: `ProviderBatchJobWidget` の GroupBox 名は「バッチジョブ状態 (監視専用)」であり、`labelMonitorOnlyHint` に「作成は Annotate タブから」と表示する。モデルピッカー、Submit、`comboBoxTaskType` は実体に存在しない(ADR 0076 / PR #884・#896)。
- **async batch = 選択モデル集合の dispatch 射影**: `services/dispatch_projection_service.py` の `project_async_batch_dispatch()` が discovery と選択集合の積を取り、非対応モデルが混在する場合は `DispatchProjectionError` で拒否する。batch-capable な 1 モデルにつき 1 つの `DispatchEntry` を生成する(ADR 0076 §2)。
- **INFERENCE LEDGER**: `gui/widgets/inference_ledger_widget.py` が SYNC と PROVIDER BATCH の 2 バンドを備える。ラベルも「推論回数合計」へ是正済みである(ADR 0075 follow-up 反映済み)。
- **rating preflight = 自動ゲート**: 同期実行は `AnnotationWorker(rating_gate=True)` で処理し、async は preflight 未完了時に fail-closed で止める(ADR 0070 / 0077)。Jobs UI から `task_type` コンボボックスは撤去済みである。

GUI 挙動は ADR ではなく Issue で駆動されていた点に注意が必要である(#803 / #754 / #805)。これらはその後に ADR 化された。

- **ADR 0077**: `RunOptions` 実行契約(dry-run 短絡、rating ゲートと refusal filter の分離。#803・PR #915 / #916)。本メモが残課題としていた #803 は決定・実装済みである。
- **ADR 0078**: Model installer の明示ジョブ化(#754・ADR 0066 §5)。
- **ADR 0079**: Jobs のステージ別 progress とサマリ帯(#805)。サマリ帯の正準項目は `running`、`queued`、`completed_7d`、`api_usage=「—」`(データソースがないため捏造禁止)である。

以上により、§6「足す価値が高い」のうち 1〜3 および 5 は実装完了済みである。残るのは登録/インポート画面(#9・ADR 0061・現状ワイヤー外)程度であり、本文は履歴として残置する。

### 2026-06-05 追記

旧 §6 の優先項目はすべて `Wireframes v11` に反映済みである。v11 では、統一品質ティア、per-scorer の `score_labels`、canonical rating 正規化、rating preflight ゲート、環境ファースト・モデルピッカー、非同期 Provider Batch、ステージング集合 Export、worker lifecycle 語彙、新フレーム `07 Export` を取り込んだ。

### 2026-06-27 全面改訂(ADR 0056–0076 を反映)

v11 以降に、ワイヤーフレームの背骨を組み替える 4 本の決定が入った。いずれも Accepted のまま責務や所在を更新する改訂であり、相互に依存する。

1. **ADR 0066 Unified Jobs Lifecycle View**: Jobs を「実行中 / キュー / 履歴」の統一ライフサイクル台帳とする。
2. **ADR 0074 `StagingStateManager` hoist**: ステージング集合の SSoT を `StagingWidget` から中立の `StagingStateManager` へ移す。対象集合の正本は `DatasetStateManager` ではなく `StagingStateManager` である。
3. **ADR 0075 アノテーションパイプライン構成ドメインモデル**: ADR 0030(環境ファースト二段フィルタ)を Superseded とし、per-stage ピッカーと「SSoT = 選択モデル集合、ステージ表示は派生ビュー」の構成へ移行する。
4. **ADR 0076 Submit を Annotate の dispatch 射影へ**: Jobs から作成入口(モデルピッカー、Submit フォーム)を撤去して純粋な監視台帳に確定し、submit を Annotate の dispatch 射影として再配置する。

この 4 本により、v12 の背骨は「**構成は Annotate、監視は Jobs、対象集合は `StagingStateManager`**」という一文に収束する。

以下はリポジトリの `docs/decisions/` を読み込んで整理した内容であり、各項目に現状・ADR の決定・対応方針を併記する。

---

## 0. 全体に効く背骨(v12)

### ステージング集合(Staging set)が全フローの中心 SSoT(ADR 0055 / 0074 / 0043 / 0041)
- 「選択中」という不可視の概念ではなく、**有界(MAX 500 枚)・可視・名前付きの集合** であるステージングを、Annotate / Batch API / Export すべての対象解決の単一ソースとする。
- SSoT の所在は `StagingStateManager` である(ADR 0074)。従来は `StagingWidget` が `OrderedDict` を所有して `connect_shared_staging` で双方向同期する仕組みだったが、中立な `gui/state/StagingStateManager`(`QObject` と `staged_images_changed` Signal)へ引き上げ、`StagingWidget` は view へ降格した。対象集合の正本は `DatasetStateManager` ではなく `StagingStateManager` である(メタ解決のために後者へ前者を注入する)。
- Export の対象もフィルタ結果の直接エクスポートではなく、ステージング集合のみとする。フィルタ結果は「ステージングへ投入」という明示操作を経て初めて対象化される。これにより 21k 件の誤エクスポート事故を構造的に防ぐ(ADR 0019)。
- Search の「📥 Stage」がこの概念に対応するため、Annotate だけでなく Export の入口にもつなぐのが正しい。

### Jobs は純粋な監視台帳、構成は Annotate に一本化(ADR 0066 / 0076)
- Jobs は「実行中 / キュー / 履歴」の 3 状態で、同期ジョブと非同期 Provider Batch を 1 ビューに統合する(ADR 0066)。
- Jobs から作成入口(モデルピッカー、Submit フォーム、staging 投入コントロール)を撤去する(ADR 0076)。Jobs に残す操作はライフサイクル管理と事故復旧のみ(`状態を確認`、`キャンセル`、二次的な `fetch`、`import`)である。
- submit は Annotate の dispatch 射影へ移す。同期と非同期は authoring の違いではなく dispatch(実行経路)の違いであるため、入口は Annotate の 1 箇所でよい。

### Web API バッチ(非同期 Provider Batch)は選択モデル集合の dispatch 射影(ADR 0038 / 0041 / 0076)
- 非同期ライフサイクルは「submit → 後で状態確認 → 完了なら自動 fetch + import」で構成される。
- 「1 submit = 1 model」は手動単一選択の制約ではなく、射影の出力不変条件である(ADR 0076)。選択モデル集合を route 分割し、batch-capable な 1 モデルにつき `provider_batch_jobs` の 1 行を生成する。

---

## 1. Annotate / モデルピッカー(Frame 2A / 2B)★全面更新(ADR 0030 → 0075 で Superseded)

### 1-1. 「選択モデル集合」を SSoT とする per-stage ドメインモデル(ADR 0075)★影響大
- **旧仕様(ADR 0030 / v11)**: 「①実行環境(API / local)→ ②タスク → ③モデル一覧」の二段フィルタであり、環境は未選択状態を持たず常に `api | local` であった。
- **新仕様(ADR 0075、0030 を Superseded)**:
  - UI は per-stage ピッカー(`StageModelPickerDialog` と `PipelineStageTableWidget`)へ全面移行する。
  - SSoT は「選択されたモデルの集合」である。ステージへの割り当ては SSoT ではなく、選択集合から毎回作り直す派生ビューにすぎない。どのモデルをどのステージに置いたかは出力にもコストにも影響しない。
  - アノテーション種類は `tags / caption / score / rating` の 4 つである。これらは逐次工程ではなく、1 推論が並列に埋め得る出力の種類を表す。各モデルがどれを出力できるかは capability(`fill_stages()`)で決まる。
  - 実行環境セグメントは `すべて(all) / APIのみ(api) / ローカルのみ(local)` の 3 値(既定 `all`)とし、ADR 0030 の「環境未選択を持たない」を上書きした。環境は絞り込みの 1 軸へ降格した。
- **対応方針**: ピッカーを per-stage テーブルと環境・種類・provider の絞り込み軸で再構成する。左レールの「環境ファースト」前提を撤去し、現在の選択モデル集合を主表示にする。

### 1-2. multimodal の固定スキーマと RATING の出どころ(ADR 0075)
- multimodal の Web API モデルは 1 推論で `{tags, captions, score}` を固定で返し、**rating は出力しない**。
- `rating` は別経路から取得する。①rating 対応モデルの出力、または ②送信前 moderation プリフライト(ADR 0070)である。
- 派生チップ(`↝ DerivedChip`)は read-only である。multimodal を 1 ステージに主割当すると、同一推論が埋める他種類は派生チップとして表示され、compose 画面では外せない(表示と実体の乖離を防ぐため、派生出力は既定で採用する)。
- 事後除外は非対称である。`tags` と `caption` は Results の soft-reject(ADR 0065)で per-row に外せるが、`score` には per-row reject 経路が現状ないため派生 score は残る。

### 1-3. 推論回数 = ユニークモデル数 × ステージング枚数(ADR 0075)
- 課金単位となる推論アイテム数は **ユニークモデル数 × ステージング枚数** である。同一モデルを複数種類に充当しても `litellm_model_id` で重複排除されるため増えない(`InferenceLedger`)。
- 暗黙の fan-out や隠れコストを作らないよう、dispatch 前に全ジョブと全推論回数をプレビューする(INFERENCE LEDGER)。

### 1-4. Annotate が dispatch mode(同期 / async Batch API)を所有する(ADR 0076)★新フロー
- Jobs から Submit を撤去する前提として、Annotate の run settings に「送信方式 = 同期 / Batch API」(dispatch mode)の選択を設ける。async dispatch は選択モデル集合の射影として `provider_batch_jobs` を生成する。
- 射影契約には、`litellm_model_id` と DB の `Model.id`、`prompt_profile` / `description`、processed / resized 画像パス(ADR 0064)、batch-capable 判定(`list_batch_capable_models()` と helper の積)を運ぶ。
- 非 batch-capable な選択を黙って落としてはならない。部分射影を拒否するか、別経路への振り分けと ledger 報告を必須とする。
- async dispatch の submit ループは、worker thread と busy / 再入ガード(ADR 0044)を引き継ぐ。

### 1-5. Web API モデル名の表示(ADR 0030 #343 / 0048)
- `openrouter/...` などの経路込み ID は前面に出さない。表示には canonical 名を使い、`litellm_model_id` は実行用に保持し、raw route と provider は tooltip に収める。OpenRouter 経由のモデルは route ID から導出した canonical identity を使用する。

### 1-6. Web API 候補の 3 軸フィルタ(ADR 0048)
- annotation 候補となる Web API モデルは、①endpoint が実行可能(`mode=chat`)、②tool / function calling が実在する、③用途適性 denylist(TTS、computer-use、deep-research などを除外)の 3 条件を満たすものとする。

### 1-7. 初回表示での自動 reconcile(ADR 0052)とローカル ML config 所有権(ADR 0040)
- ピッカーの初回生成時に、提供終了した Web API モデルを除外する非同期 sync を 1 回自動実行する(起動直後に短い更新スピナーを表示する)。
- ローカルモデルの config 所有権は ADR 0040 で整理されており、ピッカーのローカル側メタ表示の根拠となる。

### 1-8. 原画像はアノテーション対象外(ADR 0064)
- GUI はもともと `image_dataset/original_images/` の原画像を直接アノテーションさせない仕様であり、CLI 側にも同様のガードを追加した(processed / resized 画像レコードのみを対象とする)。巨大な原画像の誤送信を防ぐため、射影は staged の processed パスを運ぶ。

---

## 2. Results(Frame 5)— 品質トリアージ

### 2-1. 統一品質ティアが raw スコアの上位概念(ADR 0029)★影響大
- 検索・表示・Export の語彙は **統一品質ティア** を用いる。値は以下の 8 種類である。
  `masterpiece / best quality / good quality / normal quality / low quality / worst quality / no score / unknown`
- raw scores と `score_labels` は不変とし、ティアはその上に載る derived view(mapping 版管理 `quality-tier-v1`)として扱う。
- 複数 scorer の vote は **中央値 + `is_unanimous`** で集約する。`no score`(未採点)と `unknown`(mapping 未定義)は明確に分離する。
- **対応方針**: Results の score 列は品質ティア badge を中心に構成し、`no score` と `unknown` の状態も描画する。

### 2-2. `score_labels` は per-scorer pill で並列表示(ADR 0028)
- scorer ごとに `[model] label` の pill を並べて表示し、判定不一致(UC-C)を一目で把握できるようにする。Export と Search 側の絞り込み軸には多数決フィルタ(`min_consensus_count`)を用いる。

### 2-3. AI レーティングの canonical 正規化(ADR 0031)★影響大
- model-native rating は LoRAIro 側で canonical な `PG / PG-13 / R / X / XXX` へマッピングする。`r15` は `R` に割り当て、通常の mapper は `XXX` を自動生成しない。
- 1 モデルにつき 1 rating 行(最高 confidence)を保存する。マッピング不能な値は保存せず skip と warning で処理する。

### 2-4. OpenAI Moderations による rating preflight(ADR 0070、旧 0042-openai-moderation)★更新
- annotation API へ送信する前に OpenAI Moderations Batch(`task_type = "rating_preflight"`、`omni-moderation-latest`)で rating を判定する。`PG / PG-13 / R` は送信し、`X / XXX` は送信しない(`violence/graphic` は `R` 止まりとする)。
- これはユーザー操作ではなく自動の安全ゲートである(ADR 0076 / 0075)。射影は RATING ステージ選択の有無ではなく、画像の rating と送信可否から preflight の要否を判断する。Jobs の `task_type` コンボボックスからは撤去する。
- なお、`omni-moderation` は Moderation API 経由で無料のため、未評価画像への送信ゲート自動挿入はコスト中立である。

### 2-5. Tag / Caption の soft-reject と Export 解決(ADR 0065)★新概念
- `tags` と `captions` に nullable な `rejected_at` を持たせる。`NULL` は採用、非 `NULL` は soft-reject(採用読み出しと export から除外)を意味する。
- 物理削除は行わない。また再アノテーションで復活させない(同一 image / model / content の upsert で reject を解除しない)。
- Export 時は採用タグを string union と重複除去で解決し、衝突時は手動編集タグを優先する。caption は 1 行に解決する(手動編集を優先し、なければ最新の採用行を採用する)。
- **対応方針**: Results のトリアージに「このタグ/caption を reject」操作を追加し、`rejected_at IS NULL` を既定フィルタとする。

### 2-6. タグ正規化は保存時に danbooru canonical を焼き込む(ADR 0068)
- 表示に未整形タグ(`_touhou`、`Grey hair`、`bad_id` など)が混在していた原因は、タグ canonical 化の境界欠如であった。
- 非手動タグは保存時に `search_tags_bulk(resolve_preferred=True)`(1 画像につき 1 bulk lookup)で danbooru の preferred を焼き込む。一方、手動編集タグ(`is_edited_manually=True`)は canonical 化せずユーザー表記を保持する。
- 表示時変換は実 DB で遅すぎたため撤回し、GUI の詳細表示は verbatim とする。管理メタタグ(`type=meta`)は export 時のみ除外する。
- **対応方針**: Results のタグ表示は「保存済み canonical(手動編集は整形済み)」とし、手動編集タグは別表記として描き分けられるようにする。

---

## 3. Jobs / Errors(Frame 3 / 4)★全面更新(ADR 0066 / 0076)

### 3-1. 統一 Jobs ライフサイクルビュー(ADR 0066)★影響大
- 「実行中 / キュー / 履歴」の 3 状態で、同期ジョブと Provider Batch を 1 つのビューに統合する。Jobs の半分は台帳であるため、空状態でも履歴テーブルの枠は残す。
- 永続性は非対称である。同期ジョブの履歴はセッションスコープの in-memory(再起動で消える)とし、再起動を跨ぐ必然がある Provider Batch は既存の `provider_batch_jobs` テーブルで永続化する。
- ジョブ粒度は Pipeline / Operation レベルとする(ADR 0034)。firehose 化を防ぐため、検索やサムネ生成などの UI 応答 Worker は載せない。
- キューは実セマンティクスを持つ。ローカル GPU 推論ジョブは VRAM 競合を構造的に防ぐため同時 1 件の直列キューとし、API 系は並列実行を許容する。
- 進捗ポップアップは Phase 7 で廃止する。実行開始時に Jobs タブへ自動遷移はせず、statusbar 通知と完了時の Results 自動着地で案内する。

### 3-2. Jobs は作成入口を持たない監視台帳(ADR 0076)★影響大
- **Jobs から撤去するもの**: 単一選択のモデルピッカー、Submit フォーム、submit 専用の staging/対象選択コントロール、`rating_preflight` の `task_type` コンボ露出。
- **Jobs に残すもの**: 主操作の `状態を確認` と `キャンセル`、二次的な復旧操作の `fetch` と `import`。
- レイアウトは監視カードのみとする(v12 の `.pbatch` 帯は primary が `状態を確認`、副操作が `キャンセル` で、ピッカーと Submit は置かない)。
- **対応方針**: Jobs は監視専用として描き、submit 導線は §1-4(Annotate の dispatch mode)へ移設する。

### 3-3. Worker / Operation / Pipeline の 3 層ライフサイクル(ADR 0034)
- 「現在の操作の失敗」「置換された古い worker の失敗」「明示キャンセル後の timeout」を区別するための 3 層境界である。Errors と Jobs で使う状態語彙(`CANCELED` / `TERMINATED` / `UNRESPONSIVE` / `superseded`)の根拠となる。

### 3-4. SQLite 並行性とロックエラー分類(ADR 0067)★新
- `busy_timeout` の設定とロックエラーの分類を定める。API 並列・GPU 直列で実行する際の失敗表示と「リトライ可否」分類(一時的ロックはリトライ可、恒久エラーと区別)に直結する。

### 3-5. バッチ保存の atomic 化と I/O 分離(ADR 0012 / 0042 / 0033)
- バッチタグ保存は atomic transaction とし、DB save の I/O は分離する(ADR 0042 `batch-annotation-db-save-io`)。worker のバッチ実行契約(ADR 0033)と合わせ、部分失敗時の見せ方に制約を与える。

### 3-6. ログ運用(ADR 0045 / 0046 / 0047)
- 大量検索結果のログレベル、loguru の placeholder、per-item 診断の trace レベルを定めており、Errors における「技術詳細」の粒度設計に間接的に影響する。

---

## 4. Search(Frame 1)

### 4-1. 品質ティア・フィルタ(ADR 0029)
- 検索フィルタは raw scorer 値ではなくティアを主インターフェースとする。
  - 例: `品質: good quality 以上`、`一致条件: 1件以上・過半数・全件`、`未採点: 除外・含める・未採点のみ`

### 4-2. AI レーティング・フィルタ(ADR 0031 / 0015)
- canonical rating(`PG / PG-13 / R / X / XXX`)で絞り込む。manual rating(`MANUAL_EDIT`)と AI rating は分離し、手動側を優先する。「AI レーティング未設定のみ」も抽出可能である(マッピング不能で未保存のレコードは対象に戻らない)。

### 4-3. ステージング投入が Search → Annotate / Export の唯一の橋(ADR 0055 / 0074)
- 「フィルタ結果 → サムネ確認 → ステージングへ投入」の順に対象化する。唯一の選択ソースは `StagingStateManager` である(ADR 0074。旧メモの `DatasetStateManager` 記述から更新)。

### 4-4. 大量 ID 集合ガードと count-first(ADR 0056 / 0060)★新
- exact-set selector に大量の ID 集合が渡された場合の count-only 軽量化と上限ガードを設ける(ADR 0056)。CLI の bounded pagination / count-first 契約(ADR 0060、1 回 500 枚上限)とも整合する。Search の件数表示では重い全件取得を避け、count を先に算出する。

### 4-5. 登録パイプライン:pHash 候補の重複/別版分類(ADR 0061)★新概念(登録/インポート側)
- pHash の完全一致は「重複確定」ではなく「候補」として扱う。`width`、`height`、`has_alpha`、`is_grayscale_like` を比較し、**重複** か **別版**(カラー/グレー版、解像度違い、透過有無)かを分類する。別版は新規の `images` 行を作成する。
- ハミング距離による近似重複検知は導入せず、完全一致のみを起点とする。`phash` カラムは unique 化せず候補検索キーとして使う。
- 孤児ファイルを残さないよう、保存は分類後に実行する(重複なら保存しない)。`.txt` / `.caption` の取り込み、alias 登録、統計などの副作用は分類結果駆動とし、GUI / API / direct の全経路で統一する。
- **対応方針**: 現状ワイヤー外の登録/インポート画面に、「重複 vs 別版」の確認と分類結果表示を将来追加する論点として残す。

---

## 5. Export(Frame 7)

### 5-1. フィルタ必須・全件禁止(ADR 0019)
- Export にはフィルタ条件を必須とし、全件エクスポートは存在させない。GUI ではステージング集合を暗黙のフィルタとして扱う。

### 5-2. 対象 = ステージング集合(ADR 0055 / 0074)★スタブを実画面化する根拠
- Export の入口はツールバーに常設し、サムネグリッドの下部バーにも配置する。対象は常に staged 集合(SSoT は `StagingStateManager`)である。
- `ImageFilterCriteria.image_ids` は exact-set selector として機能し、NSFW 除外などをバイパスする(明示的にステージングした NSFW を黙って落とさない)。大量 ID には count-only ガードを適用し(ADR 0056)、changed-since フィルタはダイアログ内の post-filter とする。

### 5-3. Export 解決ルール(ADR 0065 / 0068)★新
- 採用タグ(`rejected_at IS NULL`)は string union と重複除去で解決し、手動編集タグを優先する。caption は 1 行に解決する。
- target format の出し分けは export 時に danbooru 基準から target へ変換し(ADR 0068)、管理メタタグ(`type=meta`)を除外する。
- **対応方針**: Export スタブを「ステージング集合を学習フォーマットに書き出す」実画面へ昇格させ、format 選択と meta 除外を描画する。

---

## 6. 「足す価値が高い」もの(優先度順・2026-06-27 更新)

1. **Jobs を監視専用台帳に確定+Submit を Annotate へ移設**(ADR 0066 / 0076)— v12 の背骨であり最優先。
2. **モデルピッカーを per-stage+選択モデル集合 SSoT へ刷新(環境ファースト撤去)**(ADR 0075、0030 Superseded)。
3. **Annotate に dispatch mode(同期 / async Batch API)と INFERENCE LEDGER プレビューを追加**(ADR 0076 / 0075)。
4. **Results を raw スコアから統一品質ティア badge+soft-reject 操作へ更新**(ADR 0029 / 0028 / 0065)。
5. **rating preflight を自動ゲートとして表現(ユーザー操作面から撤去)**(ADR 0070 / 0076)。
6. **対象集合の SSoT 表記を `StagingStateManager` に統一**(ADR 0074)— メモとワイヤーフレームの用語を揃える。
7. **Export スタブをステージング集合ベースの実画面(解決ルール込み)へ昇格**(ADR 0055 / 0019 / 0065 / 0068)。
8. **Search に品質ティア/canonical rating facet と count-first を反映**(ADR 0029 / 0031 / 0056 / 0060)。
9. **登録/インポート画面に「重複 vs 別版」分類を追加**(ADR 0061)— 現状ワイヤー外の新フレーム候補。

---

## 7. 用語の対応表(ADR → ワイヤーで使うべき言葉)

| 概念 | ADR | ワイヤーでの扱い |
|---|---|---|
| Staging set(有界・可視・名前付き、SSoT=`StagingStateManager`) | 0074 / 0055 / 0043 / 0041 | 「📥 Stage」を全フローの対象 SSoT にする |
| Jobs = 監視専用ライフサイクル台帳(作成入口なし) | 0066 / 0076 | Jobs からピッカーと Submit を撤去し、状態確認・キャンセル・復旧のみ残す |
| Submit = Annotate の dispatch 射影 | 0076 / 0075 | submit 導線は Annotate の dispatch mode へ移す |
| 選択モデル集合(SSoT)/ステージ表示は派生ビュー | 0075(0030 を Superseded) | per-stage ピッカーとし、環境は絞り込みの 1 軸とする |
| INFERENCE LEDGER(推論回数 = ユニークモデル × 枚数) | 0075 | dispatch 前の全ジョブ・推論回数プレビュー |
| 品質ティア(`masterpiece`…`worst` / `no score` / `unknown`) | 0029 | Results と Search の品質表現 |
| `score_labels` per-scorer pill | 0028 / 0027 | Results の score 不一致表示 |
| Tag / Caption の soft-reject(`rejected_at`) | 0065 | Results トリアージの reject 操作と Export 解決 |
| タグ canonical(保存時に danbooru 焼き込み、手動は保持) | 0068 | Results のタグ表示(verbatim) |
| canonical rating(`PG / PG-13 / R / X / XXX`) | 0031 / 0015 | rating の表示・不一致・フィルタ |
| rating preflight(Moderations、`X / XXX` 非送信、自動ゲート) | 0070 / 0076 | Annotate → Jobs の自動ゲート(ユーザー操作面には出さない) |
| Provider Batch(非同期 submit → 確認 → 自動 import、選択集合の射影) | 0038 / 0041 / 0076 | Jobs の非同期ジョブ行 |
| Web API 3 軸候補フィルタ | 0048 | ピッカーの Web API 母集団 |
| 大量 ID の count-first / bounded pagination | 0056 / 0060 | Search と Export の件数表示 |
| pHash 重複/別版分類 | 0061 | 登録/インポート画面(新フレーム候補) |
| SQLite ロックエラー分類(`busy_timeout`) | 0067 | Errors の「リトライ可否」分類 |
| Export(フィルタ必須・staging 集合・解決ルール) | 0019 / 0055 / 0065 / 0068 | Export 画面 |

> 注: 本メモはワイヤーフレームの修正決定そのものではなく、**次の改訂時の論点リスト** である。実際の反映は別途相談のうえ、Tweaks や新フレームとして段階的に取り込む想定である。CLI 専用の ADR(0057 / 0058 / 0059 / 0060 / 0063)は GUI への影響が薄いため、ここでは count-first(0056 / 0060)と原画像ガード(0064)のみを GUI 観点で拾った。
