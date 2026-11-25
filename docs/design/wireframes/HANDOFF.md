# LoRAIro Wireframes — 引き継ぎメモ

最新ファイルは `LoRAIro Wireframes v13.html` である。v1〜v12 は参照用の履歴として残置しており、次の作業は v13 を上書き更新してよい。

---

## 更新履歴(v11〜v13)

### v13 追記(大規模リファクタ反映:検索/export 分離 #698・Project DB 第一級化)

GUI ワイヤーフレームは概ね据え置きとし、変更は Frame 8・CLI および Map・各タブの実装同期に集中した。

#### 検索責務の分離(#698)
- `export create` からインラインフィルタ(`--tags` など)を撤去し、`--image-ids` を必須とした。
- 検索責務は新しい read-only コマンド `images search`(JSON 検索スキーマを受け取り、`image_id` と `file_path` の JSONL を返す)へ移譲した。
- `images` 群は 3 件から 4 件へ、総サブコマンド数は 17 件から 18 件へ更新した(proj バー、command reference ヘッダ、`list-commands` の `count:18` に反映済み)。
- command reference の export 群を「`image_ids` からデータセット書き出し(`--image-ids` 必須、検索は `images search`、全件 export 不可、ADR 0019)」へ更新し、images 群に `search new` 行を追加した。
- introspection の `list-commands` サンプルに `images search`(`read_only:true`)を追加した。
- agent driving flow を 4 ステップから 5 ステップへ拡張した。
  - ④ `images search -p … --query '{…}' --json > ids.json`(read-only。`total>500` の場合は `RESULT_SET_TOO_LARGE` で exit 2 を返すため、条件を絞るか `limit`/`offset` で分割する)
  - ⑤ `export create --image-ids $(jq … ids.json) -o ./dataset`(`--image-ids` 未指定は `VALIDATION_FAILED` で exit 2)
- CLI frame notes に緑の `v13 REFACTOR ✓` ノートで要約を記載し、contract band に `#698 検索/export 分離` の ADR チップを追加した。

#### Project DB 正規化と `lorairo_data/` 統一(ADR 0017 / 0018)
- v12 時点で Frame 1 ヘッダの `Project.name` セレクタ、`path:"lorairo_data/shiba_v3"`、schema map の Project 行へ反映済みである。GUI と CLI による同一プロジェクト共有が成立しているため、v13 での追加変更はない。
- 参照ソース: `src/lorairo/cli/commands/{export,images,project}.py`、`database/filter_criteria.py`(`ImageSearchQuery`、`ImageFilterCriteria.image_ids` の exact-set selector)、ADR 0017 / 0018 / 0019 / 0055、`CHANGELOG [Unreleased]`。

#### Frame 2・Map の全面作り直し(ユーザ指摘 2 回)
- Map の実装実態は `TagCloudWidget`(`src/lorairo/gui/widgets/tag_cloud_widget.py` および `services/tag_cloud_service.py`)である。
- 機能はキーワード連動の共起タグ探索であり、force-directed ネットワーク図とタグクラウドの 2 モードを持つ。ノードクリックで AND ドリルダウンを行う探索専用画面(ステージング導線なし)であり、元デザインは本リポジトリの `Map Tab.html` を PySide6 + QPainter で再現したものである。**散布図ではない**。
- 実装に存在しない前提だった旧 Frame 2(タグ頻度 2D 散布図、クラスタリスト、規模 3 段、投げ縄、外れ値、Stage/Search 受け渡し)は撤去した。
- 代わりに `Map Tab.html` のライブ canvas 力学グラフを `#frame-map` スコープへ移植した(id を `m2-*` に改名し、root スコープ `$` と ResizeObserver により proto モードの遅延表示へ対応)。CSS は `#frame-map .m2-*` で全スコープ化し、frame-notes も実装準拠(`STATUS=実装済み ✓`)へ書き換えた。
- ⚠ **実装側の要修正点**: `MainWindow.ui` および `MainWindow_ui.py` の `labelMapStub` に、旧プレースホルダ文言「マップビューは未実装です…embedding 散布図を予定(Phase 8)」が残存しており実態と乖離しているため削除すべきである。

#### GUI 全タブの実装状況再監査と最新実装判断の反映
- 古い `.ui` 生成物である `MainWindow_ui.py` は 6 タブ+スタブ構成だが、実体では `gui/window/main_window.py` が `gui/tab/*` の専用ウィジェットをコードで挿入し、各 `_setup_*_tab` が旧スタブ(`labelMapStub`、`labelResultsStub`)を実行時に除去している。
- つまり **8 タブすべてが実装済み** であり、ワイヤーフレームは実装が追従した設計元として概ね正確であった(前ターンの「Results は stub」という記述は誤りであり撤回する)。
  - Search = `SearchTabWidget`(#869)
  - Map = `MapTabWidget` → `TagCloudWidget`
  - Annotate = `AnnotateTabWidget`(#868・#863)
  - Jobs = `JobsTabWidget`(#867・#874)
  - Results = `ResultsTabWidget`(#870)
  - Errors = `ErrorsTabWidget`(#871)
  - Export = `ExportTabWidget`(#872)
  - CLI = `CliTabWidget`(#8)
- ナビゲーション順「検索/マップ/アノテーション/ジョブ/結果/エラー/エクスポート/CLI」と `Ctrl+1..8` はワイヤーフレームと一致している。
- 実装が先行していた以下の 4 つの設計判断についても、ユーザ承認のうえすべて実装準拠でワイヤーフレームへ反映済みである。
  1. **ADR 0074 `StagingStateManager`(ステージング集合の SSoT)**: Annotate / Jobs / Export / Search で共有し、`staged_images_changed` から `set_image_ids` でライブ同期する。Frame 3A の staged-set に `StagingStateManager · ADR 0074` を明記し、Frame 7 Export の proj も同表記へ更新した。
  2. **ADR 0076 `ModelSelectionStateManager` SSoT(#884)とジョブ作成入口の Annotate 移管**: Jobs は監視・取消・台帳・batch import 専用とした(ADR 0076 §3)。Frame 4 Jobs に緑の STATUS(監視専用、`ProviderBatchJobWidget`+同期台帳 ADR 0066+batch import、作成入口は Annotate、進捗ポップアップ廃止に伴いキャンセルは行ボタン ADR 0066 §4)を明記した。
  3. **#863 Annotate の 1 カラム化**: 旧 3 カラムの per-image エディタ(staged 一覧+画像 canvas+Tags / Caption / Score / Rating 詳細)を撤去した。実装上、per-image 編集は Annotate になく Search 詳細パネル(`SelectedImageDetailsWidget`)と Results(`ResultsWidget`)にあるためである。代わりに実装どおり staged-set ペイン(`BatchTagAddWidget`=staged サムネ列+一括タグ追加+per-image は Search/Results へ誘導)を配置した。上部の `.pipe-wrap`(パイプライン構成、preset、送信前プリフライト、推論台帳、run bar → Jobs)は実装とほぼ一致しているため維持し、title / proj / 緑 STATUS 帯を更新した。
  4. **#869 Search の 3 ペイン splitter**: Frame 1 に緑の STATUS(`SearchTabWidget` #869、facet サイドバー+サムネグリッド+プレビュー/詳細 `SelectedImageDetailsWidget` の 3 ペイン splitter、staging SSoT 共有)を注記で明示した。既存レイアウトが実装と近かったため再レイアウトは行っていない。
- 参照: `gui/window/main_window.py`(`_setup_*_tab` による旧スタブ除去と `gui/tab/*` 挿入)、`gui/tab/{annotate,jobs}_tab.py`、ADR 0074 / 0076 / 0066。

---

### v12 追記(レビュー指摘への構造対応)

外部レビュー 10 点のうち、核心を突く 3 点を反映した。設計メモの最上段に `.crit-band`(#1 / #3 / #9 の指摘・対応・反映先)と #9 の翻訳ストリップを追加している。

- **#1 タブ vs 線形フロー**: 全フレームの topnav を JS(proto controller 内の `restructureNav()`、CLI 注入と同様に DRY 実装)で再構成した。番号付きパイプライン・レール(Search → Annotate → Jobs → Results → Export を矢印で連結)とツール棚(Map・Errors・CLI)に分け、CSS に `.nav-rail` / `.flowsep` / `.navdiv` / `.nav-util` を追加した。レール内の ⌘ ヒントは円番号と重複するため非表示とした。自動遷移は「レールを前へ進むだけ」であり視覚表現と一致する。
- **#3 監査の非対称性**: Frame 5 Results の issues-band と res-toolbar の間に `.clean-audit` バンドを追加した。auto-pass した clean をランダム抽出して確認後に accept する流れと、strictest-wins で破棄した緩い票の開示を盛り込んだ。Frame 9 の `RESULTS@9k` カードにも clean サンプリング行を追加し、OPEN の「自動 accept」は v12 注記で「clean は抜き取り監査必須」へ再フレームした(v12.1 で実運用可能な仕組みとして完成)。
- **#9 data-major**: 全面再設計は行わず、「決定単位を主・schema を従」とする原則を設計メモに明文化し、翻訳ストリップで 4 例を提示した。facet 実体の再設計(特に 9k 操作モデル)は継続課題とする。
- レビューで「既決/前提が弱い」と判断した項目(#8 進捗ポップアップ、#5 派生チップの opt-out、#4 save query など)は意図的に未対応とした(理由はチャット参照)。

---

### v12.1 追記(CLEAN 抜き取り監査の運用可能化)

`.clean-audit` を実運用できる仕組みへ仕上げた。新規タブや新規フレームは作らず、Frame 5 と Frame 9 の範囲内で完結させている。CSS はすべて `.clean-audit` / `.ca-edge` プレフィックスでスコープ化した。

- **抽出枚数(母数連動)**: 規則は 1 つに統一し、母数に応じて見せ方を変える。`≤20` は全数、`21–500` は `⌈√n⌉`、`>500` は上限 30 件とする。バンド冒頭に `.ca-rule` でルールを明示し、該当段を `.rl.on` でハイライトする。
- **スコープ**: `batch` 固定とする(project / global 横断は YAGNI のため実装しない。v12.3 確定)。
- **抽出方式**: 単純ランダムではなく `tier×rating` 層化抽出とし、端ティアや高 rating を必ず含める。
- **NG 導線(最重要)**: 各サンプルに ✓ / ✕ を配置する。✕ を押すと `.ca-bad` パネルが開き、①サンプル群を flagged に戻す、②Annotate で再タグする、③clean の一括 accept を取り消す、の 3 択を提供する。これにより「見るだけ」に終わらず監査として閉じる。
- **来歴記録**: `.prov` 帯に who / when / checked N/clean / accept M を描画する。schema には `review_log(id, reviewed_at, reviewer, sampled_ids[JSON], accepted_count, batch_ref)` を追加する(v12.3 確定、`.src` に注記済み)。
- **strictest-wins 破棄票**: 開示は維持するが、緩い側への一括 revert は不可とする(canonical は保守側固定、#626 / PR 642)。個別に緩める場合は Annotate の手動上書き(`is_edited_manually`)で行う。
- **端状態**: Frame 9 に `CLEAN 監査 · 端状態` stcard を追加し、clean 0(バンドを出さない)、clean 1(抜き取り不要・re-sample 無効)、小母数 `n≤20`(全数)の 3 パターンを定義した。
- **設計メモ更新**: OPEN に「CLEAN 抜き取りの枚数・スコープ・方式」を `✓ DECIDED` 行として追加した。残 OPEN はない(抽出スコープ・一括 revert・`review_log` スキーマは v12.3 で確定)。

---

### v12.2 追記(Frame 6・Export の ADR 0068 整合)

既存の Export フレームを実装挙動に合わせて更新した(新規タブ・派生なし、`data-screen-label="06 Export"`、nav レール終点)。CSS は `#frame-export` でスコープ化している。

- **母集団**: staging set(有界 MAX 500、可視、名前付き)とする。target banner にフィルタ必須・全件 export 不可(ADR 0019)を明示した。フィルタ結果は直接 export せず、「ステージングへ投入」を経て対象化する。
- **出力 format**: `txt 分離`(`.txt` + `.caption`)、`txt 結合`、`json`(`metadata.json`)の 3 種とする。kohya / sd-scripts の旧表記は実装に合わせて撤去した。
- **target タグ format(新)**: `danbooru`(既定)、`e621`、`pony` から選択する。保存時は danbooru canonical で固定し、export 時に `convert_tags(format)` で alias → preferred 解決と `type=meta` 除外を行う(ADR 0068)。
- **変換プレビュー(新・核)**: サンプルに対して「保存値(danbooru canonical)→ 選択 format 変換後」を before / after の 2 カラムで表示する。橙色で alias 解決、赤取消線で meta 除外を可視化し、実際に書き出される集合を確定させる。
- **解像度フィルタ(新)と changed-since**: 解像度フィルタは「原寸」「長辺 1024 縮小」「768 未満除外」を設けた。changed-since は既存どおりダイアログの post-filter とし永続化しない。
- **NSFW exact-set bypass と出力操作**: 明示的にステージングした NSFW を黙って落とさない挙動を維持する。出力先パスと実行ボタンを配置し、foot に `export_with_criteria(..., tag_format="e621")` を明示した。
- **discontinued モデルの過去タグ**: `keep + warning` を採用する(v12.3 確定)。export に含めて provenance を保持し、「discontinued 由来 N 件」と注記する(exclude および silent は不採用)。
- **残 OPEN**: 変換プレビューのサンプル枚数のみである。

---

### v12.3 追記(6 件の OPEN を DECIDED 化)

文言と帯のみを更新した(新規 CSS・再設計なし)。

1. **CLEAN 抜き取りスコープ**: `batch` 固定(project / global は YAGNI で不実装)。
2. **strictest-wins 緩い側への一括 revert**: 不可(canonical は保守側固定、個別のみ Annotate で手動上書き)。
3. **`review_log` スキーマ**: `review_log(id, reviewed_at, reviewer, sampled_ids[JSON], accepted_count, batch_ref)` に確定。
4. **save query**: 既定は snapshot(`image_id` 凍結による再現性重視)、明示操作で live(再評価)とする。Frame 1 OPEN を RESOLVED 化した。
5. **discontinued モデルの Export 扱い**: `keep + warning`(provenance 保持+N 件注記)。Frame 6 および設計メモの OPEN を RESOLVED 化した。
6. **issue → query 変換**: issue type ごとの固定 facet 写像とする(`EMPTY_TAGS` / `NO_SCORE` / `RATING_DISAGREEMENT` / `SCORER_DISAGREEMENT` / `UNKNOWN_TIER` → 各 facet)。Frame 9 OPEN を RESOLVED 化した。

---

### v11 追記(CLI 大改装 #634 対応)

agent-friendly CLI 契約を図解する **Frame 8・CLI** を追加した(詳細は末尾「Frame 8・CLI」節を参照)。ナビゲーションは `Search⌘1 / Map⌘2 / Annotate⌘3 / Jobs⌘4 / Results⌘5 / Errors⌘6 / Export⌘7 / CLI⌘8` となった。

---

## プロジェクト概要

LoRA 学習用の画像素材データセット管理ツール `LoRAIro` の UI ワイヤーフレームである。`schema.py` のデータモデルに沿って画面を構成し、紙+手書き調の low-fi スタイルで提案している。

### スタイル
- **フォント**: `Kalam`(手書き)および `JetBrains Mono`
- **カラー**: `--ink #1a1a1a`、`--paper #fbfaf6`、暖色アクセント `--accent oklch(0.62 0.14 32)`
- **影と枠線**: `3px 3px 0 var(--rule)` の hard shadow を用い、`2px solid` の border で枠を切る。

### スキーマ(`schema.py` 由来)の主要モデル
- `Image`(`width`, `height`, `format`[webp 固定], `has_alpha`, `uuid`, `phash`, `created_at`)
- `ProcessedImage`(`upscaler_used`)
- `Tag`(`image_id`, `tag`, `model_id`, `confidence_score`, `existing`, `is_edited_manually`)
- `Caption`(`image_id`, `model_id`, `text`, `existing`, `is_edited_manually`)
- `Score`(`image_id`, `model_id`, `score`, `is_edited_manually`)
- `Rating`(`image_id`, `normalized_rating ∈ PG/PG-13/R/X/XXX`, `confidence_score`)
- `Model`(`name`, `type ∈ multimodal/tagger/scorer/rater/upscaler`, `requires_api_key`, `estimated_size_gb`, `discontinued_at`)
- `ErrorRecord`(`operation_type`, `error_type`, `error_message`, `image_id`, `model`, `retry_count`, `resolved_at`, `stack_trace`)
- `Project`、`ImageFilenameAlias` など

---

## i18n 規約(v10 で導入)

- `<body data-lang="ja|en">` と CSS を組み合わせて排他表示する。
- 3 語以上の英文は `<span class="tx-ja">…</span><span class="tx-en">…</span>` のペアで両言語を持たせる。
- 2 語以下の識別子、schema 参照、コード、モデル名は英語のまま固定する。
- Tweaks パネルの `Language` セグメントで切り替えられ、選択状態は保存される。

---

## 確定済み設計判断

### 実行 UI の A/B — B(独立 Jobs タブ)で決着(2026-06-11)
- **決定**: 実行 UI は **B: 独立 Jobs タブ** を採用する。現実装の進捗ポップアップ(A)は廃止予定の暫定実装として移行期のみ併存させる。
- **理由**: Provider Batch は実装上すでにタブ(`provider_batch_job_widget.py`)であり、「同期だけポップアップ」という分断を解消する必要がある。また、「Job 完了 ⇢ auto Results、issue は紅バッジ」という中核フローを成立させるには、履歴・並行ジョブ・完了後導線を置く常設タブが不可欠である。
- **反映済み(v11)**: FLOW 図と Annotate の実行ボタンに「Jobs タブへ自動スイッチ」を明記した。REJECTED に「実行ポップアップ維持(A 案)」を追加し、Frame 3 に DECIDED ノートを配置した。履歴には CANCELED 行と ADR 0034 の terminal 語彙(`FAILED` / `CANCELED` / `TERMINATED` / `UNRESPONSIVE`)の凡例を追加した。
- **検証**: 操作プロトタイプ `Jobs Flow Prototype.html`(Tweaks で A / B / B' 切替)でユーザから「違和感なし」の確認を得た。完了時の auto-Results とバッジのみの選択、Jobs の情報密度(standard vs focus)といった未決の微調整は、プロトタイプの Tweaks で引き続き比較できる。
- **規模前提**: 同期ジョブの母集団はステージング集合(上限 500)とする。

### Import / 重複検出フロー — 専用画面は不要として取り下げ(2026-06-11)
- 登録ロジック側(#633 / ADR 0061 §4 の統一登録エントリおよび `registration_worker.py`)が pHash を用いて、重複(自動 skip+`ImageFilenameAlias` 自動記録)、別版(variant 登録)、新規を全自動で分類する。したがって手動の重複解決 UI は不要である。
- これは chat3 で Errors から重複エラー行を削除した判断とも整合する。
- 残っていた UX ギャップ(登録結果が statusBar に 5 秒表示されて消える問題)は、v11 の Frame 1(Search の qbar 上)に **「登録完了サマリ」パネル** を配置して解消した。独立 frame にはせず、registered / variant / skipped / errors の件数と、skip / variant 行から「同一と判定された既存画像」へのリンクを表示し、✕ で閉じるまで残す。

### 規模対応と空状態 — FRAME 9・STATES として描画(2026-06-11)
- 設計メモの「500 で仮想スクロール、9k で per-row 非表示」を、カード 6 枚の状態カタログフレームとして実体化した(数字キー `9`、`data-screen-label="09 States"`)。
  1. **Search 0 hit**: トークン別 hit 数で矛盾を診断し、「どれを外せば何件」を提示する(NLQ タイムアウトも同じ場所に表示する)。
  2. **Results 未実行**: 次のアクションへの案内板を表示する。
  3. **Results 0 issues**: clean であることを示し、Export へ素通りさせる。
  4. **Jobs 空**: 履歴テーブルは消さずに残す。
  5. **Results@500**: 仮想スクロールを用い、同種 issue を 1 カードに集約する(ページングなし)。
  6. **Results@9k**: per-row を非描画として patterns のみを表示し、pattern から Search へ絞り込みを受け渡す。
- **DECIDED(v12.3)**: issue → query 変換は issue type ごとの固定 facet 写像(`EMPTY_TAGS` / `NO_SCORE` / `RATING_DISAGREEMENT` / `SCORER_DISAGREEMENT` / `UNKNOWN_TIER` → 各 facet)とし、pattern クリックで Search に適用する。

### `rejected_at` はターゲット非依存の正誤判断のみ(2026-06-11)
- `rejected_at` は「この画像に対してこのタグは誤りである」というターゲット非依存の正誤判断のみを表す。
- Danbooru 系や Pony 系などターゲットごとの語彙差は右パネルの採用操作では扱わず、タグ DB(`genai-tag-db-tools`)の format/エイリアス変換と Export 側のターゲット別規則(Export frame の責務)で解決する。
- そのため、**Annotate 右パネルに「ターゲット別の採用切替」のような UI は描かないこと**。
- Export frame の frame-notes には「出力 format(danbooru / e621 / pony 等)の選択と変換プレビューの余地」を FORMAT ノートとして記録済みである。

### 不要なフィルタ
- **画像拡張子フィルタ**: DB 登録時に webp に統一済みのため削除した。
- **`has_alpha` フィルタ**: α 背景でも特別仕様がないため削除済みである。
- **format / `has_alpha` 系のメタ表示**: サムネメタからも撤去し、`width × height` のみにした。

### モデル × ステージの設計(重要)
v10 の核心として、Frame 2(Annotate)のモデル実行 UX を再設計した。

- **ステージ中心**: `TAGS / CAPTION / SCORE / RATING / UPSCALE` の 5 ステージは、schema の出力テーブル(`Tag` / `Caption` / `Score` / `Rating` / `ProcessedImage`)に対応する。
- **マルチモーダルモデルの扱い**: 1 推論で得られる出力はすべて自動保存する。
  - 例として、`gpt-4o-caption` を CAPTION ステージに置くと、副産物の tag と rating も同時取得して保存される。
  - 副産物側のステージ(TAGS / RATING)には `↝ shadow chip`(破線+斜体)で「自動取得される」ことを視覚表示する。
  - ピッカーの sub には「`1推論で tags + caption + rating 取得`」と明記する。
  - `llava-next` と `qwen-vl-chat` は rating 出力を持たないため、`tags + caption` のみとなる。
- **ジョブ数表示**: マルチモーダルは 1 推論として数え、「N モデル × M 枚」ではなく「N 推論 × M 枚」と表記する。

### モデルピッカー(Frame 2B)
- **左レール**: `Model.type`、Provider、Availability、Capabilities で構成する。
- **メイン**: 検索とソートを備え、行ごとに `name · type · status · size/cost · 信頼度閾値スライダ` を表示する。
- **ステータス**: `● installed`、`● API ready`、`○ needs key`、`○ discontinued` の 4 種を使う。
- **`discontinued_at` モデル**: 履歴目的で消さず、取り消し線+disabled 状態で残す。
- **プリセット**: Default、Tags only、Full caption、Score · rate、Multimodal only などを備える。

### Search サイドバー(Frame 1)
- **DATE フィルタ**: chip から「20 本ヒストグラム+範囲スライダ+プリセット chip」へアップグレードした。
- **annotations state**: `is_edited_manually` を tag / caption / score 統合の「手動編集あり」フィルタとし、その下に内訳を表示する。
- **model filter**: 検索ボックス、📌 ピン留め、「最近使用」、「他 N 個を表示」の展開を備え、0 使用モデルは折りたたむ。
- **error state**: `all` / `エラーありのみ` / `エラーを除外` の 3 択 chip とする。

### Jobs と Errors の分離(v10 後半)
- ~~旧 Frame 3(JOBS / ERRORS 合体)~~ を **Frame 3・JOBS** と **Frame 4・ERRORS** へ分離した。
- ナビゲーションは `Search⌘1 / Map⌘2 / Annotate⌘3 / Jobs⌘4 / Errors⌘5 / Export⌘6` とした(v11 で Results / CLI を追加)。

#### Frame 3・JOBS
- **性質**: ライフサイクル管理(実行中 / キュー / 履歴)。
- **サマリ**: 実行中、キュー、過去 7 日完了、API 使用状況(rate)。
- **Running カード**: ステージ × モデルの進捗バーを表示する。rate 待機は縞模様で表し、Pause / Cancel を備える。
- **Queue**: 並び替えと推定時間の表示を行う。
- **History**: テーブルで一覧し、失敗行から `→ Errors` でトリアージへ遷移する。

#### Frame 4・ERRORS
- **性質**: 失敗のトリアージ。
- **サマリ**: 未解決、24h、解決済、`error_type` 別の件数を表示する。
- **クロスフィルタ**: status × operation × model × time で絞り込む。
- **表示モード**: デフォルトは同一原因を集約するグルーピング表示とし、個別行モードへも切り替えられる。
- **各グループ**: 件数、エラーメッセージ+バッジ、影響画像リンク、retry 可/上限到達、過去 7 日スパークライン、状況別アクション(retry / resolve / ignore / 再インポート)を表示する。
- **下部一括操作**: 「retry 可をすべて再実行」「選択を無視」を配置する。

---

## 未着手 / 検討中

### 次の優先課題(ユーザ承認済み)

#### 1. Frame 5・RESULTS(アノテーション品質トリアージ)
- **目的**: 画像素材の確認ではなく、**アノテーションの品質チェック** を行う画面である(明確化済み)。
- **規模想定**: 1 バッチは少数(〜10 枚程度)を想定する。
- **構成方針**:
  1. **品質問題を最上段に集約**: issue カードには閾値不要で客観的な構造的問題のみを載せる(空タグ、no-score、unknown tier、rating 不一致、scorer 不一致)。低信頼度タグ(`conf<0.40`)や短すぎるキャプション(`<8語`)は issue 化しない(2026-06-11 確定・inline comment)。conf 値や語数は行に表示済みで目視確認でき、恣意的な線引きは説明できないためである。これにより config 閾値・スコープ・状態管理を丸ごと削減できる。
  2. **画像単位の要約リスト**: サムネとアノテーション一式の要約を並べ、`▸ レビュー` から Annotate へ直行できるようにする。
  3. **アクション**: 1 件ごとの accept / edit / reject に加え、一括の「問題なければ承認」を備える。
- CSS は追加済み(`.res-summary`、`.issues-band`、`.issue-card`、`.res-row`、`.res-foot`)であり、残りは Frame 4 の後ろへ HTML 本体を追加する作業のみである。

### 残作業(優先順)
1. **Frame 5・RESULTS の HTML 実装**(CSS 準備済み)。
2. **Frame 2 右側パネル(Tag / Caption / Score / Rating 詳細)の整理**:
   - マルチモーダル対応に伴い、モデル別グルーピングと採用ワークフローの補強が必要である。
   - 「このモデルの tag を全採用」や「競合解決」の UI を検討する。
   - **制約**: 採用操作はターゲット非依存(`rejected_at` は正誤判断のみ)とし、ターゲット別の採用切替 UI は描かない(確定済み設計判断を参照)。
3. **Settings / API key 設定 / Model installer** — ✅ v11 で **Frame 2C・SETTINGS(独立ウィンドウ)** として実装済み(2026-06-11)。
   - `needs key` は「可視+その場で解消」に統一した。Frame 2B の `needs key` chip をクリックすると Settings の該当プロバイダ欄がハイライト表示され、保存後に `● API ready` へ切り替わる。現行実装の「キー未設定モデルを非表示」仕様は、このワイヤーフレームを正として改める予定である。
   - 9 個目のタブにはせず、現実装どおりタイトルバーの `⚙` から開く独立ウィンドウ(`ConfigurationWindow`)とした。構成は API keys(マスク表示・表示切替なし・保存済みかのみ判別可能、`config/lorairo.toml` の `[api]`)、モデル経路(`auto` / `direct` / `openrouter`、`"all"` は CLI 専用)、installer の最小構成である。
   - **Model installer(新設)**: 初回推論時の暗黙的な HuggingFace ダウンロードを明示的な install ジョブへ切り出した。`estimated_size_gb` の表示、Jobs lifecycle への進捗統合(中止は `CANCELED`、ADR 0034)、uninstall、容量合計を備える。未 install モデルをパイプラインに置くと install ジョブが自動先行する。
   - `discontinued` は現状どおり取り消し線+disabled を維持する。
4. **Map タブ**: 中身は未設計であり優先度は低い(なお Export は v12.2 で実装済み、Map も v13 で実装準拠へ更新済み)。

~~Import / 重複検出フロー~~ — pHash による全自動分類が実装済みのため取り下げた。代替となる「登録完了サマリ」は Frame 1 に描画済みである(確定済み設計判断を参照)。

---

## ファイル構成

```
Wireframes.html         初版
Wireframes v2〜 v10.html  履歴
Wireframes v11.html     ← 最新作業対象 (CLI frame 追加・Jobs A/B 決着反映済)
Jobs Flow Prototype.html  操作プロト (A/B/B' 切替・proto/ 以下に JSX)
HANDOFF.md              ← 本ファイル
```

---

## Frame 8・CLI(agent-friendly CLI 契約 / issue #634)

GUI とは別の **第二の操作面** として、CLI 契約を図解する frame を追加した。リポジトリの実装(`src/lorairo/cli/`)と `docs/cli.md` を読み込み、実際の出力形式に合わせている。

### 出典(GitHub `NEXTAltair/LoRAIro` から取得して反映)
- ADR 0057(`_emit.py` / `_errors.py` / `_boundary.py`)— JSONL および構造化エラー契約
- ADR 0058(`_output_mode.py`)— `--json` / `--no-json` > env `LORAIRO_CLI_JSON` > 既定 rich
- ADR 0059(`introspection.py`)— `list-commands` / `describe` / `--schema json_schema`
- ADR 0060 — bounded pagination(`limit ≤ 500` / `RESULT_SET_TOO_LARGE`)

### frame の構成(7 バンド)
1. **契約+出力モード解決**: 「既存 CLI に被せた機械可読契約レイヤー」と ADR チップを示す。
2. **stdout=JSONL / stderr=ログ**: 同一コマンドの出力を左右に並べた 2 ペイン端末(中心ビジュアル)。
3. **3 つの kind**: `item`、`result`、`error`。
4. **構造化エラー契約**: error JSONL 例、15 個のエラーコード(共有 11 / AI 3 / pagination 1)、exit コード(0 / 2 / 1)、flags を整理する。
5. **introspection**: `list-commands`(`type:tool`)と `describe`(`type:model` / `schema`)。
6. **bounded pagination**: `count` / `total` / `has_more` と `RESULT_SET_TOO_LARGE`。
7. **agent driving flow**: `project create` → `images register` → `annotate run` → `export create` の流れと、`code` / `has_more` の分岐(v13 で `images search` を含む 5 ステップへ更新)。

### コマンド総覧(reference バンド)
`annotate`(2)、`batch`(6)、`export`(1)、`images`(3)、`models`(2)、`project`(3)に、トップレベルの `version` / `status` / `list-commands` / `describe` を加えた計 17 サブコマンドで構成する(v13 で `images search` 追加により 18 サブコマンドへ更新)。各コマンドに read-only / `side_effect` バッジを付与した。

### スタイル / 実装メモ
- 端末ペインは `#23211d` のダーク背景に JSONL シンタックス色分け(`.j-k` / `.j-s` / `.j-n` / `.j-b`)と kind バッジ(`.kb.item` / `.result` / `.error`)を適用した。
- CSS は既存トークンとの衝突を避けるため、すべて `#frame-cli` プレフィックスでスコープ化した。
- ナビゲーションは 8 箇所の手編集を避けるため、proto controller がすべての `.topnav` へ CLI タブを JS で注入し、`SCREENS.cli`、`NUM2KEY['8']`、`TAB2KEY.CLI` を追加した。
- frame は `.app` 内に配置して他 frame と左 32px 揃えにし、proto-bar のヒントを `1–8` へ更新した。

---

## Tweaks

- `lang: ja | en` — i18n 切替
- `sidebar_collapsed`
- `show_map` — Schema mapping パネル表示
- `show_schema_tags` — `.schema-tag` / `.src` バッジ表示

`/*EDITMODE-BEGIN*/ … /*EDITMODE-END*/` で囲まれた JSON が永続化対象である。

---

## ファイル構成(旧記述・上の最新版を参照)

```
Wireframes.html         初版
Wireframes v2〜v9.html   履歴
Wireframes v10.html     ← 最新作業対象
HANDOFF.md              ← 本ファイル
```

v11 を切るか v10 を継続編集するかは次セッションで判断する方針としていた(小修正は v10 で続行、大規模再構成なら v11 にコピー)。

---

## 直近のユーザ要望

- 画像チェックではなく、アノテーション品質のトリアージ画面が必要である。
- 一度に実行する枚数は多くない(少数バッチ前提)。
- 上記方針に基づき、**Frame 5・RESULTS** として実装するのを次の作業とする。
