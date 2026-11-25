# 残り GUI Issue 群の解決ゴール(翻訳/言語・タグ種別・DB 並行バグ)

2026-07-07 の computer-use 実機操作テストで洗い出したオープン GUI Issue のうち、**バグ・配線ギャップ・性能・タグ chip 種別デザイン更新・人間レビューキュー** の 10 件をまとめて解決するためのゴール定義である。

> **前バッチ(#1221 / #1222 / #1223 / #1225)は 2026-07-07 にすべて merged + closed で完了済みである。**
> 本ファイルは、その後に洗い出された新バッチ(#1232〜#1242)のうち下記スコープ分を対象に書き換えたものである。

## 対象スコープ(2026-07-07 ヒアリング確定)

**対象(10 件)**
- 翻訳/言語バグ: #1235 / #1236 / #1237
- 性能: #1232
- DB 並行バグ: #1239
- タグ chip 種別: #1233 / #1234 / #1241 / #1242
- 人間レビューキュー: #1240

**今回スコープ外(別ゴールで後回し)**: #1238(エクスポート多言語)

## 完了条件(Stop hook 評価用)

以下のすべてを満たした時点で完了とする。

1. **対象 10 Issue すべてに、`main` へ squash merge 済みの PR が存在する**: 各 PR は当該 Issue に文書化された根本原因または要件を解決し、CI-equivalent filter のテストを通過している。
2. **Issue のクローズ**: 修正済みの Issue は GitHub 上で close されている(PR 本文の `Closes #NNNN` 経由でも可)。
3. **実機確認の扱い**: GUI 挙動そのものの最終確認(Windows 実機)はプロジェクト慣習上ユーザーが行う。エージェントは **実装 + unit/integration テスト + マージ** までを完了とし、実機確認待ちはブロッカーとしない。
4. **ブロッカー発生時の扱い**: ユーザー必須の設計判断や別 Issue へのスコープ移送などで真にブロックされた Issue がある場合は、PR/Issue リンクとブロッカーを本ファイルに明記したうえで完了扱いから外し、残りを進める。

## 前提(確定事項・変更しない)

- 実装は必ず `.agents/worktree/` 配下の worktree と PR で行う(`.claude/rules/git-workflow.md`)。`main` への直接 push は禁止する。
- PR 起票前に CI-equivalent filter を通過させる(`.claude/rules/testing.md`)。
- 既存の通っているテストは必要な範囲以外書き換えず、公開 import パスも変更しない。
- **#1234 / #1235 / #1236 / #1237** はバックエンド API がすでに存在し、LoRAIro 側の配線のみで解決可能である(調査確定済み)。submodule(`genai-tag-db-tools`)の変更は不要である。
- **#1239 のみ** `genai-tag-db-tools` の `repository.py` トランザクション境界に踏み込む可能性がある。submodule を触る場合は two-repo PR フロー(`CI-EQUIV-TESTED` marker と pin bump)を用いる。
- **タグ chip 種別デザイン更新(#1233 / #1241 / #1242)** と **人間レビューキュー(#1240)** は機能開発寄りであるため、バグ・配線・性能を先に片付け、着手前に superpowers の `brainstorming` skill で設計を合意する。
- **#1232(右クリック翻訳ポップアップの 1 秒遅延)** は性能バグである。`list_translation_candidates` の同期呼び出しがメインスレッドをブロックしている点を investigation で確定し、非同期化(worker 化)を中心に対応する。

## 対象 Issue と既知の根本原因・要件

| # | 内容 | 種別 | 根本原因 / 配線先(調査済み) |
|---|---|---|---|
| #1236 | 翻訳修正ダイアログに実データにない `'japanese'` の重複行が現れる | bug(UI) | `TagMetadataWorker._apply_preferred_translations` が preferred 訳を全 alias key(`ja` / `japanese`)へ fan-out して in-memory dict に両方格納し、`_open_translation_fix_dialog` が `.keys()` をそのまま `TranslationFixDialog` へ渡して行化している。**表示前に `language_alias_keys()` で重複排除する**。LoRAIro 側のみ |
| #1235 | 言語セレクタに `en`/`english`・`ja`/`japanese` のエイリアスが重複表示される | bug(UI) | `update_language_selector` と `initialize_language_selector` が `reader.get_tag_languages()` の生の distinct 値を alias 重複排除せず追加している(リテラル `"english"` のみ除外)。**呼び出し側で `language_alias_keys()` を適用する**。#1236 と同じ alias 家系(`utils/language_keys.py`)。LoRAIro 側のみ |
| #1237 | 言語の付け替えや誤登録タグの翻訳削除ができない(未配線) | wiring | バックエンドは実装済み(`core_api.delete_user_translation` / `suppress_translation` / `unsuppress_translation`)。CLI サブコマンドと `TranslationFixDialog` の GUI 導線を既存 public API に接続する。LoRAIro 側のみ |
| #1232 | タグ chip の右クリックから翻訳追加ポップアップ表示まで約 1 秒かかる | bug(性能) | `list_translation_candidates` の同期呼び出しがメインスレッドをブロックしている。**worker 化と非同期プリフェッチ** で応答性を改善する。tag DB クエリコスト(#1203 系)が要因かどうかは実測で切り分ける(investigation で確定) |
| #1234 | タグ種別編集が danbooru 標準 5 種にハードコードされている | wiring | バックエンドは実装済み(`update_tags_type_batch` が未知の `type_name` を自動作成する)。制約は `TagTypeEditDialog.TYPE_CHOICES` の非編集 `QComboBox` のみである。**combo を `setEditable(True)` に変更し、OK 時の検証を緩和する**。LoRAIro 側のみ |
| #1239 | 取り込み時の新規タグ登録で `FOREIGN KEY constraint failed` が多発する | bug(P1: データ完全性) | `DatabaseRegistrationWorker`(登録 INSERT)と `RefinementWorker`(tag DB 読み取り)が同一 `user_tags.sqlite` に並行アクセス中に、FK 失敗・既存 TAGS 行消失・翻訳パッチ孤立が発生する。**systematic-debugging 必須**。cross-worker DB アクセスの排他とトランザクション境界が論点であり、submodule の `repository.py` に及ぶ可能性がある |
| #1233 | タグ chip がタイプ別に色分けされていない | enhancement(design) | `character` / `copyright` / `artist` などの視覚区別を行う。#983 のデザイン更新系であり、**brainstorming 先行** とする。#1241 と描画層が重複する |
| #1241 | タグ chip の種別グリフ+ストライプおよび「種別で分ける」トグル | enhancement(design、#983) | chip の描画拡張とグルーピングトグルを追加する。#1233 の色分けと同じ chip 描画層であるため、**brainstorming で #1233 と一体設計する** |
| #1242 | タグ種別編集をユーザー定義カスタム種別まで拡張する | enhancement(design、#983) | #1234 の配線(任意 type 入力)を前提とした UI 拡張である。**#1234 の完了後に着手する** |
| #1240 | 取り込み時の未マッチタグや長文を人間レビューキュー(エラータブ拡張)でタグ/キャプション/破棄へトリアージする | feature | エラータブを拡張してトリアージ UI を新設する。**brainstorming 先行** とし、#1239(取り込み時の未マッチ/登録失敗)の import-tag 知見と連動させるため #1239 の完了後に着手する |

## 進捗(2026-07-07 実行中)

| # | 状態 | PR |
|---|---|---|
| #1234 | ✅ merged + closed | #1243 |
| #1235 | ✅ merged + closed | #1245 |
| #1236 | ✅ merged + closed | #1245 |
| #1232 | ✅ merged + closed(P2 follow-up #1247) | #1244 |
| #1237 | ✅ merged + closed(P2 も同 PR で対応) | #1246 |
| #1239 | ✅ merged + closed(P1、two-repo: genai #132 + pin。follow-up #1249) | #1248 |
| #1233 | ✅ merged + closed | #1251 |
| #1241 | ✅ merged + closed(#1233 と一体。Codex P1 重複ヘッダ修正込み) | #1251 |
| #1242 | ✅ merged + closed | #1250 |
| #1240 | ⛔ **設計判断がユーザー必須のため defer(完了条件 4 の escape hatch)** — 下記ブロッカー参照 | — |

**結果**: 対象 10 件中 9 件が merged + closed となった。#1240 のみユーザー必須の設計判断により defer した。
follow-up Issue は #1247(#1232 の P2 終端一本化)と #1249(#1239 の P2 sibling 非 atomic 経路移行)である。

## #1240 ブロッカー(完了条件 4 に基づく defer)

2026-07-07 の調査結果により、#1240 は自律実装できない **ユーザー/アーキテクチャ設計判断** を含むと判明した。完了条件 4 の escape hatch に従い、本ゴールの完了扱いから外して他 9 件を完遂する。

### 介入点(調査で確定済み・実装可能な部分)
- 未マッチ集合は `annotation_record.py:1326` の `missing_tags` で計算済みだが使い捨てになっている。また #1239 で全件登録が成功するようになったため、`batch_resolve_tag_ids` の戻り値(`dict[str, int|None]`)だけでは「既存タグ」と「今回 auto-create したタグ」を区別できない。
- 画像コンテキスト付きの `ErrorRecord` を生成できる唯一の箇所は `db_manager._import_associated_files`(`db_manager.py:418-465`、`image_id`・raw tags・`tag_id_cache` が揃う点)である。
- トリアージアクションの適用先には既存 API で足りる。タグ採用は `classify_manual_tag` + `add_tag_to_images_batch`、キャプション採用は `save_captions`、破棄は `mark_error_resolved` を使う。
- エラータブの既存資産(`ErrorRecord`、`error_triage_service`、`errors_triage_widget`、`error_notification_widget`)は `operation_type='tag_triage'` に相乗りすることでスキーマ変更なしに再利用できる。`image_link_clicked` は定義済みだが未配線(dead signal)であり、`_on_registration_view_image_requested` の先例に沿って配線できる。

### ユーザー設計判断が必須の未決事項(ブロッカー)
1. **【最重要】register-then-flag vs flag-instead-of-register**: #1239 により未マッチタグは atomic に auto-register されるようになった。トリアージ候補の扱いとして、(a)登録後に `ErrorRecord` で flag する案と、(b)登録前に intercept して flagged を `tag_db` へ登録しない案のどちらを採るか決める必要がある。(a)では共有 `genai-tag-db-tools` の `tag_db` にゴミ文字列・URL・文章が永続化し、破棄しても LoRAIro 側の `Tag` を soft-reject するだけで `tag_db` エントリが残るため、Issue が警告する「汚染」が起きる。(b)は汚染を防げるが、`_register_missing_tags` と `_import_associated_files` の制御フロー変更を要する。**共有 8.4GB の `tag_db` に対する不可逆汚染に関わるデータ完全性の判断** であるため、実装者が独断すべきではない。
2. **トリアージ振り分け heuristic の閾値**: Issue は「長さ × 存在の自動判定は危険」と警告している(正当な長文タイトルタグと base DB のゴミが混在するため)が、キューへ載せる基準自体は必要である。word 数、文字数、空白比率の具体値はプロダクト判断を要する。
3. **スコープ(3 つの呼び出し点)**: `.txt` sidecar(`registration_worker`)のみを対象とするか、provider JSONL import と AI annotation save も含めるか。
4. その他の詳細設計: グループ分類(`error_type` 単位かソースファイル単位か)、UI action signal の形、`image_link_clicked` の配線先(先例あり)。

### 推奨アプローチ(ユーザー承認待ち)
汚染回避を優先し、**(b)flag-instead-of-register** を推奨する。`_register_missing_tags` で heuristic に一致した文字列の登録をスキップして `tag_id=None` を `db_manager` へ返し、`_import_associated_files` が `image_id` 付きのトリアージ `ErrorRecord` を作成する(タグは保存しない)。heuristic は保守的に「未マッチ かつ(語数 >= 4 または 空白を含み文字数 >= 30)」程度から開始する。上記 1〜3 をユーザーが確定すれば着手できる。

## 推奨実行順

### Phase 1 — バグ・配線(LoRAIro 側のみ・独立・低リスク)
1. **#1236**: 幻の `japanese` 重複行を解消する(dict の alias 重複排除、独立)。
2. **#1235**: 言語セレクタの alias 重複を解消する。#1236 と同じ `language_keys.py` 家系であり同一ファイル領域のため、worktree を分ける場合は直列化するか、1 PR にまとめて処理する。
3. **#1237**: 翻訳の付け替えと削除を配線する(CLI サブコマンドと GUI 導線を既存 public API に接続)。
4. **#1234**: タグ種別編集 combo を editable 化し、`update_tags_type_batch` へ配線する(#1242 の前提)。
5. **#1232**: 右クリック翻訳ポップアップを非同期化(worker 化)する。#1237 と同じ右クリック→翻訳ポップアップ領域のため近接して処理する。tag DB クエリコストが要因かは実測で切り分ける。

### Phase 2 — DB 並行バグ(調査重視・設計判断や ADR の可能性あり)
6. **#1239**: FK constraint の並行アクセス問題を解決する。systematic-debugging で実行時ログを直接確認して根本原因を falsify・確定する。cross-worker 排他が設計変更を要する場合は ADR を起票し、ユーザー判断へエスカレーションする(完了条件 4 の escape hatch)。submodule を触る場合は two-repo フローを用いる。

### Phase 3 — feature・タグ chip 種別デザイン更新(brainstorming 先行)
7. **#1234 完了後に #1242**: カスタム種別の UI を拡張する。
8. **#1233 + #1241 の一体設計**: 色分けとグリフ+ストライプ+トグルは同じ chip 描画層に属する。別々に作ると描画が二重になり手戻りが生じるため、brainstorming で 1 つの設計に束ねてから実装する。
9. **#1239 完了後に #1240**: 未マッチタグの人間レビューキュー(エラータブ拡張)を実装する。#1239 で得た「取り込み時に未マッチ/登録失敗するタグ」の機構を前提に、トリアージ UI を brainstorming で設計してから着手する。

## 確定した実行方針(2026-07-07 ヒアリング)

- **マージ権限**: CI green、Codex レビュー完了、blocking 指摘なしの 3 条件を満たせば自律的に squash merge する(`agent-pr-autoloop` 準拠)。実機確認は事後に行う。P1(#1239)のデータ完全性修正も同じ基準で自律マージ対象とする。
- **feature 方針**: バグ・配線・性能(#1232 / #1234 / #1235 / #1236 / #1237 / #1239)を優先する。デザイン更新系(#1233 / #1241 / #1242)と人間レビューキュー(#1240)は superpowers の `brainstorming` skill で設計合意してから実装し、1 ループに混ぜず段階を分ける。
- **ループ粒度**: 10 件を 1 つの自律ループで連続処理し、上限 50 ターンまたは全件完了で停止する。

## 関連 Issue

- #1238(エクスポート多言語・スコープ外)
- #1206(tag DB 並行アクセス `"interrupted"`)、#1221(応答なし watchdog)、#1225(`user_tags.sqlite` は rollback-journal モード)、#1212(tag 解決重複)、#983(タグ種別デザイン)、#989 / #993 / #976 / #998(翻訳管理)

---

# 完了条件(`/goal` に渡す条件文)

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

# 実行ブリーフ(初回プロンプト)

## タスク

`docs/plans/goal-remaining-gui-issues.md` の対象 10 Issue を推奨実行順(Phase 1 バグ・配線・性能 → Phase 2 #1239 DB 並行バグ → Phase 3 feature・デザイン更新)で解決する。各 Issue は `.agents/worktree/` 配下の worktree と PR で実装し、CI-equivalent filter を通過させてから PR を起票する。その後 `agent-pr-autoloop` で CI と Codex レビューを回し、安全であれば自律的に squash merge する。

- **Phase 1(LoRAIro 側のみ・調査確定済み、submodule 変更は不要)**:
  - #1236: fan-out dict を `language_alias_keys()` で重複排除する。
  - #1235: 言語セレクタでも同じ alias 重複排除を適用する(#1236 と同じ `utils/language_keys.py` 家系のため近接処理する)。
  - #1237: 既存の `core_api.delete_user_translation` / `suppress_translation` / `unsuppress_translation` を CLI サブコマンドと `TranslationFixDialog` の GUI 導線に配線する。
  - #1234: `TagTypeEditDialog` の combo を `setEditable(True)` にし、`update_tags_type_batch` に配線する。
  - #1232: `list_translation_candidates` の同期呼び出しをメインスレッド外へ移す(worker 化と非同期プリフェッチ)。tag DB クエリコスト(#1203 系)が要因かどうかは investigation で切り分ける。
- **Phase 2(#1239)**:
  - 静的読解による推測で修正せず、まず根本原因の確証を得る。systematic-debugging で実行時ログ(`logs/lorairo.log`、`logs/image-annotator-lib.log`)を直接確認し、`DatabaseRegistrationWorker` と `RefinementWorker` による並行 `user_tags.sqlite` アクセスが FK 失敗・TAGS 行消失・翻訳パッチ孤立を引き起こす機構を falsify・確定してから修正する。
  - cross-worker 排他が設計変更を要する場合は ADR を起票し、ユーザー判断へエスカレーションする(完了条件 4 の escape hatch)。
  - `genai-tag-db-tools` の `repository.py`(`create_tag` / `update_tag_status` のトランザクション境界)を触る場合は two-repo フロー(`CI-EQUIV-TESTED` marker と submodule pin bump)を用いる。
- **Phase 3(feature・デザイン更新・brainstorming 先行)**:
  - #1234 完了後に #1242(カスタム種別の UI 拡張)へ着手する。
  - #1233(色分け)と #1241(グリフ+ストライプ+「種別で分ける」トグル)は同じ chip 描画層であるため、描画二重による手戻りを防ぐ目的で brainstorming により 1 つの設計へ束ねてから実装する。
  - #1239 完了後に #1240(未マッチタグの人間レビューキュー=エラータブ拡張)へ着手する。#1239 で得た「取り込み時に未マッチ/登録失敗するタグ」の機構を前提に、トリアージ UI(タグ/キャプション/破棄)を brainstorming で設計してから実装する。
- 各 Issue の完了時には、本計画ファイルの該当行へ PR リンクと結果を追記する。

## サブエージェント委譲方針(必須スロット・省略しない)

- 根本原因調査(該当モジュールの grep、関連ファイル読み込み、ログ解析)は `investigation` または `general-purpose` サブエージェントに委譲し、結論だけを受け取る。メインコンテキストにファイルダンプを溜めない。
- 独立した Issue の着手は可能な範囲で並列サブエージェントへ fan-out し、worktree を分離する。ただし #1235 ⇄ #1236(同一ファイル領域)、#1233 ⇄ #1241(同一描画層)、#1234 → #1242(依存関係あり)は直列を維持する。
- CI-equivalent filter のテスト実行は `test-runner` サブエージェントへ委譲し、要約のみを受け取る。
- PR レビュー観点の確認は `code-reviewer` / `security-reviewer` / `db-schema-reviewer` サブエージェントへ委譲する(#1239 は `db-schema-reviewer` と `query-analyzer` を活用する)。
- メインループは「委譲先の結論を統合して次の一手を決める」役割に徹する。
- 調査および機械的作業のサブエージェントは `model=sonnet` とし、設計判断が必要な箇所のみ `opus` を指定する。

## スコープ制約

- 実装は必ず `.agents/worktree/` 配下の worktree と PR で行う(`.claude/rules/git-workflow.md`)。`main` への直接 push は禁止する。
- `tests/` 配下の既存テストは必要範囲外を書き換えず、公開 import パスも変えない。
- #1232 / #1234 / #1235 / #1236 / #1237 は LoRAIro 側の配線のみで解決可能なため、submodule(`genai-tag-db-tools`)を触らない。#1239 のみ、必要であれば two-repo フローで submodule を触ってよい。#1240 は brainstorming の設計しだいとする。
- `.github/workflows/**`、権限・secret 設定、Git 履歴改変は自動修正の対象外とし、必要であればエスカレーションする。
- 自動マージは CI green、Codex レビュー完了、blocking 指摘なしのすべてを満たす場合のみ行う。P1(#1239)のデータ完全性修正も同じ基準で自律マージしてよい(ヒアリングで承認済み)。
- デザイン更新系(#1233 / #1241 / #1242)と人間レビューキュー(#1240)は brainstorming の設計合意を経ずに実装着手しない。設計判断がユーザー必須と判明した場合は escape hatch でエスカレーションする。
