# Async Fallback Test 修正計画 (2025-12-08)

**ブランチ**: feature/phase2-test-fixes (image-annotator-lib)
**現状**: Phase C Week 1 コミット完了、async fallback test実装したが失敗
**目標**: async fallback testを修正し、カバレッジ75%達成

---

## 問題

### テスト失敗
- **テスト**: `test_simplified_wrapper_run_inference_async_fallback` (Line 286-387)
- **エラー**: `AssertionError: Expected 'new_event_loop' to be called once. Called 0 times.`
- **原因**: async fallback経路が実行されていない

### 期待動作 vs 実際の動作
**期待**:
1. `wrapper._run_agent_inference(binary_content)` を呼ぶ
2. `_run_agent_inference()` 内で `run_sync()` が RuntimeError を raise
3. RuntimeError のメッセージに "Event loop" が含まれる
4. `_run_async_with_new_loop()` が呼ばれる
5. `asyncio.new_event_loop()` が呼ばれる

**実際**:
- `new_event_loop()` が呼ばれていない = async fallback経路が実行されていない

---

## 修正計画

### Step 1: デバッグと原因特定

**デバッグコード追加** (テストコード Line 367の前後):
```python
# Debug: Verify mock setup
print(f"DEBUG: wrapper._agent is mock_pydantic_ai_agent = {wrapper._agent is mock_pydantic_ai_agent}")
print(f"DEBUG: wrapper._agent.run_sync.side_effect = {wrapper._agent.run_sync.side_effect}")

# Act
result = wrapper._run_agent_inference(binary_content)

# Debug: Verify run_sync was called
print(f"DEBUG: run_sync.called = {mock_pydantic_ai_agent.run_sync.called}")
```

**実行**:
```bash
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py::TestSimplifiedWrapperInference::test_simplified_wrapper_run_inference_async_fallback -v -s
```

### Step 2: テストコード修正

**Case A**: patchが動作していない場合
- mock設定の確認を追加
- `assert wrapper._agent is mock_pydantic_ai_agent`

**Case B**: run_sync()が呼ばれていない場合
- テストコードのロジック見直し

**Case C**: RuntimeErrorが raise されていない場合
- side_effectの設定見直し
- `patch.object()` の使用を検討

### Step 3: テスト実行と検証

```bash
# 単一テスト
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py::TestSimplifiedWrapperInference::test_simplified_wrapper_run_inference_async_fallback -v

# 全テスト
uv run pytest local_packages/image-annotator-lib/tests/ -v

# カバレッジ測定
uv run coverage run -m pytest local_packages/image-annotator-lib/tests/
uv run coverage report --include="local_packages/image-annotator-lib/src/image_annotator_lib/*"
```

### Step 4: Git コミット

```bash
git add tests/unit/core/test_simplified_agent_wrapper.py
git commit -m "test: Fix async fallback test and achieve Phase C coverage 75%"
```

### Step 5: 完了記録メモリ更新

**メモリファイル**: `.serena/memories/phase_c_coverage_75_completion_2025_12_08.md`

---

## 成功基準

- ✅ async fallback testがパスする
- ✅ カバレッジ ≥ 75%
- ✅ 全773+テストパス
- ✅ Phase C完了記録作成

---

## タイムライン

| ステップ | 工数 |
|---------|------|
| デバッグと原因特定 | 30-60分 |
| テストコード修正 | 30-60分 |
| テスト実行と検証 | 30分 |
| Git コミット | 15分 |
| 完了記録メモリ更新 | 30分 |
| **Total** | **2.5-3.5時間** |

---

**計画策定日**: 2025-12-08
**実装開始**: デバッグ完了後
**Phase C完了見込**: 2025-12-08 (2.5-3.5時間後)

**詳細計画**: `/home/vscode/.claude/plans/happy-foraging-zephyr.md`
