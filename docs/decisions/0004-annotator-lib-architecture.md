# ADR 0004: Annotator-Lib Architecture

- **日付**: 2025-10-22
- **ステータス**: Accepted

## Context

image-annotator-lib のアーキテクチャ設計。ローカルモデル (Transformers/ONNX) と Web API モデル (OpenAI/Anthropic/Google) を統一インターフェースで扱う必要があった。

## Decision

**3層階層設計**を採用:
1. `BaseAnnotator` — 全アノテーターの共通インターフェース + 統一型 `UnifiedAnnotationResult`
2. Framework-specific Base Classes — `TransformersBaseAnnotator`, `ONNXBaseAnnotator`, `WebApiBaseAnnotator`
3. Concrete Model Classes — モデル固有ロジック + `annotator_config.toml` との連携

**Web API 専用追加コンポーネント**:
- `PydanticAIProviderFactory`: Provider + Agent の LRU キャッシュ
- `ProviderManager`: Provider レベルの推論実行 + Model ID ルーティング
- `PydanticAIAnnotatorMixin`: PIL Image → BinaryContent 変換 + 非同期推論

## Rationale

- 例外を投げずに結果 (`error` フィールド) に含めるエラーハンドリングでプロバイダー非依存の統一処理が可能
- LRU キャッシュで Agent インスタンスの再生成コストを削減
- `ModelConfigRegistry` で System/User/Runtime の3段階設定オーバーライドを実現

## Consequences

- 新ローカルモデル追加: 基底クラス継承 → `_generate_tags` 実装 → config 追加の3ステップ
- 新 Web API モデル追加: `WebApiBaseAnnotator` + `PydanticAIAnnotatorMixin` 継承 → config 追加
- LoRAIro 側との境界: `annotator_adapter.py` でアダプターパターンにより型変換を局所化
