# LoRAIro — AI タグ付け対応 LoRA 学習データセット準備ツール

## 概要

**[詳しい利用ガイド(日本語・English・繁體中文・简体中文)](https://nextaltair.github.io/LoRAIro/)**

LoRAIro は、LoRA(Low-Rank Adaptation)学習用の画像データセット作成を効率化する Python ツールです。画像のリサイズや自動クロップ、AI によるタグ付け・キャプション生成、SQLite データベースによるメタデータ管理までを統合的に提供します。デスクトップ GUI とコマンドライン(CLI)の両方から操作できます。

### 主な機能

- **画像処理**: リサイズ、フォーマット変換、自動クロップを行います。
- **メタデータ管理**: 画像ごとのタグ・キャプション・評価・属性を SQLite データベースで一元管理します。
- **タグ・キャプション生成**: GPT-4、Claude、Gemini などの Web API モデルやローカルモデルを使って自動生成します。
- **バッチ処理**: 大量の画像をまとめて効率よく処理します。
- **ファイルシステム管理**: 処理済み画像や関連ファイルをプロジェクト単位で整理して保存します。
- **GUI インターフェース**: PySide6 によるワークフロー中心のデスクトップ画面を提供します。
- **CLI インターフェース**: Typer ベースのコマンドでプロジェクト管理、画像登録、アノテーション、エクスポートを実行できます。
- **高度な検索**: タグ除外検索(`-tag` 形式)、リアルタイム件数表示、タグ補完に対応しています。
- **データセット出力**: 学習用の画像・テキストセットを条件に合わせて出力します。
- **品質評価**: CLIP aesthetic や MUSIQ による画像品質スコアリングを備えています。
- **非同期処理**: Qt の `QThread` + `moveToThread` による非同期ワーカー(進捗表示・キャンセル対応)で操作性を保ちます。

## 開発環境セットアップ

### 必要条件

- Python 3.13(`uv` による自動インストールを推奨)
- Git(Git LFS を含む)
- `uv`(Python パッケージマネージャー)
- NVIDIA GPU および CUDA 13.2 対応ドライバー(標準の PyTorch GPU wheel を使う場合)

### インストール手順

1. リポジトリをクローンします。

   ```bash
   git clone https://github.com/NEXTAltair/lorairo.git
   cd lorairo
   ```

2. サブモジュールを初期化します。

   ```bash
   git submodule update --init --recursive
   ```

3. Python と依存パッケージをセットアップします。

   ```bash
   uv python install 3.13
   uv sync
   ```

   2026 年 10 月の依存更新より前に作成した環境を更新する場合は、初回のみ次を実行してください。旧 `griffe` の削除時に同じモジュールを提供する `griffelib` のファイルが消えるため、再インストールが必要です。

   ```bash
   uv sync --reinstall-package griffelib
   ```

   LoRAIro は PyTorch と torchvision を `https://download.pytorch.org/whl/cu132` から取得する設定になっています。`uv sync` または初回の `uv run lorairo` 実行時に、CUDA 13.2 向けの PyTorch wheel が仮想環境へインストールされます。

   Windows ネイティブ環境では、次のコマンドで GPU 実行環境を確認できます。

   ```powershell
   nvidia-smi
   uv run python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
   ```

   `torch.cuda.is_available()` が `False` の場合は、NVIDIA ドライバーや GPU の互換性が標準環境と合っていない可能性があります。CPU 版 PyTorch や別バージョンの CUDA を使う場合は、`pyproject.toml` の PyTorch インデックス設定と lockfile を環境に合わせて更新してください。

## 使用方法

### GUI

```bash
uv run lorairo
```

### CLI

```bash
uv run lorairo-cli --help
```

基本的なコマンド例は次のとおりです。

```bash
# プロジェクト管理
uv run lorairo-cli project create "my-project"
uv run lorairo-cli project list

# 画像登録
uv run lorairo-cli images register ./images --project "my-project"

# データセット出力(登録後に確認した画像 ID を指定)
uv run --no-sync lorairo-cli export create -p "my-project" -o ./dataset --image-ids 42,57
```

#### エージェント・機械可読モード

既定では人間向けの整形表示(rich 出力)を行います。グローバルオプション `--json` または環境変数 `LORAIRO_CLI_JSON=1` を指定すると、機械処理しやすい JSONL モードに切り替わります。優先順位は「明示フラグ > 環境変数 > 既定の rich 表示」です。

`--json` 指定時は、標準出力(stdout)が 1 行 1 JSON オブジェクトの JSONL のみとなり、ログ・進捗・装飾は標準エラー出力(stderr)へ出ます。各コマンドは末尾で必ず 1 行の `result` または `error` を返します。

```bash
# 利用可能なコマンド一覧と入出力スキーマを確認(副作用なし)
uv run lorairo-cli --json list-commands
uv run lorairo-cli --json describe "images update"

# JSONL モードでコマンドを実行
uv run lorairo-cli --json project list
```

終了コードはエラー種別から機械的に決まります(`0`: 成功、`2`: 入力・検証エラー、`1`: その他のエラー)。詳しくは [docs/cli.md](docs/cli.md) を参照してください。

### 旧バージョンからの移行

以前の CLI バージョンから移行する場合は、以下の **破壊的変更** に注意してください。

**1. `export create` は画像 ID 指定方式になりました**

検索と出力の責務を分離しました。先に `images search` などで対象画像の ID を確認し、`--image-ids 42,57` または `--image-ids-file ids.txt` で指定してください。旧 `--tags` などの検索フィルターは `export create` では使用できません。詳しくは[出力ガイド](https://nextaltair.github.io/LoRAIro/ja/export/)を参照してください。

**2. CLI プロジェクトの保存場所が変わりました(ADR 0018)**

CLI で作成したプロジェクトの保存先が、`~/.lorairo/projects/` から `lorairo_data/`(`config/lorairo.toml` の `database_base_dir` 設定値)へ変更されました。

旧プロジェクトを移行するには `scripts/migrate_legacy_projects.py` を使用してください。

```bash
# 変更内容の事前確認(副作用なし)
uv run python scripts/migrate_legacy_projects.py --dry-run

# 旧ディレクトリをバックアップして移行
uv run python scripts/migrate_legacy_projects.py --backup
```

詳しい手順は [docs/migration/0019-legacy-projects-migration.md](docs/migration/0019-legacy-projects-migration.md) を参照してください。

## プロジェクト構造

```
lorairo/
├── config/                    # アプリケーション設定
│   └── lorairo.toml
├── local_packages/            # ローカルパッケージ(サブモジュール)
│   ├── genai-tag-db-tools/    # タグデータベース管理ツール
│   └── image-annotator-lib/   # 画像アノテーションライブラリ
├── src/                       # ソースコード
│   └── lorairo/               # メインパッケージ
│       ├── main.py            # GUI エントリーポイント
│       ├── annotation/        # AI アノテーション連携
│       ├── public_api/        # Public API
│       ├── cli/               # CLI インターフェース
│       ├── database/          # データベース操作
│       ├── domain/            # ドメインロジック(品質評価など)
│       ├── image_transforms/  # 画像処理(クロップ・アップスケール)
│       ├── gui/               # GUI コンポーネント
│       ├── services/          # ビジネスロジック
│       ├── filesystem.py      # ファイルシステム管理
│       └── utils/             # ユーティリティ
├── tests/                     # テストコード
├── docs/                      # 開発者向けドキュメント
├── pyproject.toml             # プロジェクト設定
└── README.md                  # 本ファイル
```

## 設定

アプリケーションの各種設定は `config/lorairo.toml` で管理します。設定ファイルが存在しない場合は、初回起動時に自動生成されます。API キーは設定ファイルの `[api]` セクション、またはアプリ内の設定画面から登録できます。

初期設定値は [src/lorairo/utils/config.py](src/lorairo/utils/config.py) の `DEFAULT_CONFIG` で定義しています。設定項目を追加・変更する際は、この定義を更新してください。

## 開発者向け情報

- 開発環境には VS Code を推奨します。`.vscode/lorairo.code-workspace` を開くと便利です。
- リンター・フォーマッターには Ruff を使用しています。
- テストは `uv run pytest` で実行します。
- 型チェックは `make mypy` で実行します。

### 開発コマンド

プロジェクトでは Makefile を使って開発タスクを自動化しています。

```bash
# ヘルプの表示
make help

# 開発環境のセットアップ(サブモジュール取得 + 全ワークスペース開発依存 + 外部スキル復元)
make setup

# コードの品質チェック
make format    # ruff format + check --fix
make mypy

# テストの実行
make test      # LoRAIro 本体テスト(tests/ のみ、ADR 0024)
make test-all  # local_packages を含む全テストセッションを直列実行

# クリーンアップ
make clean
```

### ドキュメント

- [docs/architecture.md](docs/architecture.md) — アーキテクチャ設計
- [docs/cli.md](docs/cli.md) — CLI リファレンス
- [docs/services.md](docs/services.md) — サービスカタログ
- [docs/testing.md](docs/testing.md) — テスト戦略

## ライセンス

MIT

## 謝辞

本プロジェクトは、以下のオープンソースおよびリソースの成果を活用しています。

- [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) — タグのクリーンアップ手法
- [DominikDoom/a1111-sd-webui-tagcomplete](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete) — `tags.db` の基になった CSV タグデータ
- [applemango](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete/discussions/265) — CSV タグデータの日本語翻訳
- [AngelBottomless/danbooru-2023-sqlite-fixed-7110548](https://huggingface.co/datasets/KBlueLeaf/danbooru2023-sqlite) — Danbooru タグデータベース
- [hearmeneigh/e621-rising-v3-preliminary-data](https://huggingface.co/datasets/hearmeneigh/e621-rising-v3-preliminary-data) — e621 タグデータベース
- [sd-webui-bayesian-merger](https://github.com/s1dlx/sd-webui-bayesian-merger) — スコアリング実装の参考
- [stable-diffusion-webui-dataset-tag-editor](https://github.com/toshiaki1729/stable-diffusion-webui-dataset-tag-editor) — スコアリング実装の参考

## エージェント用フックの初期導入

エージェント用フックの初期導入は、Claude や Codex を起動する前に通常のターミナルで実行してください。ランタイムが未復元の状態では、エージェント内からの復元コマンドもフックにより拒否されます。ワークツリーでの復元や更新を含む手順は [Agent harness restoration](docs/agent-harness.md) を参照してください。
