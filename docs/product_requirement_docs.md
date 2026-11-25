---
type: Reference
title: LoRAIro Product Requirements (PRD)
status: Accepted
timestamp: 2026-07-05
tags: [requirements, product-scope]
---
# LoRAIro プロダクト要求仕様書(PRD)

## ビジョン

LoRAIro(LoRA Image Annotation and Refinement Operations)は、LoRA(Low-Rank Adaptation)学習用の画像データセット作成を自動化するデスクトップツールである。画像の登録、AI アノテーション、品質評価、タグ整備、学習用エクスポートまでを単一アプリケーションで完結させ、手作業のタグ付けに費やす時間を大幅に削減する。

## 対象ユーザー

- 個人から小規模チームで LoRA やファインチューニング用のデータセットを作成する ML 実務者・研究者
- 自作の画像コレクションからカスタムモデル用データセットを準備するクリエイター

ローカル環境で完結するデスクトップアプリ(GUI は PySide6、CLI は Typer)であり、Web サービス化やマルチユーザー運用は対象外とする。

## 提供機能(現行)

### 画像登録・管理
- ディレクトリからの一括登録と、pHash による重複検出を行う
- プロジェクト単位のストレージ構成(`lorairo_data/<project>_YYYYMMDD_NNN/` 配下に SQLite と `image_dataset/` を配置)を採用する
- リサイズやフォーマット変換などの画像処理を行い、処理済み画像を DB で追跡する

### AI アノテーション
- OpenAI・Anthropic・Google の WebAPI とローカル ML モデルに対応する(処理は `image-annotator-lib` へ委譲し、モデル名からプロバイダーを自動決定する)
- アノテーション種別として `tags`、`caption`、`score`、`rating` を扱う(用語定義は ADR 0075 を参照)
- 同期実行(SYNC)と Provider Batch API 経由の非同期バッチ送信(PROVIDER BATCH)の 2 経路を備える。バッチ適格判定の SSoT はライブラリ側とする(ADR 0038)
- Jobs タブの推論台帳(INFERENCE LEDGER)で実行状況を監視する。失敗した画像は個別にリトライし、プロバイダー間の自動フォールバックは行わない

### タグ検索・編集
- 除外検索(`-tag`)、オートコンプリート、リアルタイム件数表示によるタグ検索を提供する
- `genai-tag-db-tools` と連携し、翻訳参照、翻訳品質のリコメンド、ユーザー DB へのタグ登録を行う
- AI タグの `confidence` はライブラリが返さない(常に `None`)ため、ノイズ排除は手動の soft-reject で行う

### 品質評価
- CLIP aesthetic や MUSIQ などによる画像品質スコアリングを行う。評価ロジックはライブラリへ委譲し、モデル固有の値をそのまま保存・表示・フィルタに用いる

### エクスポート
- 学習用のディレクトリ構造で `.txt`、`.caption`、`json` を出力する
- エクスポート時の一時的なタグ編集は、DB 永続層から分離した出力オーバーレイで実現する(ADR 0083 系)

### CLI(`lorairo-cli`)
- プロジェクト管理、画像登録、検索、アノテーション、エクスポート、DB 調査をスクリプトから実行できる。GUI 稼働中でも読み取りアクセスが可能である

## 非機能要件

- **応答性**: 長時間処理は `QThreadPool` ワーカーで非同期化し、UI をブロックしない
- **データ整合性**: スキーマ変更は Alembic マイグレーションで管理し、通常運用でデータを損失させない
- **テスト品質**: カバレッジ 75% 以上を維持し、CI 同等フィルタで検証する(`docs/testing.md`)
- **保守性**: Qt-free コア、リポジトリパターン、2 層サービスアーキテクチャを採用する(`docs/architecture.md`)
- **API キー管理**: `config/lorairo.toml` に外部化し、コードへのハードコードを禁止する

## 非目標(Non-Goals)

- Web サービス化およびマルチユーザー対応
- API 利用コストの管理や予算制御(利用者側の責任とする)
- プロバイダー間の自動フォールバック
- `confidence` 閾値による AI タグの自動フィルタ(ライブラリがタグごとの確率を提供しないため不可)

## 詳細参照

- システム設計: [architecture.md](architecture.md)
- サービス一覧: [services.md](services.md)
- 機能仕様: [specs/](specs/)
- 設計判断: [decisions/](decisions/README.md)
- CLI リファレンス: [cli.md](cli.md)
- 廃止機能: [DEPRECATIONS.md](DEPRECATIONS.md)
