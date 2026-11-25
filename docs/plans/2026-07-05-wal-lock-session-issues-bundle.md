# 2026-07-05 セッション積み残し:WAL ロック調査から派生した Issue 群の解決プロンプト

本ドキュメントは、2026-07-05 のセッション(#1165 の WAL per-connection 撤去 → #1169 のクロス OS ロック調査 → 実機確認)で派生したオープン Issue をまとめて解決するための実行プロンプトである。次セッションへそのまま渡すことを想定している。

## 前提(確定事項・変更しない)

- **#1165 はマージ済み、#1169 は方式 A で確定・クローズ済みである**: WAL を維持し、`journal_mode=DELETE` への移行は却下した。エージェント CLI は GUI と同一 OS(Windows ネイティブ)で動かし、「Windows GUI × コンテナ CLI」の同時アクセスは非サポートとする。**DELETE 化は再提案しないこと(方式 A が SSoT である)**。
- 実装は必ず `.agents/worktree/` 配下の worktree と PR で行う(`.claude/rules/git-workflow.md`)。
- PR 起票前に CI-equivalent filter を通過させる(`.claude/rules/testing.md`)。
- 既存の通っているテストは、必要な範囲以外を書き換えない。

## 対象 Issue(トリアージ済み)

| # | 種別 / repo | 内容 | 優先 | 依存 / 備考 |
|---|---|---|---|---|
| #1171 | bug / LoRAIro | GUI で CLI の DB 書き込みがプレビュー再表示に反映されない。根本原因は `gui/state/dataset_state.py:547` の `_ensure_annotations_loaded` が `"tags"` キーの存在で早期 return し、キャッシュ無効化を行わない点である | P1 | 方針は明示リロードと対象指定の無効化 API(下記「設計決定」参照)。実 GUI での最終確認は Windows 実機で人間が行い、エージェントは実装と unit テストまで担当する |
| #1172 | bug / 帰属未確定 | GUI で `user_tags.sqlite` への翻訳追加が起動中 GUI に反映されない | P2 | **根本原因は未特定**。仮説の `overlay_reader.py:403` は毎回 fresh query でキャッシュがないことを確認済みである。真因候補は tagDB エンジンの接続プール WAL スナップショット、LoRAIro 側の cached reader、usage cache(#1085)である。**まず調査 writeup を行い、盲目的な修正は禁止とする** |
| #1173 | feat / LoRAIro | `tags translations` サブコマンドを追加し、翻訳の参照・登録を CLI で完結させる | P1(機能) | IF は `translations show/add` と `tags alias`(下記「設計決定」参照)。`tags add` と同じ dry-run 規約に従う。使用 API は `search_tags` / `register_tag` / `write_user_translation` / `set_preferred_translation` / `get_translations_batch` |
| #1174 | bug / LoRAIro | `tags add` がタグ DB 未登録の文字列を `tag_id=null` のまま無言保存する | P2 | refinement 検索で分類し、既知 alias は自動解決、typo 候補は surface、真の新タグは user DB 登録とする(下記「設計決定」参照)。根本の readback 問題は tagdb #124 |
| #1175 | 混在 / LoRAIro | (a)`.claude/settings.json` の `UV_PROJECT_ENVIRONMENT=/workspaces/...` が Windows + Git Bash で化けて `uv` が落ちる (b)project 名解決のエラー文言 (c)`project list` の WARNING 13 行スパム (d)`images show` の位置引数不可。加えて #1169 由来の deferred guard(disk I/O error 時の実行環境メッセージ) | (a)P1 / 他 P3 | (a)は同一 OS 運用(方式 A)の前提を壊す環境ブロッカーのため、最優先で分離して対応する |
| #1176 | bug / LoRAIro | テスト実行が本番の `logs/lorairo-cli.log` を汚染している(ERROR 196 件中 195 件が pytest 由来)。原因は `cli/main.py` の固定 `DEFAULT_CLI_LOG_PATH` である | P2 | CLI ログパスを env / config で上書き可能にし、テスト隔離ケースを追加する |
| genai-tag-db-tools#124 | bug / **別 repo** | `create_tag` で bulk_insert 直後の `get_tag_id_by_name` による読み戻しが失敗する(正規化不一致による `TAG_ID_NOT_FOUND_AFTER_INSERT`) | P2 | **submodule 側リポジトリで対応する**。LoRAIro の worktree では触らない |

## 推奨実行順

1. **#1175(a)**: 環境ブロッカー(`settings.json` の OS 別 env 分岐)
2. **#1176**: ログ汚染(小規模・独立・完全自動検証が可能)
3. **#1174**: `tag_id=null` の surface(小規模・tagdb #124 と関連)
4. **#1173**: 翻訳 CLI サブコマンド(機能追加・エージェント翻訳の基盤)
5. **#1171**: GUI キャッシュ無効化(実装と unit テストまで。実機での反映確認は人間へ引き継ぐ)
6. **#1172**: 調査 writeup(根本原因を特定してから別途修正し、必要であれば tagdb repo へ移送する)
7. **#1175(bcd)**: CLI の UX 改善と deferred guard(まとめて対応)
8. **#124**: `genai-tag-db-tools` リポジトリで別途対応

## 設計決定の詳細(#1171 / #1173 / #1174)

着手時に Accepted 状態の軽量 ADR を作成し、PR へ同梱する(Proposed のまま main に出さない)。

### #1171 キャッシュ無効化方針

現状では `dataset_state.py:547` の `_ensure_annotations_loaded` が `"tags"` キーの存在を確認した時点で早期 return する。そのため、一度読み込んだ画像のアノテーションは、再検索で dict が再構築されるまで再照会されない。

**注意点(実機で確定済み)**: WAL モードの書き込みは `-wal` ファイルへ入るため、チェックポイントが走るまで `.db` 本体の mtime が変化しない。したがって、**`.db` の mtime を基準とする無効化は WAL 併用環境で機能しないため採用しない**。

**決定**: 明示リロードと対象指定の無効化 API を基礎とする。

- `invalidate_annotations(image_id)`(または選択画像分)でキャッシュ dict から該当項目を落とす API を用意する。
- GUI に「再読込」操作(ボタン、ショートカット、メニュー)を追加し、選択画像のキャッシュをクリアしてから再照会する。
- #965 の再選択最適化は維持し、毎選択時の DB 往復は避ける。この方針は ADR 0067 の「手動リロード」と整合する。
- 余裕があれば、利便性のためフォーカス復帰時の一括無効化を任意で追加してよい。
- unit テストでは、無効化 API 呼び出し後の再取得で最新値が入ることを検証する。実 GUI への反映はマージ後に人間が確認する。

### #1173 翻訳 CLI インターフェース

`tags add` と同じ規約(dry-run を既定とし、`--apply` で書き込み、JSON 出力対応、`show` は count-first)に揃える。

```
# 参照 (read-only)
lorairo-cli tags translations show --image-ids 1052,1082    # 画像のタグの翻訳状況 (ja/en, missing)
lorairo-cli tags translations show --tags "cat,dog"

# 登録 (dry-run 既定, --apply で書込)
lorairo-cli tags translations add --tag "european architecture" --lang ja --text "ヨーロッパ建築" [--preferred] --apply

# typo → 正タグの alias を user DB に記録
lorairo-cli tags alias --from "europian architecture" --to "european architecture" --apply
```

- **言語キー**: 入力は `ja` / `en` で受け付け、書き込みは一貫した形式に揃える。読み取り時は `ja` / `en` と `japanese` / `english` の両キーを集約する(`[[reference_tagdb_translation_language_key_mixed]]`)。正とするキーは ADR で確定する。
- **`add` の `tag_id` 解決**: #1174 と同じ経路を使い、存在しなければ user DB へ登録する。登録失敗(tagdb #124 のエッジケース)時は黙って落とさず、`tag_id=null` と警告へフォールバックする。
- **使用する public API**: `search_tags` / `search_tags_batch`、`register_tag`、`write_user_translation`、`set_preferred_translation`、`get_translations_batch` / `get_preferred_translations_batch`。

### #1174 未登録タグの扱い(refinement 分類による誘導)

tag DB にはすでに refinement 機構(`alias_tag`、`typo_alias_candidate`、`ambiguous_alias_candidates`、`non_preferred_tag`、`TagSearchRequest.partial/resolve_preferred`、`TagRegisterRequest.alias/preferred_tag_id`)が存在する。これを CLI から呼び出す薄い層で実現する。

`tags add` が未知のタグに遭遇した場合は refinement 検索で分類し、以下のとおり振る舞う。

| DB 分類 | 挙動 |
|---|---|
| 完全一致 | その `tag_id` を使用する |
| `alias_tag`(既知 alias) | `resolve_preferred` で preferred の `tag_id` へ **自動解決** する |
| `typo_alias_candidate`(typo 候補) | 自動適用せず候補を **surface** する。確定は人間またはエージェントが行う |
| `ambiguous_alias_candidates` | 決め打ちせず複数候補を surface する |
| 該当なし(真の新タグ) | **user DB(format 1000)へ新規登録** する |

- **typo 候補の自動 alias 化は禁止**: `[[project_993_translation_falsepositive_fix_design]]` の alias 偽陽性の教訓に従い、既知の `alias_tag` のみ自動解決する。typo 候補は誘導提示にとどめる。
- **空・無効トークンの登録禁止**: `clean_format` 後に空または別形になるトークンは登録しない(#124 の回避および user DB 汚染防止のため)。
- **登録先の確認**: base DB は読み取り専用であるため、`register_tag` が user DB(format 1000)を対象とすることを実装時に確認する。
- **JSON 出力での可視化**: 現状は無言で処理されているため、CLI の JSON 出力に `typo_alias_candidate` などの候補や、登録失敗時の `tag_id=null` を明示的に出力する。
- **新規 alias の記録**: `tags alias` コマンド(#1173)から `register_tag(alias=True, preferred_tag_id=...)` を呼び出して記録する。

## エージェントが自律検証できる範囲と人間の実機確認が必要な範囲

- **自律で完結できる範囲(実装 + CI-equivalent + PR)**: #1175(a)(bcd)、#1176、#1174、#1173、#1171(実装 + unit テスト)
- **人間の Windows 実機確認が必要な範囲(コンテナからは検証不能)**:
  - 検証①: GUI の「再検索」で CLI 書き込みが反映されるか(#1171 の完了判定)
  - 検証②: 翻訳 overlay がどの段階(再検索/GUI 再起動)で反映されるか(#1172 の真因層特定)
  - 検証③: `tag_id=null` のタグを GUI が表示するか(#1174)
  - これらは評価器(Haiku)からも観測不能であるため、**`/goal` の達成条件には含めない**。

## 確定した実行前決定(2026-07-05)

- **自動マージ**: 全 Issue で許可する(Codex レビューを約 8 分待った後に squash merge 可能)。
- **実機検証の扱い**: エージェントは実装からマージまでを担当し、GUI 反映などの実機確認はマージ後に人間が行う。したがって人間ゲート①②③は `/goal` 条件に含めない。
- **#1175(a)の方針**: 絶対パスの直書きをやめる。ただし、後述の制約があるため単純削除は不可とする。
- **ADR の扱い**: #1171 のキャッシュ方針と #1173 の翻訳 CLI IF は着手時に設計決定し、Accepted な軽量 ADR として PR に同梱する(Proposed のまま main へ出さない)。

### #1175(a)の実装制約(重要)

git 追跡対象かつクロス OS 共有である `.claude/settings.json` から、`UV_PROJECT_ENVIRONMENT` の OS 固有絶対パスを取り除く。ただし **コンテナ側での保持は必須** である。削除すると(1)worktree の venv 共有が壊れて 9p 上で低速化し、(2)`hook_pre_commands.py` の worktree gate が `os.environ` に `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` を見つけられず worktree 内の `uv run` をブロックするためである。

- **コンテナ**: `devcontainer.json` の env、または gitignore 済みの `.claude/settings.local.json` に `/workspaces/LoRAIro/.venv` を保持する。
- **Windows**: 未設定(`uv` 既定)とするか、各自の `settings.local.json` に `C:\LoRAIro\.venv` を設定する。
- **共有 `settings.json`**: OS 固有の絶対パスを持たせない。あわせて allowlist の `Bash(UV_PROJECT_ENVIRONMENT=/workspaces/... uv *)` も見直す。
- **ルール文書**: `.claude/rules/git-workflow.md` および `parallel-execution.md` の該当記述を更新する。

## `/goal` 用 完了条件(コピペ用・確定版)

```
/goal LoRAIro の Issue #1176, #1174, #1173, #1175, #1171 をそれぞれ .agents/worktree/ 配下の
worktree + PR で解決し、各 PR で `.venv/bin/pytest -m "not gui_show and not calls_real_webapi
and not downloads_and_runs_model and not slow" --timeout=120` を実行して 0 failed を出力で示し、
`gh pr checks` 全 pass を確認して squash merge し、`gh issue view <n> --json state` が CLOSED を
出力で示す。#1172 は tag DB の write→read 反映をコンテナ内の 2 接続で再現調査し、根本原因を
特定できたら fix を同様に PR+merge、特定できなければ調査結果を Issue にコメントして残す(クローズしない)。
制約: 各 Issue は独立 PR / 既存の通っているテストは必要範囲外で変更しない /
#1175(a) は共有 .claude/settings.json から OS 固有絶対パスを外すが、コンテナの worktree venv 共有と
hook gate が壊れないよう UV_PROJECT_ENVIRONMENT は devcontainer env か settings.local.json で
/workspaces/LoRAIro/.venv を保持する / #1171 は「明示リロード + 対象指定無効化API」で実装(.db mtime
基準は WAL で機能しないので使わない)/ #1174 は refinement 検索で分類し既知 alias は自動解決・typo 候補は
surface・真の新タグは user DB 登録(typo の自動 alias 化はしない・空正規化は登録しない)/ #1173 は
translations show/add + tags alias を追加し #1174 と同じ登録経路を使う / #1171 のキャッシュ方針と
#1173 の翻訳 CLI IF は Accepted な軽量 ADR を PR 同梱する / genai-tag-db-tools#124 は対象外 /
DELETE 化は提案しない(方式A が SSoT)/ 実機 GUI 検証は merge 後に人間が行うので条件に含めない。
達成できなければ 45 ターンで停止し、未完 Issue を列挙して報告する。
```

### この条件に置いた仮定

- **検証コマンド**: `.claude/rules/testing.md` の LoRAIro Unit/Integration 行にある CI-equivalent filter を用いる。
- **停止上限**: 45 ターン(6 Issue × worktree / PR / CI / 自動マージ保守を見積もった保守的な値)。
- **#1171 の完了基準**: 実装、unit テスト通過、マージをもって完了とする(実 GUI での反映はマージ後に人間が確認する)。
- **#1172 の完了基準**: 根本原因を特定できた場合のみ修正し、特定できなければ調査記録を残す(盲目的な修正は行わない)。
- **#1173 の IF**: `tags translations show/add` は仮仕様である。実装前に `check-existing` で `genai-tag-db-tools` の書き込み API(`write_user_translation` / `get_translations_batch`)を確認する。

## 一括ではなく分割で回す場合

40 ターン一括の実行が重い場合や、途中でレビューを挟みたい場合は、優先バッチごとに分割する。まず以下を実行する。

```
/goal Issue #1175(a settings.json OS別env) と #1176(ログ汚染) を worktree+PR で解決し、
各 PR で CI-equiv filter 0 failed を出力で示し squash merge、gh issue view で CLOSED を示す。
既存テストは必要範囲外で変更しない。main 直 push しない。15 ターンで停止。
```

上記が通過した後、#1174 → #1173 → #1171 → #1172 の順で同型の完了条件を作成して継続する。
