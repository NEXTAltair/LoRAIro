---
type: Reference
title: CLI strict read-only database access
status: Accepted
tags: [cli, database, read-only]
---

# CLI の読み取り専用接続

DB・画像・設定への論理的な書き込みを禁止する場合は、コマンド名の前に `--read-only` を指定します。既存の互換スキーマを SQLite の `mode=ro` と `query_only=ON` で開き、スキーママイグレーション、モデルシード、画像用日付ディレクトリの作成を行いません。書き込み系コマンドは本体処理の実行前に拒否します。

```bash
lorairo-cli --json --workspace "/data/作業 領域" --read-only images list --project sample
lorairo-cli --json --workspace "/data/作業 領域" --read-only images search --project sample --query '{}'
lorairo-cli --json describe "images list"
```

`--read-only` を省略した既存の CLI・GUI・Python 接続では、従来の自動準備を維持します。明示的な workspace や config の優先順位は [workspace/config 選択](cli-workspace-config.md) を参照してください。指定なしの strict モードでも既存設定の所在と CWD 相対保存先を維持し、設定ファイルを自動作成しません。

## 未準備の場合の挙動

空の DB、欠損、旧リビジョン、互換性のないスキーマ、必須 `model_types` の不足がある場合は、`PRECONDITION_FAILED`(exit 1、`ok=false`)を返します。`details.reason` には判定理由、`database_path` には対象パス、`hint` には明示準備の案内が入ります。旧 DB を黙って更新することはありません。

書き込み権限を得たうえで、同じ workspace と config を指定して事前準備を行ってください。

```bash
lorairo-cli --workspace "/data/作業 領域" project prepare --project sample
# タグ翻訳の base キャッシュ / user DB も準備する場合(ダウンロードあり):
lorairo-cli --workspace "/data/作業 領域" project prepare --project sample --tags
```

### 準備処理と破損 DB の扱い

準備処理は既存のマイグレーションとモデルシードの責務を再利用します。ただし、破損した DB やリビジョン管理されていない旧スキーマは、通常の準備だけでは復旧できない場合があります。その場合は既存のバックアップやマイグレーション手順で互換 DB を用意してください。strict モードは修復やスキーマの推測更新を行いません。

### タグ翻訳の strict 経路

タグ翻訳の strict 経路では、既存の Hugging Face キャッシュと user DB のみを読み込みます。未キャッシュ・空・旧 user スキーマの場合は同じ事前条件エラーとなり、ネットワーク取得やモデル初期化へフォールバックしません。初期化に失敗したスコープは再利用せず、準備完了後に再実行してください。

## 対象コマンド

| コマンド | strict モードでの対象 |
| --- | --- |
| `version`, `status` | バージョンおよび選択設定の読み取り |
| `project list` | プロジェクトメタデータ |
| `images list`, `images search`, `images show` | 既存 image DB |
| `tags translations show` | 既存 image DB とキャッシュ済み tag DB |
| `models list` | 準備済みのローカル registry 設定(モデルダウンロードなし) |
| `batch list` | 既存 image DB の batch 情報 |
| `errors list`, `errors get` | 既存 image DB のエラー記録 |

`list-commands` と `describe` は、各ツールの `strict_read_only_supported`、`conditional_side_effects`、`read_only_contract`、およびルートオプションを返します。従来の `read_only` と `side_effects` は ADR 0059 の定常状態の分類を維持しつつ、条件付きで発生する DB 作成・マイグレーション・シード・ディレクトリ作成を別フィールドで判別できます。なお、`--help`、`list-commands`、`describe` 自体も strict モードで使用できます。

### `models list` の cold start と読み取り専用ポリシー

`models list` の cold start には、通常 CWD の `config/annotator_config.toml` が必要です。未準備の場合は `PRECONDITION_FAILED` を返し、設定のコピーやディレクトリ作成は行いません。書き込み権限を得たうえで、同じ CWD で `--read-only` なしの `models list` を実行し、準備完了後に再試行してください。

依存パッケージの公開ポリシーである `IMAGE_ANNOTATOR_CONFIG_READ_ONLY=1` は、import 前に既存の runtime lock 内で設定し、終了時に元の値へ復元します。パッケージ内部でも設定作成と system・user・runtime-cache の保存を拒否するため、存在確認後にファイルが消えても再作成しません。このポリシーはモデルの推論やダウンロードを許可するものではありません。

なお、読み取り不能または構文エラーのあるモデル TOML ファイルは、バックアップを取ったうえで手動修復する必要があります。書き込み可能な `models list` を実行しても自動修復されません。この検査の対象はファイル読み取りと TOML パースまでであり、すべてのモデル設定フィールドの完全な検証までは行いません。

## ファイルシステム上の保証

論理データの保護と、SQLite の WAL・SHM・ロック・一時ファイルは別問題です。`mode=ro` でも既存の WAL を読み取るために共有メモリなどの調整が必要になる場合があります。また、CLI の診断ログも通常どおり出力されます。監査対象外へ保存したい場合は `LORAIRO_CLI_LOG_PATH` で出力先を変更してください。

すべてのファイル書き込みを完全に禁止したい場合は、整合したスナップショットと必要な journal 状態を用意し、読み取り専用マウントや読み取り専用メディアを使用してください。live DB に `immutable=1` を適用すると変更検知が無効になり誤読の原因となるため、この機能では使用しません。

実装は [SQLite URI](https://www.sqlite.org/uri.html)、[query_only](https://www.sqlite.org/pragma.html#pragma_query_only)、および既存の SQLAlchemy・Alembic・genai-tag-db-tools を再利用しています。新しいマイグレーション基盤やスキーマ自体の変更は導入していません。Python の接続層でも、`create_project_session_factory(path, read_only=True)` を呼ぶことで同じ互換性検査と読み取り接続を選択できます。

## 運用エラーと事前条件エラーの分類

画像 DB・タグ DB ともに、接続時のロック競合では `CONFLICT`(`retryable=true`)を返します。他の処理がロックを解放してから再実行してください。SQLite の `disk I/O error` では、`IO_ERROR` と既存の実行環境確認ヒントを維持します。これらの運用障害を準備不足として扱い、書き込みモードでの `project prepare` を案内することはありません。

タグ初期化では、ライブラリが送出する型付きの準備エラーだけを `PRECONDITION_FAILED` へ変換します。このエラー型には、必要なキャッシュや DB の欠落・互換性不足に加え、破損などによる読み取り不能も含まれます。

`project prepare` の案内はすべての破損を修復できる保証ではありません。破損が疑われる場合はバックアップを保持し、適切な復旧手順を確認してください。ライブラリが準備エラーとしてラップした場合でも、根本原因がロック競合やディスク I/O であれば、元の運用エラー分類を優先します。
