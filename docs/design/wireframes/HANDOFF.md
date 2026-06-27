# LoRAIro Wireframes — 引き継ぎメモ

最新ファイル: `wireframes.html`（v13 を統合した現行版。旧 `LoRAIro Wireframes v13.html` 由来）
版管理は git で行う。ディレクトリ別の版（v1〜v13）運用は廃止し、`wireframes.html` を上書き更新する。

> **v13 追記 (大規模リファクタ反映 — 検索/export 分離 #698 + Project DB 第一級化)**: GUI ワイヤーは概ね据え置き、変更は Frame 8 · CLI に集中。
> - **#698 検索責務の分離 (核)**: `export create` から inline フィルタ (`--tags` 等) を撤去し **`--image-ids` 必須**に。検索は新 read-only コマンド **`images search`**（JSON 検索スキーマ → `image_id`/`file_path` の JSONL）へ移譲。`images` 群 3→4、総サブコマンド 17→18 に更新（proj バー・command reference header・list-commands `count:18`）。
>   - command reference: export 群を「image_ids からデータセット書き出し / `--image-ids` 必須・検索は images search・全件 export 不可 (ADR 0019)」に。images 群に `search new` 行を追加。
>   - introspection の list-commands サンプルに `images search` (read_only:true) を追加。
>   - **agent driving flow を 4→5 ステップ化**: ④ `images search -p … --query '{…}' --json > ids.json`（read-only / `total>500` は `RESULT_SET_TOO_LARGE` exit2 → 絞る or limit/offset 分割）→ ⑤ `export create --image-ids $(jq … ids.json) -o ./dataset`（`--image-ids` 未指定は `VALIDATION_FAILED` exit2）。
>   - CLI frame notes に緑 `v13 REFACTOR ✓` ノートで要約。contract band に `#698 検索/export 分離` ADR チップ追加。
> - **ADR 0017/0018 (Project DB 正規化 + `lorairo_data/` 統一)**: v12 時点で Frame 1 ヘッダの `Project.name` セレクタ・`path:"lorairo_data/shiba_v3"`・schema map の Project 行に既に反映済 → v13 で追加変更なし（GUI/CLI 同一プロジェクト共有が成立済）。
> - 参照ソース: `src/lorairo/cli/commands/{export,images,project}.py`・`database/filter_criteria.py`（`ImageSearchQuery` / `ImageFilterCriteria.image_ids` exact-set selector）・ADR 0017/0018/0019/0055・CHANGELOG [Unreleased]。
> - **Frame 2 · Map を実装に合わせ全面作り直し (ユーザ指摘 2 回)**: Map は **実装済み = `TagCloudWidget`**（`src/lorairo/gui/widgets/tag_cloud_widget.py` + `services/tag_cloud_service.py`）。**キーワード連動の共起タグ探索** — force-directed ネットワーク図 / タグクラウドの2モード、ノードクリックで AND ドリルダウン、探索専用（ステージング導線なし）。元デザインは本リポジトリ `Map Tab.html` を PySide6+QPainter で再現したもの。**散布図ではない**。
>   - 旧 Frame 2（タグ頻度 2D 散布 + クラスタリスト + 規模3段 + 投げ縄 + 外れ値 + Stage/Search 受け渡し）は実装に存在しない前提だったため**撤去**し、`Map Tab.html` のライブ canvas 力学グラフを `#frame-map` スコープで移植（id を `m2-*` に改名、root スコープ `$`、ResizeObserver で proto モードの遅延表示に対応）。CSS は `#frame-map .m2-*` で全スコープ。frame-notes も実装準拠に書換（STATUS=実装済み ✓）。
>   - ⚠ **要修正（実装側）**: `MainWindow.ui` / `MainWindow_ui.py` の `labelMapStub` に旧プレースホルダ文言「マップビューは未実装です…embedding 散布図を予定（Phase 8）」が残存 → 実態と乖離。削除すべき。
> - **GUI 全タブの実装状況を再監査（ユーザ指摘「他に取りこぼしは？」）**: `MainWindow_ui.py`（古い .ui 生成）は 6 タブ + スタブだが、**実体は `gui/window/main_window.py` が `gui/tab/*` の専用ウィジェットをコードで挿入**し、各 `_setup_*_tab` が旧スタブ（labelMapStub / labelResultsStub）を実行時に除去している。→ **8 タブすべて実装済み**で、ワイヤーは実装が follow した設計元として概ね正確だった。
>   - 実装済みタブ: Search=`SearchTabWidget`(#869) / Map=`MapTabWidget`→`TagCloudWidget` / Annotate=`AnnotateTabWidget`(#868·#863) / Jobs=`JobsTabWidget`(#867·#874) / Results=`ResultsTabWidget`(#870) / Errors=`ErrorsTabWidget`(#871) / Export=`ExportTabWidget`(#872) / CLI=`CliTabWidget`(#8)。**Results は実装済み**（前ターンの「stub」記述は誤り・撤回）。
>   - ナビ順「検索/マップ/アノテーション/ジョブ/結果/エラー/エクスポート/CLI」+ Ctrl+1..8 はワイヤーと一致。
>   - **ワイヤーに未反映の新しい実装判断（要反映検討・大きめ）**: ① ADR 0074 `StagingStateManager` = ステージング集合の SSoT（Annotate/Jobs/Export/Search 共有・`staged_images_changed`→`set_image_ids` でライブ）② ADR 0076 `ModelSelectionStateManager` SSoT(#884) + **ジョブ作成入口は Annotate へ移管**（Jobs は監視/取消/台帳/batch import のみ・§3）③ #863 Annotate **1カラム化**（ワイヤー Frame 3 は3カラム）④ #869 Search = 3ペイン splitter。これらは未着手 gap ではなく「実装が先行した詳細」。反映可否は要相談。

> **v12 追記 (レビュー指摘への構造対応)**: 外部レビュー10点のうち、芯を食う3点を反映。設計メモ最上段に `.crit-band`（#1/#3/#9 の指摘→対応→反映先）+ #9 翻訳ストリップを追加。
> - **#1 タブ vs 線形フロー**: 全フレームの topnav を JS で**番号付きパイプライン・レール**（Search→Annotate→Jobs→Results→Export·矢印連結）と**ツール棚**（Map·Errors·CLI）に再構成（proto controller 内 `restructureNav()`、CLI 注入と同じく DRY）。CSS: `.nav-rail` / `.flowsep` / `.navdiv` / `.nav-util`。レール内の ⌘ ヒントは円番号と二重になるため非表示。自動遷移は「レールを前へ進むだけ」＝視覚と一致、という主張。
> - **#3 監査の非対称性**: Frame 5 Results に `.clean-audit` バンド追加（issues-band と res-toolbar の間）。auto-pass clean のランダム抽出→確認後 accept + strictest-wins で捨てた緩い票の開示。Frame 9 の RESULTS@9k カードにも clean サンプリング行を追加。OPEN「自動accept」を v12 注記で「clean は抜き取り監査必須」に再フレーム。**→ v12.1 で運用可能な仕組みに完成（下記）。**
> - **#9 data-major**: 全面再設計はせず、**原則を設計メモに明文化**（決定単位を主・schema を従）+ 翻訳ストリップで4例を提示。facet 実体の再設計（特に 9k 操作モデル）は継続課題。
> - レビューで「既決/前提弱い」と判断した点（#8 進捗ポップアップ・#5 派生チップ opt-out・#4 save query 等）は意図的に未対応。理由はチャット参照。

>   - **ワイヤーに未反映の新しい実装判断（要反映検討・大きめ）**: ① ADR 0074 `StagingStateManager` = ステージング集合の SSoT（Annotate/Jobs/Export/Search 共有・`staged_images_changed`→`set_image_ids` でライブ）② ADR 0076 `ModelSelectionStateManager` SSoT(#884) + **ジョブ作成入口は Annotate へ移管**（Jobs は監視/取消/台帳/batch import のみ・§3）③ #863 Annotate **1カラム化**（ワイヤー Frame 3 は3カラム）④ #869 Search = 3ペイン splitter。これらは未着手 gap ではなく「実装が先行した詳細」。反映可否は要相談。
> - **上記 ①〜④ を全て実装準拠に反映済み（ユーザ承認）**:
>   - **③ Annotate (Frame 3A) を1カラム化**: 旧 3カラム per-image エディタ（staged一覧+画像canvas+Tags/Caption/Score/Rating 詳細）を撤去。per-image 編集は実装上 Annotate に無く **Search 詳細パネル（SelectedImageDetailsWidget）/ Results（ResultsWidget）** にあるため。代わりに実装どおり **staged-set ペイン**（BatchTagAddWidget = staged サムネ列 + 一括タグ追加 + per-image はSearch/Resultsへ誘導）を配置。上部の `.pipe-wrap`（パイプライン構成 + preset + 送信前プリフライト + 推論台帳 + run bar→Jobs）は実装とほぼ一致のため維持。title/proj/緑STATUS帯を更新。
>   - **①② staging/model SSoT + Jobs 監視専用**: Frame 3A（staged-set に `StagingStateManager · ADR 0074` 明記）/ Frame 4 Jobs（緑STATUS = 監視専用・ProviderBatchJobWidget + 同期台帳 ADR 0066 + batch import・作成入口は Annotate · ADR 0076 §3・進捗ポップアップ廃止でキャンセルは行ボタン ADR 0066 §4）/ Frame 7 Export（proj を `StagingStateManager · ADR 0074` に更新）。
>   - **④ Search 3ペイン**: Frame 1 に緑STATUS = `SearchTabWidget`(#869)・3ペイン splitter（facet サイドバー + サムネグリッド + プレビュー/詳細 SelectedImageDetailsWidget）・staging SSoT 共有。既存レイアウトは実装と近かったため STATUS 注記で明示（再レイアウトなし）。
>   - 参照: `gui/window/main_window.py`（`_setup_*_tab` が旧スタブ除去 + `gui/tab/*` 挿入）・`gui/tab/{annotate,jobs}_tab.py`・ADR 0074/0076/0066。

> **v12.1 追記 (CLEAN 抜き取り監査 — 運用可能化)**: `.clean-audit` を「思いつきバンド」から実運用の仕組みへ。新規タブ・新規フレームは作らず Frame 5 と Frame 9 内で完結。
> **確定事項**:
> - **抽出枚数 = 母数連動**: `≤20 → 全数` / `21–500 → ⌈√n⌉` / `>500 → 上限30`（規則は1つ、母数で見せ方だけ変える）。バンド冒頭に `.ca-rule` でルール明示、該当段を `.rl.on` でハイライト。
> - **スコープ = batch 固定**（project/global 横断は実装しない・YAGNI / v12.3 確定）。
> - **抽出方式 = tier×rating 層化**（単純ランダムにしない。端ティア・高 rating を必ず含める）。
> - **NG 導線（最重要）**: 各サンプルに ✓/✕。✕ を押すと `.ca-bad` パネルが出て3択 — ①サンプル群を flagged に戻す ②Annotate で再タグ ③clean の一括 accept を取消。これで「見るだけ」でなく監査として閉じる。
> - **来歴記録**: `.prov` 帯に who / when / checked N/clean / accept M を描画。schema は **`review_log(id, reviewed_at, reviewer, sampled_ids[JSON], accepted_count, batch_ref)`** を追加（v12.3 確定）を `.src` 注記。
> - **strictest-wins 破棄票**: 開示は維持。**緩い側へ一括 revert は不可**（canonical は保守側固定 · #626 / PR 642）。個別に緩めるのは Annotate 手動上書き（is_edited_manually）。
> - **端状態**: Frame 9 に `CLEAN 監査 · 端状態` stcard を追加 — clean 0（バンド出さない）/ clean 1（抜き取り不要・re-sample 無効）/ 小母数 n≤20（全数）。
> - 設計メモ OPEN に「CLEAN 抜き取りの枚数・スコープ・方式」を ✓ DECIDED 行で追加。
> **残 OPEN**: なし（抽出スコープ・一括 revert・review_log スキーマは v12.3 で確定 ↓）。
> CSS は全て `.clean-audit` / `.ca-edge` プレフィックスでスコープ。

> **v12.2 追記 (Frame 6 · Export — ADR 0068 整合)**: 既存の Export フレームを実装挙動に合わせて更新（新規タブ・派生なし、`data-screen-label="06 Export"`、nav レール終点）。CSS は `#frame-export` スコープ。
> - **母集団 = staging set**（有界 MAX 500・可視・名前付き）。filter 必須・全件 export 不可（ADR 0019）を target banner に明示。フィルタ結果は直接 export せず「ステージングへ投入」を経る。
> - **出力 format**: `txt 分離`（.txt + .caption）/ `txt 結合` / `json`(metadata.json)。kohya/sd-scripts の旧表記は実装に合わせて撤去。
> - **target タグ format（新）**: `danbooru`(既定) / `e621` / `pony`。保存は danbooru canonical 固定、export 時に `convert_tags(format)` で **alias→preferred 解決** + **type=meta 除外**（ADR 0068）。
> - **変換プレビュー（新・核）**: サンプルで「保存値（danbooru canonical）→ 選択 format 変換後」を before/after 2カラム表示。橙=alias 解決、赤取消線=meta 除外を可視化。実際に書かれる集合を確定させる。
> - **解像度フィルタ（新）**: 原寸 / 長辺1024 縮小 / 768 未満除外。**changed-since** は既存（ダイアログ post-filter・永続化なし）。
> - **NSFW exact-set bypass** 維持（明示ステージした NSFW を黙って落とさない）。出力先パス + 実行ボタン。`export_with_criteria(..., tag_format="e621")` を foot に明示。
> - **discontinued モデルの過去タグ = keep + warning（v12.3 確定）**: export に含め provenance 保持・「discontinued 由来 N 件」を注記（exclude / silent は不採用）。**残 OPEN**: 変換プレビューのサンプル枚数のみ。

> **v12.3 追記 (6 OPEN を DECIDED 化)**: 文言・帯のみ更新（新規 CSS・再設計なし）。
> 1. CLEAN 抜き取りスコープ = **batch 固定**（project/global は YAGNI で不実装）。
> 2. strictest-wins の緩い側へ **一括 revert は不可**（canonical 保守側固定 · 個別のみ Annotate 手動上書き）。
> 3. review_log スキーマ確定 = **`review_log(id, reviewed_at, reviewer, sampled_ids[JSON], accepted_count, batch_ref)`**。
> 4. save query = **既定 snapshot（image_id 凍結・再現性）/ 明示操作で live（再評価）**。Frame 1 OPEN を RESOLVED 化。
> 5. discontinued モデルの Export 扱い = **keep + warning**（provenance 保持 + N 件注記）。Frame 6 + 設計メモ OPEN を RESOLVED 化。
> 6. issue → query 変換 = **issue type ごとの固定 facet 写像**（EMPTY_TAGS / NO_SCORE / RATING_DISAGREEMENT / SCORER_DISAGREEMENT / UNKNOWN_TIER → 各 facet）。Frame 9 OPEN を RESOLVED 化。

> **v11 追記 (CLI 大改装 #634 対応)**: agent-friendly CLI 契約を図解する **Frame 8 · CLI** を追加。
> 詳細は末尾「Frame 8 · CLI」節。ナビは `Search⌘1 / Map⌘2 / Annotate⌘3 / Jobs⌘4 / Results⌘5 / Errors⌘6 / Export⌘7 / CLI⌘8`。

---

## プロジェクト概要

LoRA 学習用の画像素材データセット管理ツール `LoRAIro` の UI ワイヤーフレーム。
schema.py のデータモデルに沿って画面を構成し、紙＋手書き調の low-fi スタイルで提案。

### スタイル
- フォント: `Kalam` (手書き) + `JetBrains Mono`
- カラー: `--ink #1a1a1a` / `--paper #fbfaf6` / `--accent oklch(0.62 0.14 32)` 暖色アクセント
- 影は `3px 3px 0 var(--rule)` の hard shadow。border は `2px solid` で枠を切る

### スキーマ（schema.py 由来）の主要モデル
- `Image` (width, height, format[webp固定], has_alpha, uuid, phash, created_at)
- `ProcessedImage` (upscaler_used)
- `Tag` (image_id, tag, model_id, confidence_score, existing, is_edited_manually)
- `Caption` (image_id, model_id, text, existing, is_edited_manually)
- `Score` (image_id, model_id, score, is_edited_manually)
- `Rating` (image_id, normalized_rating ∈ PG/PG-13/R/X/XXX, confidence_score)
- `Model` (name, type ∈ multimodal/tagger/scorer/rater/upscaler, requires_api_key, estimated_size_gb, discontinued_at)
- `ErrorRecord` (operation_type, error_type, error_message, image_id, model, retry_count, resolved_at, stack_trace)
- `Project` `ImageFilenameAlias` 等

---

## i18n 規約 (v10 で導入)

- `<body data-lang="ja|en">` + CSS で排他表示
- 3 語以上の英文 → `<span class="tx-ja">…</span><span class="tx-en">…</span>` のペアで両言語持つ
- 2 語以下の識別子、schema 参照、コード、モデル名 → 英語のまま固定
- Tweaks パネルの `Language` セグメントで切替（保存される）

---

## 確定済み設計判断

### 実行UIの A/B — B（独立 Jobs タブ）で決着 (2026-06-11)
- **決定**: 実行UIは **B: 独立 Jobs タブ**。現実装の進捗ポップアップ（A）は**廃止予定の暫定実装**として移行期のみ併存
- **理由**: Provider Batch は実装でも既にタブ（`provider_batch_job_widget.py`）であり「同期だけポップアップ」の分断を解消するため。「Job 完了 ⇢ auto Results・issue は紅バッジ」の中核フローは常設タブがないと成立しない（履歴・並行ジョブ・完了後導線の置き場）
- **反映済み (v11)**: FLOW 図と Annotate の実行ボタンに「Jobs タブへ自動スイッチ」を明記 / REJECTED に「実行ポップアップ維持（A案）」追加 / Frame 3 に DECIDED ノート / 履歴に CANCELED 行 + ADR 0034 terminal 語彙（FAILED / CANCELED / TERMINATED / UNRESPONSIVE）の凡例
- **検証**: `Jobs Flow Prototype.html`（操作プロト、Tweaks で A / B / B' 切替）でユーザ確認済み「違和感なし」。未決の微調整: 完了時 auto-Results vs バッジのみ / Jobs の情報密度 standard vs focus はプロトの Tweaks で引き続き比較可
- **規模前提**: 同期ジョブの母集団はステージング集合（上限 500）

### Import / 重複検出フロー — 専用画面は不要として取り下げ (2026-06-11)
- 登録ロジック側 (#633 / ADR 0061 §4 の統一登録エントリ・`registration_worker.py`) が pHash で **重複 (自動 skip + `ImageFilenameAlias` 自動記録) / 別版 (variant 登録) / 新規** を全自動分類。手動の重複解決 UI は不要
- chat3 で Errors から重複エラー行を削除した判断と整合
- 残っていた UX ギャップ（登録結果が statusBar に5秒出て消えるだけ）は **「登録完了サマリ」パネル**として v11 Frame 1 (Search・qbar の上) に描画済み: registered / variant / skipped / errors の件数 + skip/variant 行から「同一と判定された既存画像」へのリンク。独立 frame にはしない。✕ で閉じるまで残る

### 規模対応と空状態 — FRAME 9 · STATES として描画 (2026-06-11)
- 設計メモの「500で仮想スクロール、9kで per-row 非表示」を状態カタログフレーム（カード6枚）として実体化。数字キー 9 / data-screen-label="09 States"
- カード: ① Search 0 hit（トークン別 hit 数で矛盾を診断・「どれを外せば何件」提示・NLQ タイムアウトも同所）② Results 未実行（次アクションへの案内板）③ Results 0 issues（clean を祝って Export へ素通り）④ Jobs 空（履歴は消さない）⑤ Results@500（仮想スクロール + 同種 issue を1カードに集約・ページングなし）⑥ Results@9k（per-row 非描画・patterns のみ・pattern → Search へ絞り込み受け渡し）
- DECIDED (v12.3): issue → query 変換 = issue type ごとの固定 facet 写像（EMPTY_TAGS / NO_SCORE / RATING_DISAGREEMENT / SCORER_DISAGREEMENT / UNKNOWN_TIER → 各 facet）。pattern クリックで Search に適用

### rejected_at はターゲット非依存の正誤判断のみ (2026-06-11)
- `rejected_at` は「この画像にこのタグは誤り」という**正誤判断のみ**（ターゲット非依存）
- Danbooru 系 / Pony 系などターゲットごとの語彙差は、右パネルの採用操作では扱わない。タグ DB (genai-tag-db-tools) の format/エイリアス変換と Export 側のターゲット別規則（Export frame の責務）で解決
- → **Annotate 右パネルに「ターゲット別の採用切替」のような UI は描かないこと**
- → Export frame の frame-notes に「出力 format (danbooru / e621 / pony 等) の選択と変換プレビューの余地」をメモ済み (FORMAT ノート)

### 不要なフィルタ
- **画像拡張子フィルタ** — DB 登録時に webp に統一済なので削除
- **has_alpha フィルタ** — α 背景でも特別仕様なし、削除済
- **format / has_alpha 系のメタ表示** — サムネメタからも撤去（width × height のみ）

### モデル × ステージの設計（重要）
v10 の核心。Frame 2 (Annotate) のモデル実行 UX を再設計した。

- **ステージ中心**: `TAGS / CAPTION / SCORE / RATING / UPSCALE` の5ステージは schema の出力テーブル (Tag/Caption/Score/Rating/ProcessedImage) に対応
- **マルチモーダルモデルの扱い**: 1推論で取れる出力をすべて自動保存
  - 例: `gpt-4o-caption` を CAPTION ステージに置くと、副産物の tag + rating も同時取得して保存
  - 副産物側ステージ (TAGS / RATING) には `↝ shadow chip`（破線+斜体）で「自動取得される」と視覚表示
  - ピッカーの sub に `1推論で tags + caption + rating 取得` と明記
  - `llava-next` `qwen-vl-chat` は rating 出力なし → `tags + caption` のみ
- **ジョブ数表示**: 「N モデル × M枚」ではなく「N 推論 × M枚」。マルチモーダルは1推論扱い

### モデルピッカー (Frame 2B)
- 左レール: `Model.type` / Provider / Availability / Capabilities
- メイン: 検索 + ソート、行ごとに `name · type · status · size/cost · 信頼度閾値スライダ`
- ステータス: `● installed` / `● API ready` / `○ needs key` / `○ discontinued`
- `discontinued_at` モデルは取り消し線 + disabled で残す（履歴目的で消さない）
- プリセット: Default / Tags only / Full caption / Score · rate / Multimodal only など

### Search サイドバー (Frame 1)
- **DATE フィルタ**: chip → 20本ヒストグラム + 範囲スライダ + プリセット chip にアップグレード
- **annotations state**: `is_edited_manually` を tag / caption / score 統合の「手動編集あり」フィルタに。下に内訳
- **model filter**: 検索ボックス + 📌ピン留め + 「最近使用」 + 「他N個を表示」展開。0使用モデルは折りたたみ
- **error state**: chip 3択 (all / エラーありのみ / エラーを除外)

### Jobs と Errors は分離 (v10 後半)
- ~~旧 Frame 3 (JOBS / ERRORS 合体)~~ → **Frame 3 · JOBS** と **Frame 4 · ERRORS** に分離
- ナビ: `Search⌘1 / Map⌘2 / Annotate⌘3 / Jobs⌘4 / Errors⌘5 / Export⌘6`

#### Frame 3 · JOBS
- 性質: lifecycle (実行中 / キュー / 履歴)
- サマリ: 実行中 / キュー / 過去7日完了 / API使用状況 (rate)
- Running カード: ステージ × モデルの進捗バー、rate待機は縞模様、Pause/Cancel
- Queue: 並び替え、推定時間
- History: テーブル、失敗行から `→ Errors` で triage

#### Frame 4 · ERRORS
- 性質: 失敗の triage
- サマリ: 未解決 / 24h / 解決済 / error_type 別
- クロスフィルタ: status × operation × model × time
- **デフォルトはグルーピング表示** (同一原因を集約) — 個別行モードも切替可
- 各グループ: 件数、エラーメッセージ + バッジ、影響画像リンク、retry可/上限到達、過去7日スパークライン、状況別アクション (retry / resolve / ignore / 再インポート)
- bottom bulk: 「retry可をすべて再実行」「選択を無視」

---

## 未着手 / 検討中

### 次の優先課題（ユーザ承認済）
**1. Frame 5 · RESULTS（アノテーション品質トリアージ）**
- 目的: 画像素材ではなく **アノテーションの品質チェック**（明確化済）
- バッチは少数（〜10枚程度）想定
- 構成方針:
  1. **品質問題を最上段に集約** — issue カードは**構造的（閾値不要・客観的事実）のみ**: 空タグ / no-score / unknown tier / rating 不一致 / scorer 不一致。**低信頼度タグ(conf<0.40)・caption 短すぎ(<8語)は issue 化しない**（2026-06-11 確定・inline comment）— conf値・語数は行に表示済みで目で足りるし、恕意的な線は説明不能。config閾値・スコープ・状態管理を丸ごと削減できる
  2. **画像単位の要約リスト** — サムネ + アノテーション一式の要約。`▸ レビュー` で Annotate に直行
  3. **アクション** — 1件ずつ accept/edit/reject + bulk 「問題なければ承認」
- CSS は既に追加済（`.res-summary` `.issues-band` `.issue-card` `.res-row` `.res-foot`）→ あとは HTML 本体を Frame 4 の後ろに追加するだけ

### 残作業（優先順）
1. **Frame 5 · RESULTS の HTML 実装**（CSS 準備済）
2. **Frame 2 右側パネル（Tag/Caption/Score/Rating 詳細）** の整理
   - マルチモーダル対応した今、モデル別グルーピング・採用ワークフローが弱い
   - 「このモデルの tag を全採用」「競合解決」UI
   - **制約**: 採用操作はターゲット非依存（`rejected_at` = 正誤判断のみ）。ターゲット別の採用切替 UI は描かない（↑確定済み設計判断参照）
3. **Settings / API key 設定 / Model installer** — ✅ v11 で **Frame 2C · SETTINGS（独立ウィンドウ）** として実装 (2026-06-11)
   - needs key は「可視 + その場で解消」に統一: Frame 2B の needs key chip クリック → Settings の該当プロバイダ欄（ハイライト）→ 保存 → ● API ready。実装の「キー未設定モデルを非表示」仕様はこのワイヤーを正に改める予定
   - 9個目のタブにはしない（現実装どおり ConfigurationWindow 独立ウィンドウ、タイトルバー ⚙ から）。中身は API keys（マスク・表示切替なし・保存済かだけ分かる・config/lorairo.toml [api]）/ モデル経路 (auto/direct/openrouter · "all" は CLI 専用) / installer の最小構成
   - **Model installer（新設）**: 初回推論時の暗黙 HuggingFace DL を明示的な **install ジョブ**に。estimated_size_gb 表示・進捗は Jobs lifecycle に同居（中止 = CANCELED · ADR 0034）・uninstall / 容量合計あり。未 install モデルをパイプラインに置くと install ジョブが自動先行
   - discontinued は現状維持（取り消し線 + disabled）
4. **Map タブ** — 中身未設計、優先度低（Export は v12.2 で実装済 ↓）

~~Import / 重複検出フロー~~ — 実装済み（pHash 全自動分類）のため取り下げ。代替の「登録完了サマリ」は Frame 1 に描画済み（↑確定済み設計判断参照）

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

## Frame 8 · CLI（agent-friendly CLI 契約 / issue #634）

GUI とは別の **第二の操作面**として CLI 契約を図解する frame を追加。リポジトリの
実装 (`src/lorairo/cli/`) と `docs/cli.md` を読み、実際の出力形式に合わせている。

### 出典（GitHub `NEXTAltair/LoRAIro` から取得して反映）
- ADR 0057 (`_emit.py` / `_errors.py` / `_boundary.py`) — JSONL & 構造化エラー契約
- ADR 0058 (`_output_mode.py`) — `--json`/`--no-json` > env `LORAIRO_CLI_JSON` > 既定 rich
- ADR 0059 (`introspection.py`) — `list-commands` / `describe` / `--schema json_schema`
- ADR 0060 — bounded pagination (`limit ≤ 500` / `RESULT_SET_TOO_LARGE`)

### frame の構成（7 バンド）
1. **契約 + 出力モード解決** — 「既存 CLI に被せた機械可読契約レイヤー」+ ADR チップ
2. **stdout=JSONL / stderr=ログ** — 同一コマンドの 2 ペイン端末（中心ビジュアル）
3. **3 つの kind** — `item` / `result` / `error`
4. **構造化エラー契約** — error JSONL 例 + 15 codes（共有11/AI3/pagination1）+ exit 0/2/1 + flags
5. **introspection** — `list-commands`(type:tool) / `describe`(type:model/schema)
6. **bounded pagination** — `count`/`total`/`has_more` + `RESULT_SET_TOO_LARGE`
7. **agent driving flow** — project create → images register → annotate run → export create、`code`/`has_more` 分岐

### コマンド総覧（reference バンド）
`annotate`(2) `batch`(6) `export`(1) `images`(3) `models`(2) `project`(3) + top-level `version/status/list-commands/describe` = 17 サブコマンド。各コマンドに read-only / side_effect バッジ。

### スタイル / 実装メモ
- 端末ペインは `#23211d` ダーク + JSONL シンタックス色分け（`.j-k/.j-s/.j-n/.j-b`）。kind バッジ `.kb.item/.result/.error`。
- CSS は全て `#frame-cli` プレフィックスでスコープ（既存トークン衝突回避）。
- ナビ: proto controller が **全 `.topnav` に CLI タブを JS で注入**（8 nav 手編集を回避）。`SCREENS.cli` / `NUM2KEY['8']` / `TAB2KEY.CLI` を追加。
- frame は `.app` 内に配置（他 frame と左 32px 揃え）。proto-bar ヒントは `1–8` に更新。

---

## Tweaks
- `lang: ja | en` — i18n 切替
- `sidebar_collapsed`
- `show_map` — Schema mapping パネル表示
- `show_schema_tags` — `.schema-tag` / `.src` バッジ表示

`/*EDITMODE-BEGIN*/ … /*EDITMODE-END*/` で囲まれた JSON が永続化対象。

---

## ファイル構成（旧記述・上の最新版を参照）

```
Wireframes.html         初版
Wireframes v2〜v9.html   履歴
Wireframes v10.html     ← 最新作業対象
HANDOFF.md              ← 本ファイル
```

v11 を切るのか v10 を継続編集するかは次セッションで判断。
小修正は v10 で続行、大規模再構成なら v11 にコピーする方針。

---

## 直近のユーザ要望

- アノテーション品質のトリアージ画面が欲しい（画像チェックではない）
- 一度に実行する枚数は多くない（少数バッチ前提）
- → **Frame 5 · RESULTS** として上記方針で実装するのが次の作業
