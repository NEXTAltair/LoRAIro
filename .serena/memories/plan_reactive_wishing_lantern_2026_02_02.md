# Plan: reactive-wishing-lantern

**Created**: 2026-02-02 06:51:44
**Source**: plan_mode
**Original File**: reactive-wishing-lantern.md
**Status**: planning

---

# Loguru %s スタイルフォーマット → {} スタイルへの一括修正

## 概要
Loguruは `{}` スタイル（Python `str.format()`）を使用するが、コードベース内に70箇所の `%s`/`%d` スタイル（標準logging互換）が残存。これらは実行時にフォーマットされず、`%s` がリテラル出力される。

## 対象範囲

### src/lorairo/ (25箇所)
| ファイル | 箇所数 |
|---|---|
| [services/favorite_filters_service.py](src/lorairo/services/favorite_filters_service.py) | 13 |
| [services/configuration_service.py](src/lorairo/services/configuration_service.py) | 7 |
| [storage/file_system.py](src/lorairo/storage/file_system.py) | 4 |
| [services/tag_management_service.py](src/lorairo/services/tag_management_service.py) | 5 |
| [gui/widgets/filter_search_panel.py](src/lorairo/gui/widgets/filter_search_panel.py) | 6 |

### local_packages/genai-tag-db-tools/ (45箇所)
| ファイル | 箇所数 |
|---|---|
| [gui/services/tag_statistics_service.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/tag_statistics_service.py) | 7 |
| [gui/windows/main_window.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/windows/main_window.py) | 7 |
| [gui/services/db_initialization.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/db_initialization.py) | 5 |
| [io/hf_downloader.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/io/hf_downloader.py) | 5 |
| [gui/services/tag_search_service.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/tag_search_service.py) | 4 |
| [gui/services/worker_service.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/worker_service.py) | 4 |
| [gui/services/tag_register_service.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/tag_register_service.py) | 3 |
| [gui/widgets/tag_search.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/widgets/tag_search.py) | 2 |
| [db/runtime.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/runtime.py) | 1 |
| [gui/services/gui_service_base.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/gui_service_base.py) | 1 |

## 変換ルール

```python
# Before (printf-style)
logger.info("Found %d items in %s", count, path)
logger.error("Error: %s", e, exc_info=True)

# After ({} style)
logger.info("Found {} items in {}", count, path)
logger.error("Error: {}", e, exc_info=True)
```

- `%s` → `{}`
- `%d` → `{}`
- `exc_info=True` はキーワード引数なのでそのまま維持

## 実装手順

### Step 1: src/lorairo/ の修正 (25箇所)
ファイル単位で順次修正:
1. `services/favorite_filters_service.py` (13箇所)
2. `services/configuration_service.py` (7箇所)
3. `gui/widgets/filter_search_panel.py` (6箇所)
4. `services/tag_management_service.py` (5箇所)
5. `storage/file_system.py` (4箇所)

### Step 2: local_packages/genai-tag-db-tools/ の修正 (45箇所)
ファイル単位で順次修正:
1. `gui/services/tag_statistics_service.py` (7箇所)
2. `gui/windows/main_window.py` (7箇所)
3. `gui/services/db_initialization.py` (5箇所)
4. `io/hf_downloader.py` (5箇所)
5. `gui/services/tag_search_service.py` (4箇所)
6. `gui/services/worker_service.py` (4箇所)
7. `gui/services/tag_register_service.py` (3箇所)
8. `gui/widgets/tag_search.py` (2箇所)
9. `db/runtime.py` (1箇所)
10. `gui/services/gui_service_base.py` (1箇所)

### Step 3: 検証
1. `uv run ruff check src/ local_packages/` - リント確認
2. `uv run mypy -p lorairo` - 型チェック
3. `uv run pytest -m unit` - ユニットテスト実行
4. 最終grep確認: コードベースに `%s` スタイルlogger呼び出しが残っていないことを確認

## リスク評価
- **リスク: 低** - 文字列フォーマットの変更のみで、ロジック変更なし
- **ロールバック**: git revert で即時復元可能
- **注意点**: `exc_info=True` 等のキーワード引数はそのまま維持すること
