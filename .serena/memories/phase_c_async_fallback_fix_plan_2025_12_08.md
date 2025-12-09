# Async Fallback Test 修正計画と実行結果 (2025-12-08)

**ブランチ**: feature/phase2-test-fixes (image-annotator-lib)
**期間**: 2025-12-08
**ステータス**: ✅ **修正完了**（コミット 531e289）

## 実行結果サマリ

### 完了した作業
- ✅ async fallback test修正（asyncio patch + submit side_effect）
- ✅ テスト成功: 774 passed, 0 failed
- ✅ Gitコミット: 531e289
- ✅ SimplifiedAgentWrapper coverage: 69.1% → 86%
- ❌ 全体カバレッジ: 74%（目標75%未達、-1%）

**カバレッジ測定方法**:
```bash
uv run coverage run --source=local_packages/image-annotator-lib/src/image_annotator_lib -m pytest local_packages/image-annotator-lib/tests/
uv run coverage report  # TOTAL 4858 statements, 1240 missing, 74%
```

**Note**: 74.15%（Phase C Week 1時点、coverage.json）と74%（531e289時点、coverage report）の差異は表示の丸め処理による（実質的には同水準）

## 問題と解決

### 問題
テスト失敗: `AssertionError: Expected 'new_event_loop' to be called once. Called 0 times.`

### デバッグプロセス

**Step 1: Mock検証**
```
DEBUG: wrapper._agent is mock_pydantic_ai_agent = True
DEBUG: run_sync.called = True, call_count = 2
DEBUG: new_event_loop() not called
```

**結論**: Mock setupは正常、async fallback経路が実行されていない

### 根本原因

**Cause 1: asyncio patchパスが不正**
```python
# ❌ Wrong
patch("asyncio.new_event_loop")  # グローバルpatch

# ✅ Correct  
patch("image_annotator_lib.core.simplified_agent_wrapper.asyncio.new_event_loop")
```

**Cause 2: ThreadPoolExecutor.submit()が関数を実行していない**
```python
# ❌ Wrong
mock_executor.submit.return_value = mock_future  # 関数未実行

# ✅ Correct
def submit_side_effect(func):
    result = func()  # 実際に実行
    future = MagicMock()
    future.result.return_value = result
    return future
mock_executor.submit.side_effect = submit_side_effect
```

## 修正内容

**ファイル**: `tests/unit/core/test_simplified_agent_wrapper.py`
**変更**: Lines 350-370

```python
# Correct asyncio patch path
with patch(
    "image_annotator_lib.core.simplified_agent_wrapper.asyncio.new_event_loop",
    return_value=mock_loop,
) as mock_new_loop:
    with patch(
        "image_annotator_lib.core.simplified_agent_wrapper.asyncio.set_event_loop"
    ) as mock_set_loop:
        with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
            # Execute submitted function
            def submit_side_effect(func):
                result = func()
                future = MagicMock()
                future.result.return_value = result
                return future
            
            mock_executor = MagicMock()
            mock_executor.submit.side_effect = submit_side_effect
```

## テスト結果

### 単一テスト
```bash
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py::TestSimplifiedWrapperInference::test_simplified_wrapper_run_inference_async_fallback -v
# => PASSED [100%]
```

### 全テスト
```bash
uv run pytest local_packages/image-annotator-lib/tests/ -v
# => 774 passed, 7 skipped, 0 failed
```

### カバレッジ
```bash
uv run coverage report --include="local_packages/image-annotator-lib/src/image_annotator_lib/core/simplified_agent_wrapper.py"
```

**出力**:
```
Name                                                                                          Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------------------------------------------------------
local_packages/image-annotator-lib/src/image_annotator_lib/core/simplified_agent_wrapper.py      97     14    86%   39-41, 77, 126, 141, 154, 159, 166, 188, 227-230
---------------------------------------------------------------------------------------------------------------------------
TOTAL                                                                                            97     14    86%
```

## カバレッジ分析

### 目標未達の理由
- SimplifiedAgentWrapper: 86%（高水準）
- 全体: 74%（目標75%より-1%）
- 未カバー14行: エラーハンドリング（Lines 39-41, 77, その他）

### 75%到達に必要な追加作業
- 約49行のカバレッジ追加が必要
- 低カバレッジモジュール:
  - api_model_discovery.py: 15%
  - classifier.py: 21%
  - model_factory.py: 47%

## 次タスク

### 完了済み
1. ✅ async fallback test修正
2. ✅ Gitコミット（531e289）
3. ✅ メモリ更新

### 未完了（別タスク）
1. ⏳ Submodule参照更新（LoRAIro本体）
2. ⏳ PR準備・作成
3. ⏳ カバレッジ75%達成（継続的改善タスク）

---

**完了日**: 2025-12-08
**コミット**: 531e289
**実装時間**: 約2時間

## 追記: 2025-12-09 復元作業

### 問題発生
- HEADは531e289を指しているが、ワーキングツリーが古い状態に戻っていた
- 4つの修正（skip削除、asyncio patch、submit_side_effect、assertion）が失われていた

### 復元作業
```bash
git checkout HEAD -- tests/unit/core/test_simplified_agent_wrapper.py
```

### 復元検証
- ✅ @pytest.mark.skip削除確認
- ✅ asyncio patchパス確認（module-level）
- ✅ submit_side_effect実装確認
- ✅ 厳密なassertion確認

### テスト結果
- ✅ async fallback test: PASSED
- ✅ 全774テスト: PASSED
- ✅ リグレッション: なし

**復元完了日**: 2025-12-09
**詳細**: async_fallback_test_restoration_2025_12_09.md
