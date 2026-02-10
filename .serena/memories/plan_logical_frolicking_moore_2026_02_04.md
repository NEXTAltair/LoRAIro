# Plan: logical-frolicking-moore

**Created**: 2026-02-04 11:13:24
**Source**: plan_mode
**Original File**: logical-frolicking-moore.md
**Status**: planning

---

# Fix: type_name_id / type_id 混同バグ（修正版）

## 問題

`TagReader.get_type_id()` が `type_name_id`（`TAG_TYPE_NAME.type_name_id`）を返している一方で、
呼び出し側が `type_id`（`TAG_TYPE_FORMAT_MAPPING.type_id`）として扱っている。

その結果、`(format_id, type_name_id)` に対して複数の `type_id` が生成され、
`get_unknown_type_tag_ids()` の `.one_or_none()` が `MultipleResultsFound` になる。

## 修正方針（重要）

1. `type_name_id` 取得と `format` 固有 `type_id` 解決を明確に分離する。
2. `type_id=0` は `unknown` 専用とし、通常タイプへ流用しない。
3. `(format_id, type_name_id)` 重複を作らないガードを追加する。
4. 既存破損データは全フォーマット対象で修復する。

## 修正対象ファイル

すべて `local_packages/genai-tag-db-tools/` 内:

| ファイル | 変更内容 |
|---------|---------|
| `src/genai_tag_db_tools/db/repository.py` | `get_type_name_id` / `get_type_id_for_format` 追加、重複防止ガード、クリーンアップ実装 |
| `src/genai_tag_db_tools/services/tag_register.py` | `_resolve_type_id()` を2段階解決へ修正 |
| `src/genai_tag_db_tools/gui/services/tag_register_service.py` | legacyフォールバックの `type_id` 解決を format-aware 化 |
| `src/genai_tag_db_tools/db/runtime.py` | 初期化時クリーンアップを全formatへ拡張 |
| `tests/unit/test_tag_register_service.py` | モック・アサーション更新、欠落ケース追加 |
| `tests/gui/unit/test_gui_tag_register_service.py` | DummyReader更新 |
| `tests/unit/test_tag_repository.py` | 重複修復・再発防止の回帰テスト追加 |

## 実装ステップ

### Step 1: Reader API を明確化
**File**: `repository.py` / `MergedTagReader`

- `get_type_id()` は廃止し、`get_type_name_id(type_name)` に改名。
- 新規 `get_type_id_for_format(type_name, format_id)` を追加し、
  `TAG_TYPE_NAME` と `TAG_TYPE_FORMAT_MAPPING` を join して `type_id` を返す。
- 互換性のため、必要なら一時的に `get_type_id()` を deprecated alias として残す。

### Step 2: _resolve_type_id() を2段階解決へ修正
**File**: `services/tag_register.py`

- 解決手順を以下へ変更:
  1) `type_name_id = get_type_name_id(type_name)`（なければ作成）
  2) `type_id = get_type_id_for_format(type_name, fmt_id)`
  3) `type_id` が未解決なら新規マッピング作成
- 新規作成時ルール:
  - `type_name == "unknown"` のみ `type_id=0`
  - それ以外は `get_next_type_id(fmt_id)` を使用（0は使わない）

### Step 3: GUI fallback パス修正
**File**: `gui/services/tag_register_service.py`

- `register_or_update_tag()` の legacy 分岐で、
  `get_type_id(type_name)` ではなく `get_type_id_for_format(type_name, fmt_id)` を使用。
- 未解決時は core service と同じルールでマッピング作成へ委譲。

### Step 4: 再発防止ガード追加
**File**: `repository.py` (`create_type_format_mapping_if_not_exists`)

- 既存チェックを2系統にする:
  - `(format_id, type_id)` 既存
  - `(format_id, type_name_id)` 既存
- 後者が存在する場合は重複作成せず既存 `type_id` を返す。
- 必要に応じて戻り値を `None` ではなく `resolved_type_id` に変更。

### Step 5: 重複クリーンアップ実装（安全版）
**File**: `repository.py`

- `cleanup_duplicate_type_mappings(format_id)` を実装。
- `(format_id, type_name_id)` ごとに重複を検出し、代表 `type_id` を選ぶ:
  - `unknown` は `type_id=0` を優先
  - それ以外は `TAG_STATUS` 参照中の `type_id` を優先、なければ最小非0
- `TAG_STATUS` を代表 `type_id` に更新してから不要行を削除。

### Step 6: 起動時修復の適用範囲を拡大
**File**: `db/runtime.py` (`_initialize_default_user_mappings`)

- 単一 `format_id` ではなく、ユーザーDB内の全 `format_id` に対して
  `cleanup_duplicate_type_mappings()` を実行する。

### Step 7: テスト更新

- `DummyReader/DummyRepo`: `get_type_id` → `get_type_name_id` + `get_type_id_for_format` へ更新。
- 追加テスト:
  - `type_name` は存在するが `format` マッピング未作成のケース
  - `unknown` 以外が `type_id=0` に落ちないこと
  - `(format_id, type_name_id)` 重複が再作成されないこと
  - クリーンアップ後に `TAG_STATUS` 参照整合性が維持されること

## 検証方法

```bash
# 単体テスト（重点）
uv run pytest local_packages/genai-tag-db-tools/tests/unit/test_tag_register_service.py -v
uv run pytest local_packages/genai-tag-db-tools/tests/unit/test_tag_repository.py -v
uv run pytest local_packages/genai-tag-db-tools/tests/gui/unit/test_gui_tag_register_service.py -v

# 全テスト
uv run pytest local_packages/genai-tag-db-tools/tests/ -v

# LoRAIro 側の回帰
uv run pytest tests/unit/services/test_tag_management_service.py -v
uv run pytest tests/unit/database/test_db_repository_tag_registration.py -v

# 型チェック
uv run mypy local_packages/genai-tag-db-tools/src/
```
