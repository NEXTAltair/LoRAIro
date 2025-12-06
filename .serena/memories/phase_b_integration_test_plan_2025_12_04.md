# Phase B Integration Test Implementation Plan (2025-12-04)

**プロジェクト**: image-annotator-lib
**ブランチ**: feature/phase2-test-fixes
**目標**: カバレッジ 45% → 65% (+25テスト)
**前提**: Phase A完了（Core unit tests + fixtures実装済み）

---

## Phase B概要

### テスト戦略

**Mock対象（外部依存のみ）:**
- API呼び出し: `@patch("...Agent.run", new_callable=AsyncMock)`
- モデルダウンロード: `@patch("...ModelLoad.load_transformers_components")`
- システムメモリ: `@patch("psutil.virtual_memory")`
- CUDA可用性: `mock_cuda_available/unavailable` fixtures使用

**REAL使用（内部コンポーネント）:**
- 全キャッシュ辞書: `ModelLoad._MODEL_STATES`, `_MEMORY_USAGE`, `_MODEL_LAST_USED`
- Providerキャッシュ: `ProviderManager._provider_instances`, `PydanticAIProviderFactory._providers`
- 全Config操作: `config_registry.set()`, `.get()`
- 全デバイス状態: `annotator.device`, `annotator.components`
- 全ライフサイクル: `__enter__`, `__exit__`

---

## 4つのテストファイル（25テスト、~1,200行）

### Task 1: test_context_manager_lifecycle_integration.py (NEW, 7 tests)

**フォーカス**: コンテキストマネージャーの完全なライフサイクルテスト

**1.1 Full Lifecycle Tests (3 tests)**
- `test_pipeline_full_lifecycle_success()` - Pipeline: __init__ → __enter__ → annotate → __exit__
- `test_transformers_full_lifecycle_success()` - Transformersアノテーター版
- `test_webapi_full_lifecycle_success()` - WebAPIアノテーター版

**検証項目**:
- 状態遷移: None → "loaded" → "cached"
- メモリクリーンアップ
- コンポーネントライフサイクル

**1.2 Device Fallback Tests (2 tests)**
- `test_cuda_to_cpu_fallback_preserves_functionality()` - CUDA不可時のCPUフォールバック
- `test_cpu_explicit_no_fallback_needed()` - 明示的CPU設定

**1.3 Error Recovery Tests (2 tests)**
- `test_load_failure_cleanup()` - ロード失敗時のクリーンアップ
- `test_restoration_failure_continues_with_warning()` - CUDA復元失敗時のCPU継続

---

### Task 2: test_model_factory_integration.py (NEW, 8 tests)

**フォーカス**: ModelLoadキャッシュ管理とLRU排出

**2.1 Multi-Model Concurrent Loading (3 tests)**
- `test_concurrent_model_loading_cache_behavior()` - 3モデル連続ロード
- `test_cache_hit_updates_last_used()` - キャッシュヒット時のLRU更新
- `test_sequential_model_access_lru_order()` - 再アクセスによる順序更新

**2.2 Cache Eviction Under Memory Pressure (3 tests)**
- `test_lru_eviction_with_memory_pressure()` - メモリ圧迫時のLRU排出
- `test_eviction_respects_lru_order()` - LRU順序に従った排出
- `test_no_eviction_when_memory_sufficient()` - メモリ十分時は排出なし

**2.3 Device Fallback Scenarios (2 tests)**
- `test_cuda_failure_fallback_to_cpu_cache()` - CUDA失敗→CPUキャッシング
- `test_mixed_device_cache_isolation()` - CPU/CUDAモデル共存

---

### Task 3: test_cross_provider_integration.py (EXPAND, +5 tests)

**現状**: 123行 → **目標**: 250行

**フォーカス**: Provider間のリソース共有と設定一貫性

**3.1 Sequential Provider Switching (2 tests)**
- `test_sequential_provider_switching_real_instances()` - Provider間の切り替え
- `test_provider_instance_reuse_verification()` - 同一Provider再利用

**3.2 Configuration Consistency (2 tests)**
- `test_config_change_invalidates_cache()` - 設定変更でキャッシュ無効化
- `test_api_key_change_creates_new_provider()` - APIキー変更で新インスタンス

**3.3 Error Isolation (1 test)**
- `test_provider_error_isolation()` - 1つのProviderエラーが他に影響しない

---

### Task 4: test_pydantic_ai_integration.py (NEW, 5 tests)

**フォーカス**: PydanticAI AgentキャッシングとProvider共有

**4.1 Agent Caching Flow (2 tests)**
- `test_agent_cache_lifecycle()` - Agent作成 → キャッシング → 再利用
- `test_agent_cache_with_config_changes()` - 設定変更で新Agent作成

**4.2 Cache Invalidation (2 tests)**
- `test_explicit_cache_clear()` - `clear_cache()`の動作確認
- `test_cache_isolation_between_tests()` - テスト間の隔離確認

**4.3 Provider Instance Sharing (1 test)**
- `test_provider_sharing_across_models()` - 複数モデル間でProvider共有

---

## 実装順序

**Week 1** (簡単なものから):
- Task 4: PydanticAI統合テスト（最もシンプル）
- Task 1.1-1.2: ライフサイクル＋デバイスフォールバック

**Week 2** (複雑な部分):
- Task 2: ModelLoad統合テスト（メモリ管理が複雑）
- Task 1.3: エラーリカバリー

**Week 3** (総合):
- Task 3: Cross-provider統合（全概念を統合）

---

## 成功基準

### テスト品質
- ✅ 各テストにREAL/MOCKED明記のdocstring
- ✅ REALコンポーネントでのアサーション
- ✅ Mock戦略をコメント記載
- ✅ `@pytest.mark.integration` + `@pytest.mark.fast_integration`

### カバレッジ目標
- ✅ プロジェクト全体: 45% → 65%
- ✅ `core/model_factory.py`: 70% → 85%
- ✅ `core/provider_manager.py`: 60% → 80%
- ✅ `core/pydantic_ai_factory.py`: 65% → 85%
- ✅ `core/base/annotator.py`: 55% → 75%

### 実行検証コマンド
```bash
# Phase Bテストのみ実行
uv run pytest local_packages/image-annotator-lib/tests/integration -k "lifecycle or factory or cross_provider or pydantic_ai" -v

# カバレッジ確認
uv run coverage run -m pytest local_packages/image-annotator-lib/tests/integration
uv run coverage report --include="src/image_annotator_lib/core/*"
```

---

## 重要なファイル参照

### Phase A成果物（再利用）
- `tests/conftest.py` - `managed_config_registry`, `mock_cuda_*` fixtures
- `tests/integration/conftest.py` - `disable_real_api_requests`, `clear_pydantic_ai_cache`, `lightweight_test_images`

### 既存統合テスト参考
- `tests/integration/test_provider_manager_integration.py` (749行) - Providerインスタンス共有パターン
- `tests/integration/test_memory_management_integration.py` (355行) - キャッシュライフサイクルテスト

### 実装ファイル
- `src/image_annotator_lib/core/model_factory.py` - ModelLoad（LRUキャッシュ）
- `src/image_annotator_lib/core/provider_manager.py` - ProviderManager（clear_cache() API）
- `src/image_annotator_lib/core/pydantic_ai_factory.py` - PydanticAIProviderFactory（Agentキャッシング）
- `src/image_annotator_lib/core/base/annotator.py` - BaseAnnotator（コンテキストマネージャー）

---

## リスク軽減策

### 完了済み
- ✅ Phase A fixturesが再利用可能
- ✅ REALコンポーネントテスト戦略をPhase Aで検証済み
- ✅ 既存統合テストでMockパターン確立
- ✅ `clear_pydantic_ai_cache` fixtureで状態汚染防止

### Phase B固有リスク
- **ModelLoad内部API変更**: 可能な限りpublic interfaceをテスト、必要に応じて統合テストユーティリティ追加
- **キャッシュ状態汚染**: `autouse=True` fixtureで自動クリーンアップ
- **CUDAモック複雑性**: 既存fixturesを活用、CPUパスを先にテスト

---

## 見積もり

- **テスト数**: 25個
- **コード量**: ~1,200行
- **工数**: 6-8時間（3週間で段階的実装）
- **カバレッジ向上**: +20 percentage points (45% → 65%)

---

**計画策定日**: 2025-12-04
**次のステップ**: `/implement` コマンドで実装開始
**詳細計画**: `/home/vscode/.claude/plans/majestic-nibbling-reddy.md`
