# Plan: scalable-squishing-scone

**Created**: 2026-01-30 20:24:04
**Source**: plan_mode
**Original File**: scalable-squishing-scone.md
**Status**: planning

---

# アノテーション保存時のDB照会最適化

## 現状分析

ユーザーが指摘した2つのN+1問題は**既に修正済み**（commit `68e2387`）:
- **pHash → image_id**: `find_image_ids_by_phashes()` で一括照会済み
- **モデル名 → Model**: `get_models_by_names()` でキャッシュ済み

### 残存する最適化ポイント

| # | 問題 | 場所 | 影響度 |
|---|------|------|--------|
| 1 | `_image_exists()` が画像ごとに呼ばれる（冗長） | [db_repository.py:755](src/lorairo/database/db_repository.py#L755) | 低：1クエリ/画像 |
| 2 | `_get_or_create_tag_id_external()` がタグごとに外部DB検索 | [db_repository.py:997](src/lorairo/database/db_repository.py#L997) | **高**：100画像×20タグ=2000回 |
| 3 | `save_annotations()` が画像ごとに新セッション作成 | [db_repository.py:758](src/lorairo/database/db_repository.py#L758) | 低〜中 |

## 実装計画

### Step 1: `_image_exists()` チェックの省略（annotation_worker経路限定）

**ファイル**: [db_repository.py](src/lorairo/database/db_repository.py), [annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py)

`save_annotations()` に `skip_existence_check: bool = False` パラメータを追加。
**annotation_worker経路のみ**で `skip_existence_check=True` を指定。

- `save_annotations()` はGUI手動更新・DBマネージャ経由でも使われるため、デフォルトは `False` を維持
- `_save_results_to_database()` 内のループからの呼び出しのみ `True` に設定（pHashバッチ照会で存在確認済み）
- 他の全呼び出し元は既存の存在チェックを維持（後方互換性）

```python
def save_annotations(self, image_id: int, annotations: AnnotationsDict,
                     *, skip_existence_check: bool = False) -> None:
    if not skip_existence_check and not self._image_exists(image_id):
        raise ValueError(...)
```

### Step 2: 外部タグDB照会のバッチ化（最大効果）

**ファイル**: [db_repository.py](src/lorairo/database/db_repository.py), [annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py)

**発見**: `MergedTagReader.search_tags_bulk(keywords, format_name=None, resolve_preferred=False)` が存在。

#### 重要な制約事項:

1. **正規化の整合性**: `search_tags_bulk()` は内部で `strip` のみ実施。現行の単発検索は `TagCleaner.clean_format() + strip` を適用。
   → バッチ検索の**前段で `TagCleaner.clean_format().strip()` を必須適用**し、正規化済み文字列を渡す。

2. **alias/deprecatedフィルタ**: `search_tags_bulk()` は alias/deprecated のフィルタを行わない。現行は `include_aliases=True, include_deprecated=False`。
   → バッチ結果に対して **`deprecated=True` のタグを除外する後処理フィルタ**を追加。alias は `include_aliases=True` なので除外不要。

3. **format_name**: 現行の単発検索も format 未指定のため、`format_name=None` のまま（整合性維持）。

#### 実装手順:

1. **`_save_results_to_database()` でタグを事前収集** ([annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py)):
   - 全結果からユニークなタグ文字列を収集
   - **`TagCleaner.clean_format().strip()` で正規化**（原文→正規化のマッピングも保持）

2. **`batch_resolve_tag_ids()` 新メソッド追加** ([db_repository.py](src/lorairo/database/db_repository.py)):
   - 入力: 正規化済みタグ文字列のセット
   - `merged_reader.search_tags_bulk(normalized_tags)` で一括検索
   - **結果から `deprecated=True` のエントリを除外**（現行 `include_deprecated=False` と同等）
   - 見つからなかったタグのみ `tag_register_service.register_tag()` で個別登録
   - 戻り値: `dict[str, int | None]`（正規化タグ → tag_id）

3. **`_save_tags()` にキャッシュ引数追加**:
   - `tag_id_cache: dict[str, int | None] | None = None` パラメータ追加
   - キャッシュヒット時: `_get_or_create_tag_id_external()` をスキップし、キャッシュから tag_id を取得
   - キャッシュミス時（`None` キーまたはキャッシュ未提供）: 既存の `_get_or_create_tag_id_external()` にフォールバック

4. **`save_annotations()` にキャッシュ引数追加**:
   - `tag_id_cache: dict[str, int | None] | None = None` パラメータ追加
   - `_save_tags()` に受け渡し
   - デフォルト `None`（キャッシュ未使用 = 既存動作と同一）

#### 呼び出しフロー（変更後）:

```
_save_results_to_database()
  ├── find_image_ids_by_phashes()     # 既存: pHash一括
  ├── get_models_by_names()           # 既存: モデル一括
  ├── タグ収集 + TagCleaner正規化     # 新規: ユニークタグ抽出
  ├── batch_resolve_tag_ids()         # 新規: タグID一括（deprecated除外付き）
  └── for phash, annotations:
        ├── _convert_to_annotations_dict()
        └── save_annotations(
              skip_existence_check=True,  # annotation_worker経路のみ
              tag_id_cache=tag_id_cache   # バッチ解決済みキャッシュ
            )
              └── _save_tags(tag_id_cache=...)  # キャッシュ参照、ミス時はフォールバック
```

### Step 3: セッション共有（見送り）

影響度が低く、既存APIの変更範囲が大きいため今回は見送り。
`save_annotations()` の単一画像APIは他の呼び出し元でも使われるため維持。

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| [src/lorairo/database/db_repository.py](src/lorairo/database/db_repository.py) | `batch_resolve_tag_ids()` 追加、`save_annotations()` / `_save_tags()` にキャッシュ引数追加 |
| [src/lorairo/gui/workers/annotation_worker.py](src/lorairo/gui/workers/annotation_worker.py) | `_save_results_to_database()` でタグ収集・正規化・一括解決・キャッシュ受け渡し |

## 検証方法

1. `uv run ruff check src/lorairo/database/db_repository.py src/lorairo/gui/workers/annotation_worker.py`
2. `uv run mypy -p lorairo`
3. `uv run pytest tests/unit/database/` - DBリポジトリのユニットテスト
4. `uv run pytest tests/integration/` - 統合テスト
