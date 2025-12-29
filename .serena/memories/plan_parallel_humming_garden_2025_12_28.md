# Plan: LoRAIro genai-tag-db-tools 公開API移行計画

**Created**: 2025-12-28
**Source**: manual_sync
**Original File**: parallel-humming-garden.md
**Status**: planning

---

## 概要

LoRAIroの外部タグデータベース統合を、`genai_tag_db_tools`の非推奨内部API（`TagRepository`）から公開APIへ移行する。

**目標**: Repository直接呼び出しを廃止し、公開API (`search_tags()`, `register_tag()`) 経由での統合を実現する。

**スコープ**:
- `src/lorairo/database/db_repository.py` - TagRepository使用箇所の置き換え
- `src/lorairo/database/db_core.py` - DB初期化ロジックは変更なし
- `src/lorairo/annotations/existing_file_reader.py` - 変更不要（TagCleanerは公開API）

---

## 要件と制約

### 機能要件
1. **タグ検索**: 正規化タグで外部DBからtag_idを取得
2. **タグ登録**: 新規タグを外部DBに登録しtag_idを返す
3. **エラーハンドリング**: 現在のグレースフルデグラデーション（tag_id=None許容）を維持
4. **トランザクション分離**: 外部DB操作とLoRAIro DB操作の独立性を保持

### 非機能要件
- **後方互換性**: 既存のデータベーススキーマ変更なし
- **パフォーマンス**: 現在と同等またはそれ以上
- **保守性**: 公開APIの安定性に依存
- **テスト容易性**: モック・スタブによる単体テスト実装可能

### 制約条件
- `tag_id` はオプショナル（`int | None`） - 外部DB障害時もシステム継続
- 外部DBと内部DBのトランザクション分離を維持
- SQLiteベース（外部DBは読み取り専用と仮定）
- 既存の4ステップフロー（正規化→検索→作成→リトライ）の保持
- **format/type マスタは起動時に user DB へ必ず追加（LoRAIro/他アプリ共通）**
- **format_name はアプリ名（例: "Lorairo" / "tag-db"）を使用**
- **type_name は不足時に "unknown" を仮置きし、マスタ未登録なら自動追加**
- **不完全判定は `type_name == "unknown"` かつ `format_name` がユーザー登録のもの**

---

## 現状分析

### 現在の実装（db_repository.py）

```python
# Line 85: 初期化
self.tag_repository = TagRepository()  # 非推奨内部API
self.tag_cleaner = TagCleaner()

# Line 653: タグ検索
tag_id = self.tag_repository.get_tag_id_by_name(normalized_tag, partial=False)

# Line 665: タグ登録
tag_id = self.tag_repository.create_tag(source_tag=tag_string, tag=normalized_tag)
```

### 問題点
1. **非公開API依存**: `genai_tag_db_tools.data.tag_repository.TagRepository` はリファクタリング後削除予定
2. **初期化の不透明性**: `TagRepository()` の内部依存が不明確
3. **エラーハンドリング**: 現在は汎用Exceptionキャッチ、公開APIは特定例外を投げる可能性
4. **TagRegisterService Qt依存**: `app_services.py`のTagRegisterServiceがQObject継承（PySide6依存）、CLI/非GUI環境で使用不可

---

## 推奨ソリューション: 公開API完全移行

### ユーザー要件確認結果

**Phase 2（ensure_databases統合）**: 不要
- HF自動ダウンロード対応はLoRAIroの責任範囲外
- デフォルトDBでの運用で問題なし
- **結論**: Repository置き換えのみ実装

**タグ登録の必要性**: 必要
- AI生成の新規タグをUser DBに追加してtag_idを取得
- 現在の `TagRepository.create_tag()` の挙動を維持

**format_name / type_name**: アプリごとに決定
- format_name はインストール/起動しているプロジェクト名を使用（例: "Lorairo", 単体起動なら "tag-db"）
- type_name は不足時に "unknown" を仮置きし、ユーザーが後で再解決
- 不完全レコード判定: `type_name == "unknown"` かつ `format_name` がユーザー登録のもの

### アプローチ選択理由

**選択**: **公開API完全移行**

**理由**:
- genai-tag-db-toolsのリファクタリング完了により公開APIが安定
- `TagRecordPublic.tag_id` / `TagRegisterResult.tag_id` フィールド追加済み
- LoRAIroの長期保守性を優先
- ensure_databases()統合不要により実装スコープが明確化

---

## アーキテクチャ設計

### 新しい初期化フロー

```python
# ImageRepository.__init__() (db_repository.py)
from genai_tag_db_tools.db.repository import MergedTagReader
from genai_tag_db_tools.db.user_db import UserDatabase
from genai_tag_db_tools.utils.cleanup_str import TagCleaner

class ImageRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

        # 外部タグDB統合
        self.tag_cleaner = TagCleaner()  # ✅ 既に公開API
        self.merged_reader = self._initialize_merged_reader()  # 🆕 遅延初期化
        self.user_db: UserDatabase | None = None  # 🆕 タグ登録用（Qt依存なし）
```

**重要**: TagRegisterServiceはQObject継承のためCLI/非GUI環境で使用不可。代わりにUserDatabaseを直接使用してタグ登録を実装。

### 新しいタグ検索・登録フロー

```python
def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
    # Step 1: 正規化（変更なし）
    normalized_tag = TagCleaner.clean_format(tag_string).strip()
    if not normalized_tag:
        return None

    # Step 2: 検索（公開API経由、MergedReaderがNoneなら即座にスキップ）
    if self.merged_reader is None:
        logger.debug("MergedTagReader unavailable, skipping tag search")
        return None
    
    try:
        from genai_tag_db_tools import search_tags
        from genai_tag_db_tools.models import TagSearchRequest

        request = TagSearchRequest(
            query=normalized_tag,
            partial=False,  # 完全一致検索
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=False
        )
        result = search_tags(self.merged_reader, request)

        if result.items and len(result.items) > 0:
            return result.items[0].tag_id  # ✅ tag_idフィールド使用
    except Exception as e:
        logger.error(f"Error searching tag: {e}", exc_info=True)
        return None

    # Step 3: 登録（UserDatabase直接使用、Qt依存なし、デフォルトパス自動作成）
    if self.merged_reader is None:
        logger.debug("MergedTagReader unavailable, skipping tag registration")
        return None
    
    try:
        from genai_tag_db_tools.io.hf_downloader import default_cache_dir
        from genai_tag_db_tools.db.user_db import init_user_db

        # UserDatabase遅延初期化（デフォルトキャッシュディレクトリ使用）
        if self.user_db is None:
            self.user_db = self._initialize_user_db()
            if self.user_db is None:
                logger.debug("UserDatabase initialization failed, skipping tag registration")
                return None

        # タグ直接登録（format_id/type_idを事前解決）
        format_id = self.merged_reader.get_format_id("lorairo")
        type_id = self.merged_reader.get_type_id("general")
        
        if not format_id or not type_id:
            logger.error("Failed to resolve format_id or type_id")
            return None

        tag_id = self.user_db.create_tag(
            tag=normalized_tag,
            source_tag=tag_string,
            format_id=format_id,
            type_id=type_id
        )
        return tag_id

    except IntegrityError:
        # Step 4: 競合リトライ（現在と同じロジック）
        logger.warning("Race condition detected, retrying search...")
        try:
            result = search_tags(self.merged_reader, request)
            if result.items:
                return result.items[0].tag_id
        except Exception as retry_error:
            logger.error(f"Retry failed: {retry_error}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error creating tag: {e}", exc_info=True)
        return None
```

---

## 実装計画

### GUIサービス移動
- `genai_tag_db_tools/services/app_services.py` のGUI依存クラスを `genai_tag_db_tools/gui/services` へ完全移行
  - 移動対象: `GuiServiceBase`, `TagSearchService`, `TagCleanerService`, `TagRegisterService`, `TagStatisticsService`
- `TagCoreService` など非GUIは新規 `genai_tag_db_tools/services/core_services.py` へ分離
- 既存の import を **全て新パスへ更新**（re-export なしで完全移行）
- GUI関連テスト/CLI/GUIコードの import を更新

### Repository API置き換え

#### タスク1: インポート修正
**ファイル**: `src/lorairo/database/db_repository.py`

**削除**:
```python
from genai_tag_db_tools.data.tag_repository import TagRepository
```

**追加**:
```python
from genai_tag_db_tools import search_tags
from genai_tag_db_tools.models import TagSearchRequest, TagSearchResult
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.db.user_db import UserDatabase, init_user_db
from genai_tag_db_tools.io.hf_downloader import default_cache_dir
```

**注意**: 
- `register_tag()` / `TagRegisterService` は使用しない（Qt依存のため）
- 代わりに `UserDatabase.create_tag()` を直接使用
- `init_user_db()` でユーザーDBパスを自動作成・初期化（テストでも動作）

#### タスク2: 初期化メソッド追加
```python
def _initialize_merged_reader(self) -> MergedTagReader:
    """外部タグDBリーダーを初期化（遅延初期化）"""
    try:
        return get_default_reader()
    except Exception as e:
        logger.error(f"Failed to initialize MergedTagReader: {e}", exc_info=True)
        raise

def _initialize_register_service(self) -> TagRegisterService:
    """タグ登録サービスを初期化（遅延初期化）"""
    try:
        return TagRegisterService(parent=None)  # Qt parent不要（CLIでも動作）
    except Exception as e:
        logger.error(f"Failed to initialize TagRegisterService: {e}", exc_info=True)
        raise
```

#### タスク2.5: format/type マスタ初期化
- 起動時に user DB へ format/type マスタを追加（存在しなければ作成）
- format_name はアプリ名（例: "Lorairo" / "tag-db"）を使用
- type_name は不足時に "unknown" を仮置きし、ユーザーが後で再解決
- 不完全判定は `type_name == "unknown"` かつ `format_name` がユーザー登録のもの

#### タスク3: ImageRepository.__init__() 修正
**ファイル**: `src/lorairo/database/db_repository.py` (lines 71-86)

```python
def __init__(self, session_factory: sessionmaker[Session]) -> None:
    self.session_factory = session_factory

    # 外部タグDB統合（公開API、Qt依存なし、失敗時はNoneで継続）
    self.tag_cleaner = TagCleaner()
    self.merged_reader = self._initialize_merged_reader()  # 失敗時はNone
    self.user_db: UserDatabase | None = None  # 遅延初期化（Qt依存なし）
```

#### タスク4: _get_or_create_tag_id_external() 書き換え
**ファイル**: `src/lorairo/database/db_repository.py` (lines 621-691)

- 検索: `search_tags()` 使用
- 登録: `register_tag()` 使用（format_name="lorairo"）
- エラーハンドリング維持

#### タスク5: 不要なコード削除
- `self.tag_repository` 削除（line 85）
- `self.tag_db_path` 削除（line 82-83） - 公開API経由では不要

---

## テスト戦略

### 単体テスト（pytest -m unit）

```python
class TestImageRepositoryTagIntegration:
    """外部タグDB統合の単体テスト"""

    def test_get_or_create_tag_id_external_search_success(self):
        """既存タグ検索成功"""
        mock_result = TagSearchResult(items=[TagRecordPublic(tag="cat", tag_id=123)])
        with patch("lorairo.database.db_repository.search_tags", return_value=mock_result):
            repo = ImageRepository(session_factory=...)
            tag_id = repo._get_or_create_tag_id_external(session, "cat")
            assert tag_id == 123

    def test_get_or_create_tag_id_external_create_success(self):
        """新規タグ登録成功"""
        with patch("lorairo.database.db_repository.search_tags", return_value=TagSearchResult(items=[])):
            with patch.object(UserDatabase, "create_tag", return_value=456):
                repo = ImageRepository(session_factory=...)
                tag_id = repo._get_or_create_tag_id_external(session, "new_tag")
                assert tag_id == 456

    def test_get_or_create_tag_id_external_race_condition(self):
        """競合検出とリトライ"""
        with patch("lorairo.database.db_repository.search_tags") as mock_search:
            mock_search.side_effect = [
                TagSearchResult(items=[]),  # First search
                TagSearchResult(items=[TagRecordPublic(tag="tag", tag_id=789)])  # Retry
            ]
            with patch.object(UserDatabase, "create_tag", side_effect=IntegrityError):
                repo = ImageRepository(session_factory=...)
                tag_id = repo._get_or_create_tag_id_external(session, "tag")
                assert tag_id == 789

    def test_get_or_create_tag_id_external_graceful_degradation(self):
        """外部DB障害時のグレースフルデグラデーション"""
        with patch("lorairo.database.db_repository.search_tags", side_effect=Exception("DB error")):
            repo = ImageRepository(session_factory=...)
            tag_id = repo._get_or_create_tag_id_external(session, "tag")
            assert tag_id is None  # システムは継続動作
```

### カバレッジ目標
- 単体テスト: 85%+（既存75%から向上）
- 統合テスト: 主要フロー網羅
- エラーケース: 全パターンテスト

---

## リスクと対策

| リスク | 影響 | 確率 | 対策 |
|--------|------|------|------|
| **MergedTagReader初期化失敗** | 外部タグDB利用不可 | 中 | グレースフルデグラデーション: merged_reader=None、tag_id=None で動作継続、警告ログ |
| **UserDatabase初期化失敗** | 新規タグ登録不可 | 低 | グレースフルデグラデーション: user_db=None、検索のみ動作、警告ログ |
| **format_id/type_id解決失敗** | タグ登録不可 | 低 | エラーログ出力、tag_id=None で継続 |
| **公開APIの破壊的変更** | 将来的な互換性問題 | 低 | genai-tag-db-toolsのバージョン固定、変更監視 |
| **パフォーマンス劣化** | レスポンス遅延 | 低 | ベンチマーク測定、必要ならキャッシング追加 |
| **競合検出ロジック変更** | データ不整合 | 低 | 既存ロジック維持、IntegrityErrorハンドリング保持 |

---

## 実装順序

### 実装ステップ

1. **インポート修正**: 非推奨API削除、公開API追加
2. **初期化メソッド追加**: `_initialize_merged_reader()`, `_initialize_register_service()`
3. **ImageRepository.__init__() 更新**: 新しい初期化フロー適用
4. **_get_or_create_tag_id_external() 書き換え**:
   - 検索: `search_tags()` 使用（partial=False で完全一致）
   - 登録: `UserDatabase.create_tag()` 直接使用（Qt依存回避）
   - format_id/type_id を事前解決（MergedTagReader経由）
   - エラーハンドリング維持
5. **不要コード削除**: `self.tag_repository`, `self.tag_db_path`
6. **単体テスト実装**: 新APIモック、エラーケース網羅
7. **統合テスト実行**: 既存機能動作確認
8. **最終検証**: パフォーマンス、ログ出力確認

---

## 成功基準

- ✅ すべての単体テスト合格（85%+ カバレッジ）
- ✅ 統合テスト合格（既存機能動作保証）
- ✅ 既存データベースとの互換性維持
- ✅ エラーハンドリングの正常動作（tag_id=None フォールバック）
- ✅ パフォーマンス劣化なし（±5%以内）
- ✅ ログ出力適切（デバッグ可能性）

---

## 関連ファイル

### 変更対象
- `src/lorairo/database/db_repository.py` (主要変更)

### 参照のみ
- `src/lorairo/database/db_core.py` (変更なし)
- `src/lorairo/annotations/existing_file_reader.py` (変更不要)
- `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/__init__.py`
- `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/models.py`
- `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py`

### テスト
- `tests/unit/database/test_db_repository.py` (追加)
- `tests/integration/database/test_tag_integration.py` (新規)

---

## 設計判断の記録

### format/type マスタの扱い
- 起動時に user DB へ format/type マスタを自動追加する
- format_name はアプリ名（例: "Lorairo" / "tag-db"）を使用
- type_name は不足時に "unknown" を仮置きし、ユーザーが後で再解決
- 不完全判定は `type_name == "unknown"` かつ `format_name` がユーザー登録のもの


### なぜ遅延初期化？
- `UserDatabase` は書き込み操作でのみ必要
- 初期化コスト削減（読み取り専用ケース）
- エラーハンドリングの柔軟性向上

### なぜUserDatabase直接使用？
- `TagRegisterService` はQObject継承（PySide6依存）でCLI/非GUI環境に不向き
- `UserDatabase` はQt非依存でシンプルなSQLite操作
- LoRAIroのCLI/非GUIコンテキストで正常動作
- format_id/type_id を MergedTagReader 経由で解決することで公開API互換性を維持

### なぜ init_user_db() + default_cache_dir() を使用？
- `--user-db-dir` オプション不要でデフォルトパス自動決定（HF_HOME準拠）
- `init_user_db()` がユーザーDBディレクトリとSQLiteファイルを自動作成・初期化
- テスト環境でもユーザーDBを自動セットアップ可能
- CLIとGUI両方で一貫した動作を保証

### なぜエラースローを削除？
- `get_default_reader()` は「ベースDBもユーザーDBも無い」場合にエラー
- LoRAIroは外部タグDB無しでも動作継続すべき（tag_id=None許容）
- 初期化失敗時は `None` を返し、検索・登録時に早期リターン
- グレースフルデグラデーション: 警告ログのみ出力、システム起動は継続

### なぜ format_name="lorairo"？
- LoRAIro固有のタグ体系（既存DB連携なし）
- 将来的にDanbooru/e621等への変換機能追加可能
- "custom"より明確なプロジェクト識別

### なぜ ensure_databases() 不要？
- ユーザー要件: デフォルトDBで十分、自動ダウンロード不要
- 既存の bundled database で問題なく動作
- 実装スコープ削減でリスク最小化
