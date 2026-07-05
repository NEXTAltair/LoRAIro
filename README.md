# LoRAIro - AIタグ付LoRA画像データセット準備ツール

## 概要

本プロジェクトは、LoRA（Low-Rank Adaptation）学習用の画像データセット作成を自動化するPythonツールです。画像のリサイズ、AI自動タグ付け、キャプション生成、データベース管理などの機能を統合的に提供し、効率的なデータセット作成をサポートします。GUIとCLIの両方のインターフェースを備えています。

### 主な機能

- **画像処理**: 画像のリサイズ、フォーマット変換、自動クロップなどを行います。
- **メタデータ管理**: 画像のメタデータをSQLiteデータベースで管理します。
- **タグ・キャプション生成**: GPT-4、Claude、Geminiなどの各種AIモデルを使用して、画像のタグとキャプションを自動生成します。
- **バッチ処理**: 大量の画像を効率的に処理するためのバッチ処理機能を提供します。
- **ファイルシステム管理**: 処理された画像や生成されたデータの保存を体系的に管理します。
- **GUIインターフェース**: PySide6による使いやすいワークフロー中心のインターフェースを提供します。
- **CLIインターフェース**: Typerベースのコマンドラインツールでプロジェクト管理、画像登録、アノテーション、エクスポートを実行できます。
- **高度な検索**: タグ除外検索（`-tag`プレフィックス）、リアルタイム件数表示、タグオートコンプリートに対応しています。
- **データセットエクスポート**: 学習用データセットのエクスポート機能を提供します。
- **品質評価**: CLIP aesthetic、MUSIQによる画像品質スコアリングを搭載しています。
- **非同期処理**: Qt QThread + moveToThread ベースの非同期ワーカーシステム（進捗通知・キャンセル対応）を搭載します。

## 開発環境セットアップ

### 必要条件

- Python 3.13（uv による自動インストールを推奨）
- Git (Git LFSを含む)
- uv (Pythonパッケージマネージャー)
- NVIDIA GPU / CUDA 13.2 対応ドライバー（標準の PyTorch GPU wheel を使う場合）

### インストール手順

1. リポジトリをクローンします：

   ```bash
   git clone https://github.com/NEXTAltair/lorairo.git
   cd lorairo
   ```

2. サブモジュールを初期化します：

   ```bash
   git submodule update --init --recursive
   ```

3. 環境セットアップ：

   ```bash
   uv python install 3.13
   uv sync
   ```

   LoRAIro は PyTorch / torchvision を `https://download.pytorch.org/whl/cu132` から取得する設定です。
   `uv sync` または初回の `uv run lorairo` 時に、CUDA 13.2 向けの PyTorch wheel が仮想環境へインストールされます。

   Windows ネイティブ環境では、GPU 実行環境を次のコマンドで確認できます：

   ```powershell
   nvidia-smi
   uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
   ```

   `torch.cuda.is_available()` が `False` の場合は、NVIDIA ドライバーや GPU 互換性が標準環境と合っていない可能性があります。
   CPU 版 PyTorch や別 CUDA バージョンを使う場合は、`pyproject.toml` の PyTorch index と lockfile を環境に合わせて更新してください。

## 使用方法

### GUI

```bash
uv run lorairo
```

### CLI

```bash
uv run lorairo-cli --help
```

基本的なCLIコマンド例:

```bash
# プロジェクト管理
uv run lorairo-cli project create "my-project"
uv run lorairo-cli project list

# 画像登録
uv run lorairo-cli images register ./images --project "my-project"

# データセットエクスポート（フィルタ条件は必須）
uv run lorairo-cli export create -p "my-project" -o ./dataset --tags cat
```

#### エージェント / 機械可読モード

既定は rich な人間向け出力です。グローバル `--json` フラグまたは環境変数 `LORAIRO_CLI_JSON=1` を指定すると、機械可読な JSONL モードに切り替わります（解決順序は「明示フラグ > 環境変数 > 既定 rich」）。

`--json` 時は stdout が JSONL（1 行 1 JSON object）のみになり、ログ・進捗・装飾は stderr に出ます。各コマンドは終端で必ず 1 行の `result` または `error` を返します。

```bash
# 利用可能なコマンド一覧と入出力スキーマを introspection（副作用なし）
uv run lorairo-cli --json list-commands
uv run lorairo-cli --json describe "images update"

# コマンドを JSONL モードで実行
uv run lorairo-cli --json project list
```

exit code はエラーコードから機械的に導出されます（0=成功 / 2=入力・検証 / 1=その他）。詳細は [docs/cli.md](docs/cli.md) を参照してください。

### 旧バージョンからの移行

以前の CLI バージョンを使用していた場合、以下の **破壊的変更** があります。

**1. `export create` のフィルタ条件が必須化 (ADR 0019)**

フィルタ条件なしの呼び出しはエラー (exit_code=2) になります:

```bash
# NG: フィルタ条件なし
uv run lorairo-cli export create -p "my-project" -o ./dataset

# OK: 最低1つのフィルタ条件が必要
uv run lorairo-cli export create -p "my-project" -o ./dataset --tags cat
```

エラー出力例:

```
Error: エクスポートには最低1つのフィルタ条件が必要です
例: lorairo-cli export create --project foo --tags cat --output /tmp/out
詳細: lorairo-cli export create --help
```

**2. CLI プロジェクト保存場所の変更 (ADR 0018)**

CLI で作成したプロジェクトの保存場所が `~/.lorairo/projects/` から `lorairo_data/`（`config/lorairo.toml` の `database_base_dir` 設定値）に変更されました。

旧プロジェクトを移行する場合は `scripts/migrate_legacy_projects.py` を使用してください:

```bash
# プレビュー (副作用なし)
uv run python scripts/migrate_legacy_projects.py --dry-run

# 旧ディレクトリをバックアップして移行
uv run python scripts/migrate_legacy_projects.py --backup
```

詳細な手順: [docs/migration/0019-legacy-projects-migration.md](docs/migration/0019-legacy-projects-migration.md)

## プロジェクト構造

```
lorairo/
├── config/                 # アプリケーション設定
│   └── lorairo.toml
├── local_packages/         # ローカルパッケージ（サブモジュール）
│   ├── genai-tag-db-tools/  # タグデータベース管理ツール
│   └── image-annotator-lib/ # 画像アノテーションライブラリ
├── src/                    # ソースコード
│   └── lorairo/            # メインパッケージ
│       ├── main.py         # GUIエントリーポイント
│       ├── annotation/     # AIアノテーション連携
│       ├── public_api/     # Public API
│       ├── cli/            # CLIインターフェース
│       ├── database/       # データベース操作
│       ├── domain/         # ドメインロジック（品質評価等）
│       ├── image_transforms/ # 画像処理（クロップ・アップスケール）
│       ├── gui/             # GUIコンポーネント
│       ├── services/        # ビジネスロジック
│       ├── filesystem.py    # ファイルシステム管理
│       └── utils/           # ユーティリティ
├── tests/                  # テストコード
├── docs/                   # ドキュメント
├── pyproject.toml          # プロジェクト設定
└── README.md               # 本ファイル
```

## 設定

`config/lorairo.toml` でアプリケーションの各種設定を管理します。設定ファイルがない場合は初回起動時に自動生成されます。APIキーは設定ファイルの `[api]` セクション、またはアプリケーション内の設定画面から設定できます。

初期設定値は [src/lorairo/utils/config.py](src/lorairo/utils/config.py) の `DEFAULT_CONFIG` で定義しています。設定項目を追加・変更する場合は、この定義を更新してください。

## 開発者向け情報

- 開発には VS Code の使用を推奨します。`.vscode/lorairo.code-workspace` を使用すると便利です。
- リンターとフォーマッターには Ruff を使用しています。
- テストは pytest で実行します：`uv run pytest`
- 型チェック：`make mypy`

### 開発コマンド

プロジェクトではMakefileを使用して開発タスクを自動化しています：

```bash
# ヘルプの表示
make help

# 開発環境のセットアップ（サブモジュール取得 + uv sync --dev、推奨エントリーポイント）
make setup

# コードの品質チェック
make format  # ruff format + check --fix
make mypy

# テストの実行
make test      # LoRAIro 本体テスト（tests/ のみ、ADR 0024）
make test-all  # local_packages を含む全テストセッションを順次実行

# クリーンアップ
make clean
```

### ドキュメント

- [docs/architecture.md](docs/architecture.md) - アーキテクチャ設計
- [docs/cli.md](docs/cli.md) - CLIリファレンス
- [docs/services.md](docs/services.md) - サービスカタログ
- [docs/testing.md](docs/testing.md) - テスト戦略

## ライセンス

MIT

## 謝辞

本プロジェクトは以下のリソースに感謝します：

- [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) - タグのクリーンナップ手法
- [DominikDoom/a1111-sd-webui-tagcomplete](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete) - tags.dbの基になったCSV tag data
- [applemango](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete/discussions/265) - CSV tag data の日本語翻訳
- [AngelBottomless/danbooru-2023-sqlite-fixed-7110548](https://huggingface.co/datasets/KBlueLeaf/danbooru2023-sqlite) - danbooru タグのデータベース
- [hearmeneigh/e621-rising-v3-preliminary-data](https://huggingface.co/datasets/hearmeneigh/e621-rising-v3-preliminary-data) - e621 タグのデータベース
- [sd-webui-bayesian-merger](https://github.com/s1dlx/sd-webui-bayesian-merger) - スコアリング実装の参考
- [stable-diffusion-webui-dataset-tag-editor](https://github.com/toshiaki1729/stable-diffusion-webui-dataset-tag-editor) - スコアリング実装の参考
