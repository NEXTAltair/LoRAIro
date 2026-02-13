# Plan 1 PydanticAI Model Factory マージ完了記録

## 日付: 2026-02-12

## 概要
Plan 1 (infer_model()専用) アーキテクチャを採用し、image-annotator-libのPydanticAI統合を簡素化。

## 変更サマリー

### image-annotator-lib (サブモジュール)
- **ソース**: 6ファイル変更
  - `pydantic_ai_factory.py`: PydanticAIAgentFactory (infer_model()ベース)
  - `provider_manager.py`: 統一推論エントリポイント (151行)
  - 4 annotator: 薄いラッパー化 (ProviderManager.run_inference_with_model()に委譲)
- **テスト**: 5ファイル変更
  - `test_api_errors.py`: ProviderManager経由のエラーテスト
  - `test_openai_api_chat.py`: WebAPIModelConfig DIパターン
  - `test_provider_manager.py`, `test_pydantic_ai_factory.py`: Plan 1用
  - `conftest.py`: PydanticAIAgentFactory参照に更新
- **ネット削減**: -2,287行

### LoRAIro本体
- `AnnotationExecutionResult`: 実行統計付き結果型
- `AnnotationSummaryDialog`: 処理結果サマリー表示
- `AnnotationWorker`: エラー詳細収集・サマリー生成
- `MainWindow`: サマリーダイアログ表示対応
- テストインフラ: ヘッドレスconftest整備

## 削除されたクラス/パターン
- `PydanticAIProviderFactory` → `PydanticAIAgentFactory`
- `PydanticAIAnnotatorMixin` → 削除
- `ProviderInstance`階層 (OpenAI/Anthropic/Google) → 削除
- `get_cached_agent()` → `get_or_create_agent()`
- `run_with_model()` → `ProviderManager.run_inference_with_model()`

## テスト結果
- image-annotator-lib unit: 345 passed, 5 skipped
- LoRAIro全体: 1189 passed

## テスト移行パターン
- WebAPIModelConfig DIでconfig_registry依存回避
- calculate_phashは`image_annotator_lib.core.utils.calculate_phash`でパッチ
- エラーパスでは`get_model_capabilities`モックも必要

## 実験用worktree
- `/workspaces/LoRAIro-plan1` と `/workspaces/LoRAIro-plan2` を削除済み
- `experiment/plan1-*`, `experiment/plan2-*` ブランチも削除済み
