# LoRAIro CLI ドキュメント

LoRAIro のコマンドラインインターフェース（CLI）。GUI なし環境でのデータセット管理、バッチ処理、プログラマティックアクセスを提供します。

## インストール

```bash
# LoRAIro をインストール
uv sync

# CLI が利用可能か確認
lorairo-cli --version
```

## 基本的な使い方

### ヘルプ表示

```bash
# 全体的なヘルプ
lorairo-cli --help

# 特定のコマンドのヘルプ
lorairo-cli project --help
lorairo-cli project create --help
```

### バージョン確認

```bash
lorairo-cli version
# Output: LoRAIro CLI v0.0.8
```

### システムステータス確認

```bash
lorairo-cli status
# Output: Service Status テーブル表示
```

---

## コマンド一覧

### images - 画像管理

LoRAIro プロジェクトに画像を登録・管理します。pHash（知覚ハッシュ）で重複検出を行います。

#### images register - 画像登録

**構文**:
```bash
lorairo-cli images register <directory> --project <name> [--skip-duplicates|--include-duplicates]
```

**引数**:
- `directory`: 登録する画像が含まれるディレクトリ（必須）

**オプション**:
- `--project <name>` / `-p <name>`: 対象プロジェクト（必須）
- `--skip-duplicates`: 重複画像をスキップ（デフォルト）
- `--include-duplicates`: 重複画像も登録

**例**:
```bash
# 基本的な使い方
lorairo-cli images register /path/to/images --project my_dataset

# 重複を含めて登録
lorairo-cli images register /path/to/images --project my_dataset --include-duplicates
```

**出力例**:
```
Found 150 image(s)
画像登録中... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Registration Summary
Registered     125
Skipped (duplicates) 25
Errors         0

✓ Images registered to project: my_dataset
```

**内部動作**:
1. ディレクトリ内の全画像ファイル（JPG, PNG, GIF など）を検索
2. 各画像のpHashを計算（知覚ハッシュ）
3. 重複検出（既存pHash と比較）
4. プロジェクトへ登録
5. Rich Progress バーで進捗表示

**対応形式**: JPG, JPEG, PNG, GIF, BMP, WebP

---

#### images list - 画像一覧

**構文**:
```bash
lorairo-cli images list --project <name> [--limit <count>]
```

**オプション**:
- `--project <name>` / `-p <name>`: 対象プロジェクト（必須）
- `--limit <count>` / `-l <count>`: 表示最大件数（オプション）

**注記**: 現在開発中。今後実装予定です。

---

#### images update - メタデータ更新

**構文**:
```bash
lorairo-cli images update --project <name> --tags <tags>
```

**オプション**:
- `--project <name>` / `-p <name>`: 対象プロジェクト（必須）
- `--tags <tags>`: 追加するタグ（カンマ区切り）

**例**:
```bash
lorairo-cli images update --project my_dataset --tags "landscape,outdoor"
```

**注記**: 現在開発中。今後実装予定です。

---

### project - プロジェクト管理

LoRAIro データセットプロジェクトの作成、一覧表示、削除を行います。

#### project create - プロジェクト作成

**構文**:
```bash
lorairo-cli project create <name> [--description <description>]
```

**引数**:
- `name`: プロジェクト名（必須）
  - Unicode 対応（日本語など）
  - 特殊文字可（ハイフン、アンダースコア）
  - 例: `my_dataset`, `テスト プロジェクト`

**オプション**:
- `--description <text>` / `-d <text>`: プロジェクトの説明（任意）

**例**:
```bash
# シンプルなプロジェクト作成
lorairo-cli project create "my_dataset"

# 説明付き
lorairo-cli project create "dataset_v1" --description "Training dataset version 1"

# Unicode 名対応
lorairo-cli project create "テスト画像データ" -d "テスト用の画像セット"
```

**出力**:
```
✓ Project created: my_dataset
Location: /home/user/.lorairo/projects/my_dataset_20260216_063000
```

**内部動作**:
1. `~/.lorairo/projects/` ディレクトリを作成（存在しない場合）
2. `project_name_YYYYMMDDhhmmss` という名前でプロジェクトディレクトリを作成
3. `.lorairo-project` メタデータファイルを生成
4. `image_dataset/original_images/` ディレクトリ構造を初期化

---

#### project list - プロジェクト一覧表示

**構文**:
```bash
lorairo-cli project list [--format <format>]
```

**オプション**:
- `--format <format>` / `-f <format>`: 出力フォーマット
  - `table`: リッチテーブル表示（デフォルト）
  - `json`: JSON 形式（CI/CD 対応）

**例**:
```bash
# テーブル形式（デフォルト）
lorairo-cli project list

# JSON 形式
lorairo-cli project list --format json

# CI/CD パイプラインでの使用
lorairo-cli project list --format json | jq '.[] | .name'
```

**出力例**:

テーブル形式:
```
Projects
Name             Created         Path
─────────────────────────────────────────────────────
my_dataset       20260216_063000 ~/.lorairo/projects/my_dataset_20260216_063000
test_project     20260215_120000 ~/.lorairo/projects/test_project_20260215_120000
```

JSON 形式:
```json
[
  {
    "name": "my_dataset",
    "created": "20260216_063000",
    "path": "/home/user/.lorairo/projects/my_dataset_20260216_063000"
  },
  {
    "name": "test_project",
    "created": "20260215_120000",
    "path": "/home/user/.lorairo/projects/test_project_20260215_120000"
  }
]
```

---

#### project delete - プロジェクト削除

**構文**:
```bash
lorairo-cli project delete <name> [--force]
```

**引数**:
- `name`: 削除するプロジェクト名（必須）

**オプション**:
- `--force` / `-f`: 確認プロンプトをスキップして即座に削除

**例**:
```bash
# 確認プロンプト付き（推奨）
lorairo-cli project delete "old_dataset"
# Output: Delete project 'old_dataset' at ~/.../old_dataset_xxx? This cannot be undone. [y/N]:

# 確認をスキップして削除
lorairo-cli project delete "old_dataset" --force
```

**出力**:
```
✓ Project deleted: old_dataset
```

---

## 出力フォーマット

### リッチテーブル出力

デフォルトの出力形式。カラー表示、整形されたテーブルで視覚的にわかりやすい表示。

```bash
lorairo-cli project list
```

**特徴**:
- カラー表示（見やすい）
- テーブル形式（整列）
- インタラクティブ環境向け

### JSON 出力

CI/CD パイプライン、プログラマティックアクセス向け。

```bash
lorairo-cli project list --format json
```

**特徴**:
- 機械可読形式
- `jq` などでパース可能
- スクリプト処理に最適

**例**: JSON からプロジェクト名のみ抽出
```bash
lorairo-cli project list --format json | jq -r '.[].name'
```

---

## よくある使用パターン

### 1. 新しいデータセットの初期化から学習データ作成まで

```bash
# 1. プロジェクト作成
lorairo-cli project create "my_training_dataset" \
  --description "Training data for LoRA model"

# 2. プロジェクト確認
lorairo-cli project list | grep my_training_dataset

# 3. 画像登録
lorairo-cli images register /path/to/images --project my_training_dataset

# 4. AIアノテーション実行
lorairo-cli annotate run --project my_training_dataset --model gpt-4o-mini

# 5. 学習用データセットをエクスポート
lorairo-cli export create \
  --project my_training_dataset \
  --output ./training_data/ \
  --format txt \
  --resolution 512
```

### 2. CI/CD パイプラインでの利用

```bash
# GitHub Actions での例
- name: Create dataset project
  run: |
    lorairo-cli project create "${{ env.DATASET_NAME }}" \
      --description "Automated dataset creation"

- name: List projects in JSON
  run: |
    lorairo-cli project list --format json > projects.json
```

### 3. スクリプトでの自動化

```bash
#!/bin/bash

# 複数プロジェクト一括作成
for i in {1..5}; do
  lorairo-cli project create "dataset_v$i" \
    --description "Version $i of training dataset"
done

# 一覧確認
lorairo-cli project list --format json | jq '.[] | .name'
```

### 4. プロジェクトのバックアップ

```bash
# プロジェクト情報を JSON で保存
lorairo-cli project list --format json > backup_projects.json

# 後で復元
jq -r '.[] | .name' backup_projects.json | while read name; do
  echo "Project: $name"
done
```

### 5. 複数モデルでのアノテーション比較

```bash
# プロジェクト作成
lorairo-cli project create "annotation_test" -d "Testing different annotation models"

# 画像登録
lorairo-cli images register /path/to/test/images --project annotation_test

# 複数モデルで同時アノテーション
lorairo-cli annotate run \
  --project annotation_test \
  --model gpt-4o-mini \
  --model claude-3-5-sonnet \
  --model gemini-2.0-flash-thinking-exp

# 結果をエクスポートして比較
lorairo-cli export create \
  --project annotation_test \
  --output ./comparison/ \
  --format json
```

### 6. バッチ処理での大規模データセット作成

```bash
#!/bin/bash

# 大量の画像を処理
PROJECT_NAME="large_dataset"

# プロジェクト作成
lorairo-cli project create "$PROJECT_NAME"

# 画像を複数回に分けて登録（ディレクトリごと）
for dir in /data/images/*; do
  lorairo-cli images register "$dir" --project "$PROJECT_NAME"
done

# バッチサイズを大きくしてアノテーション実行
lorairo-cli annotate run \
  --project "$PROJECT_NAME" \
  --model gpt-4o-mini \
  --batch-size 50

# 高解像度でエクスポート
lorairo-cli export create \
  --project "$PROJECT_NAME" \
  --output ./training_1024/ \
  --resolution 1024
```

---

## トラブルシューティング

### プロジェクトが見つからない

**症状**: `lorairo-cli project list` で何も表示されない

**原因**: プロジェクトディレクトリがまだ作成されていない

**解決**:
```bash
# プロジェクトを作成
lorairo-cli project create "first_project"

# 確認
lorairo-cli project list
```

### 削除操作をキャンセルしたい

**症状**: `project delete` 実行後、確認プロンプトが表示されている

**解決**: `n` を入力して Enter キーを押す
```bash
Delete project 'dataset'? This cannot be undone. [y/N]: n
```

### JSON 出力をパースしたい

**症状**: JSON が複数行に分割されて表示される

**解決**: `jq` コマンドを使用
```bash
# プロジェクト数をカウント
lorairo-cli project list --format json | jq 'length'

# プロジェクト名のみを抽出
lorairo-cli project list --format json | jq -r '.[].name'
```

---

## ストレージの場所

プロジェクトはユーザーのホームディレクトリに保存されます：

```
~/.lorairo/projects/
├── project1_20260216_120000/
│   ├── .lorairo-project       # メタデータ（JSON）
│   ├── image_dataset/
│   │   ├── original_images/   # 元画像
│   │   └── [将来用: resolutions]/
│   └── [将来用: image_database.db]
├── project2_20260215_080000/
└── ...
```

---

## 環境変数

### LORAIRO_CLI_MODE

CLI モードを有効にするための環境変数（内部用）。

```bash
# 既に src/lorairo/cli/__init__.py で自動設定されます
export LORAIRO_CLI_MODE=true
```

---

### annotate - AI アノテーション

プロジェクトの画像に対してAIモデルを使用してアノテーション（タグ付け）を実行します。

#### annotate run - アノテーション実行

**構文**:
```bash
lorairo-cli annotate run --project <name> --model <model_name> [--output <dir>] [--batch-size <size>]
```

**オプション**:
- `--project <name>` / `-p <name>`: 対象プロジェクト（必須）
- `--model <model_name>` / `-m <model_name>`: 使用するモデル名（必須、複数指定可能）
  - 対応モデル: `gpt-4o`, `gpt-4o-mini`, `claude-3-5-sonnet`, `gemini-2.0-flash-thinking-exp`など
- `--output <dir>` / `-o <dir>`: アノテーション結果の出力先ディレクトリ（オプション）
- `--batch-size <size>` / `-b <size>`: バッチ処理サイズ（デフォルト: 10）

**例**:
```bash
# 単一モデルでアノテーション実行
lorairo-cli annotate run --project my_dataset --model gpt-4o-mini

# 複数モデルで実行
lorairo-cli annotate run -p my_dataset -m gpt-4o -m claude-3-5-sonnet

# バッチサイズ指定
lorairo-cli annotate run -p my_dataset -m gpt-4o-mini --batch-size 20

# 出力先指定
lorairo-cli annotate run -p my_dataset -m gpt-4o-mini --output ./annotations/
```

**出力例**:
```
Found 150 image(s)
Using model(s): gpt-4o-mini
画像ロード中... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
Loaded 150 image(s) (0 failed)
Starting annotation...
アノテーション実行中... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Annotation Summary
Total Images    150
Models Used     gpt-4o-mini
Results         150

✓ Annotation completed successfully!
```

**内部動作**:
1. プロジェクトの`image_dataset/original_images/`から画像を読み込み
2. 指定されたモデルを使用してアノテーション実行
3. 結果をデータベースに保存
4. Rich Progress バーで進捗表示

**注意**:
- APIキーが`config/lorairo.toml`で設定されている必要があります
- 大量の画像をアノテーションする場合、API利用料金が発生します
- アノテーション中にエラーが発生した場合は、ログファイルを確認してください

---

### export - データセットエクスポート

プロジェクトからトレーニング用データセットをエクスポートします。

#### export create - データセットエクスポート

**構文**:
```bash
lorairo-cli export create --project <name> --output <dir> [--format <format>] [--resolution <size>]
```

**オプション**:
- `--project <name>` / `-p <name>`: 対象プロジェクト（必須）
- `--output <dir>` / `-o <dir>`: エクスポート先ディレクトリ（必須）
- `--format <format>` / `-f <format>`: エクスポート形式（デフォルト: txt）
  - `txt`: テキストファイル形式（各画像に対応する.txtファイル）
  - `json`: JSON形式（メタデータを含む）
- `--resolution <size>` / `-r <size>`: ターゲット解像度（デフォルト: 512）
  - 512, 768, 1024など

**例**:
```bash
# 基本的な使い方（TXT形式、512px）
lorairo-cli export create --project my_dataset --output ./export/

# JSON形式でエクスポート
lorairo-cli export create -p my_dataset -o ./export/ --format json

# 解像度指定
lorairo-cli export create -p my_dataset -o ./export/ --resolution 1024

# 全オプション指定
lorairo-cli export create \
  --project my_dataset \
  --output ./training_data/ \
  --format txt \
  --resolution 768
```

**出力例**:
```
Loading project database: my_dataset
Note: Working with currently configured database. Ensure config/lorairo.toml points to the correct project.
画像情報取得中... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
Found 150 image(s)
Export format: txt
Target resolution: 512px
Starting export...
エクスポート中... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Export Summary
Total Images    150
Export Format   txt
Resolution      512px
Output Path     ./export/

✓ Export completed successfully!
```

**出力ディレクトリ構造**:
```
export/
├── image_001.png
├── image_001.txt    # タグ・キャプション
├── image_002.png
├── image_002.txt
└── ...
```

**TXT形式の例**:
```txt
1girl, solo, long_hair, blue_eyes, smile, outdoor, landscape
```

**JSON形式の例**:
```json
{
  "image_001.png": {
    "tags": ["1girl", "solo", "long_hair"],
    "captions": ["A girl with long hair standing in a field"],
    "metadata": {
      "width": 512,
      "height": 512,
      "source_id": 123
    }
  }
}
```

**注意**:
- 現在の実装では、`config/lorairo.toml`で設定されたデータベースを使用します
- 将来的には動的なプロジェクト切り替えに対応予定です
- エクスポート先ディレクトリが存在しない場合、自動的に作成されます

---

## 参考リソース

- [LoRAIro メインドキュメント](../README.md)
- [アーキテクチャ](./architecture.md)
- [開発ガイド](../CLAUDE.md)
- [Typer 公式ドキュメント](https://typer.tiangolo.com/)
- [Rich 公式ドキュメント](https://rich.readthedocs.io/)
