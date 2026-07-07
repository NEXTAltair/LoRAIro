# 残り GUI Issue 群の解決ゴール (翻訳/言語・タグ種別・DB 並行バグ)

2026-07-07 の computer-use 実機操作テストで洗い出したオープン GUI Issue のうち、
**バグ・配線ギャップ・性能・タグ chip 種別デザイン更新・人間レビューキュー** の 10 件をまとめて
解決するためのゴール定義。

> **前バッチ (#1221 / #1222 / #1223 / #1225) は 2026-07-07 に全て merged + closed で完了済み。**
> 本ファイルはその後に洗い出された新バッチ (#1232〜#1242) のうち、下記スコープ分を対象に書き換えたもの。

## 対象スコープ (2026-07-07 ヒアリング確定)

**対象 (10 件)**:
- 翻訳/言語バグ: #1235 / #1236 / #1237
- 性能: #1232
- DB 並行バグ: #1239
- タグ chip 種別: #1233 / #1234 / #1241 / #1242
- 人間レビューキュー: #1240

**今回スコープ外 (別ゴールで後回し)**: #1238 (エクスポート多言語)。

## 完了条件 (Stop hook 評価用)

以下がすべて満たされたら完了:

1. **対象 10 Issue すべてに、main へ squash merge 済みの PR がある** — 各 PR は当該 Issue の文書化された
   根本原因/要件を解決し、CI-equivalent filter の test が pass している。
2. 修正済みの Issue は GitHub 上で close されている (PR の `Closes #NNNN` 経由でも可)。
3. GUI 挙動そのものの最終確認 (Windows 実機) はプロジェクト慣習上ユーザーが行う。エージェントは
   **実装 + unit/integration test + merge** までを完了とする。実機確認待ちは blocker ではない。
4. いずれかの Issue が真にブロックされた場合 (設計判断がユーザー必須 / スコープが別 Issue へ移送等) は、
   PR/Issue リンクと blocker を本ファイルに明記した上で、その Issue を完了扱いから外して残りを進める。

## 前提 (確定事項・変更しない)

- 実装は必ず `.agents/worktree/` 配下の worktree + PR (`.claude/rules/git-workflow.md`)。main 直 push 禁止。
- PR 起票前に CI-equivalent filter を pass させる (`.claude/rules/testing.md`)。
- 既存の通っているテストは必要な範囲以外書き換えない。公開 import パスは変えない。
- **#1234/1235/1236/1237 はバックエンド API が既存で LoRAIro 側配線のみで解決可能** (調査確定)。
  submodule (genai-tag-db-tools) の変更は不要。
- **#1239 のみ** genai-tag-db-tools の `repository.py` トランザクション境界に踏み込む可能性があり、
  submodule を触る場合は two-repo PR フロー (`CI-EQUIV-TESTED` marker + pin bump) が必要。
- **タグ chip 種別デザイン更新 (#1233/1241/1242)** と **人間レビューキュー (#1240)** は feature 寄り。
  実装前に superpowers `brainstorming` skill で設計を合意してから着手する (バグ/配線・性能を先に片付ける)。
- **#1232 (右クリック翻訳ポップアップ 1 秒)** は性能バグ。`list_translation_candidates` の同期呼び出しが
  メインスレッドをブロックする点を investigation で確定し、非同期化 (worker 化) 中心で対応する。

## 対象 Issue と既知の根本原因 / 要件

| # | 内容 | 種別 | 根本原因 / 配線先 (調査済み) |
|---|---|---|---|
| #1236 | 翻訳修正ダイアログに実データに無い 'japanese' 幻の重複行 | bug (UI) | `TagMetadataWorker._apply_preferred_translations` が preferred 訳を全 alias key (`ja`/`japanese`) へ fan-out し in-memory dict に両方格納 → `_open_translation_fix_dialog` が `.keys()` を生で `TranslationFixDialog` に渡し行化。**表示前に `language_alias_keys()` で dedup**。LoRAIro 側のみ |
| #1235 | 言語セレクタに en/english・ja/japanese のエイリアスが重複表示 | bug (UI) | `update_language_selector`/`initialize_language_selector` が `reader.get_tag_languages()` の raw distinct 値を alias dedup せず追加 (literal `"english"` のみ除外)。**`language_alias_keys()` を呼び出し側で適用**。#1236 と同じ alias 家系 (`utils/language_keys.py`)。LoRAIro 側のみ |
| #1237 | 言語の付け替え・誤登録タグの翻訳削除ができない (未配線) | wiring | backend 済 (`core_api.delete_user_translation`/`suppress_translation`/`unsuppress_translation`)。CLI サブコマンド + `TranslationFixDialog` の GUI 導線を既存 public API に接続。LoRAIro 側のみ |
| #1232 | タグ chip 右クリック→翻訳追加ポップアップの表示に約 1 秒 | bug (性能) | `list_translation_candidates` の同期呼び出しがメインスレッドをブロック。**worker 化/非同期プリフェッチ**で応答性改善。tag DB クエリコスト (#1203 系) が要因なら実測で切り分け。investigation で確定 |
| #1234 | タグ種別編集が danbooru 標準 5 種にハードコード | wiring | backend 済 (`update_tags_type_batch` が未知 type_name を auto-create)。制約は `TagTypeEditDialog.TYPE_CHOICES` の非編集 `QComboBox` のみ。**combo を `setEditable(True)` にし OK 検証を緩和**。LoRAIro 側のみ |
| #1239 | 取り込み時 新規タグ登録で FOREIGN KEY constraint failed 多発 | bug (P1: データ完全性) | `DatabaseRegistrationWorker` (登録 INSERT) と `RefinementWorker` (tag DB 読み) が同一 `user_tags.sqlite` に並行アクセス中に FK 失敗 + 既存 TAGS 行消失 + 翻訳パッチ孤立。**要 systematic-debugging**。cross-worker DB アクセスの排他/トランザクション境界。submodule `repository.py` に及ぶ可能性 |
| #1233 | タグ chip がタイプ別に色分けされていない | enhancement (design) | character/copyright/artist 等の視覚区別。#983 デザイン更新系。**brainstorming 先行**。#1241 と描画が重複 |
| #1241 | タグ chip の種別グリフ+ストライプ + 「種別で分ける」トグル | enhancement (design, #983) | chip 描画拡張 + グルーピングトグル。#1233 の色分けと同じ chip 描画層。**brainstorming で #1233 と一体設計** |
| #1242 | タグ種別編集をユーザー定義カスタム種別まで拡張 | enhancement (design, #983) | #1234 の配線 (任意 type 入力) を前提に UI 拡張。**#1234 完了後に着手** |
| #1240 | 取り込み時の未マッチタグ・長文を人間レビューキュー (エラータブ拡張) でタグ/キャプション/破棄にトリアージ | feature | エラータブを拡張しトリアージ UI を新設。**brainstorming 先行**。#1239 (取り込み時の未マッチ/登録失敗) の import-tag 知見と連動 → #1239 後に着手 |

## 進捗 (2026-07-07 実行中)

| # | 状態 | PR |
|---|---|---|
| #1234 | ✅ merged + closed | #1243 |
| #1235 | ✅ merged + closed | #1245 |
| #1236 | ✅ merged + closed | #1245 |
| #1232 | ✅ merged + closed (P2 follow-up #1247) | #1244 |
| #1237 | ✅ merged + closed (P2 も同 PR で対応) | #1246 |
| #1239 | ✅ merged + closed (P1, two-repo: genai #132 + pin。follow-up #1249) | #1248 |
| #1233 | ✅ merged + closed | #1251 |
| #1241 | ✅ merged + closed (#1233 と一体。Codex P1 重複ヘッダ修正込み) | #1251 |
| #1242 | ✅ merged + closed | #1250 |
| #1240 | ⛔ **設計判断ユーザー必須で defer (完了条件4 escape hatch)** — 下記 blocker 参照 | — |

**結果: 対象 10 件中 9 件 merged + closed。#1240 のみ設計判断ユーザー必須で defer。**
follow-up: #1247 (#1232 P2 終端一本化), #1249 (#1239 P2 sibling 非 atomic 経路移行)。

## #1240 blocker (完了条件4 に基づく defer)

調査 (2026-07-07) の結果、#1240 は自律実装できない **ユーザー/アーキテクチャ設計判断** を含むため、完了条件4 の
escape hatch に従い本ゴールの完了扱いから外す。他 9 件は完遂する。

### 介入点 (調査で確定・実装可能な部分)
- 未マッチ集合は `annotation_record.py:1326` の `missing_tags` で既に計算済みだが使い捨て。`batch_resolve_tag_ids` の戻り値が
  `dict[str, int|None]` で「既存タグ」と「今 auto-create したタグ」を区別できない (#1239 で全て登録成功するようになったため)。
- 画像コンテキスト付き ErrorRecord を作れるのは `db_manager._import_associated_files` (db_manager.py:418-465、image_id + raw tags + tag_id_cache が揃う唯一の点)。
- triage アクション適用先は既存 API で足りる: タグ採用=`classify_manual_tag`+`add_tag_to_images_batch`、キャプション採用=`save_captions`、破棄=`mark_error_resolved`。
- エラータブ資産 (`ErrorRecord`/`error_triage_service`/`errors_triage_widget`/`error_notification_widget`) は `operation_type='tag_triage'` 相乗りで再利用可 (schema 変更不要)。`image_link_clicked` は定義済みだが未配線 (dead signal、`_on_registration_view_image_requested` の先例で配線可)。

### ユーザー設計判断が必須の未決事項 (これが blocker)
1. **【最重要】register-then-flag vs flag-instead-of-register**: #1239 で未マッチタグは atomic に auto-register するようになった。
   triage 候補を (a) 登録してから ErrorRecord で flag する (共有 genai-tag-db-tools tag_db に garbage 文字列/URL/文章が
   永続。破棄しても LoRAIro 側 Tag を soft-reject するだけで tag_db エントリは残り、issue が明示的に警告する「汚染」が起きる) か、
   (b) 登録前に intercept して flagged を tag_db に登録しない (汚染回避だが `_register_missing_tags`/`_import_associated_files`
   の制御フロー変更が必要) か。**共有 8.4GB tag_db の不可逆汚染に関わるデータ完全性の設計判断**で、実装者が独断すべきでない。
2. **triage 振り分け heuristic の閾値**: issue は「長さ×存在の自動判定は危険」と警告 (正当な長文タイトルタグ + base DB のゴミ)
   しつつ、queue に載せる基準自体は必要。word/char count/space ratio の具体値は product 判断。
3. **スコープ (3 呼び出し点)**: `.txt` sidecar (registration_worker) のみか、provider JSONL import・AI annotation save も含むか。
4. group taxonomy (per error_type か per source file か)、5. UI action signal 形、6. image_link_clicked 配線先 (先例あり)。

### 推奨アプローチ (ユーザー承認待ち)
汚染回避を優先し **(b) flag-instead-of-register** を推奨: `_register_missing_tags` で heuristic 一致文字列は登録スキップ→
tag_id=None を db_manager へ返し、`_import_associated_files` が image_id 付き triage ErrorRecord を作成 (タグは保存しない)。
heuristic は保守的に「未マッチ かつ (語数>=4 または 空白含み char>=30)」程度から開始。1.〜3. をユーザーが確定すれば着手可能。

## 推奨実行順

**Phase 1 — バグ/配線 (LoRAIro 側のみ・self-contained・低リスク)** を先に片付ける:

1. **#1236** — 幻の japanese 重複行。dict の alias dedup。self-contained。
2. **#1235** — 言語セレクタの alias 重複。#1236 と同じ `language_keys.py` 家系。#1236 と近接して処理
   (同一ファイル領域なので worktree を分けるなら直列化、まとめて 1 PR も可)。
3. **#1237** — 翻訳付け替え/削除の配線 (CLI サブコマンド + GUI 導線)。既存 public API に接続。
4. **#1234** — タグ種別編集 combo の editable 化 + `update_tags_type_batch` 配線。#1242 の前提。
5. **#1232** — 右クリック翻訳ポップアップの非同期化 (worker 化)。#1237 と同じ右クリック→翻訳ポップアップ
   領域なので近接処理。tag DB クエリコストが要因なら実測で切り分け。

**Phase 2 — DB 並行バグ (investigation-heavy・設計判断/ADR の可能性)**:

6. **#1239** — FK constraint 並行アクセス。systematic-debugging で実行時 (logs) を叩き根本原因を
   falsify・確定。cross-worker 排他が設計変更を要すれば ADR 起票 + ユーザー判断でエスカレーション候補
   (完了条件 4 の escape hatch)。submodule を触るなら two-repo フロー。

**Phase 3 — feature / タグ chip 種別デザイン更新 (brainstorming 先行)**:

7. **#1234 完了後に #1242** — カスタム種別 UI 拡張。
8. **#1233 + #1241 は一体設計** — 色分けとグリフ+ストライプ+トグルは同じ chip 描画層。
   brainstorming で 1 設計に束ねてから実装 (別々に作ると描画が二重になり手戻り)。
9. **#1239 完了後に #1240** — 未マッチタグの人間レビューキュー (エラータブ拡張)。#1239 で得た
   「取り込み時に未マッチ/登録失敗するタグ」の機構を前提に、トリアージ UI を brainstorming で設計してから実装。

## 確定した実行方針 (2026-07-07 ヒアリング)

- **merge 権限**: CI green + Codex レビュー完了 + blocking 指摘なしで自律 squash merge (agent-pr-autoloop 準拠)。
  実機確認は事後。P1 (#1239) のデータ完全性修正も同基準で自律 merge 対象。
- **feature 方針**: バグ/配線/性能 (#1232/1234/1235/1236/1237/1239) を優先。デザイン更新系
  (#1233/1241/1242) と人間レビューキュー (#1240) は superpowers `brainstorming` skill で設計合意してから
  実装。1 ループに混ぜず段階分け。
- **ループ粒度**: 10 件を 1 つの自律ループで連続処理。上限 50 ターン、または全件完了で停止。

## 関連

- #1238 (エクスポート多言語・スコープ外)
- #1206 (tag DB 並行アクセス "interrupted")、#1221 (応答なし watchdog)、#1225 (`user_tags.sqlite` は
  rollback-journal モード)、#1212 (tag 解決重複)、#983 (タグ種別デザイン)、#989/#993/#976/#998 (翻訳管理)

---

# 完了条件 (`/goal` に渡す条件文)

```
Issue #1232 #1233 #1234 #1235 #1236 #1237 #1239 #1240 #1241 #1242 の10件すべてが、main へ
squash merge 済みの PR で解決され GitHub 上で closed になっている。判定は各ターンでエージェント自身に
各 Issue 分の `gh issue view <N> --json number,state,stateReason` と
`gh pr list --search "<N> in:body" --state merged --json number,title` を実行・出力させ、
10件すべて state=CLOSED かつ対応する merged PR が存在することを確認する。
各 PR は文書化した根本原因/要件を解決し、CI-equivalent filter
(uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow")
の test が pass している。ただし tests/ 配下の既存テストは必要範囲外を書き換えず、公開 import パスは
変えない。バグ/配線/性能 (#1232/1234/1235/1236/1237/1239) を先に片付け、デザイン更新系
(#1233/1241/1242) と人間レビューキュー (#1240) は brainstorming で設計合意してから実装する。
#1239 が cross-worker DB アクセスの設計変更を要しユーザー判断が必須と判明した場合、または他の
Issue が設計判断でユーザー必須と判明した場合は、その Issue の PR/Issue リンクと blocker を
docs/plans/goal-remaining-gui-issues.md に明記し、完了扱いから外して残りを進める。
達成できなければ50ターンで停止。
```

# 実行ブリーフ (初回プロンプト)

## タスク

`docs/plans/goal-remaining-gui-issues.md` の対象 10 Issue を推奨実行順 (Phase 1 バグ/配線/性能 →
Phase 2 #1239 DB 並行バグ → Phase 3 feature/デザイン更新) で解決する。各 Issue は `.agents/worktree/`
配下の worktree + PR で実装し、CI-equivalent filter を pass させてから PR 起票、agent-pr-autoloop で
CI/Codex を回し、safe なら自律 squash merge する。

- **Phase 1 (LoRAIro 側のみ・調査確定済み)**: #1236 (fan-out dict を `language_alias_keys()` で dedup)、
  #1235 (言語セレクタで同 alias dedup、#1236 と同じ `utils/language_keys.py` 家系なので近接処理)、
  #1237 (既存 `core_api.delete_user_translation`/`suppress_translation`/`unsuppress_translation` を
  CLI サブコマンド + `TranslationFixDialog` GUI 導線に配線)、#1234 (`TagTypeEditDialog` combo を
  `setEditable(True)` にし `update_tags_type_batch` に配線)、#1232 (`list_translation_candidates` の
  同期呼び出しをメインスレッド外へ = worker 化/非同期プリフェッチ。tag DB クエリコスト #1203 系が
  要因か investigation で切り分け)。**submodule 変更は不要**。
- **Phase 2 (#1239)**: 根本原因の確証を先に。systematic-debugging で実行時 (logs/lorairo.log,
  logs/image-annotator-lib.log) を直接叩き、`DatabaseRegistrationWorker` と `RefinementWorker` の
  並行 `user_tags.sqlite` アクセスによる FK 失敗 + TAGS 行消失 + 翻訳パッチ孤立の機構を falsify・確定
  してから修正する。静的読解で「たぶんこれ」で修正しない。cross-worker 排他が設計変更を要す場合は
  ADR 起票 + ユーザー判断へエスカレーション (完了条件 4 の escape hatch)。genai-tag-db-tools の
  `repository.py` (`create_tag`/`update_tag_status` のトランザクション境界) を触る場合は two-repo
  フロー (`CI-EQUIV-TESTED` marker + submodule pin bump)。
- **Phase 3 (feature/デザイン更新・brainstorming 先行)**: #1234 完了後に #1242 (カスタム種別 UI 拡張)。
  #1233 (色分け) と #1241 (グリフ+ストライプ+「種別で分ける」トグル) は同じ chip 描画層なので
  brainstorming で 1 設計に束ねてから実装 (別々だと描画二重で手戻り)。#1239 完了後に #1240
  (未マッチタグの人間レビューキュー = エラータブ拡張)。#1239 で得た「取り込み時に未マッチ/登録失敗する
  タグ」の機構を前提に、トリアージ UI (タグ/キャプション/破棄) を brainstorming で設計してから実装。
- 各 Issue 完了時に本計画ファイルの該当行へ PR リンクと結果を追記する。

## サブエージェント委譲方針 (必須スロット・省略しない)

- 根本原因調査 (該当モジュールの grep・関連ファイル読み・logs 解析) は investigation / general-purpose
  サブエージェントに委譲し、結論だけ受け取る。メインコンテキストにファイルダンプを溜めない。
- 独立した Issue 着手は可能な範囲で並列サブエージェントに fan-out (worktree を分離。ただし
  #1235⇄#1236 は同一ファイル領域、#1233⇄#1241 は同一描画層、#1234→#1242 は依存があるため直列を維持)。
- CI-equivalent filter の test 実行は test-runner サブエージェントに投げ、要約だけ受ける。
- PR レビュー観点の確認は code-reviewer / security-reviewer / db-schema-reviewer サブエージェントに委譲する
  (#1239 は db-schema-reviewer / query-analyzer を活用)。
- メインループは「委譲先の結論を統合して次の一手を決める」役に徹する。
- 調査/機械的作業のサブエージェントは model=sonnet、設計判断が要る箇所のみ opus を指定する。

## スコープ制約

- 実装は必ず `.agents/worktree/` 配下の worktree + PR (`.claude/rules/git-workflow.md`)。main 直 push 禁止。
- tests/ 配下の既存テストは必要範囲外を書き換えない。公開 import パスを変えない。
- #1232/1234/1235/1236/1237 は submodule (genai-tag-db-tools) を触らない (LoRAIro 側配線のみで解決可能)。
  #1239 のみ、必要なら two-repo フローで submodule を触ってよい。#1240 は brainstorming の設計しだい。
- `.github/workflows/**`・権限/secret・Git 履歴改変は自動修正の対象外 (必要ならエスカレーション)。
- 自動 merge は CI green + Codex レビュー完了かつ blocking 指摘なしの場合のみ。P1 (#1239) の
  データ完全性修正でも同基準で自律 merge してよい (ヒアリングで承認済み)。
- デザイン更新系 (#1233/1241/1242) と人間レビューキュー (#1240) は brainstorming の設計合意を経ずに
  実装着手しない。設計判断がユーザー必須と判明したら escape hatch でエスカレーション。
