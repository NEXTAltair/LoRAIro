---
type: Reference
title: CLI strict read-only database access
status: Accepted
tags: [cli, database, read-only]
---

# CLI の読み取り専用接続

DB・画像・設定への論理書込みを禁止する場合は、コマンド名の前に `--read-only` を指定します。
既存の互換 schema を SQLite の `mode=ro` / `query_only=ON` で開き、schema migration、
model seed、画像用日付ディレクトリ作成を行いません。書込みコマンドは本体実行前に拒否します。

```bash
lorairo-cli --json --workspace "/data/作業 領域" --read-only images list --project sample
lorairo-cli --json --workspace "/data/作業 領域" --read-only images search --project sample --query '{}'
lorairo-cli --json describe "images list"
```

`--read-only` を省いた既存の CLI / GUI / Python 接続は、従来の自動準備を維持します。
明示 workspace / config の優先順位は [workspace/config 選択](cli-workspace-config.md) を参照してください。
指定なしの strict モードも既存設定の所在と CWD 相対保存先を維持し、設定ファイルを自動作成しません。

## 未準備の場合

空・欠損・旧 revision・互換性のない schema・不足した必須 model_types は
`PRECONDITION_FAILED`（exit 1、`ok=false`）になります。`details.reason` は判定理由、
`database_path` は対象、`hint` は明示準備の案内です。旧 DB を黙って更新しません。
書込み権限を得たうえで、同じ workspace / config を指定して準備してください。

```bash
lorairo-cli --workspace "/data/作業 領域" project prepare --project sample
# タグ翻訳の base キャッシュ / user DB も準備する場合（ダウンロードあり）:
lorairo-cli --workspace "/data/作業 領域" project prepare --project sample --tags
```

準備は既存の migration / model seed の責務を利用します。破損 DB や revision 管理されていない
旧 schema は一般的な準備だけで復旧できない場合があります。既存のバックアップ・migration 手順で
互換 DB を用意してください。strict モードは修復も schema の推測更新も行いません。

タグ翻訳の strict 経路は既存の Hugging Face キャッシュと user DB のみを読みます。
未キャッシュ・空・旧 user schema は同じ事前条件エラーとなり、ネットワークや model 初期化へ
フォールバックしません。初期化失敗後のスコープを再利用せず、準備後に再実行します。

## 対象コマンド

| コマンド | strict での対象 |
| --- | --- |
| `version`, `status` | バージョン / 選択設定の読取り |
| `project list` | プロジェクトメタデータ |
| `images list`, `images search`, `images show` | 既存 image DB |
| `tags translations show` | 既存 image DB + キャッシュ済み tag DB |
| `models list` | 準備済みのローカル registry 設定（モデルダウンロードなし） |
| `batch list` | 既存 image DB の batch 情報 |
| `errors list`, `errors get` | 既存 image DB のエラー記録 |

`list-commands` / `describe` は各 tool の `strict_read_only_supported`、
`conditional_side_effects`、`read_only_contract`、root option を返します。
従来の `read_only` / `side_effects` は ADR 0059 の定常状態の分類を維持し、
条件付き DB 作成・migration・seed・ディレクトリ作成を別フィールドで判別できます。
`--help`、`list-commands`、`describe` 自体も strict モードで使用できます。

`models list` の cold start は通常 CWD の `config/annotator_config.toml` を必要とします。
未準備なら `PRECONDITION_FAILED` を返し、設定のコピー・ディレクトリ作成は行いません。
書込み権限を得て同じ CWD で `models list` を `--read-only` なしで実行し、準備後に再試行します。
依存パッケージの公開ポリシー `IMAGE_ANNOTATOR_CONFIG_READ_ONLY=1` は import 前に
既存 runtime lock 内で設定し、終了時に元の値へ復元します。パッケージ内部でも設定作成と
system/user/runtime-cache 保存を拒否するため、存在確認後にファイルが消えても再作成しません。
このポリシーはモデルの推論やダウンロードを許可するものではありません。

## ファイルシステム上の保証

論理データの保護と SQLite の WAL/SHM・ロック・一時物は別です。`mode=ro` でも既存 WAL の
読取りのために共有メモリなどの調整が必要になる場合があります。CLI の診断ログも通常どおり出力し、
`LORAIRO_CLI_LOG_PATH` で監査対象外へ保存できます。
すべてのファイル書込みを禁止する場合は、整合した snapshot と必要な journal 状態を用意し、
読み取り専用 mount / media を使ってください。live DB に `immutable=1` を適用すると変更検知を
無効にして誤読するため、この機能では使用しません。

実装は [SQLite URI](https://www.sqlite.org/uri.html) と
[query_only](https://www.sqlite.org/pragma.html#pragma_query_only)、既存の SQLAlchemy / Alembic /
genai-tag-db-tools を再利用します。新しい migration 基盤や schema 自体の変更は導入していません。
Python の接続層は `create_project_session_factory(path, read_only=True)` でも同じ互換性検査と
読み取り接続を選択できます。

Unreadable or syntactically invalid model TOML requires backing up and repairing the configuration; writable `models list` does not repair it. This check covers reading and TOML parsing, not complete validation of every model configuration field.


画像DB・タグDBとも、接続時のロック競合は `CONFLICT` (`retryable=true`) を保持します。
他の処理がロックを解放してから再実行してください。SQLite の `disk I/O error` は
`IO_ERROR` と既存の実行環境確認ヒントを保持します。これらの運用障害を準備不足として扱い、
書込みモードでの `project prepare` を案内することはありません。
タグ初期化では、ライブラリの型付き準備エラーだけを `PRECONDITION_FAILED` へ変換します。
この型には必要なキャッシュ/DBの欠落・互換性不足に加え、破損などによる読取り不能も含まれます。
`project prepare` の案内はすべての破損を修復できる保証ではありません。破損が疑われる場合は
バックアップを保持し、対応した復旧手順を確認してください。ライブラリが準備エラーに包んだ場合も、
原因がロックやディスク I/O なら元の運用エラー分類を優先します。
