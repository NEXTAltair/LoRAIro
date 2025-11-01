# test_unified_error_handling 失敗記録（2025-10-24）

## ステータス

**未修正** - 今後修正予定

## 失敗内容

### テストファイル
`local_packages/image-annotator-lib/tests/integration/test_unified_provider_level_integration.py::TestUnifiedErrorHandling::test_unified_error_handling`

### エラー詳細

```python
ValueError: not enough values to unpack (expected 2, got 1)

During handling of the above exception, another exception occurred:
pydantic_ai.exceptions.UserError: Unknown model: openai-test-model
```

### エラー発生箇所

1. **PydanticAI infer_model()**: `model.split(':', maxsplit=1)` でプロバイダープレフィックスを期待
   - 期待: `"openai:gpt-4"`形式
   - 実際: `"openai-test-model"`（プレフィックスなし）

2. **呼び出しスタック**:
   ```
   test_unified_error_handling
   → openai_api_response.py:34 __enter__
   → pydantic_ai_factory.py:288 _setup_agent
   → pydantic_ai_factory.py:158 get_cached_agent
   → pydantic_ai_factory.py:134 create_agent
   → Agent.__init__
   → models.infer_model
   → ValueError/UserError
   ```

### ログ出力

```
2025-10-24 13:22:25.178 | WARNING  | image_annotator_lib.core.pydantic_ai_factory:_extract_provider_name - Unable to extract provider from api_model_id: 'openai-test-model', defaulting to 'unknown'
2025-10-24 13:22:25.179 | WARNING  | image_annotator_lib.core.pydantic_ai_factory:create_agent - Unknown provider 'unknown', skipping environment variable setup
2025-10-24 13:22:25.179 | ERROR    | image_annotator_lib.core.pydantic_ai_factory:create_agent - Agent creation failed: model=test-openai-model, api_id=openai-test-model, error_type=UserError, message=Unknown model: openai-test-model
```

## 問題の本質

### 根本原因
PydanticAI v1.2.1では、`Agent(model=api_model_id)`に渡すモデルIDに**プロバイダープレフィックス**（`openai:`, `anthropic:`, `google-gla:`など）が必須。

### テストコード問題点

**ファイル**: `test_unified_provider_level_integration.py`
**問題箇所**: テスト用モデル設定

```python
# 現在の設定（問題あり）
{
    "api_model_id": "openai-test-model",  # プレフィックスなし
}

# 必要な形式
{
    "api_model_id": "openai:gpt-4o-mini",  # プロバイダー:モデル名
}
```

### 影響範囲

- テスト: `test_unified_error_handling` のみ
- 実装: `pydantic_ai_factory.py:134` - `Agent(model=api_model_id, ...)`

## 修正方針（今後対応）

### Option A: テスト設定修正（簡単）
テストで使用するモデルIDにプレフィックスを追加:
```python
"api_model_id": "openai:gpt-4o-mini"  # or "openai:test-model"
```

### Option B: 実装修正（堅牢）
`pydantic_ai_factory.py`でプレフィックス自動補完:
```python
def create_agent(cls, model_name: str, api_model_id: str, api_key: str) -> Agent:
    # プロバイダープレフィックスが無い場合は自動補完
    if ":" not in api_model_id:
        provider_name = cls._extract_provider_name(api_model_id)
        if provider_name != "unknown":
            api_model_id = f"{provider_name}:{api_model_id}"
    
    agent = Agent(model=api_model_id, output_type=AnnotationSchema, system_prompt=BASE_PROMPT)
```

### Option C: バリデーション追加（防御的）
設定読み込み時にプレフィックスの有無を検証:
```python
def _validate_api_model_id(api_model_id: str) -> None:
    if ":" not in api_model_id:
        raise ValueError(f"api_model_id must include provider prefix (e.g., 'openai:gpt-4'): {api_model_id}")
```

## 推奨アプローチ

**Option A + Option B の組み合わせ**:
1. テスト設定を修正してプレフィックスを追加（即座対応）
2. 実装に自動補完ロジックを追加（後方互換性確保）

**理由**:
- テスト修正で即座に問題解決
- 実装修正で将来の同様問題を防止
- 既存の動作コードへの影響を最小化

## 関連情報

### PydanticAI 公式仕様
- モデル指定形式: `provider:model-name`
- 例: `openai:gpt-4`, `anthropic:claude-3-5-sonnet`, `google-gla:gemini-1.5-pro`
- ドキュメント: https://ai.pydantic.dev/models/

### 既存の正常動作例
```python
# AnthropicAPI統合テスト（正常動作）
{
    "api_model_id": "claude-3-5-sonnet",  # PydanticAI内部で "anthropic:" 補完
}

# GoogleAPI統合テスト（正常動作）
{
    "api_model_id": "gemini-pro",  # PydanticAI内部で "google-gla:" 補完
}
```

**注意**: 上記は`infer_model()`の推論機能によって動作しているが、PydanticAI v1.2.1以降は明示的プレフィックスが推奨されている（Deprecation警告あり）。

## 次のステップ

1. テストファイル `test_unified_provider_level_integration.py` を確認
2. モデル設定箇所を特定
3. Option A（テスト修正）を実施
4. 動作確認後、Option B（実装修正）を検討

**作成日**: 2025-10-24  
**ステータス**: 未修正・今後対応予定  
**関連Memory**: 
- `fixture_simplification_success_2025_10_24` - テスト環境修正履歴
- `test_unified_annotation_result_migration_2025_10_24` - UnifiedAnnotationResult移行記録
