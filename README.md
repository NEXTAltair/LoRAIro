# LoRAIro - AIタグ付LoRA画像データセット準備ツール

## 概要

本プロジェクトは、LoRA（Low-Rank Adaptation）学習用の画像データセット作成を自動化するPythonツールです。画像のリサイズ、AI自動タグ付け、キャプション生成、データベース管理などの機能を統合的に提供し、効率的なデータセット作成をサポートします。

### 主な機能

- **画像処理**: 画像のリサイズ、フォーマット変換、自動クロップなどを行います。
- **メタデータ管理**: 画像のメタデータをSQLiteデータベースで管理します。
- **タグ・キャプション生成**: GPT-4、Claude、Geminiなどの各種AIモデルを使用して、画像のタグとキャプションを自動生成します。
- **バッチ処理**: 大量の画像を効率的に処理するためのバッチ処理機能を提供します。
- **ファイルシステム管理**: 処理された画像や生成されたデータの保存を体系的に管理します。
- **GUIインターフェース**: PySide6による使いやすいインターフェースを提供します。

## 開発環境セットアップ

### 必要条件

- Python 3.12以上
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
3. 仮想環境を作成し、依存パッケージをインストールします：

   ```bash
   # 仮想環境の作成
   uv venv

   # 依存パッケージのインストール（開発モード）
   # uvは自動的に仮想環境を使用するため、アクティベーション不要
   uv pip install -e .[dev]

   # ローカルパッケージのインストール
   uv pip install -e local_packages/genai-tag-db-tools
   uv pip install -e local_packages/image-annotator-lib
   ```

   注: 従来の pip を使用する場合は、以下のようにアクティベーションが必要です：

   ```bash
   # Windows PowerShellの場合
   .venv\Scripts\Activate.ps1
   # または bash/zsh の場合
   # source .venv/bin/activate

   pip install -e .[dev]
   ```

## 使用方法

インストール後、以下のコマンドでアプリケーションを起動できます：

```bash
lorairo
```

または、以下のようにモジュールとして実行することもできます：

```bash
python -m lorairo.main
```

## プロジェクト構造

```
lorairo/
├── .vscode/                # VS Code設定
├── local_packages/         # ローカルパッケージ（サブモジュール）
│   ├── genai-tag-db-tools/ # タグデータベース管理ツール
│   └── image-annotator-lib/ # 画像アノテーションライブラリ
├── src/                    # ソースコード
│   └── lorairo/            # メインパッケージ
│       ├── __init__.py
│       ├── main.py         # エントリーポイント
│       ├── config/         # 設定管理
│       ├── database/       # データベース操作
│       ├── gui/            # GUIコンポーネント
│       ├── image/          # 画像処理
│       └── utils/          # ユーティリティ
├── tests/                  # テストコード
│   ├── __init__.py
│   └── resources/          # テスト用リソース
├── docs/                   # ドキュメント
├── .env.example            # 環境変数の例
├── pyproject.toml          # プロジェクト設定
└── README.md               # 本ファイル
```

## 設定

`.env` ファイルを作成し、必要なAPI キーなどを設定します（`.env.example` を参照）。アプリケーション内の設定画面からも多くのオプションを設定できます。

## 開発者向け情報

- 開発には VS Code の使用を推奨します。`.vscode/lorairo.code-workspace` を使用すると便利です。
- リンターとフォーマッターには Ruff を使用しています。
- テストは pytest で実行します：`pytest`

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
