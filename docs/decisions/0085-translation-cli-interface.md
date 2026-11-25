---
type: ADR
title: 翻訳 CLI インターフェース (tags translations show/add + tags alias)
status: Accepted
timestamp: 2026-07-05
tags: [cli, tagdb, translation, user-db, alias, agent-workflow]
---
# ADR 0085: 翻訳 CLI インターフェース (tags translations show/add + tags alias)

- **関連 Issue**: #1173(翻訳の参照・登録を CLI で完結)、#1174(`tags add` の refinement 分類)、#976・#993・#998(翻訳品質)
- **関連 ADR**: 0057(CLI の構造化出力・エラー契約)、0060(終了コード方針)、0068(タグ正規化の tagdb 委譲)

## Context

これまで、エージェントがタグの日本語訳・英語訳を整備するには、GUI の翻訳管理ダイアログを使うか、場当たり的なスクリプトを書く必要があった。

一方で、タグ DB(`genai-tag-db-tools`)には安定した公開 API(`search_tags`、`register_tag`、`write_user_translation`、`set_preferred_translation`)がそろっている。LoRAIro 側にも Qt 非依存の `TagManagementService`(解決、一覧、追加、主訳設定)が存在する。そこで、CLI から翻訳の参照と登録を完結させる薄いインターフェース層を定義する。

## Decision

`tags add` と同じ規約(既定で dry-run、`--apply` で反映、JSON および JSONL 出力、`-p` 必須)に従い、次のコマンドを追加する。

```
lorairo-cli tags translations show -p proj --image-ids 1052,1082   # 画像のタグの翻訳状況
lorairo-cli tags translations show -p proj --tags "cat,dog"        # タグ指定 (最大 100 件)
lorairo-cli tags translations add  -p proj --tag T --lang ja --text "訳" [--preferred] --apply
lorairo-cli tags alias -p proj --from "typo spelling" --to "preferred tag" --apply
```

各仕様の詳細は以下のとおりとする。

1. **言語キーの統一**: 入力は `ja` と `en` のみを受け付け、**書き込みも `ja` と `en` に統一する**(#1050 を踏襲)。読み込み時は `utils/language_keys.py` を経由して `ja`・`japanese` および `en`・`english` の両表記を集約する(#976 で確認された混在実データへの対応)。
2. **`tag_id` の解決は #1174 と同一経路を用いる**: `classify_manual_tag` で入力を分類し、次のように処理する。
   - **完全一致または既知エイリアス**: 解決済みの `tag_id` を使用する。
   - **未登録の新規タグ(unregistered)**: `--apply` 指定時に `register_user_tag`(`scope=user`、format 1000+)で登録する。
   - **誤記や曖昧な候補**: **自動登録せず、候補を提示して `INVALID_INPUT` エラーを返す**。誤記を自動的にエイリアス化せず、確定操作は `tags alias` で明示的に行う。
   - **登録失敗(tagdb #124 の境界条件)**: 黙って無視せず、`DB_ERROR` として明示的に返す。
3. **`tags alias` の挙動**: `--to` には既存タグを必須とする。`--from` がすでに解決可能な場合、同一の推奨タグを指していれば冪等な無操作とし、別タグへの付け替えは CLI では許可せず拒否する。登録には `register_tag(alias=True, preferred_tag=<canonical>, scope="user")` を使用する。
4. **`--preferred` オプション**: 指定された場合のみ `set_preferred_translation` で主訳として設定する。省略時は `write_user_translation` による候補追加のみを行う。
5. **全コマンドで `-p` を必須とする**: タグ DB 自体はプロジェクト非依存だが、リポジトリ層へのアクセスにアクティブなプロジェクトを要求する既存の `tags` 系コマンドと規約を統一する。

## Consequences

- エージェントは、`translations show` で欠落している翻訳を見つけ、`translations add` で補完し、誤記は `tags alias` で確定するという一連の作業を CLI だけで完結できる(#1171・#1172 の実機確認導線)。
- 書き込み先はユーザー DB オーバーレイのみに限定され、ベース DB は変更されない。
- `translations show --tags` は上限を 100 件とする。タグごとの候補列挙は N+1 クエリになるが、件数上限によって負荷を抑えられる。

## Related

- Issue #1173 / #1174 / genai-tag-db-tools#124
- ADR 0057 / 0060 / 0068 / メモリ: tagdb 翻訳 language キー混在(#976 PR #991)
