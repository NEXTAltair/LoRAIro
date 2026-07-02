---
name: lorairo-cli-db-access
version: "1.0.0"
description: Inspect or modify the LoRAIro image database (lorairo_data/*/image_database.db) through lorairo-cli instead of raw sqlite3. Use whenever a task needs to read image/tag/annotation/model/error records, count or search images, or edit tags from a shell or agent session. Raw sqlite3 against the live DB fails with disk I/O errors on the 9p bind mount and risks WAL corruption while the GUI is running.
metadata:
  short-description: LoRAIro 画像DBの調査・編集は sqlite3 直叩きではなく lorairo-cli 経由で行う。
---

# lorairo-cli-db-access

LoRAIro のプロジェクト DB (`lorairo_data/<project>/image_database.db`) に対する
調査・編集は **lorairo-cli を第一選択** にする。

## なぜ sqlite3 直叩きを避けるか

- devcontainer の `lorairo_data/` は Windows 9p bind mount 上にあり、稼働中の DB へ
  `sqlite3` で直接クエリすると `disk I/O error (10)` になる (2026-07-02 実測)
- SQLite は single concurrent writer。GUI 稼働中の直接書き込みは WAL 破損リスク
- CLI は busy_timeout (既定 30s) 待ち → CONFLICT (retryable) のロック制御と
  作業集合上限 (500件) / count-first の安全装置を持つ

## 基本形

プロジェクトルートから実行する (`.venv` は uv が解決):

```bash
uv run lorairo-cli --json <group> <command> [args]   # JSONL 出力 (エージェント向け)
uv run lorairo-cli <group> <command> --help          # 各コマンドの引数確認
uv run lorairo-cli list-commands                     # 機械可読なコマンド一覧
uv run lorairo-cli describe <command>                # エージェント/CI 向けコマンド仕様
```

主なコマンド群:

| group | 用途 |
|---|---|
| `project` | プロジェクト一覧・作成 |
| `images` | `list` / `search` (read-only, JSON search schema) / `register` / `update` |
| `tags` | タグ編集 (agent-friendly) |
| `annotate` / `batch` | アノテーション実行 / Provider Batch job |
| `models` | モデルレジストリ参照 |
| `errors` | エラーレコード管理 |
| `export` | データセットエクスポート |
| `status` | システム状態 |

## 運用ルール

1. **count-first**: 件数確認が既定。500 件超は `RESULT_SET_TOO_LARGE` になるので
   条件を絞ってから fetch する
2. **GUI 併用時**: 読み取りは安全。書き込みは GUI と競合させない。CLI 書き込み後は
   GUI 側で再検索/リロードしないと反映されない
3. **CONFLICT が返ったら** リトライ可能 (ロック競合)。連打せず間隔を置く

## CLI で表現できないクエリの fallback

集計 SQL (GROUP BY 等) が CLI に無い場合のみ、**DB ファイルをコピーしてから**
読み取り専用で sqlite3 を使う。稼働中の実体ファイルには絶対に直接触れない:

```bash
cp lorairo_data/<project>/image_database.db /tmp/.../scratchpad/db_copy.db
sqlite3 /tmp/.../scratchpad/db_copy.db "SELECT tag, COUNT(*) FROM tags GROUP BY tag ..."
```

コピーは点時点スナップショットであり、GUI の最新状態とはずれ得ることを結果に明記する。

## 参照

- `docs/cli.md` — CLI 全体ドキュメント
- `docs/cli-rating-preflight.md` — rating 付与ワークフロー
