---
type: Reference
title: LoRAIro Technical Specification
status: Accepted
timestamp: 2026-04-08
tags: [service-layer]
depends_on: [pyside6, sqlalchemy, sqlite, pydantic]
---
# LoRAIro 技術仕様

## 技術スタック

### コア技術

**Python 3.12+**: モダンな型ヒントと AI / ML エコシステムを備えた主要開発言語である。

**PySide6**: クロスプラットフォーム対応の Qt for Python GUI フレームワークである。

**データベース**: SQLite に SQLAlchemy ORM と Alembic マイグレーションを組み合わせる。

**パッケージ管理**: 依存解決と仮想環境管理に uv を使用する。

### AI 統合

**対応プロバイダー**: OpenAI GPT-4、Anthropic Claude、Google Gemini、ローカル ML モデルである。

**主要な統合構成**:
- **WorkerService** → **AnnotationWorker** → **image-annotator-lib**
- ローカルパッケージ統合によるマルチプロバイダー統一インターフェース
- ローカルパッケージ: `image-annotator-lib`、`genai-tag-db-tools`

詳細な統合パターンは `docs/integrations.md` を参照する。

### 開発ツール

**コード品質**: Ruff (リンター / フォーマッター)、mypy (型チェック)

**テスト**: pytest によるカバレッジ解析および Qt GUI テスト

**ロギング**: Loguru による構造化ログ (設定は `src/lorairo/utils/log.py`)

## 開発支援ツール

**開発エージェント**: Claude Code / Codex (エージェントスキルとサブエージェント。`.agents/skills/` および `docs/development-workflow.md` を参照)

**ドキュメント**: 設計判断は `docs/decisions/`、計画記録は `docs/plans/` に配置する。
**長期記憶**: `docs/decisions/` (ADR) + `docs/lessons-learned.md`

**コーディングワークフローを強化するための開発専用ツール群である。**

## 開発環境

### システム要件
- **OS**: Windows 10/11、macOS 10.15+、Linux (Ubuntu 20.04+)
- **ハードウェア**: 最小 8GB RAM (推奨 16GB)、ストレージ 10GB、ローカル ML モデル用の任意 GPU
- **Python**: 仮想環境をサポートする 3.12 以上

### セットアップ
```bash
git clone --recurse-submodules https://github.com/user/LoRAIro.git
uv sync --dev
```

### 設定
- **メイン設定**: `config/lorairo.toml` - アプリケーション設定、API キー、ログ設定
- **環境変数**: OpenAI、Anthropic、Google 各プロバイダーの API キー

## データベース設計

### スキーマアーキテクチャ

**コアテーブル**: Images、Annotations、Quality Scores を適切な外部キー関係で構成する。

**主な特徴**:
- SQLite + SQLAlchemy ORM + Alembic マイグレーション
- 一貫した日時処理のための UTC タイムゾーン標準化
- 最適なクエリ実行のためのパフォーマンスインデックス
- 参照整合性を保つ CASCADE 削除

**マイグレーション管理**: Alembic による自動マイグレーション生成およびロールバック対応

設計判断の詳細 (UNIQUE 制約を設けない方針、外部タグ DB への FK を設けない方針) は `docs/decisions/0002-database-schema-decisions.md` を参照する。

## コードアーキテクチャ

### デザインパターン

**主要パターン**:
- **Repository Pattern**: SQLAlchemy 実装によるデータアクセス抽象化
- **Service Layer Pattern**: 2 層アーキテクチャ (ビジネスロジック + GUI サービス)
- **Factory Pattern**: AI プロバイダーの生成と管理
- **Dependency Injection**: 階層化アーキテクチャに基づくサービスコンテナ

各パターン選定の根拠は `docs/decisions/` を参照する。

### エラーハンドリング戦略

**カスタム例外階層**: `LoRAIroException` を基底とし、専用例外型 (Configuration、Database、ImageProcessing、AIProvider) を定義する。

**エラーハンドリングパターン**: コンテキストマネージャーを用いて一貫したエラー処理とリカバリを行う。

### 型システム

**型定義**: 構造化データには `TypedDict` (`ImageMetadata`、`AnnotationResult`、`QualityScore`) を使用する。

**プロトコル定義**: インターフェース準拠を検証するため、ランタイムチェック可能なプロトコルを使用する。

## パフォーマンス最適化

**主な特徴**:
- **メモリ管理**: リソース監視を伴う画像処理の最適化
- **データベース性能**: コネクションプーリングとクエリ最適化
- **バッチ処理**: 100 枚単位のバッチ処理 (1000 枚を 5 分以内で処理する目標)
- **非同期処理**: `QThreadPool` によるバックグラウンドタスク管理

ML ライブラリの遅延インポート判断については `docs/decisions/0010-torch-import-design.md` を参照する。

## セキュリティ考慮事項

**主な特徴**:
- **API キー管理**: 環境変数での保管とマスク済みログ出力
- **入力検証**: ファイルパスの検証および画像コンテンツの検証
- **設定のセキュリティ**: 個人開発用途を前提とした平文保存

セキュリティガイドラインは `.claude/rules/security.md` を参照する。

## デプロイメント考慮事項

**ビルドと配布**: `pyproject.toml` と環境設定を用いたアプリケーションパッケージング

**環境構築**: リソース制限とロギングを備えた本番構成
