# 531e289コミット内容復元作業 (2025-12-09)

**ブランチ**: feature/phase2-test-fixes (image-annotator-lib)
**期間**: 2025-12-09
**ステータス**: ✅ **復元完了**

## 問題

**発生状況**:
- HEADコミット: 531e289 (test: Fix async fallback test for SimplifiedAgentWrapper)
- ワーキングツリー: 古い状態に戻っている
- `git diff HEAD`で大量の差分検出

**失われた修正**:
1. `@pytest.mark.skip`削除（Line 286）
2. asyncio patchパス修正（module-level import対応）
3. `submit_side_effect`実装（ThreadPoolExecutor実行）
4. 厳密なassertion（`mock_new_loop.assert_called_once_with()`）

## 実施作業

### Step 1: ファイル復元
```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git checkout HEAD -- tests/unit/core/test_simplified_agent_wrapper.py
```

**結果**: working tree clean

### Step 2: 復元内容検証

**検証1: @pytest.mark.skip削除**
- ファイルのLine 286を確認
- `@pytest.mark.skip`が存在しないことを確認

**検証2: asyncio patchパス**
- Line 351を確認
- `image_annotator_lib.core.simplified_agent_wrapper.asyncio.new_event_loop`が存在することを確認

**検証3: submit_side_effect実装**
- Lines 359-365を確認
- `def submit_side_effect(func):`関数定義が存在することを確認
- `mock_executor.submit.side_effect = submit_side_effect`が存在することを確認

**検証4: 厳密なassertion**
- Line 380を確認
- `mock_new_loop.assert_called_once_with()`が存在することを確認

### Step 3: テスト実行

**単一テスト**:
```bash
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py::TestSimplifiedWrapperInference::test_simplified_wrapper_run_inference_async_fallback -v
# => PASSED [100%] (26.56s)
```

**全テスト**:
```bash
uv run pytest local_packages/image-annotator-lib/tests/ -v
# => 774 passed, 7 skipped, 0 failed (82.17s)
```

## 復元された修正内容

### 修正1: @pytest.mark.skip削除
```python
# Line 285-286
@pytest.mark.unit
# @pytest.mark.skip(reason="...") ← 削除
def test_simplified_wrapper_run_inference_async_fallback(...):
```

### 修正2: asyncio patchパス（module-level）
```python
# Lines 350-356
with patch(
    "image_annotator_lib.core.simplified_agent_wrapper.asyncio.new_event_loop",
    return_value=mock_loop,
) as mock_new_loop:
    with patch(
        "image_annotator_lib.core.simplified_agent_wrapper.asyncio.set_event_loop"
    ) as mock_set_loop:
```

**理由**: SimplifiedAgentWrapperモジュール内でインポート済みの`asyncio`に影響させるため

### 修正3: submit_side_effect実装
```python
# Lines 359-365
def submit_side_effect(func):
    """Execute the submitted function and return a mock future."""
    result = func()  # Actually execute the function
    future = MagicMock()
    future.result.return_value = result
    return future

mock_executor = MagicMock()
mock_executor.submit.side_effect = submit_side_effect
```

**理由**: ThreadPoolExecutor.submit()が実際に関数を実行し、async fallback経路をカバー

### 修正4: 厳密なassertion
```python
# Lines 379-389
# Assert: new_event_loop called
mock_new_loop.assert_called_once_with()

# Assert: set_event_loop called with new loop
mock_set_loop.assert_called_once_with(mock_loop)

# Assert: run_until_complete called
mock_loop.run_until_complete.assert_called_once()

# Assert: loop.close called
mock_loop.close.assert_called_once()

# Assert: ThreadPoolExecutor used
mock_executor_class.assert_called_once()
mock_executor.submit.assert_called_once()
```

**理由**: async fallback経路の完全な実行を保証

## 成果

### テスト結果
- ✅ async fallback test: PASSED
- ✅ 全774テスト: PASSED
- ✅ リグレッション: なし

### カバレッジ

**SimplifiedAgentWrapper**: 86%（97 statements, 14 missing）
```bash
uv run coverage report --include="local_packages/image-annotator-lib/src/image_annotator_lib/core/simplified_agent_wrapper.py"
# Stmts: 97, Miss: 14, Cover: 86%
# Missing: 39-41, 77, 126, 141, 154, 159, 166, 188, 227-230
```

**全体**: 74%（4858 statements, 1240 missing）
```bash
uv run coverage report
# TOTAL: 4858 statements, 1240 missing, 74%
```

**async fallback path**: 完全カバー（Lines 155-174）

## 技術的要点

### なぜmodule-level patchが必要か
```python
# simplified_agent_wrapper.py (Line 2)
import asyncio

# テスト内で正しくpatchする
patch("image_annotator_lib.core.simplified_agent_wrapper.asyncio.new_event_loop")
# ❌ patch("asyncio.new_event_loop")  # グローバルpatchでは効かない
```

### なぜsubmit()を実際に実行する必要があるか
```python
# _run_async_with_new_loop() (Lines 162-164)
with concurrent.futures.ThreadPoolExecutor() as executor:
    future = executor.submit(run_with_new_loop)  # この関数を実際に実行
    return future.result()

# テストではside_effectで実行
mock_executor.submit.side_effect = lambda func: func()  # 実行必須
```

## 次タスク

### 完了済み
1. ✅ 531e289コミット内容復元
2. ✅ テスト検証（774 passed）
3. ✅ メモリ更新

### 未完了
1. ⏳ Submodule参照更新（LoRAIro本体側）
2. ⏳ PR準備・作成

---

**完了日**: 2025-12-09
**作業時間**: 約10分
**次作業**: Submodule参照更新
