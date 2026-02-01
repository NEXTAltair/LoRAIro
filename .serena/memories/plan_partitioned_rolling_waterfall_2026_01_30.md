# Plan: partitioned-rolling-waterfall

**Created**: 2026-01-30 08:50:06
**Source**: plan_mode
**Original File**: partitioned-rolling-waterfall.md
**Status**: implemented

---

# N+1クエリ解消計画

## 概要
3箇所のN+1クエリをバッチクエリに置き換え、DB照会回数をO(N)→O(1)に削減する。

## 対象Issue

| # | 問題 | 該当ファイル | 現状クエリ数 (N画像) | 改善後 |
|---|------|------------|---------------------|--------|
| 1 | バッチ更新後メタデータ再読込 | dataset_state.py | N回 SELECT | 1回 IN |
| 2 | アノテーション状態フィルタ | search_criteria_processor.py | N回 SELECT+JOIN | 1回 EXISTS |
| 3 | アノテーション保存時DB照会 | annotation_worker.py | N(pHash)+M(model) | 2回 IN |

---

## Phase 1: リポジトリ層にバッチメソッド追加

### 1-1. `get_images_metadata_batch()` → [db_repository.py](src/lorairo/database/db_repository.py)

既存の `_fetch_filtered_metadata(session, image_ids, resolution=0)` を公開ラッパーで呼ぶ。
`Image.id.in_(image_ids)` + `joinedload` でタグ/キャプション/スコア/レーティングを1クエリ取得。

```python
def get_images_metadata_batch(self, image_ids: list[int]) -> list[dict[str, Any]]:
```

### 1-2. `get_annotated_image_ids()` → [db_repository.py](src/lorairo/database/db_repository.py)

`EXISTS` サブクエリでタグまたはキャプションが存在するIDのsetを返す。

```python
def get_annotated_image_ids(self, image_ids: list[int]) -> set[int]:
```

### 1-3. `find_image_ids_by_phashes()` → [db_repository.py](src/lorairo/database/db_repository.py)

`Image.phash.in_(phashes)` で pHash→image_id マッピングを1クエリ取得。

```python
def find_image_ids_by_phashes(self, phashes: set[str]) -> dict[str, int]:
```

### 1-4. `get_models_by_names()` → [db_repository.py](src/lorairo/database/db_repository.py)

`Model.name.in_(names)` + `selectinload(Model.model_types)` で一括取得。

```python
def get_models_by_names(self, names: set[str]) -> dict[str, Model]:
```

### 1-5. `get_annotated_image_ids()` 委譲 → [db_manager.py](src/lorairo/database/db_manager.py)

`SearchCriteriaProcessor` が `db_manager` 経由でアクセスするため委譲メソッド追加。

---

## Phase 2: 呼び出し元をバッチ化

### 2-1. `refresh_images()` 書き換え → [dataset_state.py](src/lorairo/gui/state/dataset_state.py:475)

- `get_images_metadata_batch()` で1クエリ一括取得
- `id→metadata` dictを作成、各IDに対し `update_image_metadata()` でキャッシュ更新
- `refresh_image()` は単一画像用に維持（後方互換）

### 2-2. `filter_images_by_annotation_status()` 書き換え → [search_criteria_processor.py](src/lorairo/services/search_criteria_processor.py:352)

- 画像IDリストを収集 → `db_manager.get_annotated_image_ids(image_ids)` で1クエリ
- 返されたsetでメモリ内フィルタリング

### 2-3. `_save_results_to_database()` / `_convert_to_annotations_dict()` 書き換え → [annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py:196)

- ループ前に `find_image_ids_by_phashes(set(results.keys()))` で全pHash→ID一括取得
- ループ前に全ユニークモデル名を収集 → `get_models_by_names(names)` で一括取得
- `_convert_to_annotations_dict()` にモデルキャッシュ dict を引数追加
- 外部タグDB(`_get_or_create_tag_id_external`)は外部ライブラリAPI変更不可のため対象外

---

## Phase 3: テスト

### 新規テスト
`tests/unit/database/test_db_repository_batch_queries.py`:
- `get_images_metadata_batch`: 正常・空リスト・存在しないID
- `get_annotated_image_ids`: タグのみ・キャプションのみ・未アノテーション除外・空リスト
- `find_image_ids_by_phashes`: 正常マッピング・存在しないpHash
- `get_models_by_names`: 正常マッピング・存在しない名前

### 既存テスト更新
- `test_dataset_state.py`: `refresh_images()` が `get_images_metadata_batch` を1回呼ぶこと確認
- `test_search_criteria_processor.py`: `filter_images_by_annotation_status` が `get_annotated_image_ids` を1回呼ぶこと確認
- `test_annotation_worker.py`: `_save_results_to_database` が `find_image_ids_by_phashes`・`get_models_by_names` を各1回呼ぶこと確認

---

## Phase 4: 検証

```bash
uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/
uv run mypy -p lorairo
uv run pytest
```

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| [db_repository.py](src/lorairo/database/db_repository.py) | 4メソッド追加 |
| [db_manager.py](src/lorairo/database/db_manager.py) | 1委譲メソッド追加 |
| [dataset_state.py](src/lorairo/gui/state/dataset_state.py) | `refresh_images()` 書き換え |
| [search_criteria_processor.py](src/lorairo/services/search_criteria_processor.py) | `filter_images_by_annotation_status()` 書き換え |
| [annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py) | `_save_results_to_database()` + `_convert_to_annotations_dict()` 書き換え |
| テストファイル（新規+既存） | バッチメソッドのテスト追加 |

## スコープ外
- 外部タグDB (`genai-tag-db-tools`) のバッチAPI追加（ライブラリAPI変更不可）
- `refresh_image()` 単体メソッドの変更（後方互換維持）
- `check_image_has_annotation()` の削除（他の呼び出し元が存在する可能性）
