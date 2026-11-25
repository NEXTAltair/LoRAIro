---
type: ADR
title: Annotator-Lib Architecture
status: Accepted
timestamp: 2025-10-22
tags: []
---
# ADR 0004: Annotator-Lib Architecture

## Context

`image-annotator-lib` のアーキテクチャ設計において、ローカルモデル(Transformers および ONNX)と Web API モデル(OpenAI、Anthropic、Google)を統一インターフェースで扱う必要があった。

## Decision

**3 層階層設計**を採用する。

1. **`BaseAnnotator`**: 全アノテーターの共通インターフェースと、統一結果型 `UnifiedAnnotationResult` を定義する。
2. **フレームワーク別基底クラス**: `TransformersBaseAnnotator`、`ONNXBaseAnnotator`、`WebApiBaseAnnotator` を提供する。
3. **具象モデルクラス**: モデル固有のロジックを実装し、`annotator_config.toml` と連携する。

あわせて、Web API 専用の追加コンポーネントを配置する。

- `PydanticAIProviderFactory`: Provider と Agent の LRU キャッシュを管理する。
- `ProviderManager`: Provider レベルの推論実行と Model ID に基づくルーティングを担う。
- `PydanticAIAnnotatorMixin`: PIL Image から `BinaryContent` への変換と非同期推論を提供する。

## Rationale

- 例外を送出せず結果オブジェクトの `error` フィールドにエラー情報を格納することで、プロバイダーに依存しない統一的なエラー処理を実現できる。
- LRU キャッシュにより、Agent インスタンスの再生成コストを削減できる。
- `ModelConfigRegistry` により、System、User、Runtime の 3 段階で設定を上書きできる。

## Consequences

- 新しいローカルモデルを追加する手順は、基底クラスの継承、`_generate_tags` の実装、設定の追加という 3 ステップになる。
- 新しい Web API モデルを追加する手順は、`WebApiBaseAnnotator` と `PydanticAIAnnotatorMixin` の継承、および設定の追加で完結する。
- LoRAIro 本体との境界は `annotator_adapter.py` に集約され、アダプターパターンによって型変換を局所化できる。
