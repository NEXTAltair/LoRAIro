---
type: ADR
title: Submit を Annotate の dispatch 射影へ移し Jobs を純粋な監視台帳にする
status: Accepted
timestamp: 2026-06-24
tags: [gui, annotation, jobs, provider-batch, state]
---
# ADR 0076: Submit を Annotate の dispatch 射影へ移し Jobs を純粋な監視台帳にする

- **関連 Issue**: #884(モデル選択状態の引き上げと複数選択から単一選択への射影)、#867(Epic: MainWindow 分解)、#874(JobsTabWidget 抽出)
- **一部改訂対象**(本 ADR の Accepted 昇格コミットで逆参照を適用済み。ADR 0060 の前例に倣い、Proposed の間は確定済み ADR を編集しなかった):
  - ADR 0041(Provider Batch 実行 UI 統一): §1 の統一レイアウトにある Submit 条項の配置先を変更する。
  - ADR 0066(Unified Jobs Lifecycle View): Jobs に作成(Submit)の入口を持たせない旨を追補する。
  - ADR 0075(アノテーションパイプライン構成ドメインモデル): 選択モデル集合(SSoT)の所在を `ModelSelectionWidget` のチェックボックス状態から `gui/state/` の選択状態マネージャへ移す(#884 の状態引き上げ)。SSoT が「選択モデル集合」である定義自体は不変である。
- **関連 ADR**: 0030(Batch Annotation Model Selection UI)、0034(Worker / Operation / Pipeline Lifecycle Boundary)、0038(Provider Batch API Integration Strategy)、0070(OpenAI Moderation WebAPI Preflight)、0074(StagingStateManager の状態引き上げ)、0075(アノテーションパイプライン構成ドメインモデル)

## Context

「アノテーションタブのモデル選択が Jobs タブに反映されない」(#884)という問題の原因をコードで確認したところ、`ModelSelectionWidget` が独立した 2 つのインスタンスとして存在し、両者を接続する配線がないことが判明した。

- **Annotate タブ**(`tab/annotate_tab.py`): 複数選択に対応し、パイプラインの各ステージ(TAGS、CAPTION、SCORE、RATING)へモデルを割り当てる。SSoT は選択モデル集合である(ADR 0075)。
- **Jobs タブ**(`widgets/provider_batch_job_widget.py`): `set_single_selection_mode(True)` により、バッチ対応モデルの単一選択を行う(ADR 0041「1 submit = 1 model」)。

これは機能回帰ではなく、過去の ADR を統合した際に残った未調整の責務移動である。経緯はコードと ADR から一意にたどれる。

1. **ADR 0038**: Provider Batch の投入(Submit)は `submit_batch(request)` によるリクエストベースの作成操作である。監視系の `refresh`、`cancel`、`fetch` とは別のワーカー群(`BatchSubmitWorker`、`BatchPollWorker`、`BatchImportWorker`)に分離されており、投入と監視はもともと別責務だった。
2. **ADR 0041**: Provider Batch が独立タブだった時期は、ステージング、単一ピッカー、Submit、状態表示を 1 つのウィジェットに同居させる設計が妥当だった。
3. **ADR 0066**: そのウィジェットを丸ごと Jobs タブへ吸収し、「Jobs は同期処理と非同期バッチのライフサイクル台帳である(Jobs is the ledger)」と再定義した。この際、Submit 画面もそのまま持ち込まれ、投入責務の再配置が行われなかった。その結果、「台帳であるはずの Jobs が実行の入口を併せ持つ」という矛盾が生じた。

この矛盾はワイヤーフレームとの乖離にも表れている。wireframes v12 の `.pbatch` 帯にはすでに監視カードしか描かれていない。主ボタンは「状態を確認」、副ボタンは「キャンセル」のみで、モデルピッカーも Submit フォームも存在しない。ワイヤーフレームは Submit フォームを削除した一方で、実装は ADR 0041 のまま Jobs 側に Submit を残していた。この乖離こそが #884 の正体である。

## Decision

### 1. 役割境界: 構成は Annotate、監視は Jobs

同期実行と非同期実行は、構成(何を走らせるか)の違いではなく実行経路(どのように送信するか)の違いである。そのため、構成と実行の入口は Annotate の 1 箇所に一本化する。

- **Annotate はアノテーション構成の唯一の入口とする**: 選択モデル集合(SSoT、ADR 0075)、パイプラインのステージ割当、および同期・非同期双方の実行トリガーを所有する。
- **Jobs の Submit 撤去に先立ち、Annotate に送信方式の選択を設ける**: 現状では Annotate の `annotation_execute_requested` が `MainWindow.start_annotation()`(同期ワークフロー専用)に接続されており、`RunOptions` に Provider Batch 用の非同期モードがない。Jobs の Submit を削除する前に、Annotate 側の実行詳細設定に送信方式(同期または Batch API)の選択と `RunOptions` への非同期経路を追加する。これがないと、通常アノテーションの非同期バッチ作成経路が失われる。
- **非同期送信の投入ループは GUI スレッドから切り離す(ADR 0044)**: `submit_images()` は DB、ファイルシステム、ネットワークの I/O を伴う。現行の `ProviderBatchJobWidget` は投入処理を `_ProviderBatchSubmitWorker`(ワーカースレッド)へ移し、`_set_submit_button_busy` でビジー制御と再入防止を行っている。新しい `RunOptions` 経路をボタンや MainWindow のスロットから直接呼ぶと、複数モデル射影時に Qt UI が固まり、重複投入の競合が再発する。新経路でもワーカースレッド化と再入防止ガード(ADR 0044)を引き継ぐ。
- **Jobs は実行ライフサイクルの純粋な監視台帳とする**: 実行中、キュー待機中、履歴の一覧を表示し、操作はライフサイクル管理と事故復旧に限定する。主操作の「状態を確認」「キャンセル」に加え、ADR 0041 §7 が定める二次的な復旧操作(`fetch` や `import` による再取得・再取り込み)は残す。Jobs から取り除くのは作成入口(モデルピッカーと Submit フォーム)のみである。

### 2. 非同期バッチを選択モデル集合からの送信射影として定義する

Provider Batch(非同期実行)は、Annotate で選択されたモデル集合から生成する「送信射影」として定義する。

- **モデル単位でジョブを生成する**: 選択モデル集合を実行経路ごとに分割し、バッチ対応モデル 1 台につき `provider_batch_jobs` を 1 行生成する。
- **バッチ非対応モデルを黙って除外しない**: ローカルモデルや OpenRouter 経路などバッチ非対応のモデルが選択された状態で非同期 Batch API を選んだ場合、射影はバッチ対応の部分集合だけをジョブ化する。ADR 0075 は選択モデル集合を期待出力とコストの SSoT と定めているため、無言で落とすと「選んだモデルが走らない」状態になる。実行計画を確定する前に、「部分射影を拒否する」か「非対応モデルを別経路へ回す・台帳で明示報告する」のいずれかを必須とする。
- **「1 submit = 1 model」を射影の出力不変条件として守る**: ADR 0041 および ADR 0038 の原則は、手動で 1 つだけ選ばせる UI 制約ではなく、射影の出力不変条件として維持する。`provider_batch_workflow_service.submit_images(*, litellm_model_id: str, model_id: int | None, ...) -> int` は単一モデルで 1 ジョブを返すため、バッチ対応モデル N 台に対してループ呼び出しを行えばサービス層を無改変のまま N 行を生成できる。
- **DB の `Model.id`(`model_id`)も射影に含める**: `_validate_submit_task` は `task_type = "rating_preflight"` で `model_id` が `None` の場合に処理を拒否し、結果の取り込みも DB のモデル ID に依存する。射影の橋渡し層で `model_id` を省略するとモデレーション用バッチが投入前に失敗するため、選択・登録済みの `Model.id` を射影の出力契約に含める。
- **`prompt_profile` と `description` を送信契約に含める**: 現行の `ProviderBatchJobWidget.submit_job()` は `lineEditPromptProfile` と `lineEditDescription` を読み取り、`submit_images(prompt_profile=..., description=...)` へ渡している。ADR 0038 でも `prompt_profile` はジョブのメタデータとして扱われる。Annotate 側の送信でこれらを渡さないと、`prompt_profile="default"` 固定かつ `description` 欠落となり、リクエスト内容と監査データが変わってしまう。Annotate の実行詳細設定でこの 2 値を指定できるようにし、射影契約に含める。
- **処理済み・リサイズ済み画像パスを射影に引き継ぐ(ADR 0064)**: ステージングが処理済み画像パスで構成されていても、`submit_images` に `image_ids` だけを渡すと、`ProviderBatchWorkflowService` は `get_images_metadata_batch(..., resolution=0)` により元画像の `stored_image_path` へフォールバックする。その結果、ADR 0064 の処理済み画像による安全策を迂回し、巨大な元画像をアップロードする恐れがある。射影契約には、ステージング済みの処理済みパス(`image_paths` の上書き)または明示的な解像度指定を含める。
- **モデレーション事前検査(preflight)は送信ゲートとして判定する(ADR 0070)**: モデレーション事前検査は未評価画像に対する WebAPI 送信の事前判定(fail-closed)であり、RATING 出力の派生ではない。したがって、射影は RATING ステージが選択されているかではなく、画像のレーティング状態と送信可否から事前検査の要否を判断する。TAGS、CAPTION、SCORE のみを要求し、かつ未評価画像が含まれる場合でも事前検査を省略してはならない。
- **事前検査のモデルは射影が `openai/omni-moderation-latest` を自動解決する**: 事前検査ジョブのモデルはユーザーの選択モデル集合には含まれない。未評価画像があり、選択モデルが通常のアノテーションモデルだけでも、射影は登録済みの omni-moderation の `Model` 行を解決または新規登録し、`rating_preflight` の投入を合成する。これを契約に含めないと、モデレーションジョブが生成されない、あるいは `_validate_submit_task` が `openai/omni-moderation-*` 必須条件で拒否する事態になる。ただし、ADR 0070 の 30 行目は Provider Batch の自動 2 段オーケストレーションを対象外としているため、本 ADR では契約(`model_id` の同伴と送信ゲート由来の判定)のみを定義し、自動 2 段実行の実装は ADR 0070 の先送り方針を引き継ぐ後続タスクとする(一括事前検査用の手動 `rating_preflight` タスクは §3 のとおり CLI に残す)。

#### コスト可視化と事前検査の課金について

ADR 0041 が却下したのは「暗黙の複数ジョブ展開と隠れたコスト増」である。本設計では、送信前に `INFERENCE LEDGER`(ADR 0075)で全ジョブと総推論回数をプレビューするため、コストが暗黙に増える状況を作らない。ADR 0041 の意図を満たしたまま、選択方式を「手動の単一選択」から「集合の射影と事前プレビュー」へ置き換える。

なお、モデレーション事前検査自体はコスト中立である。OpenAI の `omni-moderation` は Moderation API 経由で無料提供されており(課金はなく、制約は利用ティアに応じたレート制限のみ。参照: [OpenAI Help Center](https://help.openai.com/en/articles/4936833-is-the-moderation-endpoint-free-to-use) および [OpenAI announcement](https://openai.com/index/upgrading-the-moderation-api-with-our-new-multimodal-moderation-model/))、未評価画像へ送信ゲートを自動挿入しても課金は発生しない。ADR 0041 がコスト面で懸念した複数ジョブ展開はアノテーション推論側の問題であり、無料の事前検査挿入とは別軸である。

### 3. 第 2 ピッカーの撤去と状態マネージャへの引き上げ

- **Jobs 側の Submit パネルを丸ごと撤去する**: `provider_batch_job_widget.py` から、単一選択の `ModelSelectionWidget` と Submit 導線だけでなく、投入専用に存在するステージング・対象選択コントロール(`StagingWidget`、`buttonAddSelected` 等)も撤去する。これらは `submit_job` にしか使われないため、監視専用台帳に構成用コントロールを残さない。ステージング集合の SSoT は `StagingStateManager`(ADR 0074)であり、対象選択 UI は Annotate と Search 側にすでに存在する。
- **`rating_preflight` を GUI の手動操作にしない**: `rating_preflight` は、レーティング情報がない画像を WebAPI へ送信してよいか確認する自動の安全チェック(ADR 0070、fail-closed)である。ユーザーがコンボボックスで選んで投入する機能ではない。現行の `ProviderBatchJobWidget` がタスク種別コンボボックスに `rating_preflight` を出しているのは、内部の安全機構を誤って操作面へ露出した状態である。Jobs の Submit 撤去に合わせてこの露出も取り除き、Annotate 側にも手動の事前検査作成口は設けない。一括事前検査や監査用途の `rating_preflight` はすでに CLI(`lorairo-cli batch submit --task-type rating_preflight`)にあり、ADR 0070 が定める手動タスクの要件は CLI 経路で満たす。
- **モデル選択状態を `gui/state/` へ引き上げる**: #884 の対応として、ADR 0074 の `StagingStateManager` に倣い、モデル選択状態を `gui/state/` へ移す。正準データは選択モデル集合とし、Annotate はそれを購読する唯一のビュー、Jobs は購読しない監視専用とする。これは ADR 0075 の「SSoT = 選択モデル集合」の**所在**を `ModelSelectionWidget` のチェックボックス状態から `gui/state/` の選択状態マネージャへ移す改定であり、ADR 0075 を改定対象に含める(本 ADR の Accepted 昇格と同一コミットで逆参照を適用した)。
- **バッチ対応判定の SSoT を再利用する**: バッチ対応フィルタ判定の SSoT は、Qt 非依存サービス `lorairo.services.provider_batch_capability`(`direct_provider_for_model`、`model_supports_task_type`、`endpoint_for_task`、`litellm_id_from_batch_model`)である。両 GUI ウィジェットはすでにこれをインポートしている。送信射影レイヤもこの Qt 非依存ヘルパーを再利用し、`ModelSelectionWidget` の Qt 依存メソッドへの依存や判定ロジックの再実装を避ける。これにより、OpenAI アノテーションやモデレーション除外などのプロバイダ・タスク規約の乖離を防ぐ。
- **バッチ適格性はライブラリ検出結果とヘルパー判定の積集合で決める**: `provider_batch_capability` のヘルパーはプロバイダとタスクのルールのみを検査するため、単独ではバッチ適格性を保証できない。現行ピッカーは、まず `model_source.list_batch_capable_models()`(`image-annotator-lib` のモデル検出機能、ADR 0038 におけるバッチ適格性の SSoT)で候補を列挙し、そのうえでヘルパーを適用している。射影でも同様に、選択モデルと `list_batch_capable_models()` の結果の積集合を取ってからヘルパーを適用する。これを怠ると、ライブラリ検出が意図的に除外した OpenAI や Anthropic の直接モデルを誤って投入してしまう。

## ADR 0041 / 0066 / 0075 への影響

- **ADR 0041**: §1 統一レイアウトの「右上に単一選択ピッカー + Submit」条項の配置先を変更する。ステージングを共通対象集合とする点(ADR 0074)と「1 submit = 1 model」の不変条件は変わらない。変更されるのは Submit の**置き場**が Jobs タブから Annotate の送信射影へ移る点のみである。
- **ADR 0066**: 「Jobs = ライフサイクル台帳」という定義は不変である。本 ADR は「Jobs は作成(Submit)の入口を持たない」ことを明文化し、Submit 面の所在を Annotate に確定する追補となる。ライフサイクル・復旧操作(状態を確認、キャンセル、`fetch`、`import`)やキューの実行規約(GPU 直列、API 並列)は維持する。
- **ADR 0075**: 「SSoT = 選択モデル集合」という定義は不変である。ただし、SSoT の**所在**を `ModelSelectionWidget` のチェックボックス状態から `gui/state/` の選択状態マネージャへ移す改定を行う(#884 の状態引き上げ)。これを明示しないと、2 つの確定済み記述が競合し、実装時に状態引き上げを見落とす恐れがある。

上記 3 件の ADR はいずれも Status を Accepted のまま維持し、責務と所在の記述のみを更新する。確定済み ADR(0041、0066、0075)本体への逆参照は本 ADR の Accepted 昇格コミットで適用した(ADR 0060 の前例に倣い、Proposed の間は編集しなかった)。あわせて `make adr-index` を実行し、0076 を Accepted として含む索引を再生成する。

## Rationale

### 1. 設定を Annotate に一本化する理由(縦割り維持を採らない理由)

同期実行を Annotate で完結させ、非同期実行を Jobs で完結させる縦割り構造を維持すると、二重ピッカー、二重状態、および #884 の不具合を「仕様」として永続化することになる。これは ADR 0066 の「Jobs is the ledger」という原則を自ら覆す結果となる。

設定を Annotate に一本化すれば、v12 の 2 本の柱(ステージングを共通対象の SSoT とする、Jobs を台帳とする)と完全に整合し、「構成は Annotate、監視は Jobs」と一文で説明できる。

### 2. 双方向同期ではなく第 2 ピッカーを撤去する理由

複数選択(パイプライン用)と単一選択(バッチ用)を双方向同期させると、一方の意味をもう一方へ翻訳し続ける必要が生じ、UX 上のノイズが残る。

選択モデル集合から非同期バッチへの一方向の射影として定義すれば、SSoT は選択モデル集合の 1 つだけになる。Jobs は派生状態すら持つ必要がなくなり、純粋な監視に専念できる。

## Consequences

### 良い点

- モデル選択状態が `gui/state/` の 1 箇所に集約され、#884(選択が反映されない問題)が構造的に解消する。
- 「設定は Annotate、監視は Jobs」と一文で説明でき、役割境界が一意になる。
- サービス層(`submit_images`)は改変せずに済み、射影からのループ呼び出しで実現できる。

### 悪い点・トレードオフ

- ADR 0041 のレイアウト条項の配置先を変更するため、既決事項の暗黙改変を避ける観点から、本 ADR が Accepted になるまで Jobs および Annotate のワイヤーフレーム反映と実装を保留する必要がある。
- 射影レイヤ(実行経路の分割、バッチ対応フィルタ、`rating_preflight` 分岐)という新コンポーネントが必要になる。`gui/state/` の選択状態マネージャと送信を組み立てるサービス層の責務分担は、実装計画で確定する。

### フォローアップ

- `gui/state/` に選択モデル状態マネージャを新設できるか調査する(#884 進め方 2)。
- ワイヤーフレーム v12 へ本決定を反映する。具体的には、Annotate に実行経路バッジ、`INFERENCE LEDGER` に非同期バッチレーンを追加して単一ピッカーを撤去し、Jobs の `.pbatch` を監視専用として「作成入口なし」を明示する。
- #874 の Jobs スコープに本決定を反映する(#884 が #874 着手の前提となる)。
