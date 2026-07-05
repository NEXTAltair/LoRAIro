---
type: Reference
title: LoRAIro Product Requirements (PRD)
status: Accepted
timestamp: 2026-07-05
tags: [requirements, product-scope]
---
# LoRAIro Product Requirements Document (PRD)

## ビジョン

LoRAIro (LoRA Image Annotation and Refinement Operations) は、LoRA (Low-Rank Adaptation)
学習用の画像データセット作成を自動化するデスクトップツール。画像の登録・AI アノテーション・
品質評価・タグ整備・学習用エクスポートまでを単一アプリケーションで完結させ、
手作業のタグ付けに費やす時間を大幅に削減する。

## 対象ユーザー

- 個人〜小規模で LoRA / fine-tuning 用データセットを作る ML 実務者・研究者
- 自作画像コレクションからカスタムモデル用データセットを準備するクリエイター

ローカル完結のデスクトップアプリ (GUI: PySide6 / CLI: Typer) であり、
Web サービスやマルチユーザー運用は対象外。

## 提供機能（現行）

### 画像登録・管理
- ディレクトリからの一括登録、pHash による重複検出
- プロジェクト単位ストレージ: `lorairo_data/<project>_YYYYMMDD_NNN/` (SQLite + image_dataset/)
- リサイズ・フォーマット変換等の画像処理 (処理済み画像は DB で追跡)

### AI アノテーション
- マルチプロバイダ対応: OpenAI / Anthropic / Google の WebAPI + ローカル ML モデル
  (image-annotator-lib へ委譲。モデル名から provider を自動決定)
- アノテーション種類: tags / caption / score / rating (用語は ADR 0075)
- 同期実行 (SYNC) と Provider Batch API 経由の非同期バッチ送信 (PROVIDER BATCH) の 2 経路。
  バッチ適格判定は lib が SSoT (ADR 0038)
- Jobs タブでの推論台帳 (INFERENCE LEDGER) 監視。失敗画像は個別リトライ、
  プロバイダ間の自動フォールバックは行わない

### タグ検索・編集
- タグ検索: 除外検索 (`-tag`)、オートコンプリート、リアルタイム件数表示
- タグ編集: genai-tag-db-tools 連携 (翻訳参照、翻訳品質 recommendation、ユーザー DB 登録)
- AI タグの confidence は lib が返さないため (常に None)、ノイズ排除は手動 soft-reject で行う

### 品質評価
- CLIP aesthetic / MUSIQ 等による画像品質スコアリング (評価ロジックは lib に委譲、
  モデル固有の値をそのまま保存・表示・フィルタに使う)

### エクスポート
- 学習用ディレクトリ構造での出力 (.txt / .caption / json)
- エクスポート時のタグ一時編集 (DB 永続層とは分離した出力 overlay、ADR 0083 系)

### CLI (lorairo-cli)
- プロジェクト管理・画像登録・検索・アノテーション・エクスポート・DB 調査を
  スクリプタブルに実行 (GUI 稼働中でも読み取りアクセス可)

## 非機能要件

- **応答性**: 長時間処理は QThreadPool worker で非同期化し UI をブロックしない
- **データ整合性**: スキーマ変更は Alembic migration で管理。通常運用でデータ損失なし
- **テスト品質**: カバレッジ 75% 以上、CI-equivalent filter での検証 (docs/testing.md)
- **保守性**: Qt-free core / repository pattern / 2 層サービスアーキテクチャ (docs/architecture.md)
- **API キー管理**: `config/lorairo.toml` で外部化、コードへのハードコード禁止

## 非目標 (Non-Goals)

- Web サービス化・マルチユーザー対応
- API 利用コストの管理・予算制御 (利用者責任)
- プロバイダ間の自動フォールバック
- confidence 閾値による AI タグ自動フィルタ (lib が per-tag 確率を提供しないため不可)

## 詳細参照

- システム設計: [architecture.md](architecture.md) / サービス一覧: [services.md](services.md)
- 機能仕様: [specs/](specs/) / 設計判断: [decisions/](decisions/README.md)
- CLI リファレンス: [cli.md](cli.md) / 廃止機能: [DEPRECATIONS.md](DEPRECATIONS.md)
