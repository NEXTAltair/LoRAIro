# image-annotator-lib 開発教訓集

**作成日**: 2025-10-22
**目的**: プロジェクト開発で学んだ教訓とベストプラクティスを記録
**参照元**: docs/lessons-learned.md, .cursor/rules/lessons-learned.mdc

---

## 2025-07-01: Integration Test Design and PydanticAI Testing Patterns

### 問題の概要
Memory management integration testでテスト失敗が多発。主な問題：
1. 複雑すぎるモック設定
2. PydanticAIテストパターンの誤解
3. 実装の詳細に過度に依存したテスト設計

### 学んだ教訓

#### 1. PydanticAIテストのベストプラクティス
**正しいアプローチ:**
- `TestModel`または`FunctionModel`を使用してLLMコールをモック
- `Agent.override()`でAgentのモデルを置き換え
- `models.ALLOW_MODEL_REQUESTS=False`で実APIコールを防止

**間違ったアプローチ:**
- 内部のPydanticAI Agentを直接モック
- 複雑な`side_effect`でAsyncMockを設定
- Provider factoryの内部実装詳細をモック

#### 2. テスト設計の原則
**堅牢なテスト設計:**
```python
# 良い例：本質的な機能をテスト
def test_cache_functionality(self):
    cache_info = WebApiAgentCache.get_cache_info()
    assert cache_info["cache_size"] == 0
```

**脆弱なテスト設計:**
```python
# 悪い例：実装詳細に依存
def mock_agent_creation(model_name, api_model_id, api_key, config_data=None):
    # 複雑な内部状態シミュレーション
```

#### 3. 段階的テスト開発
**推奨アプローチ:**
1. 最初に単純で本質的な機能をテスト
2. 段階的に複雑さを追加
3. 実装詳細ではなく公開インターフェースをテスト

**事例:**
- `test_memory_management_simple.py`を作成
- 基本的なキャッシュ操作とメモリクリーンアップをテスト
- 複雑なE2Eテストは後回し

#### 4. モック設定のベストプラクティス
**設定不備の回避:**
```python
# 必要な設定項目を事前に確認
"memory_local_small": {
    "class": "ImprovedAesthetic",
    "model_path": "test/small/model",
    "base_model": "improved-aesthetic",  # 必須項目追加
    "device": "cpu",
    "estimated_size_gb": 0.5,
}
```

**クラス登録の確実な実行:**
```python
# conftest.pyでテスト用クラスマッピングを確実に設定
def _ensure_test_class_mapping(model_name: str, config: dict):
    # 実際のクラス名との対応を正確に設定
    if class_name == "OpenAIApiChatAnnotator":
        from image_annotator_lib.model_class.annotator_webapi.openai_api_chat import OpenRouterApiAnnotator
        registry[model_name] = OpenRouterApiAnnotator
```

#### 5. エラーパターンの分類と対策

**設定エラー:**
- 症状：`base_model が設定されていません`
- 対策：テスト設定でモデル固有の必須パラメータを確認

**モックエラー:**
- 症状：`object MagicMock can't be used in 'await' expression`
- 対策：PydanticAIの正しいテストパターンを使用

**クラス登録エラー:**
- 症状：`Model 'X' not found in class registry`
- 対策：テスト用のクラスマッピングを事前に設定

### 技術的な解決策

#### 1. テスト環境でのPydanticAI設定
```python
@pytest.fixture(autouse=True)
def setup_pydantic_ai_testing(self):
    # APIコールを無効化
    models.ALLOW_MODEL_REQUESTS = False
    yield
```

#### 2. 段階的モック戦略
```python
# Level 1: 基本的なキャッシュ機能テスト
def test_cache_basic_operations():
    # 内部実装に依存しないテスト
    
# Level 2: 設定とクラス登録テスト  
def test_model_configuration():
    # 設定が正しく読み込まれることを確認

# Level 3: E2Eテスト（慎重に設計）
def test_full_annotation_workflow():
    # TestModelを使用した実際のワークフローテスト
```

#### 3. 堅牢なテストfixtureパターン
```python
@pytest.fixture
def memory_test_configs(self, managed_config_registry):
    configs = {...}  # 必須パラメータを全て含む
    
    for model_name, config in configs.items():
        managed_config_registry.set(model_name, config)
        _ensure_test_class_mapping(model_name, config)  # 確実に登録
    
    return configs
```

### 今後の開発指針

1. **テストファーストではなく、理解ファースト**: 複雑なシステムでは、まず動作原理を理解してからテストを書く

2. **段階的複雑化**: 単純なテストから始めて、段階的に複雑さを追加

3. **公開インターフェースのテスト**: 実装詳細ではなく、公開されたAPIをテスト

4. **フレームワーク固有のベストプラクティスを尊重**: PydanticAIのようなフレームワークには推奨テストパターンがある

5. **エラードキュメント化**: 遭遇したエラーパターンと解決策を記録

### 参考リソース

- [PydanticAI Unit Testing Documentation](https://ai.pydantic.dev/unit-testing/)
- プロジェクト内の`test_memory_management_simple.py`（段階的テスト設計の例）
- `tests/integration/conftest.py`（テスト用クラス登録パターン）

**結論**: 複雑なシステムのintegration testでは「動作する最小版から始める」アプローチが重要。

---

## pytest-bdd: Scenario Outlineで日本語+<param>記法の既知問題

### 概要
- Scenario Outlineで日本語ステップと<param>(例: <cache_state>)を組み合わせると、pytest-bddが<param>部分を正しくパースできず、step定義がマッチしないことがある。

### 詳細
- 英語では正常動作するが、日本語やマルチバイト文字列では<param>の展開・マッチングが不安定。
- 公式issueや日本語コミュニティでも同様の報告多数。
- pytest-bddのバージョンアップで解消される可能性もあるが、現状は「日本語+<param>」は非推奨。

### 対応方針
- 今後この警告・エラーは既知の仕様制約として**無視**する。
- 必要なら英語に置き換える、または具体値で全列挙・正規表現stepで回避する。

---

## プロジェクト初期教訓（2023-10-27頃）

### ドキュメント管理
- **初期方針**: `memory-bank` ディレクトリ内にプロジェクトコンテキスト、進捗、決定ログを記録
- **決定ログ形式**: 日付、決定内容、理由、代替案、影響記録形式採用

### ドキュメント整理経緯

**統合計画（日付不明）**:
- リファクタリング後ドキュメント更新計画立案
- 既存構造把握、リファクタリング詳細確認、更新計画作成、実施、確認、完了ステップ定義

**削減計画（2025-04-18）**:
- ドキュメントファイル数多すぎ（11ファイル）フィードバック受け、約7ファイルへ削減計画立案
- 必須ドキュメント維持しつつ、解説・設計関連ドキュメントを統合、不要ファイル削除方針決定

**現状整理（2025-04-29～）**:
- 設定ドキュメント（V2: Updates）基盤
- `memory-bank` 内容を推奨メモリファイル（`docs/product_requirement_docs.md`, `docs/architecture.md`, `docs/technical.md`, `tasks/tasks_plan.md`, `tasks/active_context.md`, `.cursor/rules/lessons-learned.mdc`, `.cursor/rules/error-documentation.mdc`）へ移行・統合中

---

## 旧ライブラリ統合経緯

### 統合元
現状 `image-annotator-lib` は、旧ライブラリ `scorer_wrapper_lib` と `tagger_wrapper_lib` 統合版。

### 統合理由
- 機能的重複多く、特にモデル管理・コア基底クラス設計で共通化メリット大と判断
- API 統一で利用者が両機能をシームレスに扱えるようにすることも目的

### 主要変更点
1. **クラス階層最適化**: 以前個別モデルクラスで相当重複あったコードを、基底クラスに集約
2. **結果形式統一**: 異形式だった Tagger/Scorer 結果を統一フォーマット返却に変更
3. **メモリ管理改善**: より洗練されたモデルキャッシュ戦略実装
4. **エラーハンドリング強化**: より詳細・一貫したエラー報告導入

---

**更新日**: 2025-10-22  
**参照**: CLAUDE.md（開発ガイドライン）
