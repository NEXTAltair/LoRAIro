---
type: Reference
title: CLI workspace and config selection
status: Accepted
tags: [cli, configuration, project]
---

# CLI workspace/config 選択

CWD に依存せず対象を固定するには、コマンド名より前に `--workspace DIR` または
`--config FILE` を指定します。既存プロジェクト・DB の移動や migration は行いません。プロジェクト DB のファイル名
`image_database.db` は従来どおりです。

```bash
lorairo-cli --json --workspace "/data/作業 領域" project list
lorairo-cli --json --workspace "/data/作業 領域" --config "/settings/個別設定.toml" status
lorairo-cli --workspace "/data/作業 領域" images list --project same-name
```

| 指定 | 読む設定 | 設定内の相対ディレクトリの基準 |
| --- | --- | --- |
| なし | 従来のソースルート `config/lorairo.toml` | 従来どおり実行 CWD |
| `--workspace DIR` | `DIR/config/lorairo.toml`。不存在なら既定設定 | DIR |
| `--config FILE` | 指定ファイル（存在必須） | FILE の親ディレクトリ |
| 両方 | 指定 FILE（workspace 内の既定設定より優先） | 指定 DIR |

オプション自体の相対パスは実行 CWD を基準に絶対化します。二つの CWD から同じ対象を
選ぶ自動化では、オプションには同じ絶対パスを渡してください。空白・日本語を含むパスも
利用できます。シェルから渡す場合は引用符で囲みます。対話入力は不要です。

明示モードでは `[directories]` の `*_dir` 値を基準位置から絶対化します。空の値は
維持し、既に絶対パスの値はその場所を維持します。たとえば `database_base_dir` に
絶対パスが設定されていれば workspace を変えてもその共通保存先を選択します。
既定 `database_base_dir = "lorairo_data"` なら `DIR/lorairo_data` を選択します。
CLI の `--output` や画像入力など、コマンド引数の相対パスの意味は変わりません。

明示指定した設定が存在しない、ファイルでない、TOML が不正な場合は `INVALID_INPUT` /
終了コード 2 を返します。workspace が既存の通常ファイルの場合も同様です。
明示モードは設定を自動作成・保存せず、`project list` / `status` で workspace を作成しません。
作成コマンドは指定先へ通常どおり書き込みます。

`status` の JSONL は `workspace`、`config_path`、`projects_base_dir`、`tag_database_dir` を絶対パスで返します。
`config_found` は選択した設定の有無を表します。`--help` と
`describe "project list" --schema json_schema` の `GlobalOptions` からも指定契約を取得できます。

明示モードはコマンドごとに設定と ServiceContainer を分離し、以前のプロジェクトの
キャッシュを引き継ぎません。既存の `set_active_project` で DB を選択します。
タグの user DB は明示モードでは `directories.database_dir`（空なら
`database_base_dir`）直下の `user_tags.sqlite` を使います。自動日付連番ディレクトリは
作りません。初回にタグ DB が必要な操作で初期化し、`status` は保存先のみ表示します。
共通の絶対パスを設定した場合は意図的に共有先を選択します。

タグ DB の runtime も公開 API `database_runtime_scope()` で分離し、終了時は元の接続を
再初期化せず復元します。同期 CLI の入れ子呼び出しに対応します。同一プロセスで
スコープ外の GUI/旧 API アクセスと同時実行したり、非同期タスクでスコープを交差させたり
しないでください。ワーカーと DB ハンドルの使用は CLI 呼び出し内で完了させます。

CWD や永続的な環境設定は書き換えません。指定なしでは互換性のため従来動作を維持します。

## 再利用判断

ADR 0018 の `database_base_dir` 統一と既存の ConfigurationService / ProjectManagementService /
ServiceContainer を再利用しました。新しい設定ライブラリや別のプロジェクト registry は
導入していません。コマンド単位の設定には標準ライブラリ
[ContextVar](https://docs.python.org/3/library/contextvars.html) を使い、終了時に復元します。
