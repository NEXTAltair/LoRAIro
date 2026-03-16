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
- **非同期処理**: Qt QRunnable/QThreadPoolベースの効率的な非同期タスク実行システムを搭載します。

## 開発環境セットアップ

### 必要条件

- Python 3.12（3.13は未対応）
- Git (Git LFSを含む)
- uv (Pythonパッケージマネージャー)

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
   uv sync
   ```

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
```

詳細は [docs/cli.md](docs/cli.md) を参照してください。

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
│       ├── annotations/    # AIアノテーション連携
│       ├── api/            # Public API
│       ├── cli/            # CLIインターフェース
│       ├── database/       # データベース操作
│       ├── editor/         # 画像編集（クロップ・アップスケール）
│       ├── gui/            # GUIコンポーネント
│       ├── services/       # ビジネスロジック
│       ├── storage/        # ファイルシステム管理
│       └── utils/          # ユーティリティ
├── tests/                  # テストコード
├── docs/                   # ドキュメント
├── pyproject.toml          # プロジェクト設定
└── README.md               # 本ファイル
```

## 設定

`config/lorairo.toml` でアプリケーションの各種設定を管理します。APIキーは設定ファイルの `[api]` セクション、またはアプリケーション内の設定画面から設定できます。

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

# 開発環境のセットアップ
make install-dev  # uv sync を実行

# コードの品質チェック
make lint
make format
make mypy

# テストの実行
make test

# ドキュメントのビルドと公開
make docs
make docs-publish

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
