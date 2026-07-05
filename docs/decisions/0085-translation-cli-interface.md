---
type: ADR
title: 翻訳 CLI インターフェース (tags translations show/add + tags alias)
status: Accepted
timestamp: 2026-07-05
tags: [cli, tagdb, translation, user-db, alias, agent-workflow]
---
# ADR 0085: 翻訳 CLI インターフェース (tags translations show/add + tags alias)

- **関連 Issue**: #1173 (翻訳の参照・登録を CLI で完結), #1174 (tags add の refinement 分類), #976/#993/#998 (翻訳品質)
- **関連 ADR**: 0057 (CLI 構造化出力/エラー契約), 0060 (exit code policy), 0068 (タグ正規化の tagdb 委譲)

## Context

エージェントがタグの日本語/英語訳を整備するには、これまで GUI の翻訳管理ダイアログか
ad-hoc スクリプトが必要だった。tag DB (genai-tag-db-tools) には安定公開 API
(`search_tags` / `register_tag` / `write_user_translation` / `set_preferred_translation`) が
揃っており、LoRAIro 側にも Qt-free の `TagManagementService` (resolve/list/add/set_preferred)
がある。CLI から翻訳の参照・登録を完結させる薄い層を定義する。

## Decision

`tags add` と同じ規約 (dry-run 既定 / `--apply` / JSON JSONL 出力 / `-p` 必須) で以下を追加する。

```
lorairo-cli tags translations show -p proj --image-ids 1052,1082   # 画像のタグの翻訳状況
lorairo-cli tags translations show -p proj --tags "cat,dog"        # タグ指定 (最大 100 件)
lorairo-cli tags translations add  -p proj --tag T --lang ja --text "訳" [--preferred] --apply
lorairo-cli tags alias -p proj --from "typo spelling" --to "preferred tag" --apply
```

1. **言語キー**: 入力は `ja` / `en` のみ受け付け、**書き込みも `ja` / `en` の一貫形** (#1050 踏襲)。
   読みは `ja`/`japanese`・`en`/`english` のエイリアス両表記を `utils/language_keys.py` 経由で
   集約する (#976 の混在実データ対応)。
2. **tag_id 解決は #1174 と同経路**: `classify_manual_tag` で分類し、
   - 完全一致 / 既知 alias → 解決済み tag_id を使用
   - 真の新タグ (unregistered) → `--apply` 時に `register_user_tag` (scope=user, format 1000+)
   - typo / 曖昧候補 → **登録せず候補を提示してエラー** (INVALID_INPUT)。確定は `tags alias` で行う
     (typo の自動 alias 化はしない)
   - 登録失敗 (tagdb #124 edge) → 静かに落とさず DB_ERROR で明示する
3. **`tags alias`**: `--to` は既存タグ必須。`--from` が既に解決可能なら冪等 no-op (同一 preferred) か
   拒否 (別タグへの付け替えは CLI で行わない)。登録は `register_tag(alias=True,
   preferred_tag=<canonical>, scope="user")`。
4. **`--preferred`**: 付けた場合のみ主訳化 (`set_preferred_translation`)。無しは
   `write_user_translation` のみ (候補追加)。
5. **`-p` は全コマンド必須**: tag DB 自体はプロジェクト非依存だが、既存 `tags` 系コマンドの
   規約 (repository 層アクセスに active project が必要) と統一する。

## Consequences

- エージェントは `translations show` で missing を発見 → `translations add` で補完 →
  typo は `tags alias` で確定、のループを CLI だけで回せる (#1171/#1172 の実機確認導線)。
- user DB overlay のみに書き込み、base DB は変更しない。
- `translations show --tags` は 100 件上限 (タグごとの候補列挙は N+1 だが bounded)。

## Related

- Issue #1173 / #1174 / genai-tag-db-tools#124
- ADR 0057 / 0060 / 0068 / メモリ: tagdb 翻訳 language キー混在 (#976 PR #991)
