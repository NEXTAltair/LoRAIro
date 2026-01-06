# genai-tag-db-tools: tags_v3.db 参照の最終クリーンアップ TODO

**日付**: 2025-12-30  
**コンテキスト**: Phase 2完了後、tags_v3.dbへの直接参照が残存している可能性  
**目的**: レガシー参照を完全に削除し、公開APIのみを使用する状態に移行

## 背景

Phase 2（タグ登録ロジック完成）の完了により、以下が実装済み：
- format_id 1000+予約実装
- type_name自動作成ロジック
- TagRegisterServiceのテスト完全カバレッジ（75%+）

しかし、以下の可能性が残っている：
- tags_v3.db への直接ファイルパス参照
- TagRepository の旧実装への依存
- 非推奨API（`genai_tag_db_tools.data.*`）の使用

## 調査項目

### 1. tags_v3.db 直接参照の検索

```bash
cd local_packages/genai-tag-db-tools
grep -r "tags_v3" --exclude-dir=.git --exclude-dir=__pycache__ .
```

**確認箇所**:
- テストコード（許容: テスト用フィクスチャでの使用は問題なし）
- 実装コード（要削除: 直接パス参照は公開API経由に置き換え）
- ドキュメント（要更新: 古い使用例の更新）

### 2. 旧Repository API使用箇所の検索

```bash
grep -r "from genai_tag_db_tools.data" --exclude-dir=.git .
grep -r "TagRepository()" --exclude-dir=.git .
```

**確認対象**:
- CLI実装（`cli.py`）
- GUI実装（`gui/`）
- サービス層（`services/`）
- テストコード（`tests/`）

### 3. 公開API移行チェックリスト

**必須移行**:
- [ ] `TagRepository` → `MergedTagReader` + `TagRegisterService`
- [ ] `tags_v3.db` 直接パス → `get_default_reader()` / `init_user_db()`
- [ ] 非推奨import → 公開API import

**推奨移行**:
- [ ] `TagCleaner` インスタンス化 → 静的メソッド使用（`TagCleaner.clean_format()`）
- [ ] 直接DB接続 → サービス層API経由

## 削除基準

### 削除して良い参照

1. **実装コードの直接パス参照**
   - `tags_v3.db` のファイルパス文字列
   - `Path("tags_v3.db")` などの直接構築
   - 環境変数からのtags_v3.dbパス取得

2. **旧APIインポート**
   - `from genai_tag_db_tools.data.tag_repository import TagRepository`
   - `from genai_tag_db_tools.data.*` 系統

3. **直接DB初期化コード**
   - `engine = create_engine("sqlite:///tags_v3.db")`
   - 手動SessionFactory作成

### 残して良い参照

1. **テストフィクスチャ**
   - `tests/resources/tags_v3.db` などのテスト用DBファイル
   - `@pytest.fixture` 内での一時DB作成

2. **ドキュメント内の言及**
   - 設計文書での仕様説明
   - マイグレーションガイドでの旧実装説明

3. **スキーマ定義**
   - `schema.py` のテーブル定義（tags_v3.db と同じスキーマを使用）

## 実装手順

1. **grep検索実行** → 参照箇所リストアップ
2. **各箇所の判定** → 削除対象 or 残存許可
3. **削除対象の置き換え** → 公開API使用
4. **テスト実行** → 全テスト通過確認
5. **最終検索** → `tags_v3` 参照がテストのみになったことを確認

## 関連メモリ

- [genai_tag_db_tools_phase2_tag_registration_completion_2025_12_30.md](.serena/memories/genai_tag_db_tools_phase2_tag_registration_completion_2025_12_30.md) - Phase 2完了記録
- [plan_parallel_humming_garden_2025_12_28.md](.serena/memories/plan_parallel_humming_garden_2025_12_28.md) - 公開API移行計画

## 優先度

**低** - Phase 2完了後の品質向上タスク  
**前提**: Phase 2.5（不完全タグ管理）実装前に完了推奨

## メモ

このクリーンアップは、Phase 2.5実装前に完了することで、新機能実装時の混乱を防ぐ。
