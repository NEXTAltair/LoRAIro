# genai-tag-db-tools DB初期化依存の完全除去

## 変更日時
2025-12-27

## 対象ファイル
`tests/unit/test_app_services.py`

## 変更内容
全ての `TagSearchService` ユニットテストに `merged_reader=Mock()` を注入し、DB初期化への依存を完全に排除:

```python
from unittest.mock import Mock

# Before: DB初期化が発生する可能性あり
service = TagSearchService(searcher=searcher)

# After: merged_reader注入でDB初期化を完全回避
service = TagSearchService(searcher=searcher, merged_reader=Mock())
```

## 対象テスト
1. `test_tag_search_service_get_tag_formats` - merged_reader注入追加
2. `test_tag_search_service_get_tag_languages` - merged_reader注入追加
3. `test_tag_search_service_get_tag_types` - merged_reader注入追加
4. `test_tag_search_service_get_tag_types_none_format` - merged_reader注入追加
5. `test_tag_search_service_search_tags` - merged_reader注入追加、`get_default_reader` モック削除（不要になった）

## 設計原則
**ユニットテストはDB初期化なし、依存注入で完結**:
- `TagSearchService` と `TagStatisticsService` は両方とも `merged_reader` 注入可能な設計
- ユニットテストでは `merged_reader=Mock()` または `merged_reader=object()` を注入
- `_get_merged_reader()` が `get_default_reader()` を呼ぶことを防ぎ、DB初期化を完全に回避

**統合テスト（将来実装時）**:
- `@pytest.mark.requires_real_db` で実DBダウンロード
- CI環境では自動スキップ、ローカル環境でのみ実行

## テスト結果
全 215 テストが 7.53 秒で合格

## 関連記録
- `.serena/memories/genai_tag_db_tools_test_quality_fix_completion_2025_12_28` - 元のテスト品質対応
- `.serena/memories/genai_tag_db_tools_ci_workflow_update_2025_12_27` - CI環境変数追加
