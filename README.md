# LoRA用画像をいろいろするスクリプト

## 概要

本プロジェクトは、LoRA（Low-Rank Adaptation）学習用の画像データセット作成を自動化するPythonスクリプト集です。画像のリサイズ、タグ付け、キャプション生成、データベース管理などの機能を提供し、効率的なデータセット作成をサポートします。

### 主な機能

- **画像処理**: 画像のリサイズ、フォーマット変換、自動クロップなどを行います。
- **メタデータ管理**: 画像のメタデータをSQLiteデータベースで管理します。
- **タグ・キャプション生成**: GPT-4などのAIモデルを使用して、画像のタグとキャプションを自動生成します。
- **バッチ処理**: 大量の画像を効率的に処理するためのバッチ処理機能を提供します。
- **ファイルシステム管理**: 処理された画像や生成されたデータの保存を体系的に管理します。

### 主要コンポーネント

- **ImageEditor.py**: 画像処理を担当。リサイズ、クロップ、フォーマット変換などを行います。
- **caption_tags.py**: 画像分析とタグ・キャプション生成を行います。
- **api_utils.py**: APIとの通信を管理。バッチ処理のサポートも含みます。
- **db.py**: SQLiteデータベースの操作を担当します。
- **file_sys.py**: ファイルシステムの操作を管理します。
- **config.py**: 設定ファイルの読み込みと管理を行います。
- **log.py**: ログ機能を提供します。
- **cleanup_txt.py**: テキストデータのクリーンアップを行います。

## セットアップ

### 必要条件

- Python 3.11以上

### インストール手順

1. リポジトリをクローンします：
   ```bash
   git clone https://github.com/NEXTAltair/Lorayougazouwoiroirosurusukuriputo.git
   ```

2. 必要なパッケージをインストールします：
   ```bash
   pip install -r requirements.txt
   ```

3. `processing.toml` ファイルを設定します。

## 使用方法

1. `processing.toml` ファイルで必要な設定を行います。
2. メイン処理を実行します：
   ```bash
   stert.bat
   ```

## 設定

`processing.toml` ファイルで以下の設定が可能です：

- データセットディレクトリ
- 出力ディレクトリ
- 画像処理パラメータ
- API設定
- ログ設定
- その他の処理オプション

## 開発者向け情報

- 各モジュールは独立して動作し、`main.py` で統合されています。
- 新機能の追加時は、既存のクラスとメソッドの拡張を検討してください。
- ユニットテストの追加を推奨します。

## 今後の展望

- GUIインターフェースの追加
- 他のAI画像分析APIのサポート
- パフォーマンス最適化
- より高度なタグ管理システムの実装

## ライセンス

MIT

### 参考

- [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) タグのクリーンナップ
- [DominikDoom/a1111-sd-webui-tagcomplete](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete) tags.dbの基になったCSV tag data
- [applemango](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete/discussions/265) CSV tag data の日本語翻訳
- としあき製 CSV tag data の日本語翻訳
- [AngelBottomless/danbooru-2023-sqlite-fixed-7110548](https://huggingface.co/datasets/KBlueLeaf/danbooru2023-sqlite) danbooru タグのデータベース
- [hearmeneigh/e621-rising-v3-preliminary-data](https://huggingface.co/datasets/hearmeneigh/e621-rising-v3-preliminary-data) e621 rule34 タグのデータベース
- [sd-webui-bayesian-merger](https://github.com/s1dlx/sd-webui-bayesian-merger) スコアリング実装
- [stable-diffusion-webui-dataset-tag-editor](https://github.com/toshiaki1729/stable-diffusion-webui-dataset-tag-editor) スコアリング実装
