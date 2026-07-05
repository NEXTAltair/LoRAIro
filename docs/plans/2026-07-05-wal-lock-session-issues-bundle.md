# 2026-07-05 セッション積み残し: WAL ロック調査から派生した Issue 群の解決プロンプト

このセッション（#1165 WAL per-connection 撤去 → #1169 クロス OS ロック調査 → 実機確認）で
派生したオープン Issue をまとめて解決するための実行プロンプト。次セッションにそのまま渡す。

## 前提（確定事項・変更しない）

- **#1165 merge 済 / #1169 は方式A で確定・クローズ**: WAL 維持、`journal_mode=DELETE` 移行は却下。
  エージェント CLI は GUI と同一 OS（Windows ネイティブ）で動かす。「Windows GUI × コンテナ CLI」
  同時アクセスは非サポート。**DELETE 化を再提案しない（方式A が SSoT）**。
- 実装は必ず `.agents/worktree/` 配下の worktree + PR（`.claude/rules/git-workflow.md`）。
- PR 起票前に CI-equivalent filter を pass させる（`.claude/rules/testing.md`）。
- 既存の通っているテストは必要な範囲以外書き換えない。

## 対象 Issue（トリアージ済み）

| # | 種別/repo | 内容 | 優先 | 依存/備考 |
|---|---|---|---|---|
| #1171 | bug / LoRAIro | GUI: CLI の DB 書込がプレビュー再表示で反映されない。根本確定 = `gui/state/dataset_state.py:547 _ensure_annotations_loaded` が `"tags"` キーで早期 return（キャッシュ無効化なし） | P1 | 方針=明示リロード + 対象指定無効化API（下記「設計決定」）。実 GUI 反映の最終確認は Windows 実機（人間）。エージェントは実装 + unit まで |
| #1172 | bug / 帰属未確定 | GUI: user_tags.sqlite 翻訳追加が起動中 GUI に反映されない | P2 | **根本未特定**。主張の `overlay_reader.py:403` は毎回 fresh query でキャッシュ無し（確認済）。真因候補=tagDB エンジンの接続プール WAL スナップショット / LoRAIro 側 cached reader / usage cache(#1085)。**まず調査 writeup、盲目的 fix 禁止** |
| #1173 | feat / LoRAIro | `tags translations` サブコマンド追加（翻訳の参照・登録を CLI で完結） | P1(機能) | IF=`translations show/add` + `tags alias`（下記「設計決定」）。`tags add` 同様の dry-run 規約。API= `search_tags`/`register_tag`/`write_user_translation`/`set_preferred_translation`/`get_translations_batch` |
| #1174 | bug / LoRAIro | `tags add` がタグ DB 未登録文字列を `tag_id=null` で無言保存 | P2 | 方針=refinement 検索で分類し「既知 alias は自動解決 / typo 候補は surface / 真の新タグは user DB 登録」（下記「設計決定」）。根本の readback は tagdb #124 |
| #1175 | 混在 / LoRAIro | (a) `.claude/settings.json` の `UV_PROJECT_ENVIRONMENT=/workspaces/...` が Windows+Git Bash で化けて uv 死 (b) project 名解決エラー文言 (c) `project list` WARNING 13行スパム (d) `images show` 位置引数不可。+ #1169 由来 deferred guard（disk I/O error 時の実行環境メッセージ） | (a)P1/他P3 | (a) を最優先で分離。(a) は同一OS運用（方式A）の前提を壊す環境ブロッカー |
| #1176 | bug / LoRAIro | テスト実行が本番 `logs/lorairo-cli.log` を汚染（ERROR 196件中195件が pytest 由来）。原因 = `cli/main.py` の固定 `DEFAULT_CLI_LOG_PATH` | P2 | CLI ログパスを env/config 上書き可能に + test 隔離ケース追加 |
| genai-tag-db-tools#124 | bug / **別 repo** | `create_tag`: bulk_insert 直後の `get_tag_id_by_name` 読み戻し失敗（正規化不一致で `TAG_ID_NOT_FOUND_AFTER_INSERT`） | P2 | **submodule 側リポジトリで対応**。LoRAIro worktree では触らない |

## 推奨実行順

1. **#1175(a)** 環境ブロッカー（settings.json の OS 別 env 分岐）
2. **#1176** ログ汚染（小・独立・完全自動検証可）
3. **#1174** tag_id=null の surface（小・tagdb#124 とリンク）
4. **#1173** 翻訳 CLI サブコマンド（機能・エージェント翻訳の enabler）
5. **#1171** GUI キャッシュ無効化（実装 + unit、実機反映確認は人間へ）
6. **#1172** 調査 writeup（根本特定してから別途 fix / 必要なら tagdb repo へ移送）

## 設計決定の詳細（#1171 / #1173 / #1174）

着手時に Accepted な軽量 ADR を PR 同梱する（Proposed のまま main に出さない）。

### #1171 キャッシュ無効化方針

現状: `dataset_state.py:547 _ensure_annotations_loaded` は `"tags"` キーがあれば早期 return。
一度読んだ画像のアノテは検索で dict 再構築されるまで再照会されない。

**罠（実機で確定）: WAL 書き込みは `.db` 本体の mtime を変えない**（-wal に入り checkpoint まで
`.db` mtime 不変）。→ **`.db` mtime 基準の無効化は WAL 併用で機能しないので採用しない**。

**決定: 明示リロード + 対象指定無効化 API を基礎にする。**
- `invalidate_annotations(image_id)`（または選択画像分）でキャッシュ dict から該当を落とす API を用意
- GUI に「再読込」操作（ボタン/ショートカット/メニュー）を足し、選択画像のキャッシュをクリア→再照会
- #965 の再選択最適化は維持（毎選択 DB 往復にはしない）。ADR 0067 の「手動リロード」と整合
- 余裕があれば focus 復帰時の一括無効化を利便で追加（任意）
- unit: 無効化 API 後の再取得で最新値が入ることを検証。実 GUI 反映は merge 後に人間が確認

### #1173 翻訳 CLI インターフェース

`tags add` と同じ規約（dry-run 既定 / `--apply` / JSON 出力 / `show` は count-first）に揃える。

```
# 参照 (read-only)
lorairo-cli tags translations show --image-ids 1052,1082    # 画像のタグの翻訳状況 (ja/en, missing)
lorairo-cli tags translations show --tags "cat,dog"

# 登録 (dry-run 既定, --apply で書込)
lorairo-cli tags translations add --tag "european architecture" --lang ja --text "ヨーロッパ建築" [--preferred] --apply

# typo → 正タグの alias を user DB に記録
lorairo-cli tags alias --from "europian architecture" --to "european architecture" --apply
```

- 言語キー: 入力は `ja`/`en` で受け、書き込みは一貫形。読みは `ja`/`en` と `japanese`/`english`
  両キーを集約（[[reference_tagdb_translation_language_key_mixed]]）。正のキーは ADR で確定
- `add` の tag_id 解決は #1174 と同経路（無ければ user DB 登録）。登録失敗（tagdb #124 の edge）は
  tag_id=null + 警告に fallback して静かに落とさない
- 使う public API: `search_tags`/`search_tags_batch`, `register_tag`, `write_user_translation`,
  `set_preferred_translation`, `get_translations_batch`/`get_preferred_translations_batch`

### #1174 未登録タグの扱い（refinement 分類で誘導）

tag DB は既に refinement 機構を持つ（`alias_tag` / `typo_alias_candidate` /
`ambiguous_alias_candidates` / `non_preferred_tag`、`TagSearchRequest.partial/resolve_preferred`、
`TagRegisterRequest.alias/preferred_tag_id`）。これを CLI から呼ぶ薄い層で実現する。

`tags add` が未知タグに当たったら refinement 検索で分類:

| DB 分類 | 挙動 |
|---|---|
| 完全一致 | その tag_id を使う |
| `alias_tag`（既知 alias） | `resolve_preferred` で preferred tag_id へ**自動解決** |
| `typo_alias_candidate`（typo 候補） | 候補を **surface**（自動適用しない）。確定は人間/エージェント |
| `ambiguous_alias_candidates` | 複数候補を surface、決め打ちしない |
| 該当なし（真の新タグ） | **user DB (format 1000) に新規登録** |

- **typo 候補を自動 alias 化しない**（[[project_993_translation_falsepositive_fix_design]] の alias 偽陽性教訓）。
  既知 `alias_tag` のみ自動解決、候補は誘導提示に留める
- 空/無効に正規化されるトークン（`clean_format` 後が空/別形）は登録しない（#124 回避・user DB 汚染防止）
- `register_tag` が user DB (format 1000) をターゲットにすることを実装時に確認（base DB は読み取り専用）
- CLI JSON 出力に `typo_alias_candidate` 等の候補と、登録失敗時の tag_id=null を **surface**（現状は無言）
- 新規 alias の記録は `tags alias` コマンド（#1173）で `register_tag(alias=True, preferred_tag_id=...)`
7. **#1175(bcd)** CLI UX papercut ＋ deferred guard（まとめて）
8. **#124** は genai-tag-db-tools repo で別途

## エージェントが自律検証できる範囲 / 人間の実機確認が要る範囲

- **自律で完結（実装+CI-equiv+PR）**: #1175(a)(bcd), #1176, #1174, #1173, #1171(実装+unit)
- **人間の Windows 実機確認が必要（コンテナからは検証不能）**:
  - 検証① GUI「再検索」で CLI 書込が反映されるか → #1171 の done 判定
  - 検証② 翻訳 overlay がどの段階（再検索/GUI 再起動）で反映するか → #1172 の真因層特定
  - 検証③ `tag_id=null` タグを GUI が表示するか → #1174
  - これらは評価器（Haiku）からも観測不能なので **/goal の達成条件に入れない**

## 確定した実行前決定（2026-07-05）

- **自動マージ = 許可**（全 Issue、Codex レビュー ~8分待ち後に squash merge 可）。
- **実機検証は不要**: エージェントは実装 + merge まで。GUI 反映等の実機確認は merge 後に人間が行う。
  よって人間ゲート①②③は /goal 条件に含めない。
- **#1175(a) = 絶対パスをやめる**。ただし単純削除は不可（下記制約）。
- #1171 キャッシュ方針 / #1173 翻訳 CLI IF は着手時に設計決定（軽量 ADR は Accepted で PR 同梱、
  Proposed のまま main に出さない）。

### #1175(a) の実装制約（重要）

共有 `.claude/settings.json`（git 追跡・クロス OS）から `UV_PROJECT_ENVIRONMENT` の OS 固有絶対パスを外す。
ただし**コンテナ側は保持が必須**（消すと (1) worktree の venv 共有が壊れ 9p 低速化、(2)
`hook_pre_commands.py` の worktree gate が `os.environ` に `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv`
が無いと worktree 内 `uv run` をブロックする）。よって:

- コンテナ: `devcontainer.json` env か `.claude/settings.local.json`（gitignore 済）に `/workspaces/LoRAIro/.venv` を保持
- Windows: 未設定（uv 既定）or 自分の settings.local.json に `C:\LoRAIro\.venv`
- 共有 settings.json: OS 固有絶対パスを持たない。allowlist の `Bash(UV_PROJECT_ENVIRONMENT=/workspaces/... uv *)`
  も併せて見直す
- `.claude/rules/git-workflow.md` / `parallel-execution.md` の該当記述を更新

## /goal 用 完了条件（コピペ用・確定版）

```
/goal LoRAIro の Issue #1176, #1174, #1173, #1175, #1171 をそれぞれ .agents/worktree/ 配下の
worktree + PR で解決し、各 PR で `.venv/bin/pytest -m "not gui_show and not calls_real_webapi
and not downloads_and_runs_model and not slow" --timeout=120` を実行して 0 failed を出力で示し、
`gh pr checks` 全 pass を確認して squash merge し、`gh issue view <n> --json state` が CLOSED を
出力で示す。#1172 は tag DB の write→read 反映をコンテナ内の 2 接続で再現調査し、根本原因を
特定できたら fix を同様に PR+merge、特定できなければ調査結果を Issue にコメントして残す（クローズしない）。
制約: 各 Issue は独立 PR / 既存の通っているテストは必要範囲外で変更しない /
#1175(a) は共有 .claude/settings.json から OS 固有絶対パスを外すが、コンテナの worktree venv 共有と
hook gate が壊れないよう UV_PROJECT_ENVIRONMENT は devcontainer env か settings.local.json で
/workspaces/LoRAIro/.venv を保持する / #1171 は「明示リロード + 対象指定無効化API」で実装（.db mtime
基準は WAL で機能しないので使わない）/ #1174 は refinement 検索で分類し既知 alias は自動解決・typo 候補は
surface・真の新タグは user DB 登録（typo の自動 alias 化はしない・空正規化は登録しない）/ #1173 は
translations show/add + tags alias を追加し #1174 と同じ登録経路を使う / #1171 のキャッシュ方針と
#1173 の翻訳 CLI IF は Accepted な軽量 ADR を PR 同梱する / genai-tag-db-tools#124 は対象外 /
DELETE 化は提案しない（方式A が SSoT）/ 実機 GUI 検証は merge 後に人間が行うので条件に含めない。
達成できなければ 45 ターンで停止し、未完 Issue を列挙して報告する。
```

### この条件に置いた仮定

- 検証コマンド = CI-equivalent filter（`.claude/rules/testing.md` の LoRAIro Unit/Integration 行）。
- 停止上限 = 45 ターン（6 Issue × worktree+PR+CI+自動 merge 保守の保守値）。
- #1171 は「実装 + unit pass + merge」を done とする（実 GUI 反映は merge 後に人間確認）。
- #1172 は根本を特定できた時のみ fix、できなければ調査記録で残す（盲目 fix しない）。
- #1173 の IF は `tags translations show/add` を仮。実装前に `check-existing` で
  genai-tag-db-tools の write API（`write_user_translation` / `get_translations_batch`）を確認する。

## 一括ではなく分割で回す場合

40 ターン一括が重い / 途中レビューを挟みたいなら、優先バッチごとに分ける:

```
/goal Issue #1175(a settings.json OS別env) と #1176(ログ汚染) を worktree+PR で解決し、
各 PR で CI-equiv filter 0 failed を出力で示し squash merge、gh issue view で CLOSED を示す。
既存テストは必要範囲外で変更しない。main 直 push しない。15 ターンで停止。
```

を先に回し、pass 後に #1174→#1173→#1171→#1172 の順で同型の条件を作って継続する。
