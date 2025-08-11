# AnnotatorLibAdapter廃止完全除去計画書

## 🎯 プロジェクト概要

**目的**: ModelSelectionServiceからAnnotatorLibAdapter依存を完全に除去し、Protocol-based現代アーキテクチャのみに統一する

**対象ブランチ**: `refactor/remove-annotatorlibadapter-dependencies`

**最終目標**: 古い互換用コードの完全削除、現代的なProtocol-based設計への統一

## 📊 影響範囲分析

### 🎯 Core Target: ModelSelectionService

**ファイル**: `src/lorairo/gui/services/model_selection_service.py`

#### 削除対象コード

```python
# Constructor parameter
def __init__(self, annotator_adapter: AnnotatorLibAdapter | None = None)

# Legacy method
def _load_models_legacy(self) -> list[ModelInfo]

# Legacy compatibility wrapper
def _infer_capabilities(self, model_data: dict[str, Any]) -> list[str]

# Legacy fallback logic in load_models()
if self.annotator_adapter:
    return self._load_models_legacy()
```

### 🔄 依存コンポーネント更新対象

#### 1. SearchFilterService

**ファイル**: `src/lorairo/gui/services/search_filter_service.py`

- Constructor parameter: `annotator_adapter: "AnnotatorLibAdapter | None"`
- Instance variable: `self.annotator_adapter`
- Method: `_create_model_selection_service()` でのfallback logic
- Debug info: `annotator_adapter_fallback` フィールド

#### 2. ModelSelectionWidget

**ファイル**: `src/lorairo/gui/widgets/model_selection_widget.py`

- Method: `_create_model_selection_service()` でのlegacy approach
- Legacy ModelSelectionService instantiation

### 🧪 テストファイル更新対象

#### Unit Tests
- `tests/unit/gui/services/test_model_selection_service.py`
  - MockAnnotatorLibAdapter使用テスト **[削除対象]**
  - Legacy loading テスト **[削除対象]**
- `tests/unit/gui/services/test_search_filter_service.py`
  - AnnotatorLibAdapter fallback テスト **[削除対象]**

#### Integration Tests  
- `tests/integration/gui/test_annotation_ui_integration.py` **[部分削除]**
- `tests/integration/gui/test_widget_integration.py` **[部分削除]** 
- `tests/integration/test_service_layer_integration.py` **[大幅削除]**

#### Performance Tests
- `tests/performance/test_performance.py`
  - MockAnnotatorLibAdapter使用箇所 **[削除対象]**

#### 🗑️ 完全削除対象テスト
以下のテストは AnnotatorLibAdapter 専用のため完全削除:
- `test_initialization_with_adapter()` - ModelSelectionService
- `test_load_models_legacy()` - ModelSelectionService  
- `test_annotator_adapter_fallback()` - SearchFilterService
- `test_mock_annotator_lib_adapter_performance()` - Performance tests

## 🏗️ 実装計画

### Phase 1: ModelSelectionService現代化

#### Step 1.1: Constructor簡略化

```python
# BEFORE (削除対象)
def __init__(self, annotator_adapter: AnnotatorLibAdapter | None = None):
    self.annotator_adapter = annotator_adapter

# AFTER (現代化)
def __init__(self, model_registry: ModelRegistryServiceProtocol | None = None):
    self.model_registry = model_registry or NullModelRegistry()
```

#### Step 1.2: Legacy Methods削除

- `_load_models_legacy()` method完全削除
- `_infer_capabilities_legacy()` method完全削除
- Legacy fallback logic削除

#### Step 1.3: load_models() 簡略化

```python
# Protocol-only implementation
def load_models(self) -> list[ModelInfo]:
    if self._cached_models is not None:
        return self._cached_models

    protocol_models = self.model_registry.get_available_models()
    compat_models = [self._convert_protocol_to_compat(model) for model in protocol_models]
    self._cached_models = compat_models
    return compat_models
```

### Phase 2: 依存コンポーネント更新

#### Step 2.1: SearchFilterService更新

```python
# Constructor簡略化
def __init__(
    self,
    # annotator_adapter: "AnnotatorLibAdapter | None" = None,  # 削除
    model_registry: ModelRegistryServiceProtocol | None = None,
    model_selection_service: ModelSelectionService | None = None,
):

# _create_model_selection_service() 簡略化
def _create_model_selection_service(self) -> ModelSelectionService:
    return ModelSelectionService.create(model_registry=self.model_registry)
```

#### Step 2.2: ModelSelectionWidget更新

```python
# _create_model_selection_service() 簡略化
def _create_model_selection_service(self) -> ModelSelectionService:
    return ModelSelectionService.create(model_registry=self.model_registry)
```

### Phase 3: テスト現代化と不要テスト削除

#### Step 3.1: Unit Tests更新・削除
**削除対象:**
- `test_initialization_with_adapter()` - AnnotatorLibAdapter専用初期化テスト
- `test_load_models_legacy()` - Legacy loading専用テスト  
- `test_annotator_adapter_fallback()` - SearchFilterService fallback専用テスト

**更新対象:**
- MockAnnotatorLibAdapter参照を全削除
- Protocol-based ModelRegistry mocks使用
- 残存テストのmock戦略変更

#### Step 3.2: Integration Tests更新・削除
**削除対象:**
- AnnotatorLibAdapter patches (多数)
- ServiceContainer AnnotatorLibAdapter統合テスト群
- MockAnnotatorLibAdapter performance測定テスト

**更新対象:**  
- Protocol-based integrationに統一
- ServiceContainer tests简化

#### Step 3.3: Performance Tests更新・削除
**削除対象:**
- `test_mock_annotator_lib_adapter_performance()` 
- MockAnnotatorLibAdapter使用の全performance測定

**更新対象:**
- Protocol-based mocks使用

### Phase 4: Import & 最終クリーンアップ

#### Step 4.1: Import整理

```python
# 削除対象 imports
from ..services.annotator_lib_adapter import AnnotatorLibAdapter
from ...services.annotator_lib_adapter import AnnotatorLibAdapter, MockAnnotatorLibAdapter

# 保持 imports
from ...services.model_registry_protocol import ModelRegistryServiceProtocol
```

#### Step 4.2: ServiceContainer更新考慮

- `src/lorairo/services/service_container.py`での使用継続
- 他サービスでの必要性確認
- 段階的廃止計画策定

## 🧪 テスト戦略

### 検証項目

1. **機能性**: ModelSelectionService core機能動作確認
2. **統合性**: SearchFilterService, ModelSelectionWidget統合確認
3. **性能**: Protocol-only loading performance確認
4. **回帰**: 既存機能への影響なし確認

### テスト実行順序

```bash
# Unit tests
uv run pytest tests/unit/gui/services/test_model_selection_service.py -v
uv run pytest tests/unit/gui/services/test_search_filter_service.py -v

# Integration tests
uv run pytest tests/integration/gui/test_widget_integration.py -v
uv run pytest tests/integration/test_service_layer_integration.py -v

# Full test suite
uv run pytest --co -q | grep -E "(model_selection|search_filter)"
```

## ⚠️ リスクと対策

### 高リスク項目

1. **Breaking Changes**: 他コンポーネントでの直接使用
   - **対策**: 包括的検索と段階的更新
2. **Test Failures**: Legacy依存テストの失敗
   - **対策**: Test modernization並行実施

### 中リスク項目

1. **ServiceContainer依存**: 他サービスでのAnnotatorLibAdapter使用継続
   - **対策**: 影響範囲の慎重な確認、段階的移行計画

## 🎯 実装順序とマイルストーン

### Milestone 1: Core Service現代化

- [ ] ModelSelectionService legacy code削除
- [ ] Unit tests対応

### Milestone 2: GUI Components統合

- [ ] SearchFilterService更新
- [ ] ModelSelectionWidget更新
- [ ] Integration tests対応

### Milestone 3: テスト完全現代化

- [ ] Performance tests更新
- [ ] Full test suite合格確認

### Milestone 4: 最終検証・最適化

- [ ] Code review & cleanup
- [ ] Performance benchmark
- [ ] Documentation更新

## 📝 成功基準

### 技術的成功基準

- [ ] All unit tests pass (100%)
- [ ] All integration tests pass (100%)
- [ ] No AnnotatorLibAdapter references in target files
- [ ] Protocol-based architecture完全統一

### 機能的成功基準

- [ ] Model selection functionality完全動作
- [ ] Search filter service完全動作
- [ ] GUI model selection widget完全動作
- [ ] Performance degradation無し

## 📋 実装チェックリスト

### ModelSelectionService

- [ ] Constructor parameter削除: `annotator_adapter`
- [ ] Instance variable削除: `self.annotator_adapter`
- [ ] Method削除: `_load_models_legacy()`
- [ ] Method削除: `_infer_capabilities_legacy()`
- [ ] Legacy fallback logic削除
- [ ] Import cleanup

### SearchFilterService

- [ ] Constructor parameter削除: `annotator_adapter`
- [ ] Instance variable削除: `self.annotator_adapter`
- [ ] Method简化: `_create_model_selection_service()`
- [ ] Debug info cleanup: `annotator_adapter_fallback`

### ModelSelectionWidget

- [ ] Method简化: `_create_model_selection_service()`
- [ ] Legacy instantiation削除

### Tests

- [ ] Unit tests modernization & deletion
- [ ] Integration tests modernization & deletion
- [ ] Performance tests modernization & deletion
- [ ] Mock strategy revision
- [ ] Obsolete test removal (AnnotatorLibAdapter専用テスト群)

このプランに基づき、段階的かつ安全にAnnotatorLibAdapter依存を完全除去し、現代的なProtocol-based設計への統一を実現します。
