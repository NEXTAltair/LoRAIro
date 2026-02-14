# Issue #6 BaseAnnotator.predict() UnifiedAnnotationResult 統一実装 (2026-02-14)

## 概要
BaseAnnotator.predict() の戻り値型を `list[AnnotationResult]` から `list[UnifiedAnnotationResult]` に統一し、型の不整合を解消。

## 問題
- BaseAnnotator.predict() が AnnotationResult (TypedDict) を返していたが、api.py の _annotate_model() は UnifiedAnnotationResult を期待
- Worker側で _extract_scores_from_formatted_output() によるフォールバック処理が必要だった

## 実装内容

### 1. BaseAnnotator 修正
- **predict() 戻り値型変更**: `list[AnnotationResult]` → `list[UnifiedAnnotationResult]`
- **_build_results() 修正**:
  - `formatted_predictions` が UnifiedAnnotationResult インスタンスの場合は直接使用
  - dict 形式の場合は UnifiedAnnotationResult に変換
  - scores フィールドへの自動マッピング実装
- **_create_error_results() 修正**: UnifiedAnnotationResult を返すよう変更

### 2. テスト修正
- PydanticAIProviderFactory → PydanticAIAgentFactory への名称変更対応
- 全テストファイルで一括置換実施（`find ... -exec sed -i ...`）

### 3. Worker側フォールバック削除
- registration_worker.py から _extract_scores_from_formatted_output() 削除済み
- scores フィールドに直接アクセス可能に

## テスト結果
- BaseAnnotator テスト全18件パス確認済み
- Worker側でスコア抽出フォールバック不要を確認

## 受け入れ基準達成
✅ predict() が list[UnifiedAnnotationResult] を返す
✅ 全アノテータサブクラスのテストがパス
✅ Worker側フォールバック削除可
⏳ 型チェック（mypy）は別途確認予定

## コミット
- fb718bb: fix: Issue #6 BaseAnnotator.predict() 戻り値型を UnifiedAnnotationResult に統一
- ブランチ: NEXTAltair/issue6

## 技術的ポイント
- UnifiedAnnotationResult の検出は `isinstance(item, UnifiedAnnotationResult)` で判定
- 全サブクラス（CLIP, ONNX, WebAPI, Transformers, Pipeline等）が UnifiedAnnotationResult を返す設計に統一
- Worker層での型変換処理が不要になり、アーキテクチャがシンプルに

## 関連Issue
- Issue #6 (LoRAIro): クローズ済み
