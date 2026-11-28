---
type: Reference
title: LoRAIro CLI ドキュメント
status: Accepted
tags: [cli, annotation, dataset-export]
---
# LoRAIro CLI ドキュメント

LoRAIro のコマンドラインインターフェース(CLI)です。GUI のない環境でも、データセット管理やバッチ処理、プログラムからの自動操作を行えます。

## インストール

```bash
uv sync
lorairo-cli --help
```

設定ファイルや保存先を固定したい場合は、ルートオプションの `--workspace DIR` や `--config FILE` を指定します。詳しくは [workspace/config の優先順位と移行](cli-workspace-config.md) を参照してください。

## 基本的な使い方

OpenAI Moderation を使って未評価画像にレーティングを付与する手順は、[CLI Rating Preflight Workflow](cli-rating-preflight.md) を参照してください。

```bash
lorairo-cli --help
lorairo-cli project --help
lorairo-cli version
lorairo-cli status
```

## プロジェクトとデータセットの版

- **プロジェクト**は 1 つのライブラリ(データベースと画像の置き場)です。`project create` は新しい空のプロジェクトを作ります。
- **データセットの版**は、プロジェクトの中に残す学習データセットのスナップショットです。同じデータセットの新しい版は、新しいプロジェクトではなく**既存プロジェクト**へ `dataset import` で追加します。
- `images register` は画像をライブラリへ登録するだけで、**データセットの版は作りません**。版として残したい場合は `dataset import` を使います。

```bash
# 1. 最初だけ: 新しいプロジェクトを作る
lorairo-cli project create my-project

# 2. 版を追加する(2 版目以降も同じプロジェクトと同じ --dataset を指定する)
lorairo-cli dataset import ./v1 -p my-project --dataset my-dataset --version v1
lorairo-cli dataset import ./v2 -p my-project --dataset my-dataset --version v2 --parent-version 1

# 画像だけを足す(版は作られない)
lorairo-cli images register ./images -p my-project
```

既存のプロジェクト名で `project create` を実行すると `ALREADY_EXISTS` になり、ヒントに `dataset import` の呼び出し例が表示されます。

### `--project` / `-p` に指定する値

`--project` には、プロジェクトの `.lorairo-project` メタデータにある `name` を指定します。フォルダ名やパスではありません。

- CLI の `project create NAME` で作ったプロジェクトは、入力した `NAME` が `name` になります(フォルダ名は `NAME_日時` 形式です)。
- GUI で作成・オープンしたプロジェクトは、フォルダ名が `name` になります(#1659)。
- 使える名前は `lorairo-cli project list` で確認できます。

指定した名前が見つからないと `NOT_FOUND` になります。ヒントには、近い名前の候補(「もしかして」)と `project list` の案内が表示されます。フォルダ名を渡した場合は、そのフォルダにあるプロジェクトの `name` を案内します。JSON 出力では `details` の `available_projects`、`suggestions`、`folder_matched_project` で確認できます。

## GUI との同時利用(DB ロックの制約)

LoRAIro の画像データベースには SQLite を採用しています。SQLite は複数のプロセスから同時に読み取れますが、**同時に書き込めるのは 1 プロセスのみ**です(ADR 0067)。GUI を起動したまま CLI を併用する際は、次の点に注意してください。

- **検索や一覧の読み取りは併用できます**: WAL モードを有効にしているため、GUI が書き込み中でも CLI の読み取り処理はブロックされにくくなります。
- **書き込みの同時実行は避けてください**: GUI と CLI が同じプロジェクト DB へ同時に書き込む(アノテーション保存、画像登録、タグ編集など)と、一時的な競合が発生します。`PRAGMA busy_timeout`(既定 30 秒、`config/lorairo.toml` の `[database] busy_timeout_ms`)により短時間の競合は自動で待機・再試行されますが、長時間の書き込みを双方で同時に実行するのは推奨しません。
- **ロック競合時は再試行できます**: 待機時間を超えてもロックが解放されない場合、CLI は `CONFLICT` エラー(`retryable=true`)とともに「他プロセスの書き込み完了を待って再試行」というヒントを返します。GUI でも同様の日本語メッセージが表示されます。どちらも入力内容を変えずに再試行すれば成功する場合があります。
- **CLI で更新した後は GUI を再読み込みしてください**: CLI から DB を更新しても、GUI のメモリ上にある検索結果や件数表示は自動で更新されません。CLI を併用した後は、GUI 側で**再検索または再読み込み**を行ってください。
- **GUI 稼働中の CLI は `uv run --no-sync` で起動してください(Windows、#1190)**: Windows では GUI が共有仮想環境(venv)の `Scripts\lorairo.exe` をロックします。この状態で `uv run lorairo-cli` を実行すると、暗黙の同期処理がエントリーポイントの再生成に失敗して中断し、`lorairo-cli.exe` が消えたまま仮想環境が部分破損することがあります。`uv run --no-sync lorairo-cli ...` を使えば仮想環境を書き換えずに安全に実行できます。破損した場合は、GUI を終了してから `uv sync --dev` で復旧してください(GUI を止めずに使う応急処置は `uv run --no-sync python -c "from lorairo.cli.main import main; main()" ...` です)。

なお、大量のアノテーション処理を GUI と CLI で同時に実行する使い方は現状では想定していません。本格的な複数プロセスからの同時書き込みが必要になった場合は、PostgreSQL などへの移行を別途検討します。

## Exit Code

例外発生時の終了コードは、エラーコードから機械的に決定されます(`src/lorairo/cli/_errors.py`)。

| 終了コード | 意味 |
|---|---|
| 0 | 成功 |
| 2 | 入力・検証エラー(引数の不正、フィルタの未指定など) |
| 1 | 全件失敗、またはその他の実行時エラー |
| 3 | 部分成功(成功または正常スキップと失敗が混在) |

### 部分失敗と既存スクリプトの移行 (#1313)

次のコマンドは、集計結果を出力した後に、部分成功なら終了コード 3、全件失敗なら終了コード 1 で終了します。人間向けの出力でも同じ終了コードを使用します。

- `images register` / `images update` / `images process`
- `annotate run` / `annotate import-batch`
- `batch submit` / `batch import`
- `errors resolve`
- `export create`
- `review run`
- `tags translations add --file`

JSONL 出力の終端行は、従来どおり `kind=result` と各件数フィールドを維持しており、`status` と `ok` で結果を判定できます。ただし旧形式の `images update` と `tags translations add --file` は互換性のため従来の出力形式(`ok=true`)を維持しているため、それぞれ `failed_tags` または `errors` と終了コードを併せて確認してください。なお、`annotate run --run-id ID` の安全な再開手順は [再開契約](cli-annotation-resume.md) を参照してください。

| `status` | `ok` | 終了コード | 意味 |
|---|---|---|---|
| `success` | `true` | 0 | 成功、対象 0 件、重複・取り込み済みの正常スキップ、正常なドライラン |
| `partial_success` | `false` | 3 | 成功または正常スキップを含み、一部が失敗 |
| `failed` | `false` | 1 | 成功した対象がなく失敗 |

#### コマンド別の確認ポイント

- **画像登録(`images register`)**: `errors` と `error_details` を確認します。
- **旧バッチ結果の取り込み(`annotate import-batch`)**: `parse_errors`、`save_errors`、`unmatched` とあわせて、`unmatched_ids` および `error_details` を確認します。ドライランでも解析エラーや未一致があれば失敗扱いになります。
- **プロバイダーバッチの取り込み(`batch import`)**:
  - 従来の `skipped` には、正常スキップと取り込み不能の両方が含まれます。詳細は新しいフィールド(`already_imported`、`non_importable`、`save_skipped`、`missing_custom_ids`、`failed_custom_ids`、`error_details`)で確認してください。
  - `incomplete=true` の場合は、`batch status JOB_ID --project PROJECT` と保存済みの項目エラーを確認してください。
  - 保存結果が件数のみで部分成功した ID を特定できない場合、`failed_custom_ids` には保存完了を確認できない候補が保守的に含まれます。この一覧だけを根拠に全件を再送信せず、必ず保存状態を確認してください。
  - 対象が空の結果は終了コード 0 ですが、`job_imported=false` の場合はジョブ全体が完了したわけではありません。
- **エラー解決(`errors resolve`)**: 重複を除いた要求件数 `requested` と、実際の更新件数 `resolved` を出力します。リポジトリ処理の失敗や存在しない ID の指定により更新件数が不足した場合は、1 件でも更新できていれば終了コード 3、更新できなければ終了コード 1 になります。既に解決済みの存在する ID は、従来どおり再更新して成功扱いとします。

#### 既存スクリプトの移行方針

以前のバージョンでは、これらの部分失敗でも終了コード 0 が返る場合がありました。終了コードのみで後続処理へ進む既存スクリプトは、次のように見直してください。

- 終了コード 3(部分成功)と終了コード 1(全件失敗)を区別し、成功件数を記録する。
- 登録済みの画像や送信済みのバッチジョブを全件再送信するような自動再試行は行わない。
- 例外によって集計結果を返せない場合は、従来どおり `kind=error` と安定したエラーコードが出力されるため、こちらもあわせて処理する。

## Machine-Readable Introspection

ADR 0059 に従い、イントロスペクション機能では既存の JSONL 種別(`item`、`result`、`error`)のみを使用します。`tool`、`model`、`schema` は、`item` ペイロード内の `type` フィールドで表します。

```bash
lorairo-cli --json list-commands
lorairo-cli --json describe "images update"
lorairo-cli --json describe "annotate run" --schema json_schema
```

各コマンドの出力仕様は次のとおりです。

- **`list-commands`**: 各コマンドを `kind:"item", type:"tool"` として出力し、`read_only` と `side_effects` を含めます。
- **`describe`(既定の `compact` 形式)**: `type:"model"` の行で、入力・出力・エラーの簡易フィールド一覧を返します。各フィールドの `schema` には、制約を含む対応プロパティが入ります。
- **`describe --schema json_schema`**: Pydantic 由来の公開スキーマを `type:"schema"` の `item` 行に包んで返します。

スキーマ生成と公開範囲には、次のルールを適用しています。

- 入力スキーマは登録済みの Typer/Click 定義(型・必須・既定値・範囲)から導出し、`compact` 形式も同じ Pydantic スキーマから生成します。既定値が定義されているフィールドは、`null` を含めて公開します。
- JSON Schema の `x-cli-options` と `x-cli-destinations` により、CLI のオプション名・短縮別名と Python パラメータの対応を確認できます。
- `images search` では、`ImagesSearchInput` が CLI 引数、`ImageSearchQuery` が渡す JSON 本体のスキーマを表します。
- 処理本体で行う排他チェック、ID 件数制限、ファイル内容の検証については、各フィールドの説明も併せて参照してください。なお、生 SQL や DB スキーマは公開しません。
- 自己記述コマンドである `describe` と `list-commands` は操作コマンド一覧に含めません。この方針は終端の `result` 行の `excluded_commands` に明示し、`count` は従来どおり列挙した操作コマンドの件数を返します。また、各操作について `item` と終端 `result` の両モデルを公開します。

## Command Reference

> Generated by `scripts/generate_cli_docs.py`. Edit introspection specs, then regenerate.

**Input `GlobalOptions`**

Options precede the command name. See docs/cli-workspace-config.md for precedence.

- `log_level`: `str` (optional, default `INFO`) - Logging verbosity (DEBUG/INFO/WARNING/ERROR/CRITICAL). (CLI: `--log-level`)
- `json_output`: `bool?` (optional, default `None`) - Emit machine-readable JSONL on stdout (--json) or human-readable rich output (--no-json). (CLI: `--json`, `--no-json`)
- `read_only`: `bool` (optional, default `False`) - Root --read-only: only read_only=true commands; existing compatible DBs via mode=ro, no implicit preparation. PRECONDITION_FAILED gives preparation guidance. SQLite WAL/SHM coordination may occur. (CLI: `--read-only`)
- `workspace`: `str?` (optional, default `None`) - Root --workspace: anchor relative configured directories. Workspace/config/lorairo.toml is optional when --config is absent. (CLI: `--workspace`)
- `config`: `str?` (optional, default `None`) - Root --config: existing TOML; anchors directories at its parent unless --workspace is specified. CLI paths resolve against CWD; absolute configured directories stay absolute. No flags retain legacy CWD behavior. (CLI: `--config`)
- `install_completion`: `bool?` (optional, default `None`) - Install completion for the current shell. (CLI: `--install-completion`)
- `show_completion`: `bool?` (optional, default `None`) - Show completion for the current shell, to copy it or customize the installation. (CLI: `--show-completion`)

### `annotate import-batch`

Import provider batch annotation JSONL results.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `file_read`, `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "annotate import-batch"
```

#### Models

**Input `AnnotateImportBatchInput`**

- `jsonl_dir`: `str` (required) - JSONL files directory (OpenAI Batch API results) (CLI: `jsonl_dir`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `dry_run`: `bool` (optional, default `False`) - Show match results without saving to DB / DB書き込みを行わず照合結果のみ表示 (CLI: `--dry-run`)
- `model_name`: `str?` (optional, default `None`) - Override model name (ignores model field in JSONL) / モデル名を上書き（JSONL内のmodel名を無視） (CLI: `--model-name`)

**Output `AnnotateImportBatchResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed` (optional, default `success`) - Partial success returns ok=false and exit 3; total failure exits 1; normal skip/empty exits 0.
- `unmatched_ids`: `list[str]` (optional)
- `error_details`: `list[str]` (optional)
- `total_records`: `int` (required)
- `parsed_ok`: `int` (required)
- `parse_errors`: `int` (required)
- `matched`: `int` (required)
- `unmatched`: `int` (required)
- `saved`: `int` (required)
- `save_errors`: `int` (required)
- `model_name`: `str?` (optional, default `None`)
- `dry_run`: `bool` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `annotate run`

Run annotation and save to DB. Use --run-id to persist a run and --resume to process pending items only. See [resume contract](cli-annotation-resume.md).

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`, `file_write`, `network`

#### `--output` の移行 (#1310)

`annotate run` は、アノテーション結果をプロジェクト DB に保存するコマンドです。従来の `--output`(`-o`)オプションは未実装のまま、指定先へファイルを出力せずに成功していました。そのため現在は非推奨とし、値が指定された場合はプロジェクト確認・DB 接続・モデルや設定の取得・推論・出力先アクセスのいずれよりも前に `INVALID_INPUT`(終了コード 2)で拒否します。空文字列、存在しないパス、書き込みできないパスを指定した場合も同じ動作です。

既存スクリプトを移行する際は、次の手順で対応してください。

- `annotate run` から `--output DIR` を削除し、アノテーション完了後に同じプロジェクトと明示的な対象 ID を指定して `export create` を実行する。
- 以前の実行結果が既に DB に保存されている場合は、出力ファイルがないことだけを理由にアノテーションを再実行せず、保存内容を確認してからエクスポートする。

なお、`--output` を指定しない場合の DB 保存、推論の部分失敗、保存失敗に関する動作は従来どおり維持されます。

#### Compact Introspection

```bash
lorairo-cli --json describe "annotate run"
```

#### Models

**Input `AnnotateRunInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `model`: `list[str]` (required) - LiteLLM model ID (e.g., openrouter/openai/gpt-4o, openai/gpt-4o, wd-vit-tagger-v3). Use `lorairo-cli models list` to see available IDs. Name-only input is accepted only when it uniquely matches a single row. (CLI: `--model`, `-m`)
- `output`: `None` (optional, default `None`) - Unsupported/deprecated: any --output/-o value returns INVALID_INPUT (exit 2) before annotation. Omit it and use export create for files. (CLI: `--output`, `-o`)
- `batch_size`: `int>=1` (optional, default `10`) - Batch size for processing (>=1; bounds memory per chunk) (CLI: `--batch-size`, `-b`)
- `limit`: `int>=1?` (optional, default `None`) - Max number of images to annotate (>=1) (CLI: `--limit`)
- `offset`: `int>=0` (optional, default `0`) - Skip the first N eligible images (for sharding) (CLI: `--offset`)
- `image_id`: `list[int]` (optional, default `[]`) - Target specific image ID(s); repeatable (CLI: `--image-id`, `-i`)
- `image_ids_file`: `str?` (optional, default `None`) - UTF-8 newline/comma IDs, max 100,000; exclusive with image_id. Filter intersection, ascending ID order, offset, limit; per-image outcomes streamed. (CLI: `--image-ids-file`)
- `unrated`: `bool` (optional, default `False`) - Annotate only images without any saved rating rows. (CLI: `--unrated`)
- `missing_model`: `str?` (optional, default `None`) - Annotate only images without saved annotations from the given LiteLLM model ID. (CLI: `--missing-model`)
- `resolution`: `int>=1?` (optional, default `None`) - Use processed images at this resolution (long side in pixels, e.g. 512) to satisfy the original-image guard; omitted requires processed registered records. Images without a matching processed image are skipped. (CLI: `--resolution`)
- `run_id`: `str?` (optional, default `None`) - New durable run identity; exclusive with resume. (CLI: `--run-id`)
- `resume`: `str?` (optional, default `None`) - Resume pending items from this run; same project/models/config required; no selection or resolution overrides. (CLI: `--resume`)

**Output `AnnotateRunOutcome`**

- `kind`: `item` (optional, default `item`)
- `type`: `annotation_outcome` (optional, default `annotation_outcome`)
- `image_id`: `int` (required)
- `status`: `completed | failed | skipped | unexecuted | pending | in_flight` (required)
- `reason`: `str?` (optional, default `None`)
- `saved`: `bool` (optional, default `False`)

**Output `AnnotateRunItem`**

- `type`: `annotation` (optional, default `annotation`)
- `image_id`: `int?` (optional, default `None`)
- `phash`: `str` (required)
- `file_path`: `str?` (optional, default `None`)
- `models`: `list[AnnotateRunModelResult]` (required)

**Output `AnnotateRunResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed?` (optional, default `None`)
- `project`: `str?` (optional, default `None`)
- `total`: `int?` (optional, default `None`)
- `completed`: `int?` (optional, default `None`)
- `unexecuted`: `int?` (optional, default `None`)
- `interrupted`: `bool` (optional, default `False`)
- `reason`: `str?` (optional, default `None`)
- `run_id`: `str?` (optional, default `None`)
- `resumed`: `bool?` (optional, default `None`)
- `state_path`: `str?` (optional, default `None`)
- `pending`: `int?` (optional, default `None`)
- `in_flight`: `int?` (optional, default `None`)
- `resolution_skipped`: `int` (optional, default `0`)
- `annotated`: `int` (required)
- `skipped`: `int` (required)
- `errors`: `int` (required)
- `loaded`: `int` (required)
- `results`: `int` (required)
- `models`: `list[str]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch cancel`

Cancel a provider batch job.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch cancel"
```

#### Models

**Input `BatchCancelInput`**

- `job_id`: `int` (required) - Provider Batch job ID (CLI: `job_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)

**Output `BatchJobResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed?` (optional, default `None`)
- `project`: `str?` (optional, default `None`)
- `total`: `int?` (optional, default `None`)
- `submitted`: `int?` (optional, default `None`)
- `failed`: `int?` (optional, default `None`)
- `unsubmitted`: `int?` (optional, default `None`)
- `interrupted`: `bool` (optional, default `False`)
- `job_ids`: `list[int]` (optional)
- `job_id`: `int?` (optional, default `None`)
- `job`: `dict?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch fetch`

Fetch normalized provider batch results and artifacts.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch fetch"
```

#### Models

**Input `BatchFetchInput`**

- `job_id`: `int` (required) - Provider Batch job ID (CLI: `job_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `output_dir`: `str?` (optional, default `None`) - Artifact output directory (CLI: `--output-dir`, `-o`)

**Output `BatchFetchResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `job_id`: `int` (required)
- `provider_status`: `str?` (optional, default `None`)
- `items`: `int` (required)
- `succeeded`: `int` (required)
- `failed`: `int` (required)
- `artifacts`: `list[dict]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch import`

Fetch and import provider batch results into annotations.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch import"
```

#### Models

**Input `BatchImportInput`**

- `job_id`: `int` (required) - Provider Batch job ID (CLI: `job_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `output_dir`: `str?` (optional, default `None`) - Artifact output directory (CLI: `--output-dir`, `-o`)

**Output `BatchImportResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed` (optional, default `success`) - Partial success returns ok=false and exit 3; total failure exits 1; normal skip/empty exits 0.
- `incomplete`: `bool` (optional, default `False`)
- `already_imported`: `int` (optional, default `0`)
- `non_importable`: `int` (optional, default `0`)
- `save_skipped`: `int` (optional, default `0`)
- `missing_custom_ids`: `list[str]` (optional)
- `failed_custom_ids`: `list[str]` (optional)
- `failed_image_ids`: `list[int]` (optional)
- `error_details`: `list[str]` (optional)
- `hint`: `str?` (optional, default `None`)
- `ratings_saved`: `int?` (optional, default `None`)
- `rating_breakdown`: `dict?` (optional, default `None`)
- `job_id`: `int?` (optional, default `None`)
- `imported`: `int` (required)
- `skipped`: `int` (required)
- `errors`: `int` (required)
- `total`: `int` (required)
- `job_imported`: `bool` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch list`

List persisted provider batch jobs.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch list"
```

#### Models

**Input `BatchListInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `provider`: `str?` (optional, default `None`) - Filter by provider (CLI: `--provider`)
- `status`: `str?` (optional, default `None`) - Filter by common job status (CLI: `--status`)
- `limit`: `int[1,1000]` (optional, default `100`) - Maximum rows (CLI: `--limit`)
- `offset`: `int>=0` (optional, default `0`) - Rows to skip (CLI: `--offset`)

**Output `ProviderBatchJob`**

- `id`: `int` (required)
- `provider`: `str` (required)
- `provider_job_id`: `str?` (optional, default `None`)
- `status`: `str` (required)
- `provider_status`: `str?` (optional, default `None`)
- `endpoint`: `str?` (optional, default `None`)
- `model_id`: `int?` (optional, default `None`)
- `request_count`: `int` (required)
- `succeeded_count`: `int` (required)
- `failed_count`: `int` (required)
- `canceled_count`: `int` (required)
- `expired_count`: `int` (required)
- `submitted_at`: `str?` (optional, default `None`)
- `completed_at`: `str?` (optional, default `None`)
- `canceled_at`: `str?` (optional, default `None`)
- `expires_at`: `str?` (optional, default `None`)
- `imported_at`: `str?` (optional, default `None`)

**Output `BatchListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch status`

Show provider batch job status. Pass --items to list per-image items (custom_id, image_id, model_id, task_type, status, error_type); useful for auditing duplicate rating_preflight submissions.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch status"
```

#### Models

**Input `BatchStatusInput`**

- `job_id`: `int` (required) - Provider Batch job ID (CLI: `job_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `refresh`: `bool` (optional, default `True`) - Refresh provider status first (CLI: `--refresh`, `--no-refresh`)
- `items`: `bool` (optional, default `False`) - Emit ProviderBatchItemRecord item rows before the result. Use to inspect per-image item state or detect duplicate submissions. (CLI: `--items`, `--no-items`)
- `limit`: `int[1,500]` (optional, default `500`) - Page size for items query (only when --items is set). (CLI: `--limit`)
- `offset`: `int>=0` (optional, default `0`) - Rows to skip in items query (only when --items is set). (CLI: `--offset`)
- `item_status`: `str?` (optional, default `None`) - Filter items by status when --items is set (e.g. succeeded, failed). (CLI: `--item-status`)

**Output `ProviderBatchItemRecord`**

Emitted per item when --items is set. Precedes the BatchStatusResult row.

- `id`: `int` (required)
- `job_id`: `int` (required)
- `custom_id`: `str` (required)
- `image_id`: `int?` (optional, default `None`)
- `model_id`: `int?` (optional, default `None`)
- `task_type`: `str?` (optional, default `None`)
- `status`: `str` (required)
- `error_type`: `str?` (optional, default `None`)
- `error_message`: `str?` (optional, default `None`)

**Output `BatchStatusResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `job`: `ProviderBatchJob?` (optional, default `None`)
- `items_count`: `int?` (optional, default `None`) - Number of item rows emitted (null when --items is not set).
- `items_limit`: `int?` (optional, default `None`) - Page size used for items query.
- `items_offset`: `int?` (optional, default `None`) - Rows skipped in items query.
- `items_has_more`: `bool?` (optional, default `None`) - True when len(items) >= limit, indicating further pages may exist.

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `batch submit`

Submit registered images to a provider batch job.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "batch submit"
```

#### Models

**Input `BatchSubmitInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `model`: `str` (required) - LiteLLM model ID or unique display name (CLI: `--model`, `-m`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, exclusive with image_ids_file. (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - UTF-8 newline/comma IDs; max 100,000; exclusive with image_ids. Entire input validated before sending; jobs split at provider limit 500. (CLI: `--image-ids-file`)
- `provider`: `str?` (optional, default `None`) - Provider override: openai/anthropic (CLI: `--provider`)
- `endpoint`: `str?` (optional, default `None`) - Provider endpoint override (CLI: `--endpoint`)
- `prompt_profile`: `str` (optional, default `default`) - Prompt profile name (CLI: `--prompt-profile`)
- `description`: `str?` (optional, default `None`) - Provider job description (CLI: `--description`)
- `task_type`: `str` (optional, default `annotation`) - Task type: annotation or rating_preflight. rating_preflight requires direct openai, endpoint /v1/moderations, an openai/omni-moderation-* model, and ratings model_type. (CLI: `--task-type`)
- `resolution`: `int?` (optional, default `None`) - Processed image long-edge resolution to use (e.g. 512). Omit to use stored_image_path. When specified, the original image guard is bypassed and processed images are submitted. (CLI: `--resolution`)

**Output `BatchSubmissionItem`**

- `kind`: `item` (optional, default `item`)
- `type`: `batch_submission` (optional, default `batch_submission`)
- `status`: `submitted | failed | unsubmitted` (required)
- `image_ids`: `list[int]` (required) - At most 500 IDs assigned to this job/attempt.
- `job_id`: `int?` (optional, default `None`)
- `reason`: `str?` (optional, default `None`)

**Output `BatchJobResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed?` (optional, default `None`)
- `project`: `str?` (optional, default `None`)
- `total`: `int?` (optional, default `None`)
- `submitted`: `int?` (optional, default `None`)
- `failed`: `int?` (optional, default `None`)
- `unsubmitted`: `int?` (optional, default `None`)
- `interrupted`: `bool` (optional, default `False`)
- `job_ids`: `list[int]` (optional)
- `job_id`: `int?` (optional, default `None`)
- `job`: `dict?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `errors get`

Get a single error record by ID (full detail). `list` は error_message を切り詰め stack_trace / file_path / image_id を省くため、1 件の全容を確認するには本コマンドを使う。

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "errors get"
```

#### Models

**Input `ErrorsGetInput`**

- `error_id`: `int` (required) - Error record ID to retrieve (positional). (CLI: `error_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)

**Output `ErrorRecordDetailItem`**

- `kind`: `item` (optional, default `item`)
- `id`: `int` (required)
- `image_id`: `int?` (required)
- `operation_type`: `str` (required)
- `error_type`: `str` (required)
- `error_message`: `str` (required)
- `stack_trace`: `str?` (required)
- `file_path`: `str?` (required)
- `model_name`: `str?` (required)
- `resolved_at`: `str?` (required)
- `created_at`: `str?` (required)

**Output `ErrorsGetResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `errors list`

List error records. Default: unresolved only.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "errors list"
```

#### Models

**Input `ErrorsListInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `operation`: `str?` (optional, default `None`) - Filter by operation_type (search/registration/annotation) (CLI: `--operation`)
- `error_type`: `str?` (optional, default `None`) - Filter by error_type (CLI: `--error-type`)
- `message_contains`: `str?` (optional, default `None`) - Partial match on error_message (CLI: `--message-contains`)
- `all`: `bool` (optional, default `False`) - Include resolved records (CLI: `--all`)
- `limit`: `int[0,500]` (optional, default `50`) - Max records; 0 returns no records (CLI: `--limit`)
- `offset`: `int>=0` (optional, default `0`) - Nonnegative offset for pagination (CLI: `--offset`)

**Output `ErrorRecordItem`**

- `kind`: `item` (optional, default `item`)
- `id`: `int` (required)
- `operation_type`: `str` (required)
- `error_type`: `str` (required)
- `error_message`: `str` (required)
- `model_name`: `str?` (optional, default `None`)
- `resolved_at`: `str?` (optional, default `None`)
- `created_at`: `str?` (optional, default `None`)

**Output `ErrorListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `errors resolve`

Mark error records as resolved. Use --dry-run to preview.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "errors resolve"
```

#### Models

**Input `ErrorsResolveInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `ids`: `str?` (optional, default `None`) - Comma-separated error record IDs (CLI: `--ids`)
- `operation`: `str?` (optional, default `None`) - Bulk-resolve by operation_type (CLI: `--operation`)
- `error_type`: `str?` (optional, default `None`) - Bulk-resolve by error_type (CLI: `--error-type`)
- `message_contains`: `str?` (optional, default `None`) - Bulk-resolve by partial message match (CLI: `--message-contains`)
- `dry_run`: `bool` (optional, default `False`) - Preview count without writing (CLI: `--dry-run`)

**Output `ErrorsResolveResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `message`: `str` (required)
- `status`: `success | partial_success | failed` (optional, default `success`) - Partial success returns ok=false and exit 3; total failure exits 1; normal skip/empty exits 0.
- `requested`: `int?` (optional, default `None`)
- `resolved`: `int` (required)
- `dry_run`: `bool` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `export create`

Export selected IDs; --dry-run previews count and manifest without writes and supports root --read-only. See [export contract](cli-export-results.md).

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `file_read`, `file_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "export create"
```

#### Models

**Input `ExportCreateInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500 (or use image_ids_file). Use images search to resolve IDs. (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Path to a newline/comma-separated image ID list for bulk operations (chunked internally, max 100,000; mutually exclusive with image_ids, Issue #1216). For tags commands, bulk mode emits TagsBulkProgressItem chunk-progress rows instead of per-image TagsEditItem. (CLI: `--image-ids-file`)
- `output`: `str` (required) - Output directory for exported dataset (CLI: `--output`, `-o`)
- `resolution`: `int` (optional, default `512`) - Target resolution for processed images (CLI: `--resolution`, `-r`)
- `tag_languages`: `list[str]?` (optional, default `None`) - Tag languages to export. 'canonical' keeps existing tag output; multiple values create language-specific dataset directories. (CLI: `--tag-language`)
- `dry_run`: `bool` (optional, default `False`) - Preview image count and manifest without writing dataset outputs or database records. (CLI: `--dry-run`)

**Output `ExportCreateResult`**

Partial success exits 3; total failure exits 1; both return ok=false; total_images remains the requested count. See [export result and retry contract](cli-export-results.md).

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `status`: `success | partial_success | failed` (required)
- `requested`: `int` (required)
- `exported`: `int` (required)
- `skipped`: `int` (required)
- `failed`: `int` (required)
- `exported_ids`: `list[int]` (required)
- `failed_ids`: `list[int]` (required)
- `error_details`: `list[dict]` (required)
- `message`: `str` (required)
- `output_path`: `str?` (optional, default `None`)
- `total_images`: `int?` (optional, default `None`)
- `resolution`: `int?` (optional, default `None`)
- `tag_languages`: `list[str]?` (optional, default `None`)
- `count`: `int?` (optional, default `None`)

**Output `ExportPreviewItem`**

- `kind`: `item` (optional, default `item`)
- `image_id`: `int` (required)
- `source_path`: `str` (required)
- `destinations`: `list[ExportPreviewDestination]` (required)

**Output `ExportPreviewResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `message`: `str` (required)
- `status`: `success | partial_success | failed` (required)
- `dry_run`: `true` (required)
- `requested`: `int` (required)
- `would_export`: `int` (required)
- `skipped`: `int` (required)
- `failed`: `int` (required)
- `ready_ids`: `list[int]` (required)
- `failed_ids`: `list[int]` (required)
- `metadata_files`: `list[str]` (required)
- `error_details`: `list[dict]` (required)
- `output_path`: `str` (required)
- `total_images`: `int` (required)
- `resolution`: `int` (required)
- `tag_languages`: `list[str]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images analyze-metadata`

Read generation metadata (PNG parameters / ComfyUI prompt / EXIF UserComment) from stored image files and save the analysis. Keeps saved raw data; never edits tags or captions.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images analyze-metadata"
```

#### Models

**Input `ImagesAnalyzeMetadataInput`**

- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500. Omit to process images without an analysis result. (CLI: `image_ids_positional`, `--image-ids`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `force`: `bool` (optional, default `False`) - Replace existing results (needs IDs). (CLI: `--force`)
- `limit`: `int[1,500]` (optional, default `500`) - Max unanalyzed images when IDs are omitted. (CLI: `--limit`)
- `after_id`: `int>=0` (optional, default `0`) - Only unanalyzed images with a larger ID (pass next_after_id to continue). (CLI: `--after-id`)

**Output `ImagesAnalyzeMetadataItem`**

- `image_id`: `int` (required)
- `action`: `analyzed | skipped_analyzed | not_found | file_missing | save_failed` (required) - analyzed/skipped_analyzed/not_found/file_missing/save_failed
- `status`: `parsed | partial | unsupported | no_metadata | failed?` (optional, default `None`) - parsed/partial/unsupported/no_metadata/failed
- `tool`: `str?` (optional, default `None`)

**Output `ImagesAnalyzeMetadataResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `message`: `str` (required)
- `target_images`: `int` (required)
- `analyzed`: `int` (required)
- `skipped_analyzed`: `int` (required)
- `file_missing`: `int` (required)
- `save_failed`: `int` (required)
- `remaining_unanalyzed`: `int` (required)
- `next_after_id`: `int?` (optional, default `None`) - Pass to --after-id to continue.

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images crop`

Crop one rectangle out of a parent image and register it as an independent image. Tags and rating are copied from the parent at creation time and then managed separately.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`, `file_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images crop"
```

#### Models

**Input `ImagesCropInput`**

- `image_id`: `int` (required) - Parent image ID to crop from. (CLI: `image_id`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `x`: `int` (required) - Left edge in parent pixels. (CLI: `--x`)
- `y`: `int` (required) - Top edge in parent pixels. (CLI: `--y`)
- `width`: `int` (required) - Width in parent pixels; must be >= 1. (CLI: `--width`)
- `height`: `int` (required) - Height in parent pixels; must be >= 1. (CLI: `--height`)
- `tag`: `list[str]?` (optional, default `None`) - Tags copied onto the crop; repeat the flag. Omit to copy every candidate tag of the parent. (CLI: `--tag`)
- `rating`: `str?` (optional, default `None`) - PG, PG-13, R, X or XXX. Omit to inherit the parent manual rating. (CLI: `--rating`)
- `origin`: `str` (optional, default `manual`) - Provenance stored on the relation row, e.g. manual or a detector name. (CLI: `--origin`)

**Output `ImagesCropItem`**

- `kind`: `item` (optional, default `item`)
- `parent_image_id`: `int` (required)
- `child_image_id`: `int` (required)
- `x`: `int` (required)
- `y`: `int` (required)
- `width`: `int` (required)
- `height`: `int` (required)
- `origin`: `str` (required)
- `rating`: `str?` (optional, default `None`) - Rating stored on the crop; null when unset.

**Output `ImagesCropResult`**

An invalid rectangle or missing parent exits 2 with INVALID_INPUT and leaves no rows or files behind.

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `parent_image_id`: `int` (required)
- `child_image_id`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images crop-batch`

Create crop images in bulk from an externally prepared JSONL of rectangles (one row = image_id + rectangle). Reuses images crop per rectangle; tags and rating are copied from the parent. Coordinates are EXIF-oriented display pixels (ADR 0092). See ADR 0103.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`, `file_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images crop-batch"
```

#### Models

**Input `ImagesCropBatchInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `rects`: `str` (required) - JSONL, one object per line: {"image_id": int, "x": int, "y": int, "width": int, "height": int, "origin"?: str, "score"?: float}. Unknown keys are rejected; max 500 non-blank rows (RESULT_SET_TOO_LARGE, exit 2). (CLI: `--rects`)
- `origin`: `str` (optional, default `manual`) - Provenance for rows that omit origin. (CLI: `--origin`)
- `dry_run`: `bool` (optional, default `False`) - Validate rectangles and report would_create without writing. (CLI: `--dry-run`)

**Output `ImagesCropBatchItem`**

- `kind`: `item` (optional, default `item`)
- `line`: `int?` (optional, default `None`) - 1-based JSONL line number.
- `status`: `created | would_create | skipped | failed` (required)
- `parent_image_id`: `int?` (optional, default `None`)
- `child_image_id`: `int?` (optional, default `None`) - Created child, or the existing image when skipped.
- `x`: `int?` (optional, default `None`)
- `y`: `int?` (optional, default `None`)
- `width`: `int?` (optional, default `None`)
- `height`: `int?` (optional, default `None`)
- `origin`: `str?` (optional, default `None`)
- `score`: `float?` (optional, default `None`) - Echoed from the row; not stored.
- `reason`: `already_exists | duplicate_image | invalid_rect | parent_not_found | io_error | registration_failed | invalid_row?` (optional, default `None`)
- `message`: `str?` (optional, default `None`)

**Output `ImagesCropBatchResult`**

Re-running the same file is idempotent: existing parent+rectangle+origin rows are skipped.

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `status`: `success | partial_success | failed` (required) - Skipped rows count as success; partial success exits 3; total failure exits 1.
- `message`: `str` (required)
- `project`: `str` (required)
- `dry_run`: `bool` (required)
- `total`: `int` (required)
- `created`: `int` (required)
- `would_create`: `int` (required)
- `skipped`: `int` (required)
- `failed`: `int` (required)
- `created_ids`: `list[int]` (required)
- `failed_lines`: `list[int]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images crop-detect`

Detect persons, faces or heads with a bundled ONNX detector and create crop images from the padded boxes through the same bulk path as images crop-batch (one box = one item). origin stores the detector name; score is output only. Detection runs on EXIF-oriented pixels (ADR 0092). The model is downloaded from Hugging Face Hub on first use. See ADR 0110.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`, `file_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "images crop-detect"
```

#### Models

**Input `ImagesCropDetectInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `class`: `person | face | head | halfbody` (required) - Target class -> detector (origin) and default min_score: person -> person_detect_v1.3_s (0.324), face -> face_detect_v1.4_s (0.307), head -> head_detect_v2.0_s (0.413). halfbody is rejected with INVALID_INPUT (exit 2): its license terms are not reviewed. (CLI: `--class`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated parent image IDs, max 500 (or use --image-ids-file). (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Newline/comma-separated parent image ID list. More than 500 distinct IDs is rejected with RESULT_SET_TOO_LARGE (exit 2). (CLI: `--image-ids-file`)
- `min_score`: `float[0.0,1.0]?` (optional, default `None`) - Minimum score to crop; omit for the per-class default above. Detections scoring at least 0.5 x min_score but below it are reported as skipped (below_min_score). (CLI: `--min-score`)
- `padding`: `float[0.0,1.0]` (optional, default `0.1`) - Margin added on each side as a ratio of the box width/height, clamped to the image. (CLI: `--padding`)
- `nms_iou`: `float<=1.0>0.0` (optional, default `0.5`) - IoU threshold for non-maximum suppression within one image. (CLI: `--nms-iou`)
- `min_long_edge`: `int>=1` (optional, default `256`) - Padded boxes with a shorter long edge (px) are skipped (below_min_long_edge). (CLI: `--min-long-edge`)
- `existing_iou`: `float<=1.0>0.0` (optional, default `0.7`) - Boxes whose IoU with an existing crop of the same parent is at least this are skipped (overlaps_existing_crop). The same rectangle and origin is reported as already_exists instead. (CLI: `--existing-iou`)
- `dry_run`: `bool` (optional, default `False`) - Detect and report would_create without writing. (CLI: `--dry-run`)

**Output `ImagesCropDetectItem`**

- `kind`: `item` (optional, default `item`)
- `line`: `int?` (optional, default `None`) - Always null (detector-derived).
- `status`: `created | would_create | skipped | failed` (required)
- `parent_image_id`: `int?` (optional, default `None`)
- `child_image_id`: `int?` (optional, default `None`) - Created child, or the existing image when skipped as a duplicate.
- `x`: `int?` (optional, default `None`) - Null for per-image results (no_detection, failures).
- `y`: `int?` (optional, default `None`)
- `width`: `int?` (optional, default `None`)
- `height`: `int?` (optional, default `None`)
- `origin`: `str?` (optional, default `None`) - Detector name.
- `score`: `float?` (optional, default `None`) - Detection score; not stored.
- `reason`: `already_exists | duplicate_image | invalid_rect | parent_not_found | io_error | registration_failed | no_detection | below_min_score | below_min_long_edge | overlaps_existing_crop | detector_unavailable | detection_failed?` (optional, default `None`) - Skipped: already_exists, duplicate_image, no_detection, below_min_score, below_min_long_edge, overlaps_existing_crop. Failed: invalid_rect, parent_not_found, io_error, registration_failed, detector_unavailable (model download/load failed; not retried for later images), detection_failed.
- `message`: `str?` (optional, default `None`)

**Output `ImagesCropBatchResult`**

Same result contract as images crop-batch. Re-running is idempotent.

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `status`: `success | partial_success | failed` (required) - Skipped results count as success; partial success exits 3; total failure exits 1.
- `message`: `str` (required)
- `project`: `str` (required)
- `dry_run`: `bool` (required)
- `total`: `int` (required)
- `created`: `int` (required)
- `would_create`: `int` (required)
- `skipped`: `int` (required)
- `failed`: `int` (required)
- `created_ids`: `list[int]` (required)
- `failed_lines`: `list[int]` (required) - Always empty.

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images duplicates`

Read-only duplicate candidates from saved 64-bit pHashes, capped at 10,000 project images. See [duplicate report](cli-duplicate-report.md).

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images duplicates"
```

#### Models

**Input `DuplicateReportInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `max_distance`: `int[0,64]` (optional, default `4`) - Maximum Hamming distance of connecting pairs; cluster endpoints may exceed this threshold. (CLI: `--max-distance`)
- `limit`: `int[1,500]?` (optional, default `None`) - Output cap for clusters and members; omitted means 100, and any explicit value is rejected with --representatives. Detection and counts cover the complete bounded project. (CLI: `--limit`)
- `representatives`: `bool` (optional, default `False`) - Output only one representative for every cluster (largest width*height, ties by smallest image_id; singletons excluded). Plain mode prints one image ID per line for `review run --image-ids-file`; JSONL items use DuplicateRepresentativeItem. Reference only; not evidence for other images. (CLI: `--representatives`)

**Output `DuplicateClusterItem`**

- `kind`: `item` (optional, default `item`)
- `cluster_id`: `int` (required)
- `member_count`: `int` (required)
- `members`: `list[DuplicateMember]` (required)
- `members_truncated`: `bool` (required)

**Output `DuplicateRepresentativeItem`**

- `kind`: `item` (optional, default `item`)
- `image_id`: `int` (required)
- `cluster_id`: `int` (required)
- `member_count`: `int` (required)
- `width`: `int?` (required)
- `height`: `int?` (required)
- `pixel_count`: `int?` (required)

**Output `DuplicateReportResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `read_only`: `true` (required)
- `status`: `success` (required)
- `candidate_only`: `true` (required)
- `total_images`: `int` (required)
- `valid_phash_images`: `int` (required)
- `missing_phash_images`: `int` (required)
- `invalid_phash_images`: `int` (required)
- `unique_phashes`: `int` (required)
- `cluster_count`: `int` (required)
- `clustered_images`: `int` (required)
- `unclustered_images`: `int` (required)
- `returned_clusters`: `int` (required)
- `clusters_truncated`: `bool` (required)
- `max_distance`: `int` (required)
- `hash_bits`: `64` (required)
- `distance_metric`: `hamming` (required)
- `clustering`: `connected_components` (required)
- `compared_hash_pairs`: `int` (required)
- `limit`: `int` (required)
- `max_images`: `10000` (required)
- `max_pair_comparisons`: `49995000` (required)

**Output `DuplicateRepresentativeResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `read_only`: `true` (required)
- `status`: `success` (required)
- `candidate_only`: `true` (required)
- `total_images`: `int` (required)
- `valid_phash_images`: `int` (required)
- `missing_phash_images`: `int` (required)
- `invalid_phash_images`: `int` (required)
- `unique_phashes`: `int` (required)
- `cluster_count`: `int` (required)
- `clustered_images`: `int` (required)
- `unclustered_images`: `int` (required)
- `max_distance`: `int` (required)
- `hash_bits`: `64` (required)
- `distance_metric`: `hamming` (required)
- `clustering`: `connected_components` (required)
- `compared_hash_pairs`: `int` (required)
- `max_images`: `10000` (required)
- `max_pair_comparisons`: `49995000` (required)
- `representatives_only`: `true` (required)
- `representative_count`: `int` (required)
- `review_max_images`: `int` (required)
- `exceeds_review_max_images`: `bool` (required)
- `reference_only`: `true` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images list`

List images in a project. Count-first (ADR 0060): default returns only the matching count; --fetch returns id+path rows but only when the total is <= 500.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images list"
```

#### Models

**Input `ImagesListInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `fetch`: `bool` (optional, default `False`) - Fetch id+path rows instead of only the count. Succeeds only when total matches are <= 500; a larger result yields RESULT_SET_TOO_LARGE (narrow the filter). Omitted (default) returns the count only. (CLI: `--fetch`)
- `limit`: `int[1,500]` (optional, default `500`) - Page size within a <= 500 match set (ADR 0060). Does NOT bypass the count-first gate: a total over 500 is rejected regardless of limit. (CLI: `--limit`, `-l`)
- `offset`: `int>=0` (optional, default `0`) - Rows to skip within a <= 500 match set. Pagination is bounded to the working set; it is not a way to page through a result larger than 500. (CLI: `--offset`)
- `unrated`: `bool` (optional, default `False`) - Show only images without any saved rating rows. (CLI: `--unrated`)

**Output `ImagesListItem`**

- `image_id`: `int?` (optional, default `None`)
- `file_path`: `str?` (optional, default `None`)

**Output `ImagesListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required) - Item rows emitted in this response (0 in count-first mode). Use total for the match count.
- `total`: `int?` (optional, default `None`) - Total number of matching images.
- `limit`: `int?` (optional, default `None`)
- `offset`: `int?` (optional, default `None`)
- `has_more`: `bool?` (optional, default `None`)
- `emit_ids`: `bool?` (optional, default `None`)
- `truncated`: `bool?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images process`

Generate processed images offline from exact registered IDs; preserve originals.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`, `file_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images process"
```

#### Models

**Input `ImagesProcessInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Exact original IDs, max 500; exclusive with image_ids_file. (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - ID list file, max 100,000; exclusive with image_ids. (CLI: `--image-ids-file`)
- `resolution`: `int[32,8192]` (optional, default `512`) - Long side, multiple of 32 from 32 to 8192; offline CPU resize. (CLI: `--resolution`, `-r`)
- `rebuild`: `bool` (optional, default `False`) - Regenerate valid exact-resolution outputs too. (CLI: `--rebuild`)

**Output `ImagesProcessItem`**

- `kind`: `item` (optional, default `item`)
- `image_id`: `int` (required)
- `status`: `success | skipped | failed` (required)
- `resolution`: `int` (required)
- `output_path`: `str?` (optional, default `None`)
- `processed_image_id`: `int?` (optional, default `None`)
- `reason`: `str?` (optional, default `None`)

**Output `ImagesProcessResult`**

Partial success returns ok=false and exit 3; total failure exits 1. See [offline processing](cli-image-processing.md).

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (required)
- `status`: `success | partial_success | failed` (required)
- `message`: `str` (required)
- `project`: `str` (required)
- `resolution`: `int` (required)
- `total`: `int` (required)
- `processed`: `int` (required)
- `skipped`: `int` (required)
- `failed`: `int` (required)
- `processed_ids`: `list[int]` (required)
- `skipped_ids`: `list[int]` (required)
- `failed_ids`: `list[int]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images rate`

Set or clear manual rating (MANUAL_EDIT) for images in bulk (Issue #1504). Default dry-run; use --apply to write. Never overwrites AI model rating rows.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images rate"
```

#### Models

**Input `ImagesRateInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `rating`: `str` (required) - Manual rating value: PG, PG-13, R, X, XXX, or none to clear (case-insensitive). (CLI: `--rating`, `-r`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500 (or use --image-ids-file). (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Path to a newline/comma-separated image ID list for bulk operations (chunked internally, max 100,000; mutually exclusive with image_ids, Issue #1216). For tags commands, bulk mode emits TagsBulkProgressItem chunk-progress rows instead of per-image TagsEditItem. (CLI: `--image-ids-file`)
- `apply`: `bool` (optional, default `False`) - Write to DB (default: dry-run). (CLI: `--apply`)

**Output `ImagesRateItem`**

- `kind`: `item` (optional, default `item`)
- `image_id`: `int?` (optional, default `None`)
- `chunk_images`: `int?` (optional, default `None`)
- `processed`: `int?` (optional, default `None`)
- `rating`: `str?` (optional, default `None`)
- `updated_count`: `int?` (optional, default `None`)
- `unchanged_count`: `int?` (optional, default `None`)
- `cleared_count`: `int?` (optional, default `None`)
- `status`: `dry_run | updated | cleared | unchanged | changed | failed` (required)
- `error`: `str?` (optional, default `None`)

**Output `ImagesRateResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `status`: `success | partial_success | failed` (optional, default `success`) - Partial success returns ok=false and exit 3; total failure exits 1; normal skip/empty exits 0.
- `message`: `str` (required)
- `project`: `str` (required)
- `rating`: `str?` (optional, default `None`)
- `dry_run`: `bool` (required)
- `target_count`: `int` (required)
- `target_images`: `int` (required)
- `updated_count`: `int` (required)
- `unchanged_count`: `int` (required)
- `cleared_count`: `int` (optional, default `0`)
- `failed_chunks`: `int` (optional, default `0`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images register`

Register images and stream authoritative DB outcomes with unique selected IDs. See docs/cli-registration-workflow.md for same-project ID handoff and partial failures.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `file_read`, `file_write`, `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images register"
```

#### Models

**Input `ImagesRegisterInput`**

- `path`: `str` (required) - Image file or directory path (CLI: `path`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `skip_duplicates`: `bool` (optional, default `True`) - Exclude duplicate IDs from downstream selection; --include-duplicates selects existing IDs once. (CLI: `--skip-duplicates`, `--include-duplicates`)

**Output `ImagesRegisterItem`**

- `input_path`: `str` (required)
- `outcome`: `registered | variant | duplicate | failed` (required)
- `image_id`: `int?` (optional, default `None`)
- `project`: `str?` (optional, default `None`)
- `selected`: `bool` (optional, default `False`) - True once per unique eligible ID; duplicates require include-duplicates.
- `error`: `str?` (optional, default `None`)
- `kind`: `item` (optional, default `item`)

**Output `ImagesRegisterResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `status`: `success | partial_success | failed` (optional, default `success`) - Partial success returns ok=false and exit 3; total failure exits 1; normal skip/empty exits 0.
- `variant`: `int` (optional, default `0`)
- `project`: `str?` (optional, default `None`)
- `target_count`: `int` (optional, default `0`)
- `interrupted`: `bool` (optional, default `False`)
- `unprocessed`: `int` (optional, default `0`)
- `total`: `int` (required)
- `registered`: `int` (required)
- `skipped`: `int` (required)
- `errors`: `int` (required)
- `error_details`: `list[str]` (optional) - At most 100 samples; complete error details are in item rows.
- `error_details_truncated`: `bool` (optional, default `False`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images search`

Search images by JSON query. Returns image_ids for use with export create or tags commands.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images search"
```

#### Models

**Input `ImagesSearchInput`**

Pass exactly one of --query or --query-file.

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `query_file`: `str?` (optional, default `None`) - Path to a JSON file containing the search schema. (CLI: `--query-file`)
- `query`: `str?` (optional, default `None`) - JSON search schema string, or '-' to read from stdin. (CLI: `--query`)

**Input `ImageSearchQuery`**

JSON body schema passed via --query or --query-file.

- `image_ids`: `list[int]?` (optional, default `None`)
- `tags`: `list[str]?` (optional, default `None`)
- `excluded_tags`: `list[str]?` (optional, default `None`)
- `caption`: `str?` (optional, default `None`)
- `manual_rating`: `str?` (optional, default `None`)
- `ai_rating`: `str?` (optional, default `None`)
- `score_min`: `float?` (optional, default `None`)
- `score_max`: `float?` (optional, default `None`)
- `only_unrated`: `bool` (optional, default `False`)
- `missing_model`: `str?` (optional, default `None`)
- `include_nsfw`: `bool` (optional, default `False`)
- `width_min`: `int>=1?` (optional, default `None`) - Minimum original image width in px (Issue #1216).
- `width_max`: `int>=1?` (optional, default `None`) - Maximum original image width in px.
- `height_min`: `int>=1?` (optional, default `None`) - Minimum original image height in px.
- `height_max`: `int>=1?` (optional, default `None`) - Maximum original image height in px.
- `filename_pattern`: `str?` (optional, default `None`) - Case-insensitive SQL LIKE pattern on filename ('%'/'_' wildcards).
- `format`: `str?` (optional, default `None`) - Case-insensitive exact match on image format (e.g. 'jpeg', 'png').
- `phash`: `str?` (optional, default `None`) - Perceptual hash (16-char hex for exact match, or shorter prefix; case-insensitive, Issue #1506).
- `phash_prefix`: `str?` (optional, default `None`) - Case-insensitive prefix match on perceptual hash (Issue #1506).
- `limit`: `int[1,500]` (optional, default `500`)
- `offset`: `int>=0` (optional, default `0`)
- `emit_ids`: `bool` (optional, default `False`) - Emit ALL matching image_ids (paged internally), bypassing the count-first ResultSetTooLargeError guard, for piping into tags --image-ids-file (Issue #1216). Capped at 100,000.
- `sort`: `list[_SortSpec]` (optional)

**Output `ImagesListItem`**

- `image_id`: `int?` (optional, default `None`)
- `file_path`: `str?` (optional, default `None`)

**Output `ImagesListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required) - Number of item rows emitted in this response (0 in count-first mode).
- `total`: `int?` (optional, default `None`) - Total number of matching images.
- `limit`: `int?` (optional, default `None`)
- `offset`: `int?` (optional, default `None`)
- `has_more`: `bool?` (optional, default `None`)
- `emit_ids`: `bool?` (optional, default `None`)
- `truncated`: `bool?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images show`

Show current tags, captions, scores, and ratings for images (read-only). Use as judgment material before tags add/remove/replace.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "images show"
```

#### Models

**Input `ImagesShowInput`**

- `image_ids`: `str` (required) - Comma-separated image IDs, max 500. Positional form `images show 42 57` also works. (CLI: `image_ids_positional`, `--image-ids`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `include_rejected`: `bool` (optional, default `False`) - Include soft-rejected tags/captions in the output. (CLI: `--include-rejected`)

**Output `ImagesShowItem`**

- `image_id`: `int` (required)
- `phash`: `str?` (optional, default `None`) - Perceptual hash (16-char hex) for cross-checking error logs and duplicates (Issue #1506).
- `stored_image_path`: `str?` (optional, default `None`) - Project-relative stored image path (Issue #1506).
- `metadata`: `dict?` (optional, default `None`) - Image file metadata (stored_image_path/original_image_path/width/height/format/filename/extension/phash/uuid). Null when unavailable.
- `tags`: `list[dict]` (required)
- `captions`: `list[dict]` (required)
- `scores`: `list[dict]` (required)
- `score_labels`: `list[dict]` (required)
- `ratings`: `list[dict]` (required)
- `quality_summary`: `dict` (required)

**Output `ImagesShowResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `target_images`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images tag-ai-generated`

Apply or revoke the ai generated tag in bulk from saved generation metadata (pseudo model GENERATION_METADATA, ADR 0107). Use --dry-run to preview counts.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images tag-ai-generated"
```

#### Models

**Input `ImagesTagAiGeneratedInput`**

- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500. Omit to target all images in the project. (CLI: `image_ids_positional`, `--image-ids`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `revoke`: `bool` (optional, default `False`) - Delete ai generated tag rows added by GENERATION_METADATA instead of adding. (CLI: `--revoke`)
- `dry_run`: `bool` (optional, default `False`) - Count tags that would be added or revoked without writing. (CLI: `--dry-run`)

**Output `ImagesTagAiGeneratedResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required)
- `revoked`: `bool` (required)
- `target_images`: `int` (required)
- `evidence_images`: `int` (required)
- `tags_added`: `int` (required)
- `tags_skipped`: `int` (required)
- `tags_revoked`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `images update`

Add tags to images in a project.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "images update"
```

#### Models

**Input `ImagesUpdateInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `tags`: `str?` (optional, default `None`) - Tags to add (comma-separated) (CLI: `--tags`)
- `image_id`: `int?` (optional, default `None`) - Target specific image by ID (CLI: `--image-id`)

**Output `ImagesUpdateResult`**

Legacy payload retains ok=true; inspect failed_tags and exit code: partial success 3, total failure 1, success 0.

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str?` (optional, default `None`)
- `target_images`: `int?` (optional, default `None`)
- `tags`: `list[str]?` (optional, default `None`)
- `added`: `int?` (optional, default `None`)
- `failed_tags`: `list[str]?` (optional, default `None`)
- `count`: `int?` (optional, default `None`) - Set to 0 on the no-image (no-target) success path.

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `maintenance check`

Read-only provider batch DB consistency, missing image file, and optional remote provider status checks (`--scope provider`); no repair. See [DB maintenance check](cli-maintenance-check.md).

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "maintenance check"
```

#### Models

**Input `MaintenanceCheckInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `scope`: `list[str]?` (optional, default `None`) - Repeat for several scopes: batch, files, provider. Default runs batch and files. (CLI: `--scope`)
- `limit`: `int[1,500]` (optional, default `100`) - Maximum IDs per check; counts cover the whole project. (CLI: `--limit`)

**Output `MaintenanceCheckItem`**

- `kind`: `item` (optional, default `item`)
- `check`: `batch_unknown_status | batch_import_marker_mismatch | batch_active_past_expiry | batch_unlinked_items | image_file_missing | processed_file_missing | provider_status_mismatch | provider_job_missing | provider_counts_mismatch` (required)
- `scope`: `batch | files | provider` (required)
- `id_type`: `job_id | image_id` (required)
- `count`: `int` (required)
- `ids`: `list[int]` (required)
- `ids_truncated`: `bool` (required)
- `description`: `str` (required)

**Output `MaintenanceCheckResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `read_only`: `true` (required)
- `status`: `success | partial_success` (optional, default `success`)
- `scopes`: `list[batch | files | provider]` (required)
- `limit`: `int` (required)
- `checked_batch_jobs`: `int?` (required)
- `checked_images`: `int?` (required)
- `checked_processed_images`: `int?` (required)
- `provider_queried`: `bool` (required)
- `repaired`: `false` (required)
- `checks_run`: `int` (required)
- `issue_count`: `int` (required)
- `issues_found`: `bool` (required)
- `failing_checks`: `list[str]` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `models list`

List available annotator models.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['model_config_create']`
- Side effects: `db_read`, `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "models list"
```

#### Models

**Input `ModelsListInput`**

- `include_deprecated`: `bool` (optional, default `False`) - Include deprecated WebAPI models (CLI: `--include-deprecated`)
- `type`: `str` (optional, default `all`) - Filter by execution type (all / webapi / local) (CLI: `--type`)
- `category`: `str` (optional, default `all`) - Filter by model category (all / tagger / scorer / captioner / vision / rating) (CLI: `--category`)
- `route`: `str?` (optional, default `None`) - Route preference (Issue #241). auto: API key 設定済み provider に応じて direct を優先 / direct: 直接プロバイダー経路のみ / openrouter: OpenRouter 経由のみ / all: 同一モデルの全 route を 1 行ずつ表示。未指定時は config の [model_selection].route_preference を使う (Issue #249)。 (CLI: `--route`)
- `show_unavailable`: `bool` (optional, default `False`) - API key 未設定で利用不可な行も表示する (Issue #249)。default は available な行のみ。ローカル ML モデルは常に available 扱い。 (CLI: `--show-unavailable`)

**Output `ModelsListItem`**

- `provider`: `str` (required)
- `route`: `str` (required)
- `litellm_id`: `str` (required)
- `type`: `webapi | local` (required)
- `category`: `str` (required)
- `available`: `bool` (required)
- `deprecated`: `bool` (required)

**Output `ModelsListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required)
- `preference`: `str` (required)
- `preference_source`: `str` (required)
- `unavailable`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `models refresh`

Refresh available WebAPI model metadata and sync it into the DB.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `network`, `db_write`, `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "models refresh"
```

#### Models

**Input `ModelsRefreshInput`**

- `project`: `str?` (optional, default `None`) - Project to sync model metadata into; the default DB is used when omitted. Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)

**Output `ModelsRefreshResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `discovered`: `int` (required)
- `summary`: `str` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `project create`

Create a project.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `[]`
- Side effects: `file_write`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "project create"
```

#### Models

**Input `ProjectCreateInput`**

- `name`: `str` (required) - Project name (CLI: `name`)
- `description`: `str` (optional, default ``) - Project description (CLI: `--description`, `-d`)

**Output `ProjectCreateResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `name`: `str` (required)
- `path`: `str` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `project delete`

Delete a project.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `[]`
- Side effects: `file_write`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "project delete"
```

#### Models

**Input `ProjectDeleteInput`**

- `name`: `str` (required) - Project name to delete (CLI: `name`)
- `force`: `bool` (optional, default `False`) - Required in JSON mode (--json): omitting it yields INVALID_INPUT since interactive confirmation cannot be driven over stdout. (CLI: `--force`, `-f`)

**Output `ProjectDeleteResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `name`: `str?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `project list`

List projects.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `[]`
- Side effects: `file_read`, `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "project list"
```

#### Models

**Input `ProjectListInput`**

- `format`: `str` (optional, default `table`) - Human-readable format (table)。機械可読出力はグローバル --json を使う (ADR 0057/0058)。 (CLI: `--format`, `-f`)

**Output `ProjectListItem`**

- `name`: `str` (required)
- `created`: `str` (required)
- `path`: `str` (required)

**Output `ProjectListResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `count`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `project prepare`

Explicitly prepare image schema/model seeds; --tags also prepares/downloads tag databases.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_write`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "project prepare"
```

#### Models

**Input `ProjectPrepareInput`**

- `project`: `str` (required) - Existing project to prepare for database access. Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `tags`: `bool` (optional, default `False`) - Also initialize/download tag databases with write permission (CLI: `--tags`)

**Output `ProjectPrepareResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `tags`: `bool` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `review run`

Evaluate existing tags/captions with local Clef; explicit IDs or crop children required. No DB changes unless --save-results stores per-image results (db_write; not with --read-only).

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_write', 'schema_migration', 'directory_create']`
- Side effects: `db_read`, `file_read`, `network`

#### Compact Introspection

```bash
lorairo-cli --json describe "review run"
```

#### Models

**Input `ReviewRunInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Explicit positive image IDs in CSV; exactly one of image_ids/image_ids_file/crop_children_of/crop_children is required. Review max 500 unique images per run; larger selections fail with RESULT_SET_TOO_LARGE before opening the project or sending requests. CSV reader accepts up to 100,000 IDs; duplicates evaluated once. No implicit all-image review. (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - UTF-8 newline/comma IDs, exclusive with image_ids. Review max 500 unique images per run; larger selections fail with RESULT_SET_TOO_LARGE before opening the project or sending requests. File reader accepts up to 100,000 IDs; duplicates evaluated once. (CLI: `--image-ids-file`)
- `crop_children_of`: `int?` (optional, default `None`) - Parent image ID; review only its crop children from crop_relations (parent excluded). Exclusive with other selections. Unknown parent fails with NOT_FOUND; zero children succeeds with image_count=0 (対象 0 件). Over 500 children fails with RESULT_SET_TOO_LARGE. Crop children are resolved inside the opened project, so the 500 cap is checked after opening it but before any Clef request or result save. With save_results the project is opened for writing even when 0 or over 500 children match: an old DB is migrated and missing standard project directories are created, but no review results are saved. (CLI: `--crop-children-of`)
- `crop_children`: `bool` (optional, default `False`) - Review every crop child image in crop_relations. Exclusive with other selections. Zero children succeeds with image_count=0; over 500 fails with RESULT_SET_TOO_LARGE. Crop children are resolved inside the opened project, so the 500 cap is checked after opening it but before any Clef request or result save. With save_results the project is opened for writing even when 0 or over 500 children match: an old DB is migrated and missing standard project directories are created, but no review results are saved. (CLI: `--crop-children`)
- `save_results`: `bool` (optional, default `False`) - Save each image result to annotation_review_results like the GUI (fingerprint, newer result kept). Default false: no DB writes. When true, the project is opened like other write commands (old DB migrated, missing standard directories created), including crop-child resolution. Rejected with root --read-only (INVALID_INPUT). A per-image save failure continues the run and returns exit 3 (or 1 if nothing was saved). (CLI: `--save-results`)

**Output `ReviewRunItem`**

- `kind`: `item` (optional, default `item`)
- `type`: `annotation_review` (required)
- `image_id`: `int` (required)
- `fingerprint`: `str` (required)
- `model_name`: `str` (required)
- `candidate_id`: `str` (required)
- `candidate_kind`: `tag | caption` (required)
- `text`: `str` (required)
- `probability`: `float[0.0,1.0]?` (required)
- `status`: `ok | warning | failed | unevaluated` (required)
- `error`: `str?` (required)

**Output `ReviewRunOutcome`**

- `kind`: `item` (optional, default `item`)
- `type`: `annotation_review_outcome` (required)
- `image_id`: `int` (required)
- `fingerprint`: `str` (required)
- `model_name`: `str` (required)
- `status`: `completed | partial | failed | cancelled | stale | unevaluated` (required)
- `item_count`: `int` (required)
- `error`: `str?` (required)
- `save_status`: `saved | skipped | failed?` (optional, default `None`) - Null without --save-results; skipped means a newer stored result was kept.
- `save_error`: `str?` (optional, default `None`)

**Output `ReviewRunResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `status`: `success | partial_success | failed` (required)
- `image_count`: `int` (required)
- `item_count`: `int` (required)
- `successful`: `int` (required)
- `partial`: `int` (required)
- `failed`: `int` (required)
- `cancelled`: `int` (required)
- `stale`: `int` (required)
- `unevaluated`: `int` (required)
- `warnings`: `int` (required)
- `save_results`: `bool` (optional, default `False`)
- `saved`: `int` (optional, default `0`)
- `save_skipped`: `int` (optional, default `0`)
- `save_failed`: `int` (optional, default `0`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `status`

Show system status (config file and API key availability).

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `[]`
- Side effects: `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "status"
```

#### Models

**Output `StatusResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `environment`: `str` (required)
- `phase`: `str` (required)
- `config_found`: `bool` (required)
- `workspace`: `str?` (optional, default `None`)
- `config_path`: `str?` (optional, default `None`)
- `user_config_path`: `str?` (optional, default `None`)
- `project_config_path`: `str?` (optional, default `None`)
- `user_config_found`: `bool?` (optional, default `None`)
- `project_config_found`: `bool?` (optional, default `None`)
- `projects_base_dir`: `str?` (optional, default `None`)
- `tag_database_dir`: `str?` (optional, default `None`)
- `api_keys`: `dict?` (optional, default `None`)
- `initialized_services`: `dict?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags add`

Add tags to images. Default dry-run; use --apply to write.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags add"
```

#### Models

**Input `TagsAddInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500 (or use image_ids_file). (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Path to a newline/comma-separated image ID list for bulk operations (chunked internally, max 100,000; mutually exclusive with image_ids, Issue #1216). For tags commands, bulk mode emits TagsBulkProgressItem chunk-progress rows instead of per-image TagsEditItem. (CLI: `--image-ids-file`)
- `tags`: `str` (required) - Comma-separated tags to add. (CLI: `--tags`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsEditItem`**

- `image_id`: `int` (required)
- `action`: `add | remove | replace` (required)
- `tags`: `list[str]?` (optional, default `None`) - Tags operated on (add/remove commands).
- `from`: `str?` (optional, default `None`) - Source tag (replace command only). Wire key is 'from'.
- `to`: `str?` (optional, default `None`) - Destination tag (replace command only). Wire key is 'to'.
- `status`: `str` (required)
- `reason`: `str?` (optional, default `None`)

**Output `TagsBulkProgressItem`**

Chunk-progress row emitted by --image-ids-file (bulk) instead of per-image TagsEditItem (Issue #1216). Count fields vary by action.

- `action`: `add | remove | replace` (required)
- `chunk_images`: `int` (required) - Number of image IDs processed in this chunk.
- `processed`: `int` (required) - Cumulative image IDs processed so far.
- `status`: `dry_run | changed` (required)
- `added`: `int?` (optional, default `None`)
- `would_add`: `int?` (optional, default `None`)
- `removed`: `int?` (optional, default `None`)
- `would_remove`: `int?` (optional, default `None`)
- `changed`: `int?` (optional, default `None`)
- `skipped`: `int?` (optional, default `None`)
- `from`: `str?` (optional, default `None`)
- `to`: `str?` (optional, default `None`)

**Output `TagsAddResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `target_images`: `int` (required)
- `tags`: `list[str]` (required)
- `added`: `int` (required)
- `dry_run`: `bool` (required)
- `tag_resolutions`: `list[TagResolutionEntry]` (required) - Per-tag classification (Issue #1174): `tag` / `classification` (`exact` | `alias_resolved` | `typo_candidate` | `ambiguous` | `unregistered`) / `canonical_tag` / `tag_id` (null = unresolved) / `candidates` (typo/ambiguous suggestions, never auto-applied).
- `skipped_invalid_tags`: `list[str]` (required) - Tags that normalized to empty (not added, not registered).
- `unresolved_tag_count`: `int?` (required) - Count of applied tags left with `tag_id=null` (apply mode only).
- `would_add`: `int?` (optional, default `None`) - Estimated additions if --apply were run (dry-run only, Issue #1217). Accounts for existing-duplicate skips.

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags alias`

Record a typo → preferred-tag alias in the user DB. Dry-run by default.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags alias"
```

#### Models

**Input `TagsAliasInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `from`: `str` (required) - Alias source (typo 等)。既存タグの付け替えは拒否。既に同じ preferred へ解決される場合は no-op。 (CLI: `--from`)
- `to`: `str` (required) - 解決先 preferred タグ (tag DB に存在必須)。 (CLI: `--to`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsAliasResult`**

書き込みは user DB overlay のみ。no-op 経路 (既に同じ preferred へ解決) も同形。

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required) - 既定は dry-run (true) で書き込みなし。
- `from_tag`: `str` (required)
- `to_tag`: `str` (required)
- `alias_tag_id`: `int?` (optional, default `None`)
- `status`: `dry_run | changed | noop` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags health`

Read-only tag frequencies, variant suggestions and explicitly expected missing tags. See [tag health](cli-tag-health.md).

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags health"
```

#### Models

**Input `TagHealthInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `expected_tag`: `list[str]?` (optional, default `None`) - Explicit tags expected on every image; repeat the option. No implicit expectations. (CLI: `--expected-tag`)
- `limit`: `int[1,500]` (optional, default `100`) - Maximum rows per section and IDs per missing-tag sample; counts cover all images. (CLI: `--limit`)

**Output `TagHealthFrequencyItem`**

- `kind`: `item` (optional, default `item`)
- `section`: `frequency` (required)
- `tag`: `str` (required)
- `image_count`: `int` (required)

**Output `TagHealthVariantItem`**

- `kind`: `item` (optional, default `item`)
- `section`: `variant` (required)
- `tag`: `str` (required)
- `candidate`: `str` (required)
- `reason`: `normalization | spelling` (required)
- `similarity`: `float?` (required)

**Output `TagHealthMissingItem`**

- `kind`: `item` (optional, default `item`)
- `section`: `missing_expected` (required)
- `expected_tag`: `str` (required)
- `normalized_tag`: `str` (required)
- `missing_count`: `int` (required)
- `image_ids`: `list[int]` (required)
- `image_ids_truncated`: `bool` (required)

**Output `TagHealthResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `project`: `str` (required)
- `read_only`: `true` (required)
- `total_images`: `int` (required)
- `tagged_images`: `int` (required)
- `untagged_images`: `int` (required)
- `unique_tags`: `int` (required)
- `expected_tag_count`: `int` (required)
- `frequency_count`: `int` (required)
- `variant_count`: `int` (required)
- `missing_expected_count`: `int` (required)
- `frequencies_truncated`: `bool` (required)
- `variants_truncated`: `bool` (required)
- `missing_expected_truncated`: `bool` (required)
- `spelling_vocabulary_limit`: `int` (required)
- `spelling_max_tag_length`: `int` (required)
- `spelling_similarity_threshold`: `float` (required)
- `spelling_candidates_truncated`: `bool` (required)
- `limit`: `int` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags remove`

Remove tags from images. Default dry-run; use --apply to write.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags remove"
```

#### Models

**Input `TagsRemoveInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500 (or use image_ids_file). (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Path to a newline/comma-separated image ID list for bulk operations (chunked internally, max 100,000; mutually exclusive with image_ids, Issue #1216). For tags commands, bulk mode emits TagsBulkProgressItem chunk-progress rows instead of per-image TagsEditItem. (CLI: `--image-ids-file`)
- `tags`: `str` (required) - Comma-separated tags to remove. (CLI: `--tags`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsEditItem`**

- `image_id`: `int` (required)
- `action`: `add | remove | replace` (required)
- `tags`: `list[str]?` (optional, default `None`) - Tags operated on (add/remove commands).
- `from`: `str?` (optional, default `None`) - Source tag (replace command only). Wire key is 'from'.
- `to`: `str?` (optional, default `None`) - Destination tag (replace command only). Wire key is 'to'.
- `status`: `str` (required)
- `reason`: `str?` (optional, default `None`)

**Output `TagsBulkProgressItem`**

Chunk-progress row emitted by --image-ids-file (bulk) instead of per-image TagsEditItem (Issue #1216). Count fields vary by action.

- `action`: `add | remove | replace` (required)
- `chunk_images`: `int` (required) - Number of image IDs processed in this chunk.
- `processed`: `int` (required) - Cumulative image IDs processed so far.
- `status`: `dry_run | changed` (required)
- `added`: `int?` (optional, default `None`)
- `would_add`: `int?` (optional, default `None`)
- `removed`: `int?` (optional, default `None`)
- `would_remove`: `int?` (optional, default `None`)
- `changed`: `int?` (optional, default `None`)
- `skipped`: `int?` (optional, default `None`)
- `from`: `str?` (optional, default `None`)
- `to`: `str?` (optional, default `None`)

**Output `TagsRemoveResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `target_images`: `int` (required)
- `tags`: `list[str]` (required)
- `removed`: `int` (required)
- `dry_run`: `bool` (required)
- `mode`: `soft_reject` (optional, default `soft_reject`) - Removal mode (Issue #1217): `soft_reject` marks rejected_at and is reversible via tags restore / re-add.
- `would_remove`: `int?` (optional, default `None`) - Estimated soft-reject count if --apply were run (dry-run only, Issue #1217).

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags replace`

Replace a tag with another across images. Default dry-run; use --apply to write.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags replace"
```

#### Models

**Input `TagsReplaceInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Comma-separated image IDs, max 500 (or use image_ids_file). (CLI: `--image-ids`)
- `image_ids_file`: `str?` (optional, default `None`) - Path to a newline/comma-separated image ID list for bulk operations (chunked internally, max 100,000; mutually exclusive with image_ids, Issue #1216). For tags commands, bulk mode emits TagsBulkProgressItem chunk-progress rows instead of per-image TagsEditItem. (CLI: `--image-ids-file`)
- `from_tag`: `str` (required) - Tag to replace. (CLI: `--from`)
- `to_tag`: `str` (required) - Replacement tag. (CLI: `--to`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsEditItem`**

- `image_id`: `int` (required)
- `action`: `add | remove | replace` (required)
- `tags`: `list[str]?` (optional, default `None`) - Tags operated on (add/remove commands).
- `from`: `str?` (optional, default `None`) - Source tag (replace command only). Wire key is 'from'.
- `to`: `str?` (optional, default `None`) - Destination tag (replace command only). Wire key is 'to'.
- `status`: `str` (required)
- `reason`: `str?` (optional, default `None`)

**Output `TagsBulkProgressItem`**

Chunk-progress row emitted by --image-ids-file (bulk) instead of per-image TagsEditItem (Issue #1216). Count fields vary by action.

- `action`: `add | remove | replace` (required)
- `chunk_images`: `int` (required) - Number of image IDs processed in this chunk.
- `processed`: `int` (required) - Cumulative image IDs processed so far.
- `status`: `dry_run | changed` (required)
- `added`: `int?` (optional, default `None`)
- `would_add`: `int?` (optional, default `None`)
- `removed`: `int?` (optional, default `None`)
- `would_remove`: `int?` (optional, default `None`)
- `changed`: `int?` (optional, default `None`)
- `skipped`: `int?` (optional, default `None`)
- `from`: `str?` (optional, default `None`)
- `to`: `str?` (optional, default `None`)

**Output `TagsReplaceResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `target_images`: `int` (required)
- `changed`: `int` (required)
- `skipped`: `int` (required)
- `errors`: `int` (required)
- `dry_run`: `bool` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags translations add`

Add translations to tags (user DB overlay). Dry-run by default; --apply to write.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`, `file_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags translations add"
```

#### Models

**Input `TagsTranslationsAddInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `tag`: `str?` (optional, default `None`) - Target tag (--file と排他、単発時は --lang/--text と3点セット必須)。tag_id 解決は tags add (Issue #1174) と同経路: exact/alias は解決、真の新タグは --apply 時に user DB 登録、typo/曖昧候補は候補提示でエラー (先に tags alias で確定)。 (CLI: `--tag`)
- `lang`: `str?` (optional, default `None`) - 書き込みは ja/en の一貫形。 (CLI: `--lang`)
- `text`: `str?` (optional, default `None`) - Translation text (CLI: `--text`)
- `file`: `str?` (optional, default `None`) - JSONL バッチ入力 (Issue #1211): 1 行 = {"tag", "lang", "text"[, "preferred"]}。最大 100 行。`translations show --missing-only` の出力行に text を埋めた形を受ける。typo/曖昧・既存訳・登録失敗は per-item status で報告して続行する。 (CLI: `--file`)
- `preferred`: `bool` (optional, default `False`) - その言語の主訳にする。 (CLI: `--preferred`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsTranslationsAddItem`**

書き込みは user DB overlay のみ (base DB は不変)。タグ登録失敗 (tagdb #124 edge) は単発は DB_ERROR、バッチは per-item error で明示。

- `kind`: `item` (optional, default `item`)
- `tag`: `str` (required)
- `canonical_tag`: `str` (required)
- `classification`: `str` (required)
- `tag_id`: `int?` (required)
- `language`: `str` (required)
- `translation`: `str` (required)
- `preferred`: `bool` (required)
- `registered_new_tag`: `bool` (required)
- `status`: `dry_run | changed | skipped_existing | skipped_candidates | skipped_invalid | error` (required) - skipped_* / error は --file バッチのみ (Issue #1211)。skipped_existing = 同一訳が既に存在 (再実行が冪等)。
- `candidates`: `list[str]?` (optional, default `None`) - skipped_candidates 時のみ: 類似候補。
- `error`: `str?` (optional, default `None`) - error 時のみ: 失敗理由。

**Output `TagsTranslationsAddResult`**

終端 result 行。既定は dry-run (dry_run=true) で書き込みなし。--file は既存 ok=true を維持するため errors と終了コードを確認: 部分成功3、全件失敗1、成功0。

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required)
- `tag_id`: `int?` (optional, default `None`) - 単発 --tag 時のみ。
- `language`: `str?` (optional, default `None`) - 単発 --tag 時のみ。
- `total`: `int?` (optional, default `None`) - --file バッチ時のみ: 入力行数。
- `changed`: `int?` (optional, default `None`) - --file バッチ時のみ: 書き込み件数。
- `would_add`: `int?` (optional, default `None`) - --file バッチ dry-run 時のみ: 書き込み見込み件数。
- `skipped_existing`: `int?` (optional, default `None`) - --file バッチ時のみ。
- `skipped_candidates`: `int?` (optional, default `None`) - --file バッチ時のみ。
- `errors`: `int?` (optional, default `None`) - --file バッチ時のみ。

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags translations delete`

Delete a user DB overlay translation (dry-run by default). Issue #1237. Only removes translations added via `translations add`; base-DB rows return not_found.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags translations delete"
```

#### Models

**Input `TagsTranslationsDeleteInput`**

- `tag`: `str` (required) - Target canonical tag (positional). (CLI: `tag`)
- `lang`: `str` (required) - Positional. (CLI: `lang`)
- `text`: `str` (required) - Exact translation text to delete (positional). (CLI: `text`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsTranslationsDeleteItem`**

- `kind`: `item` (optional, default `item`)
- `tag`: `str` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)
- `translation`: `str` (required)
- `status`: `dry_run | changed | not_found` (required) - not_found = user overlay に該当行が無かった (base DB 由来、または既に無い)。base DB 由来の訳は削除できない (`translations suppress` を使う)。

**Output `TagsTranslationsDeleteResult`**

既定は dry-run (dry_run=true) で書き込みなし。

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)
- `deleted`: `bool` (required) - 実際に削除できたか (dry-run 時は常に false)。

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags translations show`

Show ja/en translation status for tags (read-only). Issue #1173 / ADR 0085.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['network_download', 'tag_cache_create', 'db_create', 'directory_create']`
- Side effects: `db_read`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags translations show"
```

#### Models

**Input `TagsTranslationsShowInput`**

- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `image_ids`: `str?` (optional, default `None`) - Show translation status of these images' tags. Mutually exclusive with --tags. (CLI: `--image-ids`)
- `tags`: `str?` (optional, default `None`) - Tags to inspect, max 100. Mutually exclusive with --image-ids. (CLI: `--tags`)
- `missing_only`: `bool` (optional, default `False`) - 未翻訳 (tag, lang) ペアだけを 1 行 1 件で出力する (Issue #1211)。出力行は text を埋めるだけで `translations add --file` に渡せる。 (CLI: `--missing-only`)

**Output `MissingTranslationPairItem`**

--missing-only 指定時の item 行 (未翻訳ペア単位、Issue #1211)。

- `kind`: `item` (optional, default `item`)
- `tag`: `str` (required)
- `tag_id`: `int?` (required)
- `lang`: `ja | en` (required)
- `text`: `str` (required) - 常に空文字。翻訳を埋めて add --file へ渡す。
- `image_id`: `int?` (optional, default `None`) - --image-ids 指定時のみ。

**Output `TagTranslationStatusItem`**

--tags 指定時の item 行 (tag 単位)。

- `tag`: `str` (required)
- `tag_id`: `int?` (required) - null = 未解決 (tag DB 未登録)。
- `translations`: `dict` (required) - `{ja,en: {candidates, preferred}}`。読みは ja/japanese・en/english を集約。
- `missing`: `list[str]` (required) - 訳が無い言語。

**Output `ImageTagTranslationStatusItem`**

--image-ids 指定時の item 行 (画像単位のラッパー)。

- `kind`: `item` (optional, default `item`)
- `image_id`: `int` (required)
- `tags`: `list[TagTranslationStatusItem]` (required) - その画像のタグごとの TagTranslationStatusItem と同形式の配列。

**Output `TagsTranslationsShowResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `target_tags`: `int` (required) - 対象タグ数。
- `target_images`: `int?` (optional, default `None`) - --image-ids 指定時のみ: 対象画像数。
- `missing_pairs`: `int?` (optional, default `None`) - --missing-only 指定時のみ: 未翻訳 (tag, lang) ペア数。
- `truncated`: `bool?` (optional, default `None`)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags translations suppress`

Hide a translation from merged display via tombstone (dry-run by default). Issue #1237. Base DB is not modified; use for base-DB-origin mistranslations that cannot be deleted.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags translations suppress"
```

#### Models

**Input `TagsTranslationsSuppressInput`**

- `tag`: `str` (required) - Target canonical tag (positional). (CLI: `tag`)
- `lang`: `str` (required) - Positional. (CLI: `lang`)
- `text`: `str` (required) - Exact translation text to suppress (positional). (CLI: `text`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsTranslationsSuppressItem`**

- `kind`: `item` (optional, default `item`)
- `tag`: `str` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)
- `translation`: `str` (required)
- `status`: `dry_run | changed` (required)

**Output `TagsTranslationsSuppressResult`**

既定は dry-run (dry_run=true) で書き込みなし。重複 suppress は冪等。

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `tags translations unsuppress`

Remove a suppress tombstone (dry-run by default). Issue #1237.

- Read only: `false`
- Strict read only: `false` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `['db_create', 'schema_migration', 'model_seed', 'directory_create']`
- Side effects: `db_read`, `db_write`

#### Compact Introspection

```bash
lorairo-cli --json describe "tags translations unsuppress"
```

#### Models

**Input `TagsTranslationsUnsuppressInput`**

- `tag`: `str` (required) - Target canonical tag (positional). (CLI: `tag`)
- `lang`: `str` (required) - Positional. (CLI: `lang`)
- `text`: `str` (required) - Exact translation text to unsuppress (positional). (CLI: `text`)
- `project`: `str` (required) - Project name: the `name` in the project's .lorairo-project metadata, not a folder path. A GUI-created project uses its folder name; a CLI-created one uses the name given to `project create`. Run `lorairo-cli project list` to see the names. (CLI: `--project`, `-p`)
- `apply`: `bool` (optional, default `False`) - Write to DB. Default is dry-run. (CLI: `--apply`)

**Output `TagsTranslationsUnsuppressItem`**

- `kind`: `item` (optional, default `item`)
- `tag`: `str` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)
- `translation`: `str` (required)
- `status`: `dry_run | changed | not_found` (required) - not_found = tombstone が元々無かった。

**Output `TagsTranslationsUnsuppressResult`**

既定は dry-run (dry_run=true) で書き込みなし。

- `kind`: `result` (optional, default `result`)
- `ok`: `bool` (optional, default `True`)
- `message`: `str` (required)
- `dry_run`: `bool` (required)
- `tag_id`: `int` (required)
- `language`: `str` (required)
- `removed`: `bool` (required) - 実際に tombstone を削除できたか。

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)

### `version`

Show version information.

- Read only: `true`
- Strict read only: `true` (root `--read-only`; see [contract](cli-read-only.md))
- Conditional initialization: `[]`
- Side effects: 

#### Compact Introspection

```bash
lorairo-cli --json describe "version"
```

#### Models

**Output `VersionResult`**

- `kind`: `result` (optional, default `result`)
- `ok`: `true` (optional, default `True`)
- `message`: `str` (required)
- `name`: `str` (required)
- `version`: `str` (required)
- `description`: `str` (required)

**Error `CliErrorResponse`**

Structured error payload emitted as kind=error by the CLI boundary.

- `kind`: `error` (optional, default `error`)
- `ok`: `false` (optional, default `False`)
- `code`: `str` (required)
- `message`: `str` (required)
- `retryable`: `bool` (required)
- `user_action_required`: `bool` (required)
- `hint`: `str?` (optional, default `None`)
- `details`: `dict?` (optional, default `None`)
