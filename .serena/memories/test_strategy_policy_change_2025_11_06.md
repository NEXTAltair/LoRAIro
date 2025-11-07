# テスト戦略方針変更 (2025-11-06)

## 方針変更内容

### 旧方針（廃止）: ハイブリッド戦略
- 統合テストに `@pytest.mark.fast_integration` と `@pytest.mark.real_api` を混在
- 統合テストで実APIテストも含める
- オプションで実API検証を統合テストで実施

### 新方針（採用）: 役割の明確な分離

#### 統合テスト (`tests/integration/`)
- **目的**: ライブラリ間の連携テスト
- **実装**: モックのみ使用
- **マーカー**: `@pytest.mark.integration` + `@pytest.mark.fast_integration`
- **APIリクエスト**: 送らない
- **実行環境**: CI/CD で常時実行可能
- **実行時間**: 数秒～数十秒

#### E2Eテスト (`tests/bdd/` - Pytest BDD)
- **目的**: 実際の動作確認
- **実装**: 実API使用
- **マーカー**: `@pytest.mark.bdd`
- **APIリクエスト**: 実際に送信
- **実行環境**: APIキーがある環境のみ
- **実行時間**: 数分～数十分

## 変更理由

1. **責任の明確化**: 統合テストとE2Eテストの役割を明確に分離
2. **CI/CD効率化**: 統合テストはAPIキー不要で高速実行
3. **保守性向上**: テストの目的が明確で理解しやすい
4. **実API検証の集約**: E2EテストでBDDシナリオとして体系的に管理

## 影響範囲

### 既存テストの方針

**廃止するパターン**:
```python
@pytest.mark.integration
@pytest.mark.real_api
@pytest.mark.skipif(not api_key_available(), reason="API key required")
def test_real_api_call():
    # 実API呼び出し
    ...
```

**統合テストの標準パターン**:
```python
@pytest.mark.integration
@pytest.mark.fast_integration
def test_library_integration():
    # モックのみ使用
    with patch.object(ProviderManager, "_run_agent_safely") as mock:
        mock.return_value = mock_result
        # テスト実行
```

**E2Eテストの標準パターン**:
```python
# tests/bdd/features/annotation.feature
Scenario: OpenAI APIで画像アノテーション
  Given OpenAI APIキーが設定されている
  When "gpt-4o"モデルで画像をアノテーションする
  Then タグと説明文が返される

# tests/bdd/step_defs/test_annotation.py
@given("OpenAI APIキーが設定されている")
def openai_api_key_configured():
    # 実環境確認
    ...

@when('"gpt-4o"モデルで画像をアノテーションする')
def annotate_with_gpt4o(context):
    # 実API呼び出し
    ...
```

## 実装ガイドライン

### 統合テスト実装時

**必須**:
- `@pytest.mark.integration` + `@pytest.mark.fast_integration`
- すべての外部API呼び出しをモック
- `_run_agent_safely`, Agent実行などをモック
- APIキー不要で実行可能

**禁止**:
- 実APIリクエスト
- `@pytest.mark.real_api` マーカー
- `skipif(not api_key_available())` 条件

### E2Eテスト実装時

**必須**:
- `@pytest.mark.bdd`
- Gherkin シナリオ記述 (`.feature` ファイル)
- 実API呼び出し
- APIキー確認とスキップ処理

**推奨**:
- ユーザー視点のシナリオ
- 複数コンポーネントにまたがるフロー
- 実際の使用ケースを反映

## 既存テストの対応

### test_provider_manager_integration.py

**確認済み**:
- `test_provider_instance_sharing_real_api` - `@pytest.mark.real_api` 使用

**対応方針**:
- このテストは削除または E2E テストに移行
- 統合テストには real_api マーカーを使用しない

### 今後の実装

**test_pydantic_ai_factory_integration.py**:
- モックのみ使用
- Agent キャッシュロジックの検証
- Factory 動作の検証

**test_cross_provider_integration.py**:
- モックのみ使用
- マルチプロバイダー切り替えロジックの検証
- プロバイダー間の一貫性検証

## 参考: RFC 005との関係

**RFC 005 (統合テスト実装計画)** では3層ハイブリッド戦略を採用していたが、本方針変更により以下に簡素化:

- **統合テスト**: モックのみ（高速・CI対応）
- **E2Eテスト**: 実API（BDD・ユーザーシナリオ）

RFC 005の「real_api」テストは E2E テストに集約。

## まとめ

**明確な分離**:
- 統合テスト = ライブラリ連携 + モック
- E2Eテスト = 実動作確認 + 実API + BDD

**利点**:
- CI/CD で統合テストが常時実行可能
- E2E テストは BDD シナリオで体系的管理
- テスト目的が明確で保守しやすい

---

**記録日**: 2025-11-06  
**適用開始**: 即時  
**影響**: 今後のすべての統合テスト・E2Eテスト実装