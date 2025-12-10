# Phase C Model Class & Edge Case Test Implementation Plan (2025-12-06)

**プロジェクト**: image-annotator-lib  
**ブランチ**: feature/annotator-library-integration  
**現状カバレッジ**: 71% (4855 stmts, 1404 miss)  
**目標カバレッジ**: 75%+ (ギャップ: 4%)  
**戦略**: 高影響・低カバレッジモジュールへの集中投資  
**予定テスト数**: ~30テスト  
**工数見積**: 20時間 (2.5日)

---

## Phase C 概要

### 前提条件
- ✅ **Phase A Complete**: Core unit tests + fixtures実装済み (20% → 45%)
- ✅ **Phase B Complete**: Integration tests実装済み (45% → 65%)
  - PydanticAI統合テスト: 5テスト
  - Context manager lifecycle: 7テスト
  - ModelLoad cache management: 8テスト
  - Cross-provider integration: 5テスト追加

### Phase C 目標
- カバレッジ 71% → 75%+ 達成
- 高影響モジュールの戦略的テストカバレッジ向上
- 既存テスト品質基準の維持

---

## クリティカルカバレッジギャップ分析（検証済み）

### Tier 1: 最高影響度（即座優先）

1. **openai_api_chat.py** - 17% → 70%+ (gain ~53%)
   - **欠落**: 63/76 lines
   - **範囲**: Context manager setup, error handling, batch processing, custom headers
   - **影響**: OpenAI/OpenRouter WebAPI modelのコア実装

2. **simple_config.py** - 35% → 85%+ (gain ~50%)
   - **欠落**: 28/43 lines
   - **範囲**: TOML loading, file error handling, settings merge logic
   - **影響**: Simplified PydanticAI models用設定管理

3. **simplified_agent_wrapper.py** - 26% → 75%+ (gain ~49%)
   - **欠落**: 70/94 lines
   - **範囲**: Async event loop handling, image preprocessing, output formatting
   - **影響**: Simplified PydanticAI interface wrapper

### Tier 2: 高影響度（フォローアップ）

4. **simplified_agent_factory.py** - 58% → 85%+ (gain ~27%)
5. **scorer_clip.py** - 65% → 90%+ (gain ~25%)
6. **utils.py** - 79% → 90%+ (gain ~11%)
7. **config.py** - 75% → 85%+ (gain ~10%)

---

## 実装計画詳細

### Week 1: Critical Path (15 tests, ~10h)

#### Priority 1A: OpenAI WebAPI Models (5 tests)
**新規ファイル**: `tests/unit/model_class/test_openai_api_chat.py`

**Test 1: test_openai_chat_context_manager_initialization()**
- **カバレッジ**: Lines 34-56 (`__enter__` setup)
- **MOCKED**: PydanticAI Agent creation, config_registry.get
- **REAL**: OpenRouter prefix handling ("openrouter:" addition), referer/app_name headers
- **検証項目**: Agent created, config loaded, custom headers set correctly

**Test 2: test_openai_chat_run_with_model_success()**
- **カバレッジ**: Lines 63-140 (run_with_model core logic)
- **MOCKED**: Agent.run() returns AnnotationSchema
- **REAL**: UnifiedAnnotationResult conversion, capabilities handling
- **検証項目**: Response parsed, tags extracted, raw_output serialized, no errors

**Test 3: test_openai_chat_error_handling_http_errors()**
- **カバレッジ**: Lines 141-168 (ModelHTTPError path)
- **MOCKED**: ModelHTTPError with status code/body
- **REAL**: Error wrapping to UnifiedAnnotationResult
- **検証項目**: Error message formatted correctly, result contains error field

**Test 4: test_openai_chat_batch_processing()**
- **カバレッジ**: Lines 71-83 (batch loop iteration)
- **MOCKED**: Multiple agent.run() calls, time.sleep (レート制御実装時)
- **REAL**: Loop iteration, BinaryContent conversion per image
- **検証項目**:
  - 全画像処理完了（ループ回数が入力数と一致）
  - `_wait_for_rate_limit()`呼び出し（実装されている場合）
  - バッチ処理中に例外なし
  - **注**: レート制御未実装の場合はループ正常性のみ検証

**Test 5: test_openrouter_custom_headers()**
- **カバレッジ**: Lines 185-220 (_run_inference with image preprocessing)
- **MOCKED**: config_registry.get for referer/app_name
- **REAL**: "openrouter:" prefix addition, headers in config_data
- **検証項目**: Correct prefix, referer/app_name in Agent config

---

#### Priority 1B: Simple Config Module (4 tests)
**新規ファイル**: `tests/unit/core/test_simple_config.py`

**Test 6: test_simple_config_load_from_toml()**
- **カバレッジ**: Lines 21-30 (_load_config success path)
- **MOCKED**: Temp TOML file with global_defaults/model_overrides
- **REAL**: toml.load(), _config_cache population
- **検証項目**: _config_cache populated correctly, logger.info called

**Test 7: test_simple_config_missing_file_fallback()**
- **カバレッジ**: Lines 29-30 (file not found handling)
- **MOCKED**: MODEL_SETTINGS_PATH.exists() returns False
- **REAL**: Default config dict creation
- **検証項目**: Default structure created, warning logged

**Test 8: test_simple_config_toml_parse_error()**
- **カバレッジ**: Lines 31-33 (exception handling)
- **MOCKED**: toml.load() raises toml.TomlDecodeError
- **REAL**: Exception handling, fallback to defaults
- **検証項目**: Error logged, defaults used, no crash

**Test 9: test_simple_config_get_model_settings_merge()**
- **カバレッジ**: Lines 45-55 (get_model_settings merge logic)
- **MOCKED**: None (uses real dict operations)
- **REAL**: Global defaults + model overrides merge
- **検証項目**: Model overrides take precedence, global defaults preserved

---

#### Priority 1C: Simplified Agent Wrapper (6 tests)
**新規ファイル**: `tests/unit/core/test_simplified_agent_wrapper.py`

**Test 10: test_simplified_wrapper_initialization_and_setup()**
- **カバレッジ**: Lines 20-41 (`__init__`, _setup_agent)
- **MOCKED**: get_agent_factory().get_cached_agent()
- **REAL**: model_id assignment, BaseAnnotator init
- **検証項目**: _agent set, model_id stored correctly

**Test 11: test_simplified_wrapper_context_manager()**
- **カバレッジ**: Lines 43-52 (`__enter__`/`__exit__`)
- **MOCKED**: Agent instance
- **REAL**: Context manager flow
- **検証項目**: Returns self on __enter__, no exceptions on __exit__

**Test 12: test_simplified_wrapper_preprocess_images_to_binary()**
- **カバレッジ**: Lines 54-64, 128-136 (_preprocess_images, _pil_to_binary_content)
- **MOCKED**: None (real PIL operations)
- **REAL**: PIL.Image → BinaryContent conversion
- **検証項目**: BytesIO used, PNG format, BinaryContent created correctly

**Test 13: test_simplified_wrapper_run_inference_sync()**
- **カバレッジ**: Lines 66-147 (_run_inference, _run_agent_inference sync path)
- **MOCKED**: agent.run_sync() success
- **REAL**: Sync execution path
- **検証項目**: run_sync called, result returned

**Test 14: test_simplified_wrapper_run_inference_async_fallback()**
- **カバレッジ**: Lines 148-175 (_run_async_with_new_loop)
- **MOCKED**:
  - run_sync時にRuntimeError ("Event loop")
  - asyncio.new_event_loop()がモックループ返す
  - concurrent.futures.ThreadPoolExecutorをパッチ
  - 非同期パスで成功
- **REAL**: フォールバックロジックフロー
- **検証項目**:
  - sync失敗時にnew_event_loop()呼び出し
  - set_event_loop()が新ループで呼ばれる
  - loop.run_until_complete()呼び出し
  - finallyブロックでloop.close()呼び出し
  - ThreadPoolExecutor正常使用
- **安全性**: モックイベントループでリアル非同期コンテキスト問題を回避

**Test 15: test_simplified_wrapper_format_output_and_tags()**
- **カバレッジ**: Lines 85-111, 113-126, 177-193 (_format_predictions, _generate_tags, _format_output)
- **MOCKED**: Agent result with tags attribute
- **REAL**: Tag extraction, dict formatting
- **検証項目**: Tags list extracted, method field set to "simplified_pydantic_ai"

---

### Week 2: High Priority (10 tests, ~7h)

#### Priority 2A: Utils Edge Cases (4 tests)
**拡張ファイル**: `tests/unit/core/test_utils.py`

**Test 16: test_download_from_url_with_caching()**
- **カバレッジ**: Lines 130-140 (_perform_download)
- **MOCKED**: requests.get stream, tqdm progress
- **REAL**: Cache path generation, file writing
- **検証項目**: File downloaded, progress displayed, cache directory used

**Test 17: test_get_file_path_url_vs_local()**
- **カバレッジ**: Lines 91-93, 206-214 (get_file_path, URL resolution)
- **MOCKED**: URL download for http/https
- **REAL**: urlparse, path resolution logic
- **検証項目**: URLs trigger download, local paths validated, correct path returned

**Test 18: test_determine_effective_device_cuda_unavailable()**
- **カバレッジ**: Lines 224-239 (CUDA fallback)
- **MOCKED**: torch.cuda.is_available() returns False
- **REAL**: Warning logging, CPU fallback
- **検証項目**: "cpu" returned, warning logged

**Test 19: test_determine_effective_device_invalid_cuda_index()**
- **カバレッジ**: Lines 281-290 (CUDA index validation)
- **MOCKED**: torch.cuda.device_count() returns 1
- **REAL**: Index validation (cuda:2 with 1 device)
- **検証項目**: Fallback to cuda:0, warning logged

---

#### Priority 2B: CLIP Scorer Models (3 tests)
**拡張ファイル**: `tests/unit/model_class/test_scorer_models.py`

**Test 20: test_clip_scorer_missing_base_model_error()**
- **カバレッジ**: Lines 22-23 (validation in __enter__)
- **MOCKED**: Config without base_model key
- **REAL**: Validation logic
- **検証項目**: ValueError or ConfigError raised with clear message

**Test 21: test_clip_scorer_mlp_head_initialization()**
- **カバレッジ**: Lines 31-32 (MLP layer creation)
- **MOCKED**: CLIP model components
- **REAL**: MLP layer creation (Linear + ReLU + Dropout)
- **検証項目**: MLP created with correct architecture

**Test 22: test_clip_scorer_image_encoding_and_score()**
- **カバレッジ**: Lines 37-38 (encode + score calculation)
- **MOCKED**: model.encode_image() returns features
- **REAL**: MLP forward pass, score calculation
- **検証項目**: Features extracted, score in [0, 1] range

---

#### Priority 2C: Simplified Agent Factory (3 tests)
**新規ファイル**: `tests/unit/core/test_simplified_agent_factory.py`

**Test 23: test_simplified_factory_get_cached_agent_creation()**
- **カバレッジ**: Lines 34-40 (agent creation)
- **MOCKED**: PydanticAI Agent constructor
- **REAL**: Factory instantiation, cache storage
- **検証項目**: Agent created once, cached with correct key

**Test 24: test_simplified_factory_agent_cache_reuse()**
- **カバレッジ**: Lines 67-85 (cache lookup)
- **MOCKED**: Agent creation counter
- **REAL**: Cache hit logic
- **検証項目**: Same agent returned, no duplicate creation

**Test 25: test_simplified_factory_config_change_invalidates_cache()**
- **カバレッジ**: Lines 98-103 (cache invalidation)
- **MOCKED**: Different config dicts
- **REAL**: Cache key comparison
- **検証項目**: New agent created on config mismatch

---

### Week 3: Polish & Buffer (5-7 tests, ~3h)

#### Priority 3A: Config Module Edge Cases (3 tests)
**拡張ファイル**: `tests/unit/fast/test_config.py`

**Test 26-28**: Config registry edge cases
- get() with defaults
- set() validation
- reload() behavior

#### Priority 3B: Optional Coverage Boost (2-4 tests)
- Base CLIP module tests (if needed)
- Additional error path coverage (if needed)

---

## Mock戦略フレームワーク

### Level 1: 常にMock（外部依存）
- API呼び出し: `requests.get()`, PydanticAI `Agent.run()`
- モデルロード: `transformers.pipeline()`, `clip.load()`
- ファイル操作: `huggingface_hub.hf_hub_download()`
- ハードウェア: `torch.cuda.is_available()`, `torch.cuda.device_count()`

### Level 2: Unit TestでMock（高負荷操作）
- モデル推論: `pipeline(images)`, `agent.run_sync()`
- 画像エンコード: `model.encode_image()`
- 重計算: `imagehash.phash()`

### Level 3: 常にReal（コアロジック）
- 設定管理: `config_registry.get()`, `.set()`
- データ変換: PIL変換, スコア正規化
- エラーハンドリング: Exception wrapping, result formatting
- キャッシュロジック: LRU操作, 無効化

---

## 必要Fixtures

### 既存Fixturesを再利用（conftest.py）
- `managed_config_registry` - 自動クリーンアップ付き設定管理
- `lightweight_test_images` - 3個のRGBテスト画像
- `mock_cuda_available`/`mock_cuda_unavailable` - デバイスモック
- `clear_pydantic_ai_cache` - PydanticAIクリーンアップ (autouse=True)

### 新規Fixtures実装必要
```python
@pytest.fixture
def mock_simple_config_toml(tmp_path):
    """一時TOMLファイル作成（テスト用）"""

@pytest.fixture
def mock_pydantic_ai_agent():
    """PydanticAI Agentモック（wrapper tests用）"""

@pytest.fixture
def mock_clip_processor():
    """CLIP前処理コンポーネントモック"""
```

---

## 成功基準

### 最小要件（必須達成）
- ✅ 全体カバレッジ ≥ 75%
- ✅ 全30テストパス（総テスト数 781+）
- ✅ 既存744テストでリグレッションなし
- ✅ openai_api_chat.py ≥ 70%
- ✅ simple_config.py ≥ 85%
- ✅ simplified_agent_wrapper.py ≥ 75%

### 品質基準（維持必須）
- ✅ 包括的docstrings（REAL/MOCKEDセクション付き）
- ✅ 適切な `@pytest.mark.unit` マーカー
- ✅ テストごと最低3アサーション
- ✅ 独立テスト（共有状態なし）
- ✅ Unit tests完了時間 <1秒/テスト

### Nice-to-Have（オプション）
- 🎯 カバレッジ ≥ 77% (2%バッファ)
- 🎯 全Tier 1モジュール個別 ≥ 75%

---

## クリティカルファイル一覧

### 作成テストファイル
1. `tests/unit/model_class/test_openai_api_chat.py` (5テスト, ~120行)
2. `tests/unit/core/test_simple_config.py` (4テスト, ~100行)
3. `tests/unit/core/test_simplified_agent_wrapper.py` (6テスト, ~150行)
4. `tests/unit/core/test_simplified_agent_factory.py` (3テスト, ~80行)

### 拡張テストファイル
5. `tests/unit/core/test_utils.py` (+4テスト, ~100行)
6. `tests/unit/model_class/test_scorer_models.py` (+3テスト, ~80行)
7. `tests/unit/fast/test_config.py` (+3テスト, ~80行)

### テスト対象ソースファイル
- `src/image_annotator_lib/model_class/annotator_webapi/openai_api_chat.py`
- `src/image_annotator_lib/core/simple_config.py`
- `src/image_annotator_lib/core/simplified_agent_wrapper.py`
- `src/image_annotator_lib/core/simplified_agent_factory.py`
- `src/image_annotator_lib/core/utils.py`
- `src/image_annotator_lib/model_class/scorer_clip.py`
- `src/image_annotator_lib/core/config.py`

---

## リスク軽減策

### Risk 1: OpenAI API Mock複雑性
**解決策**: Phase B PydanticAI mockingパターン使用  
**参照**: `tests/integration/test_pydantic_ai_integration.py`

### Risk 2: Async Event Loop衝突
**解決策**: 既存asyncパターンに従う（`asyncio.new_event_loop()`使用）  
**参照**: Phase B統合テスト

### Risk 3: CLIPモデルロード（テスト内）
**解決策**: 全CLIP操作をMock、fake tensors使用  
**参照**: 既存 `test_scorer_models.py` fixtures

### Risk 4: カバレッジ計算変動
**解決策**: 3回実行して平均取得  
**フラグ**: `--no-cov-on-fail` 使用

---

## 実行コマンド

### Week 1テスト実行
```bash
# プロジェクトルートから
uv run pytest local_packages/image-annotator-lib/tests/unit/model_class/test_openai_api_chat.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simple_config.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py -v
```

### カバレッジ検証
```bash
# 各週完了後
uv run coverage run -m pytest local_packages/image-annotator-lib/tests/
uv run coverage report --include="local_packages/image-annotator-lib/src/*" --fail-under=75
```

### 全テストスイート
```bash
# 最終化前
uv run pytest local_packages/image-annotator-lib/tests/ -v --cov --no-cov-on-fail
```

---

## タイムライン見積

- **Week 1 (Tier 1)**: 15テスト, ~10時間
  - OpenAI API: 4h
  - Simple config: 2h
  - Agent wrapper: 4h

- **Week 2 (Tier 2)**: 10テスト, ~7時間
  - Utils: 2h
  - CLIP scorers: 2h
  - Factory: 2h
  - Buffer: 1h

- **Week 3 (Polish)**: 5-7テスト, ~3時間
  - Config edge cases: 1.5h
  - Optional coverage: 1.5h

**Total**: ~20時間 (2.5日集中作業)

---

## 承認後の次ステップ

1. Week 1テスト実装（Tier 1優先）
2. カバレッジ検証実行 → 約73-74%期待
3. Week 2テスト実装（Tier 2優先）
4. カバレッジ検証実行 → 約75-76%期待
5. 必要に応じてWeek 3テストで補完
6. 最終検証: 全テストパス、カバレッジ ≥ 75%
7. 完了記録でメモリ更新

---

---

## 実装詳細の明確化

### Q1: AnnotationSchema/UnifiedAnnotationResultフィクスチャ
**回答**: `tests/unit/model_class/conftest.py`に共有`mock_annotation_schema`フィクスチャ作成  
**理由**: OpenAI, Google, Anthropic WebAPIテスト間で再利用  
**内容**: 典型的なtags/captions/scoreを持つAnnotationSchemaを返す

### Q2: CLIPフェイク埋め込み/MLP重み
**回答**: `mock_clip_processor`フィクスチャで`torch.randn(1, 512)`定義  
**場所**: `tests/unit/model_class/conftest.py`またはテストファイル内  
**MLP**: MLPモジュール全体をモック、リアルな重み初期化不要

### Q3: レート制御検証戦略
**回答**:
1. まずopenai_api_chat.pyで`_wait_for_rate_limit()`の存在確認
2. 存在する場合: パッチして呼び出し回数がバッチサイズと一致を検証
3. 存在しない場合: ループ正常性のみ検証（反復回数、クラッシュなし）
**決定**: メソッド利用可能性に基づく条件付きアサーション

---

**計画策定日**: 2025-12-06  
**更新日**: 2025-12-06 (指摘事項反映)  
**次のステップ**: `/implement` コマンドで実装開始  
**詳細計画**: `/home/vscode/.claude/plans/twinkly-coalescing-goose.md`
