# レガシーテストファイル削除記録 (2025-08-30)

## 削除したファイル
- `tests/unit/database/test_image_database_manager_extended.py`

## 削除理由

### 構造的不整合
1. **コンストラクタ不整合**: `ImageDatabaseManager(":memory:")` → 現在は `ImageDatabaseManager(repository, config_service, fsm?)`
2. **スキーマ不整合**: `from lorairo.database.schema import Annotation` → 現在のスキーマに`Annotation`クラス不存在
3. **メソッド不整合**: テストしているメソッドが現在の実装と一致しない

### 修復不可能な理由
- テストファイル全体が古いアーキテクチャ前提で作成
- 現在のスキーマ: `Caption`, `Tag`, `Score`, `Rating` 個別クラス
- 過去のスキーマ: `Annotation` 統合クラス（存在しない）
- メソッドシグネチャの根本的変更

### 影響評価
- **削除影響**: なし（テストが実行不可能だったため）
- **カバレッジ**: 他のテストで `ImageDatabaseManager` はカバー済み
  - `conftest.py` で適切なテストfixture提供
  - `test_database_worker.py` で実際の連携テスト実行
- **回帰リスク**: なし（既存機能への影響なし確認済み）

### 正常なテストファイル確認済み
- `tests/conftest.py` - 現在のスキーマ対応済み
- `tests/unit/workers/test_database_worker.py` - 正しいコンストラクタ使用
- `tests/unit/database/test_tag_database_duplicate_handling.py` - 新規作成、完全動作

## 品質保証
- ✅ 他のテストファイルに構造的問題なし
- ✅ 既存テストスイート正常動作 (17 passed)
- ✅ 新規テスト正常動作 (5 passed, 2 skipped)
- ✅ コード品質基準維持 (ruff check pass)

レガシーコード削除により、テストスイートの整合性と保守性が向上しました。