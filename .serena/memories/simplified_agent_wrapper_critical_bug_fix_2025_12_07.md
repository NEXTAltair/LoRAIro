# SimplifiedAgentWrapper Critical Bug Fix Implementation (2025-12-07)

## 概要
Phase C Week 1-2で発見された3つの重大バグを修正。特に**run_inference()が推論を一切呼び出していない**致命的実装エラーを解決。

## 修正したバグ

### Bug 1: run_inference()実装エラー（CRITICAL）
**症状**: 常に空タグを返す（本番環境で実質動作不能）

**原因**: 
```python
# 誤った実装（lines 195-213 旧版）
def run_inference(self, image: Image.Image) -> AnnotationResult:
    tags = self._generate_tags(image)  # PIL Image渡し（dictを期待）
    formatted_output = self._format_output(image, tags)
    return AnnotationResult(tags=tags, ...)
```

**修正内容**（lines 195-238 新版）:
```python
def run_inference(self, image: Image.Image) -> AnnotationResult:
    # Step 1: Preprocess image to BinaryContent
    processed = self._preprocess_images([image])
    
    # Step 2: Run inference with agent
    raw_outputs = self._run_inference(processed)
    
    # Step 3: Format agent results
    formatted_outputs = self._format_predictions(raw_outputs)
    
    # Step 4: Extract tags from formatted output
    formatted_output = formatted_outputs[0] if formatted_outputs else {}
    tags = self._generate_tags(formatted_output)
    
    return AnnotationResult(tags=tags, formatted_output=formatted_output, error=None)
```

**参照**: BaseAnnotator.predict() lines 146-176の4ステップパイプラインパターン

---

### Bug 2: テスト設定レジストリ不足（HIGH）

**症状**: ValueError: "Model 'test/...' not found in config_registry"

**原因**: SimplifiedAgentWrapper.__init__() → BaseAnnotator.__init__() → _load_config_from_registry()の連鎖で設定未登録エラー

**修正対象テスト**:
1. `test_simplified_wrapper_format_output_no_tags` (line 485)
2. `test_simplified_wrapper_run_inference_success` (line 542)

**修正内容**:
```python
def test_xxx(self, mock_pydantic_ai_agent, managed_config_registry):  # ← fixture追加
    # Register config BEFORE wrapper initialization
    managed_config_registry.set(
        "test/model-xxx",
        {
            "class": "SimplifiedAgentWrapper",
            "model_name_on_provider": "test/model-xxx",
            "api_model_id": "test/model-xxx",
            "api_key": "test_key",
        },
    )
    
    wrapper = SimplifiedAgentWrapper(model_id="test/model-xxx")
```

---

### Bug 3: TypedDict assertionエラー（実装時発覚）

**症状**: `TypeError: TypedDict does not support instance and class checks`

**原因**: `isinstance(result, AnnotationResult)` でTypedDictをチェック

**修正内容**:
```python
# 誤り
assert isinstance(result, AnnotationResult), "AnnotationResult型"

# 修正
assert isinstance(result, dict), "AnnotationResult型はdict"
assert "tags" in result, "tagsキー存在"
assert "formatted_output" in result, "formatted_outputキー存在"
assert "error" in result, "errorキー存在"
```

---

## 修正ファイル

### ソースコード
**local_packages/image-annotator-lib/src/image_annotator_lib/core/simplified_agent_wrapper.py**
- Lines 195-238: run_inference()メソッド完全書き換え

### テストコード
**local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py**
- Lines 485-535: test_simplified_wrapper_format_output_no_tags
  - managed_config_registry追加
  - 設定登録処理追加
  
- Lines 542-611: test_simplified_wrapper_run_inference_success
  - managed_config_registry追加
  - 設定登録処理追加
  - `_generate_tags()`モック削除（実パイプラインテスト）
  - TypedDict assertion修正
  - 期待タグ値を`["mock_tag_1", "mock_tag_2", "mock_tag_3"]`に変更

---

## テスト結果

### SimplifiedAgentWrapperテスト
- ✅ 7 passed
- ⏭️ 1 skipped (async fallback - ユーザー判断で保留)
- ❌ 0 failed

### 全体テストスイート
- ✅ **773 passed**
- ⏭️ 8 skipped
- ❌ 0 failed
- ⚠️ 5 warnings (既存)

### カバレッジ
- **SimplifiedAgentWrapper**: 69% (67/97 lines)
  - 未カバー: 主に async fallback (lines 148-175, 27行)
  - 目標範囲: 68-72% → **達成**
  
- **プロジェクト全体**: 74% (3,602/4,858 lines)
  - 75%目標に対し-1%（許容範囲）

---

## 技術的知見

### 1. SimplifiedAgentWrapperの設計問題
- **名ばかり**（ユーザー指摘）: PydanticAIをBaseAnnotator APIに強制適合させる薄いラッパー
- 実装の複雑さは変わらず、依存関係も同等
- 真の簡素化ではなく互換性レイヤー

### 2. BaseAnnotatorパイプライン必須
- すべての推論メソッドは4ステップ必須:
  1. `_preprocess_images([image])`
  2. `_run_inference(processed)`
  3. `_format_predictions(raw_outputs)`
  4. `_generate_tags(formatted_output)`

### 3. managed_config_registryパターン
- BaseAnnotator継承クラスの初期化前に必ず設定登録
- fixture引数追加 + `.set()` 呼び出し
- 参照: conftest.py lines 118-166

### 4. TypedDict型チェック
- `isinstance(obj, TypedDict)`不可（Python仕様）
- 代替: `isinstance(obj, dict)` + キー存在確認
- AnnotationResult, UnifiedAnnotationResult等に適用

---

## 残存課題

### Async Fallback Test（MEDIUM優先度）
- **ステータス**: SKIPPED (line 299)
- **理由**: モック設定複雑、イベントループ競合リスク
- **影響**: 27行未カバー（async fallback経路）
- **判断**: ユーザー承認済み保留（将来タスク）

### Overall Coverage 74%
- 75%目標に1%不足
- SimplifiedAgentWrapperバグ修正では到達困難
- 他モジュール（openai_api_chat, simple_config等）の追加テスト必要

---

## 検証コマンド

```bash
# SimplifiedAgentWrapperテスト
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py -v

# カバレッジ測定
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_simplified_agent_wrapper.py \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/core \
  --cov-report=term-missing:skip-covered

# 全体テスト
uv run pytest local_packages/image-annotator-lib/tests/ --tb=short
```

---

## 実装時間
- **計画**: 38分（6ステップ）
- **実績**: 約40分（TypedDict修正含む）

## 成功基準達成状況
✅ Bug 1修正: run_inference()完全パイプライン  
✅ Bug 2修正: テスト設定レジストリ追加  
✅ Bug 3修正: TypedDict assertion対応  
✅ テスト全合格: 773 passed, 0 failed  
✅ カバレッジ目標: 69% (68-72%範囲内)  
✅ リグレッションなし: 既存773テスト全通過  

---

## 次フェーズへの引き継ぎ

Phase C継続時の優先タスク:
1. openai_api_chat.py カバレッジ向上（17% → 70%+）
2. simple_config.py カバレッジ向上（35% → 85%+）
3. simplified_agent_factory.py カバレッジ向上（31% → 85%+）

これらで全体75%到達可能性高。
