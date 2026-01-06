# Plan: LoRAIro genai-tag-db-tools 公開API移行計画

**Created**: 2025-12-28
**Source**: manual_sync
**Original File**: parallel-humming-garden.md
**Status**: ✅ Phase 2 完了（2025-12-31 commit 584abab + 統合テスト追加）、Phase 2.5 は genai-tag-db-tools側で実装予定

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
- **unknown type判定は `type_name == "unknown"` のみ**
- **`unknown` 仮置き/不足補完はタグDBツール（core）側で実装**
- **ライブラリ利用時は `user_db_dir` 未指定なら初期化前にエラー**
- **CLI/アプリ起動時はデフォルトパスで自動作成を許可**
- **✅ ユーザーDB format_id は1000番台以降に予約（ベースDBとの衝突回避）**
- **既存ユーザーDBに1000未満がある場合は修正せず、そのまま扱う**

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

### 問題点（解決済み）
1. **非公開API依存**: `genai_tag_db_tools.data.tag_repository.TagRepository` はリファクタリング後削除予定
2. **初期化の不透明性**: `TagRepository()` の内部依存が不明確
3. **エラーハンドリング**: 現在は汎用Exceptionキャッチ、公開APIは特定例外を投げる可能性
4. **~~TagRegisterService Qt依存~~**: **✅ 解決済み** - Qt非依存の`TagRegisterService`を実装、GUI用ラッパー`GuiTagRegisterService`を分離

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
- unknown typeレコード判定: `type_name == "unknown"` のみ

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
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner

class ImageRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

        # 外部タグDB統合
        # TagCleaner.clean_format()は静的メソッドなのでインスタンス化不要
        self.merged_reader = self._initialize_merged_reader()  # 🆕 user DB自動作成、Base DBは任意
        self.tag_register_service: TagRegisterService | None = None  # 🆕 タグ登録用（Qt非依存、遅延初期化）
```

**✅ 重要**: `TagRegisterService`はQt非依存に再設計済み。CLI/ライブラリ/GUIで使用可能。

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

    # Step 3: 登録（TagRegisterService使用、Qt非依存）
    if self.merged_reader is None:
        logger.debug("MergedTagReader unavailable, skipping tag registration")
        return None

    try:
        # TagRegisterService遅延初期化（user DB存在保証により失敗しない）
        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()

        # タグ登録リクエスト作成
        from genai_tag_db_tools.models import TagRegisterRequest

        register_request = TagRegisterRequest(
            tag=normalized_tag,
            source_tag=tag_string,
            format_name="Lorairo",  # app name
            type_name="unknown"  # type unresolved until user resolves
        )

        result = self.tag_register_service.register_tag(register_request)
        logger.debug(f"Registered new tag_id {result.tag_id} for '{normalized_tag}'")
        return result.tag_id

    except ValueError as e:
        # format_name/type_name解決失敗
        logger.error(f"Tag registration failed (invalid format/type): {e}")
        return None
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

### ✅ GUIサービス移動（完了）
- **完了**: `genai_tag_db_tools/services/tag_register.py` にQt非依存の`TagRegisterService`を実装
- **完了**: `genai_tag_db_tools/gui/services/tag_register_service.py` にQt依存の`GuiTagRegisterService`（ラッパー）を実装
- **アーキテクチャ**:
  - `TagRegisterService`: Qt非依存、CLI/ライブラリ/GUI全てで使用可能
  - `GuiTagRegisterService(GuiServiceBase)`: `TagRegisterService`をラップ、Qtシグナル発行（`error_occurred`, `progress_updated`, `process_finished`）
  - `GuiTagRegisterService._core`: 内部で`TagRegisterService`インスタンスを保持
- **使用箇所**:
  - CLI: `cli.py` → `TagRegisterService`直接使用
  - GUI: `gui/windows/main_window.py`, `gui/widgets/tag_register.py` → `GuiTagRegisterService`使用
  - テスト: `tests/unit/test_tag_register_service.py` (Qt非依存), `tests/gui/unit/test_gui_tag_register_service.py` (Qt依存)

### Repository API置き換え

#### タスク1: インポート修正
**ファイル**: `src/lorairo/database/db_repository.py`

**削除**:
```python
from genai_tag_db_tools.data.tag_repository import TagRepository
```

**追加**:
```python
from genai_tag_db_tools import search_tags, register_tag
from genai_tag_db_tools.models import TagSearchRequest, TagSearchResult, TagRegisterRequest
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.services.tag_register import TagRegisterService
```

**✅ 注意**:
- `TagRegisterService` はQt非依存に再設計済み（CLI/ライブラリ/GUIで使用可能）
- 公開API `register_tag()` も使用可能（内部で`TagRegisterService`を使用）
- GUI用は `genai_tag_db_tools.gui.services.tag_register_service.GuiTagRegisterService` を使用

#### タスク2: 初期化メソッド追加（2025-12-30更新）
```python
def _initialize_merged_reader(self) -> MergedTagReader:
    """外部タグDBリーダーを初期化（user DB自動作成）
    
    - CLI/GUI: init_user_db() でデフォルトパスに user DB 自動作成
    - ライブラリ: user_db_dir 未指定時はエラー
    - Base DB: 任意（無くても user DB のみで動作）
    """
    from genai_tag_db_tools.db.runtime import init_user_db, get_default_reader
    
    # user DB 初期化（LoRAIroはCLI/GUIアプリとして動作、デフォルトパス使用）
    init_user_db()  # user_db_dir=None → HF_HOME準拠のデフォルトパスで自動作成
    
    # MergedTagReader 取得（user DB 存在保証により失敗しない）
    return get_default_reader()

def _initialize_tag_register_service(self) -> TagRegisterService:
    """タグ登録サービスを初期化（Qt非依存、user DB存在保証により失敗しない）"""
    return TagRegisterService(reader=self.merged_reader)
```

#### タスク2.5: format/type マスタ初期化
- 起動時に user DB へ format/type マスタを追加（存在しなければ作成）
- format_name はアプリ名（例: "Lorairo" / "tag-db"）を使用
- type_name は不足時に "unknown" を仮置きし、ユーザーが後で再解決
- unknown type判定は `type_name == "unknown"` のみ
- **✅ ID衝突回避**: ユーザーDB format_id は1000番台以降を使用（ベースDB: 1-999、ユーザーDB: 1000-）
- **注意**: 既存ユーザーDBに1000未満のformat_idがある場合は補正せず、新規format作成時のみ1000番台を使用

#### タスク3: ImageRepository.__init__() 修正
**ファイル**: `src/lorairo/database/db_repository.py` (lines 71-86)

```python
def __init__(self, session_factory: sessionmaker[Session] = DefaultSessionLocal):
    self.session_factory = session_factory
    logger.info("ImageRepository initialized.")

    # 外部タグDB統合（公開API、Qt依存なし、user DB自動作成）
    # TagCleaner.clean_format()は静的メソッドなのでインスタンス化不要
    self.merged_reader = self._initialize_merged_reader()  # user DB自動作成、Base DBは任意
    # TagRegisterServiceは遅延初期化（登録時のみ必要）
    self.tag_register_service: TagRegisterService | None = None
```

#### タスク4: _get_or_create_tag_id_external() 書き換え
**ファイル**: `src/lorairo/database/db_repository.py` (lines 644-699)

- **現状**: 検索のみ実装済み（`search_tags()`使用）
- **Phase 2 実装予定**: タグ登録機能（`TagRegisterService.register_tag()`使用、format_name="Lorairo" / type_name="unknown"）
- **エラーハンドリング**: ValueError（format/type解決失敗）、IntegrityError（競合）は tag_id=None で継続、その他の例外もログ記録後継続

#### タスク5: 不要なコード削除
- **✅ 完了**: `self.tag_repository` 削除（旧実装の痕跡を削除）
- **✅ 完了**: `self.tag_db_path` 削除（公開API経由では不要）
- **現状**: `ImageRepository.__init__()` はクリーンな状態（lines 73-87）

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

| リスク | 影響 | 確率 | 対策 | 状態 |
|--------|------|------|------|------|
| **MergedTagReader初期化失敗** | 外部タグDB利用不可 | 低 | init_user_db() で user DB 自動作成、Base DB は任意（無くても動作）、CLI/GUI: デフォルトパス自動作成、ライブラリ: user_db_dir未指定時エラー | ⏳ Phase 2で実装予定 |
| **TagRegisterService初期化失敗** | 新規タグ登録不可 | 低 | MergedTagReader 初期化成功時のみ作成、user DB 存在保証により失敗しない | ⏳ Phase 2で実装予定 |
| **format_id/type_id解決失敗** | タグ登録不可 | 低 | ValueError発生、エラーログ出力、tag_id=None で継続 | ⏳ Phase 2で実装予定 |
| **公開APIの破壊的変更** | 将来的な互換性問題 | 低 | genai-tag-db-toolsのバージョン固定、変更監視 | 継続監視 |
| **パフォーマンス劣化** | レスポンス遅延 | 低 | ベンチマーク測定、必要ならキャッシング追加 | 継続監視 |
| **競合検出ロジック変更** | データ不整合 | 低 | 既存ロジック維持、IntegrityErrorハンドリング保持 | ⏳ Phase 2で実装予定 |

---

## Phase 2.5: unknown typeタグ管理機能（新規）

**日付**: 2025-12-30  
**状態**: 🔄 仕様策定完了

### 背景と目的

LoRAIroからの一括タグ登録時、都度type判定を行うと作業フローが悪化するため、一時的にtype不明のデータ（`type_name="unknown"`）を蓄積し、後で一括修正できる機能を実装する。

### 仕様決定事項

#### unknown type判定基準
- **`type_name == "unknown"` のみで判定**
- format_nameフィルタ不要（format_idでスコープ分離済み）

#### type_name処理
- 任意の文字列許可、存在しなければ自動作成
- 既存実装: `TagRegisterService.register_tag()` で対応済み ([tag_register.py:151-174](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_register.py#L151-L174))

#### type_id採番戦略
- **1000+オフセット不要**と判断
- 理由: type_idはformat内ローカル番号のため、format_id分離で衝突しない
- Base DB: `(format_id=1, type_id=0)` / User DB: `(format_id=1000, type_id=0)` 共存可能

#### GUI実装
- 不要（LoRAIro側でサービス層として利用）

### 実装タスク

- [ ] **P2.5-1**: format内type_id採番ロジック実装
  - `get_next_type_id(format_id: int) -> int`
  - 現在のformat_idで使用中のtype_idからmax+1を返す
  - 既存マッピングがなければ0を返す

- [ ] **P2.5-2**: unknown typeタグ一括更新API実装
  - `update_tags_type_batch(tag_updates: List[TagTypeUpdate], format_id: int)`
  - type_nameからtype_name_id取得/作成
  - TagTypeFormatMappingの自動作成（type_id自動採番）
  - トランザクション保証

- [ ] **P2.5-3**: テストケース追加（75%+ カバレッジ維持）
  - format内type_id採番テスト
  - 一括更新トランザクションテスト
  - エラーハンドリングテスト

- [ ] **P2.5-4**: type_name選択・割り当てインターフェース実装
  - 既存type_name一覧取得のエクスポート（`get_all_types()`, `get_tag_types(format_id)` 活用）
  - 一括更新API (`update_tags_type_batch()`) との統合
  - LoRAIroから利用可能なAPI設計

### 既存API活用

- `get_unknown_type_tags(format_id)` - unknown typeタグ検索
- `update_tag_status(type_id=...)` - 単一タグ更新 ([repository.py:461-537](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L461-L537))
- `create_type_name_if_not_exists()` - type_name自動作成 ([repository.py:655-679](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L655-L679))
- `create_type_format_mapping_if_not_exists()` - マッピング作成 ([repository.py:681-714](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L681-L714))
- `MergedTagReader.get_all_types()` - 全type_nameリスト取得 ([repository.py:1007-1013](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L1007-L1013))
- `MergedTagReader.get_tag_types(format_id)` - format内type_nameリスト取得 ([repository.py:991-997](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L991-L997)))

### 検証基準

- format内で同一type_nameに対して一意のtype_id割り当て
- 複数type_nameの同時作成で衝突なし
- LoRAIroからの一括タグ登録→修正ワークフロー動作

**詳細仕様**: [genai_tag_db_tools_incomplete_tag_management_spec_2025_12_30.md](.serena/memories/genai_tag_db_tools_incomplete_tag_management_spec_2025_12_30.md)

---

## 実装順序

### 実装ステップ（Phase 1: 検索のみ）

1. **✅ インポート修正**: 非推奨API削除、公開API追加
2. **✅ 初期化メソッド追加**: `_initialize_merged_reader()`, `_initialize_tag_register_service()`
3. **✅ ImageRepository.__init__() 更新**: 新しい初期化フロー適用
4. **✅ _get_or_create_tag_id_external() 書き換え**（Phase 1: 検索のみ）:
   - **✅ 検索**: `search_tags()` 使用（partial=False で完全一致）
   - **⏳ 登録**: Phase 2で実装予定（`TagRegisterService.register_tag()`使用）
   - **✅ エラーハンドリング**: グレースフルデグラデーション維持
5. **✅ 不要コード削除**: `self.tag_repository`, `self.tag_db_path`
6. **⏳ 単体テスト実装**: Phase 2で新APIモック、エラーケース網羅
7. **⏳ 統合テスト実行**: Phase 2で既存機能動作確認
8. **⏳ 最終検証**: Phase 2でパフォーマンス、ログ出力確認

### Phase 2: タグ登録機能実装（予定）

1. **タグ登録ロジック追加**: `_get_or_create_tag_id_external()` に登録処理を追加
   - `TagRegisterService.register_tag()` 使用
   - format_name="Lorairo", type_name="unknown"（ユーザーが後で再解決）
   - IntegrityError時の競合リトライ
2. **単体テスト追加**: 登録成功、競合リトライ、エラーハンドリング
3. **統合テスト実行**: AI生成タグの登録・検索フロー確認
4. **パフォーマンス測定**: タグ登録のレイテンシ確認

---

## 成功基準

### Phase 1（検索のみ、現状）
- ✅ MergedTagReader初期化成功（user DB自動作成、Base DBは任意）
- ✅ 既存タグ検索機能動作（`search_tags()`使用）
- ✅ エラーハンドリング正常動作（tag_id=None フォールバック）
- ✅ 既存データベースとの互換性維持
- ✅ ログ出力適切（デバッグ可能性）

### Phase 2（タグ登録、実装予定）
- ⏳ すべての単体テスト合格（85%+ カバレッジ）
- ⏳ 統合テスト合格（AI生成タグ登録フロー動作保証）
- ⏳ TagRegisterService統合成功（format_name="Lorairo", type_name="unknown"）
- ⏳ 競合検出・リトライ機能動作
- ⏳ パフォーマンス劣化なし（±5%以内）

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
- unknown type判定は `type_name == "unknown"` のみ
- `unknown` 仮置き/不足補完はタグDBツール（core）側で実装


### なぜ遅延初期化？
- `UserDatabase` は書き込み操作でのみ必要
- 初期化コスト削減（読み取り専用ケース）
- エラーハンドリングの柔軟性向上

### ✅ なぜTagRegisterServiceを使用？（設計変更）
- **旧計画**: `TagRegisterService`はQt依存（QObject継承）のため`UserDatabase`直接使用
- **実装時の変更**: `TagRegisterService`をQt非依存に再設計
  - `services/tag_register.py`: Qt非依存の`TagRegisterService`（CLI/ライブラリ/GUI共通）
  - `gui/services/tag_register_service.py`: Qt依存の`GuiTagRegisterService`（ラッパー、シグナル発行）
- **利点**:
  - 公開API互換性維持（`register_tag()`内部で`TagRegisterService`使用）
  - CLI/非GUI環境で正常動作
  - format_id/type_id 解決ロジックをサービス層で統一
  - テスト容易性向上（Qt依存なしで単体テスト可能）

### なぜ init_user_db() + default_cache_dir() を使用？（2025-12-30更新）
- **LoRAIroの動作モード**: CLI/GUIアプリケーションとして genai-tag-db-tools を使用（ライブラリモードではない）
- CLI/GUIは `--user-db-dir` 未指定ならデフォルトパス（HF_HOME準拠）で自動作成
- ライブラリ利用（他アプリから genai-tag-db-tools を使う場合）は `user_db_dir` を必須にし、未指定なら初期化前にエラー
- `init_user_db()` がユーザーDBディレクトリとSQLiteファイルを自動作成・初期化
- Base DBは任意（無くてもuser DBのみで動作）
- テスト環境でもユーザーDBを自動セットアップ可能
- CLIとGUI両方で一貫した動作を保証

### なぜ format_name をアプリ名にする？
- インストール/起動しているプロジェクトごとに区別できる
- 既存DB連携がない場合でも衝突を避けられる
- 将来的に他フォーマット（danbooru/e621等）への変換機能追加が可能

### ✅ なぜユーザーDB format_id を1000番台予約？（2025-12-30追加）
- **問題**: ベースDB未取得時にユーザーDBがformat_id=1から開始 → 後でベースDBダウンロードすると衝突
- **問題**: ベースDB更新時に新format追加 → 既存ユーザーDB IDと衝突の可能性
- **解決**: ユーザーDBは常に1000番台以降を使用（ベースDB: 1-999予約）
- **既存DBの扱い**: 既存ユーザーDBに1000未満のformat_idがある場合、自動補正は行わない（データ整合性保持のため）
  - 新規format作成時のみ1000番台を使用
  - 既存formatは現在のIDを維持
- **利点**:
  - ベースDBの有無・状態に完全非依存（環境差異なし）
  - 処理がシンプル（ベースDB読み取り不要）
  - ID範囲が明確（衝突リスクゼロ）
  - 999個のベースformat十分（実際は数十個）
- **実装**: `USER_DB_FORMAT_ID_OFFSET = 1000`定数で管理

### なぜ ensure_databases() 不要？
- ユーザー要件: デフォルトDBで十分、自動ダウンロード不要
- 既存の bundled database で問題なく動作
- 実装スコープ削減でリスク最小化
