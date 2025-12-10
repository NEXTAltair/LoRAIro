# Phase C Coverage 75% Implementation Plan (2025-12-08)

**ブランチ**: feature/phase2-test-fixes (image-annotator-lib)
**作成日**: 2025-12-08
**現状**: Phase C Week 1完了、カバレッジ 74.15% / 75%
**目標**: カバレッジ 75.0%+ 達成

---

## 現状分析

### カバレッジ状況
- **Current**: 74.15% (4858 statements, 1256 missing)
- **Target**: 75.0%
- **Gap**: 0.85% (約41-42行)

### 主要ギャップモジュール
- `openai_api_chat.py`: 52.6% (36 lines missing)
- `simplified_agent_wrapper.py`: 69.1% (30 lines missing)

### Skipped Test
- **ファイル**: `tests/unit/core/test_simplified_agent_wrapper.py`
- **テスト**: `test_simplified_wrapper_run_inference_async_fallback` (Line 286)
- **理由**: "FIXME: Async fallback mock setup needs debugging - Week 1 deferral"
- **対象コード**: `_run_async_with_new_loop()` (Lines 155-174, 20行)

---

## 実装計画

### Step 1: Async Fallback Testの完成

**対象ファイル**: `tests/unit/core/test_simplified_agent_wrapper.py`
**対象メソッド**: `SimplifiedAgentWrapper._run_async_with_new_loop()`
**Lines**: 155-174 (20行)

**実装内容**:
1. `@pytest.mark.skip` デコレータを削除
2. Async fallback mockの実装を完成させる

**Mock戦略**:
```python
# Runtime Error発生時の動作をモック
with patch.object(mock_agent, "run_sync", side_effect=RuntimeError("Event loop already running")):
    # asyncio.new_event_loop()のモック
    mock_loop = MagicMock()
    with patch("asyncio.new_event_loop", return_value=mock_loop):
        with patch("asyncio.set_event_loop") as mock_set_loop:
            # Agent.run()の非同期呼び出しをモック
            mock_loop.run_until_complete.return_value = mock_agent_result_with_tags
            
            # ThreadPoolExecutorをモック
            with patch("concurrent.futures.ThreadPoolExecutor"):
                # Test execution
                results = wrapper._run_agent_inference(binary_content)
```

**検証項目**:
- `run_sync()` が呼ばれて RuntimeError を発生させる
- `new_event_loop()` が呼ばれる
- `set_event_loop()` が新しいループで呼ばれる
- `loop.run_until_complete()` が呼ばれる
- `loop.close()` が finally ブロックで呼ばれる
- `ThreadPoolExecutor` が正しく使用される

---

### Step 2: テスト実行と検証

**実行コマンド**:
```bash
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py::TestSimplifiedAgentWrapper::test_simplified_wrapper_run_inference_async_fallback -v
```

**期待結果**:
- テストがパスする
- カバレッジが増加する (69.1% → 75%+)

---

### Step 3: 全テスト実行とカバレッジ測定

**実行コマンド**:
```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
uv run pytest tests/ -v
uv run coverage run -m pytest tests/
uv run coverage report --include="src/image_annotator_lib/*"
```

**成功基準**:
- 773+ tests passed
- 0 failed
- Coverage ≥ 75%

---

### Step 4: Git コミット

**ステージング**:
```bash
git add tests/unit/core/test_simplified_agent_wrapper.py
```

**コミットメッセージ**:
```
test: Achieve Phase C coverage 75% - Complete async fallback test

Complete skipped async fallback test implementation:
- Remove @pytest.mark.skip decorator
- Implement async event loop fallback mock setup
- Add RuntimeError → async path validation
- Verify ThreadPoolExecutor usage

Coverage impact:
- SimplifiedAgentWrapper: 69.1% → 75%+
- Overall coverage: 74.15% → 75.0%+
- Lines covered: _run_async_with_new_loop() (20 lines)

Test results:
- 773+ passed, 8 skipped (no failures)
- Phase C target 75% achieved

Related:
- Phase C Week 1 (17 tests) + async fallback completion
- Closes coverage gap from Week 1 completion

Refs: phase_c_week1_completion_2025_12_08
```

---

### Step 5: 完了記録メモリ作成

**メモリファイル**: `.serena/memories/phase_c_coverage_75_completion_2025_12_08.md`

**記録内容**:
- カバレッジ達成 (74.15% → 75.0%+)
- 実装詳細 (async fallback test完成)
- Phase C全体完了宣言
- 次ステップ (Submodule更新、PR準備)

---

## タイムライン

| Step | 作業内容 | 工数 |
|------|---------|------|
| 1 | Async fallback test完成 | 1-2時間 |
| 2 | テスト実行と検証 | 30分 |
| 3 | 全テスト実行とカバレッジ測定 | 30分 |
| 4 | Git コミット | 15分 |
| 5 | 完了記録メモリ作成 | 30分 |
| **Total** | | **3-4時間** |

---

## 技術詳細

### _run_async_with_new_loop() メソッド構造

```python
def _run_async_with_new_loop(self, binary_content: BinaryContent) -> Any:
    """Run async inference with a new event loop."""
    if not self._agent:
        raise RuntimeError(f"Agent not initialized for model {self.model_id}")

    def run_with_new_loop() -> Any:
        new_loop = asyncio.new_event_loop()  # Line 161
        asyncio.set_event_loop(new_loop)     # Line 162
        try:
            if not self._agent:
                raise RuntimeError(f"Agent not initialized for model {self.model_id}")
            return new_loop.run_until_complete(self._agent.run([binary_content]))  # Line 167
        finally:
            new_loop.close()  # Line 169

    import concurrent.futures  # Line 171

    with concurrent.futures.ThreadPoolExecutor() as executor:  # Line 173
        future = executor.submit(run_with_new_loop)
        return future.result()
```

**カバー対象**: Lines 155-174 (20行)

---

## 成功基準

### 必須達成
- ✅ Async fallback test完成 (skip解除)
- ✅ 全テストパス (773+)
- ✅ カバレッジ ≥ 75%
- ✅ Phase C完了記録作成

### 品質基準
- ✅ 包括的docstrings維持
- ✅ 適切なmock戦略 (Level 1)
- ✅ 独立テスト (shared state なし)

---

## リスク軽減

### Risk 1: Event Loop Mock複雑性
**対策**: MagicMock使用、リアルイベントループ回避

### Risk 2: ThreadPoolExecutor Mock
**対策**: contextlib.ExitStack または patch context manager使用

### Risk 3: カバレッジ目標未達
**対策**: 20行カバーで+5-9%向上見込み（十分なマージン）

---

## 次ステップ (Phase C完了後)

1. **Submodule参照更新** (1時間)
   - `git add local_packages/image-annotator-lib`
   - `git commit -m "chore: Update image-annotator-lib with Phase C completion"`

2. **PR準備** (2-3時間)
   - CHANGELOG更新
   - Breaking changes確認
   - PR description作成

3. **LoRAIro統合テスト修正** (別タスク、2-4時間)
   - 7 failed tests修正
   - AttributeError対応

---

**計画策定日**: 2025-12-08
**実装開始**: 承認後即時
**Phase C完了見込**: 2025-12-08 (3-4時間後)
