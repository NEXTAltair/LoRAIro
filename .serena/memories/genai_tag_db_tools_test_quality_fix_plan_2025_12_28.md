# genai-tag-db-tools テスト品質問題修正計画

**作成日**: 2025-12-28  
**ブランチ**: `refactor/db-tools-hf`  
**状態**: Planning Phase完了  
**優先度**: High  

## 背景

テスト失敗30件を修正した際に、以下の品質問題を導入：

### 指摘された5つの品質問題

#### Priority: High
1. **H1**: autouse fixtureによる強制DB初期化
   - 全テストで `runtime.init_user_db()` を強制実行
   - DB未初期化エラーや初期化順序の不具合を検知不能
   - 実運用の不具合を隠す「テストが通るための前提」を作成

2. **H2**: runtimeグローバル状態の不適切な操作
   - `reset_runtime` が内部グローバル(`_engine`, `_SessionLocal`等)を直接操作
   - `engine.dispose()` 未実施、DB接続リーク
   - テスト間の干渉リスク

#### Priority: Medium
3. **M1**: `test_tag_search_service_emits_error_on_exception`
   - エラー発火を検証せず、空結果を返すのみ
   - テスト名と内容が不一致

4. **M2**: `test_tag_statistics_service_emits_error_on_exception`
   - 例外発火や`error_occurred`シグナル発火を検証せず
   - フォールバック結果の構造のみ確認

#### Priority: Low
5. **L1**: 統計プレゼンターのチャート値検証不足
   - 値の検証をやめ、系列名の存在のみ確認
   - 値の崩れを検知できない

## 修正方針: マーカーベース条件付きFixture適用

### アーキテクチャ設計

```python
# conftest.py - マーカーベース条件付きfixture
@pytest.fixture(autouse=True, scope="function")
def reset_runtime_for_integration(request, tmp_path):
    """統合テストのみDB状態をリセット（公開API使用）"""
    from genai_tag_db_tools.db import runtime
    
    # マーカーチェック
    markers = [m.name for m in request.node.iter_markers()]
    is_integration = "db_integration" in markers
    
    if not is_integration:
        # ユニットテストはスキップ（DB未初期化エラーを検知可能）
        yield
        return
    
    # 統合テストのみDB初期化
    user_db_dir = tmp_path / "user_db"
    user_db_dir.mkdir()
    runtime.init_user_db(user_db_dir)
    
    yield
    
    # 公開APIで適切にクリーンアップ（engine.dispose()確実実行）
    runtime.close_all()
```

## 実装計画

### フェーズ1: Fixture基盤の再構築（1-2時間）

**Task 1-1**: `reset_runtime` autouse fixtureの修正
- マーカーベース条件付き適用に変更
- `runtime.close_all()` 公開API使用
- 内部グローバル直接操作を削除

**Task 1-2**: pytest.iniにマーカー定義
```ini
markers =
    db_tools: genai-tag-db-tools specific tests
    db_integration: Tests requiring database initialization
```

### フェーズ2: テスト分類とマーカー付与（2-3時間）

**統合テスト判定基準**:
- `runtime`や`ensure_db`を経由する処理
- DBファイルI/Oが発生する処理
- `get_default_reader()`の暗黙依存によりDB未初期化エラーが発生
- 複数レイヤー（service→db/runtime→reader）を跨ぐ処理

**対象テスト（推定5-8件）**:
- `test_db_initialization_service.py` の統合系テスト
- `test_app_services.py` の一部（DB依存）

**Task 2-1**: 統合テストに `@pytest.mark.db_integration` 付与

**Task 2-2**: ユニットテストのモック注入強化
```python
@pytest.mark.db_tools
def test_service_logic_only(monkeypatch):
    """サービスロジックのみをテスト（DB不要）"""
    mock_reader = Mock()
    service = MyService(reader=mock_reader)  # モック注入
    
    # ロジック検証
    result = service.some_method()
    assert result == expected_value
```

### フェーズ3: 5つの品質問題の個別修正（1-2時間）

**Task 3-1**: H1対応 - autouse fixture強制DB初期化
- フェーズ1で解決（マーカーベース条件付き適用）

**Task 3-2**: H2対応 - runtime.close_all()使用
- フェーズ1で解決（公開API使用）

**Task 3-3**: M1対応 - test_tag_search_service_emits_error_on_exception
```python
# 修正後: エラー発火とシグナル発火の両方を検証
@pytest.mark.db_tools
def test_tag_search_service_emits_error_on_exception(qtbot, monkeypatch):
    searcher = DummySearcher()
    service = TagSearchService(searcher=searcher, merged_reader=Mock())
    
    # モックでエラーを発生させる
    monkeypatch.setattr(
        "genai_tag_db_tools.core_api.search_tags",
        Mock(side_effect=RuntimeError("Test error"))
    )
    
    error_signals = []
    service.error_occurred.connect(lambda msg: error_signals.append(msg))
    
    # 例外とシグナルの両方を検証
    with pytest.raises(RuntimeError, match="Test error"):
        service.search_tags("test")
    
    assert len(error_signals) == 1
    assert "Test error" in error_signals[0]
```

**Task 3-4**: M2対応 - test_tag_statistics_service_emits_error_on_exception
- 実装確認後、適切なエラーハンドリング検証を追加

**Task 3-5**: L1対応 - 統計プレゼンターチャート値検証
```python
# 修正後: 値も検証
assert len(result.series) == 2
assert result.series[0].value > 0  # 値が正しいことを確認
```

### フェーズ4: 統合テストと検証（30分）

**Task 4-1**: テスト実行と確認
```bash
# ユニットテストのみ実行（高速）
uv run pytest local_packages/genai-tag-db-tools/tests/unit/ -v

# 統合テストのみ実行
uv run pytest local_packages/genai-tag-db-tools/tests/ -m db_integration -v

# 全テスト実行
uv run pytest local_packages/genai-tag-db-tools/tests/ -v
```

**Task 4-2**: カバレッジ確認
```bash
uv run pytest --cov=local_packages/genai-tag-db-tools/src --cov-report=term-missing
```

## テスト戦略パターン

### ユニットテストパターン

**原則**:
- DB初期化なし
- モック注入による依存解決
- 高速実行（< 100ms/test）

**実装パターン**:
```python
@pytest.mark.db_tools
def test_service_logic_only():
    """サービスロジックのみをテスト（DB不要）"""
    mock_reader = Mock()
    service = MyService(reader=mock_reader)
    
    result = service.some_method()
    assert result == expected_value
```

### 統合テストパターン

**原則**:
- `@pytest.mark.db_integration` マーカー必須
- runtime.init_user_db() による DB初期化（autouse fixtureで自動）
- 複数コンポーネント連携を検証

**実装パターン**:
```python
@pytest.mark.db_tools
@pytest.mark.db_integration
def test_db_integration_flow():
    """DB統合フロー検証（runtime自動初期化）"""
    # autouse fixtureにより自動的にDB初期化済み
    service = MyService()  # get_default_reader()を使用
    
    result = service.complex_operation()
    assert result.success
```

## リスクと対策

### 高リスク

**R1: マーカー付与漏れ**
- **対策**: 統合テスト判定基準のチェックリスト作成
- **検証**: `pytest -m db_integration` で意図したテストのみ実行

**R2: テスト実行時間増加**
- **対策**: ユニットテストはDB初期化をスキップして高速化
- **目標**: 全テスト実行時間 < 20秒（現状: 15.48秒）

### 中リスク

**R3: 既存テストの動作変更**
- **対策**: 段階的移行（フェーズごとにテスト実行）
- **検証**: 各フェーズ完了後に全テスト実行

## 成功基準

1. **全テスト合格**: 215件すべて成功
2. **品質問題解決**: 5つの問題すべて修正完了
3. **カバレッジ維持**: 75%以上
4. **テスト実行時間**: < 20秒
5. **コード品質**: Ruff lint/format全通過

## 次ステップ

1. `/implement` コマンドで実装フェーズ開始
2. フェーズ1から順次実装
3. 各フェーズ完了後にテスト実行・確認
4. 全完了後にメモリ更新

## 参照ドキュメント

- `.serena/memories/test_strategy_policy_change_2025_11_06` - テスト戦略方針
- `.serena/memories/genai_tag_db_tools_test_refactoring_plan_2025_12_28` - 元の修正計画
- `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/runtime.py` - runtime公開API
- `local_packages/genai-tag-db-tools/tests/conftest.py` - pytest設定
