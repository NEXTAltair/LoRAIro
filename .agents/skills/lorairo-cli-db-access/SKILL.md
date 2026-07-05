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

プロジェクトルートから実行する (`.venv` は uv が解決)。**GUI (lorairo) 稼働中は必ず
`--no-sync` を付ける** (下記「GUI 稼働中の venv 部分破損」参照):

```bash
uv run --no-sync lorairo-cli --json <group> <command> [args]   # JSONL 出力 (エージェント向け)
uv run --no-sync lorairo-cli <group> <command> --help          # 各コマンドの引数確認
uv run --no-sync lorairo-cli list-commands                     # 機械可読なコマンド一覧
uv run --no-sync lorairo-cli describe <command>                # エージェント/CI 向けコマンド仕様
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

## GUI 稼働中の venv 部分破損 (Windows, #1190)

GUI (`lorairo`) が共有 venv から起動していると `Scripts\lorairo.exe` をロックする。
この状態で `uv run lorairo-cli ...` (暗黙 sync あり) を実行すると、uv が editable
install の entry point 再生成で `lorairo.exe` の削除に失敗して sync が中断し、先に
削除された **`lorairo-cli.exe` が消失したまま venv が部分破損**する (2026-07-05 実測)。

- **予防**: GUI 稼働中の CLI 実行は常に `uv run --no-sync lorairo-cli ...`
  (`--no-sync` は venv を書き換えないため常用しても安全)
- **破損時の症状**: `Failed to spawn: lorairo-cli / program not found`
- **応急処置** (GUI を止めずに使う):
  ```powershell
  uv run --no-sync python -c "from lorairo.cli.main import main; main()" --json images show -p <project> --image-ids <id>
  ```
- **復旧**: GUI 終了後に `uv sync --dev`

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
