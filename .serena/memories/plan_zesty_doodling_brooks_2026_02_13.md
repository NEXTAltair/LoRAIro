# Plan: zesty-doodling-brooks

**Created**: 2026-02-13 00:21:43
**Source**: plan_mode
**Original File**: zesty-doodling-brooks.md
**Status**: implemented

---

# Issue #13: db_manager.py 長大関数4件の分割

## Context

`src/lorairo/database/db_manager.py` の `ImageDatabaseManager` クラスに60行超の関数が4件残存。
各関数が複数の責務を持ち、テスタビリティと可読性が低下している。
目標: 長大関数の分割（<=60行）、責務分離、回帰テスト維持。

## 実装方針: Agent Teams + Git Worktree

**戦略**: 各関数を別worktreeの別ブランチで並列リファクタリングし、最後にマージ。

### Worktree構成

| Teammate | Worktree | ブランチ | 担当 |
|---|---|---|---|
| Lead | `/workspaces/LoRAIro` | `NEXTAltair/issue13` | 統括・マージ・最終検証 |
| Teammate 1 | `../LoRAIro-thumbnail` | `issue13/thumbnail` | `_generate_thumbnail_512px()` 分割 + テスト |
| Teammate 2 | `../LoRAIro-annotations` | `issue13/annotations` | `filter_recent_annotations()` 分割 + テスト |
| Teammate 3 | `../LoRAIro-register` | `issue13/register` | `register_original_image()` 分割 |
| Teammate 4 | `../LoRAIro-filter` | `issue13/filter` | `get_images_by_filter()` dataclass導入 |

### モデル使い分け（コスト最適化）

| Teammate | モデル | 理由 |
|---|---|---|
| Teammate 1-3 (メソッド分割) | **Haiku** | パターン化された分割作業 |
| Teammate 4 (dataclass設計) | **Sonnet** | 設計判断 + 広範な影響範囲 |
| Lead (統括・マージ) | **Sonnet** | 品質確認・コンフリクト解決 |

### マージ戦略

1. 各teammateがworktreeで独立して実装・テスト
2. Leadが各ブランチをレビュー
3. `NEXTAltair/issue13` に順次マージ（コンフリクト解決はLead）
4. 全テスト実行で最終検証

### セットアップ手順

```bash
# 各worktree作成（Lead実行）
git worktree add ../LoRAIro-thumbnail -b issue13/thumbnail
git worktree add ../LoRAIro-annotations -b issue13/annotations
git worktree add ../LoRAIro-register -b issue13/register
git worktree add ../LoRAIro-filter -b issue13/filter

# 各worktreeで環境構築
for dir in ../LoRAIro-thumbnail ../LoRAIro-annotations ../LoRAIro-register ../LoRAIro-filter; do
  cd "$dir" && uv sync --dev && cd -
done
```

## 修正対象ファイル

- `src/lorairo/database/db_manager.py` (主対象)
- `src/lorairo/database/db_repository.py` (get_images_by_filter dataclass対応)
- `src/lorairo/database/models/` (新規: `ImageFilterCriteria` dataclass)
- `src/lorairo/services/search_criteria_processor.py` (呼び出し元更新)
- テストファイル群

---

## Step 1: `_generate_thumbnail_512px()` 分割 (84行 → ~25行 + 2ヘルパー)

**現状**: 画像処理 + DB登録 + アップスケーラーメタデータが混在

**分割**:
- `_create_and_save_thumbnail()`: ImageProcessingManager生成 → process_image → save（画像処理）
- `_register_thumbnail_in_db()`: processed_image DB登録 + アップスケーラーメタデータ（DB責務）
- `_generate_thumbnail_512px()`: 上記を呼ぶオーケストレーター

**テスト**: 新規ユニットテスト追加 (`tests/unit/database/test_db_manager_thumbnail.py`)

## Step 2: `filter_recent_annotations()` 分割 (84行 → ~30行 + 2ヘルパー)

**現状**: datetime解析 + タイムゾーン変換 + フィルタリングが混在

**分割**:
- `_parse_annotation_timestamp()`: updated_at文字列/datetimeのパース + UTC変換
- `_find_latest_annotation_timestamp()`: 全アノテーションから最新タイムスタンプ取得
- `filter_recent_annotations()`: フィルタリング本体

**テスト**: 新規ユニットテスト追加 (`tests/unit/database/test_db_manager_annotations.py`)

## Step 3: `register_original_image()` 分割 (76行 → ~35行 + 1ヘルパー)

**現状**: pHash計算 + 重複検出 + 保存 + メタデータ設定 + サムネイル生成

**分割**:
- `_prepare_image_metadata()`: メタデータ取得 + pHash計算 + UUID/パス情報設定
- `register_original_image()`: 重複チェック → prepare → 保存 → サムネイルのオーケストレーター
- `_handle_duplicate_image()` は既存のまま

**テスト**: 既存BDD + workerテストで回帰確認

## Step 4: `get_images_by_filter()` dataclass導入 (61行 → ~15行)

**現状**: 15パラメータをそのままrepositoryに転送する薄いラッパー

**方針**: `ImageFilterCriteria` dataclass導入
- 場所: `src/lorairo/database/filter_criteria.py` (新規)
- 既存の`SearchConditions`（search_models.py）はGUI/Service層の概念。DB層専用のdataclassを別途作成
- `SearchConditions.to_db_filter_args()` → `SearchConditions.to_filter_criteria()` に変更（`ImageFilterCriteria`を返す）

**影響範囲と対応**:
| 呼び出し元 | 現在のパターン | 変更 |
|---|---|---|
| `db_manager.get_images_by_filter()` | 15 kwargs | `ImageFilterCriteria` 受け取り |
| `db_manager.execute_filtered_search()` | `**conditions` | `ImageFilterCriteria` 生成 |
| `SearchCriteriaProcessor` | `**db_args` dict | `to_filter_criteria()` 使用 |
| BDDテスト (6箇所) | 個別kwargs | 後方互換ラッパー or 更新 |
| repository層 | 15 kwargs | `ImageFilterCriteria` 受け取り |

**後方互換**: db_manager側で kwargs → `ImageFilterCriteria` 変換の `@classmethod` を提供し、既存呼び出し元を段階的に移行可能にする。

---

## テスト戦略

- Step 1-2: 新規ユニットテスト追加（テストカバレッジ0% → 75%+）
- Step 3-4: 既存テスト（BDD 10件、integration 50+件）で回帰確認
- 最終検証: `uv run pytest --timeout=10 --timeout-method=thread`

## 検証手順

1. `uv run ruff check src/lorairo/database/db_manager.py` - lint
2. `uv run ruff check src/lorairo/database/db_repository.py` - lint
3. `uv run mypy -p lorairo.database` - 型チェック
4. `uv run pytest tests/ --timeout=10 --timeout-method=thread` - 全テスト
5. 各関数が60行以下であることを確認
