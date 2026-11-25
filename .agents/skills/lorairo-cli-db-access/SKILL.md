---
name: lorairo-cli-db-access
version: "1.0.0"
description: Inspect or modify the LoRAIro image database (lorairo_data/*/image_database.db) through lorairo-cli instead of raw sqlite3. Use whenever a task needs to read image/tag/annotation/model/error records, count or search images, or edit tags from a shell or agent session. Raw sqlite3 against the live DB fails with disk I/O errors on the 9p bind mount and risks WAL corruption while the GUI is running.
metadata:
  short-description: LoRAIro 画像DBの調査・編集は sqlite3 直叩きではなく lorairo-cli 経由で行う。
---

# lorairo-cli-db-access

LoRAIro のプロジェクト DB(`lorairo_data/<project>/image_database.db`)を調査・編集するときは、**`lorairo-cli` を第一選択**とする。

## `sqlite3` の直接実行を避ける理由

- Dev Container 内の `lorairo_data/` は Windows の 9p bind mount 上にある。稼働中の DB へ `sqlite3` で直接クエリを実行すると、`disk I/O error (10)` が発生する(2026-07-02 実測)。
- SQLite は同時に 1 つのライターしか許容しない。GUI の稼働中に直接書き込むと、WAL が破損するリスクがある。
- `lorairo-cli` は `busy_timeout`(既定 30 秒)による待機と、リトライ可能な `CONFLICT` 応答によるロック制御を備えている。さらに、作業集合の上限(500 件)や件数先行確認(count-first)といった安全装置も持つ。

## 基本的な使い方

コマンドはプロジェクトルートから実行する(`.venv` は `uv` が解決する)。**GUI(`lorairo`)の稼働中は必ず `--no-sync` を付ける**(後述の「GUI 稼働中の venv 部分破損」を参照)。

```bash
uv run --no-sync lorairo-cli --json <group> <command> [args]   # JSONL 出力(エージェント向け)
uv run --no-sync lorairo-cli <group> <command> --help          # 各コマンドの引数確認
uv run --no-sync lorairo-cli list-commands                     # 機械可読なコマンド一覧
uv run --no-sync lorairo-cli describe "<group> <command>"      # エージェント・CI 向けコマンド仕様(空白を含む場合はクォート必須)
```

主なコマンド群は次のとおりである。

| コマンド群 | 用途 |
|---|---|
| `project` | プロジェクトの一覧取得・作成 |
| `images` | `list`・`search`(読み取り専用、JSON 検索スキーマ)・`show`・`register`・`update`・`reanalyze-generation`・`crop` |
| `tags` | タグの編集(`add`・`remove`・`replace`・`translations`・`alias`。エージェント向けの操作に対応) |
| `annotate` / `batch` | アノテーションの実行(`run`・`review`・`import-batch`)と Provider Batch ジョブの管理 |
| `dataset` | Kohya-ss データセットの操作(`import`・`export`・`show`・`diff`・`copy-tags`) |
| `models` | モデルレジストリの参照・同期 |
| `errors` | エラーレコードの管理 |
| `export` | データセットのエクスポート |
| `maintenance` | 読み取り専用の DB メンテナンス点検(`check`) |
| `status` | システム状態の確認 |

## 運用ルール

1. **件数先行確認(count-first)**: 既定では件数確認を優先する。結果が 500 件を超えると `RESULT_SET_TOO_LARGE` になるため、条件を絞り込んでから取得する。
2. **GUI 併用時の注意**: 読み取りは安全である。書き込みは GUI の操作と競合させない。なお、CLI から書き込んだ内容は、GUI 側で再検索またはリロードするまで反映されない。
3. **`CONFLICT` 応答時の対応**: ロック競合によるリトライ可能なエラーである。連続実行を避け、少し間隔を空けて再試行する。

## GUI 稼働中の venv 部分破損(Windows、#1190)

GUI(`lorairo`)が共有 venv から起動している間、Windows は `Scripts\lorairo.exe` をロックする。この状態で暗黙の同期を伴う `uv run lorairo-cli ...` を実行すると、`uv` が editable install のエントリーポイントを再生成する過程で `lorairo.exe` の削除に失敗する。その結果、同期が中断し、先に削除された **`lorairo-cli.exe` が消えたまま venv が部分破損**する(2026-07-05 実測)。

- **予防**: GUI 稼働中の CLI 実行には、常に `uv run --no-sync lorairo-cli ...` を使う。`--no-sync` は venv を書き換えないため常用しても安全である。
- **破損時の症状**: `Failed to spawn: lorairo-cli / program not found` が発生する。
- **応急処置**(GUI を止めずに実行する場合):
  ```powershell
  uv run --no-sync python -c "from lorairo.cli.main import main; main()" --json images show -p <project> --image-ids <id>
  ```
- **復旧**: GUI を終了してから `uv sync --dev` を実行する。

## CLI で表現できないクエリのフォールバック

`GROUP BY` などの集計 SQL が CLI に用意されていない場合に限り、**DB ファイルをコピーしてから**読み取り専用で `sqlite3` を実行する。稼働中の実体ファイルには決して直接触れてはならない。

```bash
# WAL 併用時は -wal / -shm も併せてコピーする(Issue #1216)。.db だけコピーすると
# 直近の書き込み(未 checkpoint 分)が欠け、除去直後の検証などで未反映に見える誤検出が起きる。
cp lorairo_data/<project>/image_database.db     /tmp/.../scratchpad/db_copy.db
cp lorairo_data/<project>/image_database.db-wal /tmp/.../scratchpad/db_copy.db-wal 2>/dev/null || true
cp lorairo_data/<project>/image_database.db-shm /tmp/.../scratchpad/db_copy.db-shm 2>/dev/null || true
sqlite3 /tmp/.../scratchpad/db_copy.db "SELECT tag, COUNT(*) FROM tags GROUP BY tag ..."
```

コピーは特定時点のスナップショットであり、GUI の最新状態とずれる可能性がある。報告時にはその旨を明記する。一方、CLI の読み取りコマンド(`lorairo-cli images search` や `show`)は WAL を含めて正しく参照できるため、直近の書き込み反映を確認する場合は CLI を優先する。

## 参照

- `docs/cli.md`: CLI 全体ドキュメント
- `docs/cli-rating-preflight.md`: rating 付与ワークフロー
