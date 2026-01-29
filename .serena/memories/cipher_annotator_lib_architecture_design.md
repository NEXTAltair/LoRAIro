# image-annotator-lib アーキテクチャ設計

**作成日**: 2025-10-22
**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)
**目的**: システムアーキテクチャの設計原則と構造を記録

---

## システムアーキテクチャ

### 3層階層設計

**第1層: BaseAnnotator**
- 全アノテーターの共通インターフェース
- 抽象メソッド定義（`annotate`, `_generate_tags`等）
- 型定義の統一（`UnifiedAnnotationResult`）

**第2層: Framework-specific Base Classes**
- `TransformersBaseAnnotator`, `ONNXBaseAnnotator`, `WebApiBaseAnnotator`
- 共通ロジックの集約（メモリ管理、デバイス管理、エラーハンドリング）

**第3層: Concrete Model Classes**
- 具体的なモデル実装
- モデル固有のロジック（`_generate_tags`, `_run_inference`）
- 設定ファイル（`annotator_config.toml`）との連携

## Provider-Level アーキテクチャ（Web API）

### コンポーネント

1. **PydanticAIProviderFactory**: Provider instances and Agent caching (LRU strategy)
2. **ProviderManager**: Provider-level inference execution, Model ID routing
3. **PydanticAIAnnotatorMixin**: PIL Image → BinaryContent conversion, Async inference
4. **PydanticAIWebAPIWrapper**: Backward compatibility with existing `annotate()` API

### メモリ管理

**ModelLoad（ローカルモデル）**: Pre-load size calculation, LRU cache strategy, CUDA/CPU management
**Agent Cache（WebAPIモデル）**: Agent instance caching, Configuration-based invalidation

### 設定管理

**ModelConfigRegistry**: System/user config separation, TOML loading, Model-specific parameters
```
1. System config (resources/system/annotator_config.toml)
2. User config (config/user_config.toml)
3. Runtime override
```

### 統一型システム - UnifiedAnnotationResult

```python
class UnifiedAnnotationResult(BaseModel):
    model_name: str
    capabilities: set[TaskCapability]
    error: str | None = None
    tags: list[str] | None = None
    captions: list[str] | None = None
    scores: dict[str, float] | None = None
```

### エラーハンドリング
- 例外を投げずに結果に含める
- プロバイダー非依存の統一処理
- 詳細なエラーメッセージ

### 新モデル追加方法

**ローカルモデル**: 適切な基底クラス継承 → `_generate_tags`実装 → `annotator_config.toml`設定追加
**WebAPIモデル**: `WebApiBaseAnnotator` + `PydanticAIAnnotatorMixin`継承 → `run_with_model()`実装 → `ProviderManager`追加 → 設定追加
