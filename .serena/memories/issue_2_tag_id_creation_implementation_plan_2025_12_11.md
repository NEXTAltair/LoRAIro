# Issue #2: 外部DBからtag_id取得/作成処理 実装計画

## 実装日
2025-12-11

## 問題定義

**場所**: `/workspaces/LoRAIro/src/lorairo/database/db_repository.py:684`

**現状**:
- `_get_or_create_tag_id_external()` (line 615-666) は外部tag_dbから**読み込みのみ**
- タグが見つからない場合、`None`を返す（新規作成なし）
- AI生成タグが`tag_id=None`で保存され、外部タグ分類との連携が切れる

**影響**:
- 新規AIタグが外部tag_db taxonomy（分類体系）に登録されない
- タグの正規化、エイリアス、翻訳、使用統計が活用できない
- プロジェクト間のタグ管理の一貫性が損なわれる

## 実装アプローチ: Direct TagRepository Integration

### 設計決定
genai-tag-db-toolsの`TagRepository`と`TagCleaner`を直接`ImageRepository`に統合:
- タグ正規化（ExistingFileReaderパターンと一貫性）
- 外部DB検索
- 未発見時の新規タグ作成
- エラー時の縮退動作（None返却 → tag_id=NULLで保存）

**選択理由**: YAGNI原則 - 最もシンプルで既存パターンを再利用、低リスク

## 実装ステップ

### Step 1: ImageRepositoryに依存関係追加

**ファイル**: `/workspaces/LoRAIro/src/lorairo/database/db_repository.py`

**インポート追加** (line ~11付近):
```python
from genai_tag_db_tools.data.tag_repository import TagRepository
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
```

**__init__拡張** (lines 69-80):
```python
def __init__(self, session_factory: sessionmaker[Session] = DefaultSessionLocal):
    self.session_factory = session_factory
    logger.info("ImageRepository initialized.")
    self.tag_db_path = get_tag_db_path()

    # NEW: tag_db統合ツール初期化
    self.tag_repository = TagRepository()  # 外部tag_db用の独立セッション管理
    self.tag_cleaner = TagCleaner()        # ExistingFileReaderと同じ正規化
```

### Step 2: _get_or_create_tag_id_external()リファクタリング

**ファイル**: `/workspaces/LoRAIro/src/lorairo/database/db_repository.py` (lines 615-666)

**処理フロー**:
1. `TagCleaner.clean_format()` でタグ正規化
2. `TagRepository.get_tag_id_by_name()` で検索
3. 見つからない場合: `TagRepository.create_tag()` で新規作成
4. `IntegrityError` 捕捉（競合状態）→ 再検索でリトライ
5. その他エラー時は `None` 返却（縮退動作）

**キーポイント**:
- `source_tag`: オリジナル（AI出力/ユーザー入力そのまま）
- `tag`: 正規化済み（検索・表示用）
- エラー時は`None`返却でクラッシュ回避
- ExistingFileReaderと正規化ロジック統一

### Step 3: FIXME コメント更新

**ファイル**: `/workspaces/LoRAIro/src/lorairo/database/db_repository.py` (line 684)

**変更前**:
```python
# 外部DBから tag_id を取得/作成 (FIXME: Issue #2参照 - 実際の連携処理に置き換える)
```

**変更後**:
```python
# 外部DBから tag_id を取得/作成（Issue #2実装完了 - TagRepository統合）
```

**警告ログ追加** (line 685後):
```python
external_tag_id = self._get_or_create_tag_id_external(session, tag_string)

if external_tag_id is None and tag_string:
    logger.warning(
        f"Tag '{tag_string}' could not be linked to external tag_db. "
        "Saving with tag_id=None (limited taxonomy features)."
    )
```

## テスト戦略

### 統合テスト

**新規ファイル**: `tests/integration/test_tag_db_integration.py`

**テストケース**:
1. `test_new_tag_creation`: 新規タグ作成 → tag_id返却 & 外部DB存在確認
2. `test_existing_tag_lookup`: 既存タグ検索 → 正しいtag_id、重複なし
3. `test_tag_normalization_consistency`: ExistingFileReaderと正規化一致確認
4. `test_race_condition_handling`: 同時タグ作成 → IntegrityError処理確認
5. `test_graceful_degradation`: tag_dbエラーモック → None返却、クラッシュなし
6. `test_empty_tag_handling`: 空/空白タグ → None返却
7. `test_bulk_tag_processing`: 50タグ（新30、既存20）→ 全処理確認

### 手動検証

1. AI モデルで10画像アノテーション（新規タグ）
2. 外部tag_db確認: 新規タグ存在、source_tag/正規化tag正確性
3. LoRAIro DB確認: tag_id非NULL
4. 既存タグ確認: 重複作成なし
5. tag_db利用不可シナリオ: 縮退動作確認

## 重要ファイル

### 変更対象

1. **`/workspaces/LoRAIro/src/lorairo/database/db_repository.py`**
   - インポート追加: TagRepository, TagCleaner
   - __init__更新: tag_repository/tag_cleaner初期化
   - _get_or_create_tag_id_external()リファクタリング
   - FIXMEコメント更新

### 新規作成

2. **`tests/integration/test_tag_db_integration.py`**
   - 統合テスト実装

### 参照ファイル

3. **`/workspaces/LoRAIro/src/lorairo/annotations/existing_file_reader.py`**
   - TagCleaner使用パターン参照

4. **`/workspaces/LoRAIro/local_packages/genai-tag-db-tools/src/genai_tag_db_tools/data/tag_repository.py`**
   - API仕様: create_tag(), get_tag_id_by_name()

5. **`/workspaces/LoRAIro/src/lorairo/database/schema.py`**
   - Tagモデル構造（lines 228-258）

## キー設計決定

| 項目 | 決定内容 |
|------|----------|
| **タグ正規化** | `TagCleaner.clean_format()` 使用（ExistingFileReaderと統一） |
| **source_tag vs tag** | オリジナルをsource_tagに保存、正規化版をtagに格納 |
| **縮退動作** | エラー時None返却（tag_id=NULLで保存、データ損失なし） |
| **競合処理** | IntegrityError → 再検索リトライパターン |
| **セッション独立** | TagRepositoryが独立セッション使用（クロスDB複雑性回避） |

## 成功基準

- ✅ 全AI生成タグが保存後に非NULLのtag_idを持つ
- ✅ 外部tag_dbに重複タグが作成されない
- ✅ ExistingFileReaderとタグ正規化が一貫
- ✅ tag_db利用不可時の縮退動作（tag_id=NULL、処理継続）
- ✅ 既存機能への破壊的変更なし
- ✅ 全統合テストがパス

## ロールバック計画

問題発生時:
1. db_repository.pyの変更を元に戻す
2. 読み込み専用モードに戻る（Issue #2前の状態）
3. データ損失なし（tag_id=NULLはスキーマ上有効）

## 工数見積

- コード変更: 2-3時間
- 統合テスト: 4-6時間
- 手動検証: 1-2時間
- **合計**: 約1日

## 関連Issue/Memory

- **GitHub Issue**: #2
- **FIXME箇所**: db_repository.py:684
- **関連Memory**: architecture_structure, development_guidelines
