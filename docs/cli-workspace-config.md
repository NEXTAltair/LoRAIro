---
type: Reference
title: CLI workspace and config selection
status: Accepted
tags: [cli, configuration, project]
---

# CLI の workspace・config 選択

カレントディレクトリ(CWD)に依存せず対象を固定するには、コマンド名より前に `--workspace DIR` または `--config FILE` を指定します。既存のプロジェクトや DB の移動・マイグレーションは行いません。プロジェクト DB のファイル名 `image_database.db` も従来どおりです。

```bash
lorairo-cli --json --workspace "/data/作業 領域" project list
lorairo-cli --json --workspace "/data/作業 領域" --config "/settings/個別設定.toml" status
lorairo-cli --workspace "/data/作業 領域" images list --project same-name
```

## 設定の優先順位と相対パスの基準

| 指定 | 読み込む設定 | 設定内の相対ディレクトリの基準 |
| --- | --- | --- |
| なし | 従来のソースルート `config/lorairo.toml` | 従来どおり実行時の CWD |
| `--workspace DIR` | `DIR/config/lorairo.toml`(存在しなければ既定設定) | `DIR` |
| `--config FILE` | 指定ファイル(存在必須) | `FILE` の親ディレクトリ |
| 両方 | 指定 `FILE`(workspace 内の既定設定より優先) | 指定 `DIR` |

オプション自体に渡した相対パスは、実行時の CWD を基準に絶対パスへ変換します。異なる CWD から同じ対象を選ぶ自動化では、オプションへ同じ絶対パスを渡してください。空白や日本語を含むパスも利用できます。シェルから渡す場合は引用符で囲んでください(対話入力は不要です)。

## ディレクトリ解決と入力検証

明示モードでは、`[directories]` の `*_dir` 値を基準位置から絶対パスへ解決します。

- 空の値はそのまま維持します。
- すでに絶対パスの場合はその場所を維持します(たとえば `database_base_dir` に絶対パスを設定していれば、workspace を変えてもその共通保存先を使用します)。
- 既定の `database_base_dir = "lorairo_data"` の場合は `DIR/lorairo_data` を選択します。
- `--output` や画像入力など、コマンド引数の相対パスの意味は変わりません。

ディレクトリ設定の値は空値を含めすべて文字列である必要があります。TOML の真偽値・配列・数値が指定された場合は、コマンド実行前に `INVALID_INPUT` として拒否します。

以下の場合も `INVALID_INPUT`(終了コード 2)を返します。

- 明示指定した設定ファイルが存在しない、通常ファイルでない、または TOML 構文が不正である。
- `--workspace` に既存の通常ファイルを指定した。

明示モードでは設定ファイルを自動作成・保存しません。また、`project list` や `status` で workspace ディレクトリを作成することもありません。一方、作成系コマンドは指定先へ通常どおり書き込みます。

## `status` 出力と設定層の扱い

`status` の JSONL 出力では、`workspace`、`config_path`、`projects_base_dir`、`tag_database_dir` を絶対パスで返します。`config_found` は選択した設定ファイルの有無を表します。指定契約は `--help` や `describe "project list" --schema json_schema` の `GlobalOptions` からも取得できます。

- **通常モード**: `config_path` は OS ユーザー設定を指します。共通の既定値は `project_config_path` と `project_config_found`、ユーザー設定は `user_config_path` と `user_config_found` で区別します。
- **`--workspace` 指定時**: `config_found` は workspace 設定の有無を維持しつつ、API 状態には読み込んだユーザー設定も反映します。
- **`--config` 指定時**: 指定したファイルだけを参照し、他の設定層の状態は表示しません。

## コマンド単位の分離と DB 解決

明示モードではコマンドごとに設定と `ServiceContainer` を分離し、以前のプロジェクトのキャッシュを引き継ぎません。DB の選択には既存の `set_active_project` を使用します。

- **タグの user DB**: 明示モードでは `directories.database_dir`(空の場合は `database_base_dir`)直下の `user_tags.sqlite` を使用します。自動の日付連番ディレクトリは作成しません。初回にタグ DB が必要な操作で初期化し、`status` は保存先のみを表示します。共通の絶対パスを設定した場合は、意図的に共有先を選択します。
- **タグ DB ランタイムの分離**: 公開 API `database_runtime_scope()` でランタイムを分離し、終了時は元の接続を再初期化せずに復元します。同期 CLI の入れ子呼び出しにも対応します。ただし、同一プロセス内でスコープ外の GUI や旧 API アクセスと同時実行したり、非同期タスク間でスコープを交差させたりしないでください。ワーカーと DB ハンドルの使用は CLI 呼び出し内で完了させてください。
- **`models refresh` で `--project` を省略した場合**: 明示 workspace・config モードでの既定の画像 DB は、`database_dir/image_database.db`(`database_dir` が空の場合は `database_base_dir/image_database.db`)です。呼び出しローカルのファクトリを使用し、キャッシュ済みの従来の既定ファクトリは使いません。`--project` を指定した場合は従来どおりそのプロジェクトの DB を選択します。

CWD や永続的な環境設定は書き換えません。オプションを指定しない場合は、互換性のため従来動作を維持します。

## 再利用判断

ADR 0018 による `database_base_dir` 統一と、既存の `ConfigurationService`、`ProjectManagementService`、`ServiceContainer` を再利用しています。新しい設定ライブラリや別のプロジェクトレジストリは導入していません。コマンド単位の設定分離には標準ライブラリの [ContextVar](https://docs.python.org/3/library/contextvars.html) を用い、実行終了時に復元します。
