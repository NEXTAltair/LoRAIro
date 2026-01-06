# Batch Tag Addition - Atomic Transaction Fix

**Date**: 2026-01-06
**Commit**: 22599de
**Status**: ✅ Completed

## 問題の特定

Hook feedback により、`add_tag_batch()` の実装に原子性の問題が発見された:

### 問題点
- Docstring: "全件一括コミット、エラー時は自動ロールバック"
- 実装: `save_annotations()` を画像ごとに呼び出し、各回で個別にコミット
- 結果: 部分的成功が可能（例: 100枚中50枚のみ成功）

### 根本原因
```python
# 旧実装（問題あり）
for image_id in image_ids:
    # ...既存タグ取得、重複チェック...
    self.db_manager.repository.save_annotations(  # <-- 個別コミット
        image_id=image_id,
        annotations={"tags": [tag_data]},
    )
```

`save_annotations()` は内部で `session.commit()` を呼ぶため、各画像で個別にトランザクションが完了してしまう。

## 解決策

### 1. Repository層に原子的バッチメソッド追加

**ファイル**: [src/lorairo/database/db_repository.py](src/lorairo/database/db_repository.py:670-769)

**新メソッド**: `add_tag_to_images_batch(image_ids, tag, model_id) -> tuple[bool, int]`

**実装の特徴**:
- 単一 session で全画像を処理
- 効率的なクエリ: 全画像の既存タグを1回のクエリで取得
- 全件成功 or 全件ロールバック（`session.commit()` は最後に1回のみ）
- 明示的な `session.rollback()` でエラー処理

```python
with self.session_factory() as session:
    try:
        # 全画像の既存タグを一括取得（効率化）
        existing_tags_stmt = select(Tag).where(Tag.image_id.in_(image_ids))
        all_existing_tags = session.execute(existing_tags_stmt).scalars().all()
        
        # ...重複チェック、タグ作成...
        
        session.commit()  # <-- 全件まとめて1回のみコミット
        return (True, added_count)
    except SQLAlchemyError as e:
        session.rollback()  # <-- エラー時は全件ロールバック
        raise
```

### 2. Service層の更新

**ファイル**: [src/lorairo/gui/services/image_db_write_service.py](src/lorairo/gui/services/image_db_write_service.py:301-357)

**変更内容**:
- 新しい `add_tag_to_images_batch()` を呼び出すように変更
- シンプルなラッパーに簡素化
- 原子性の責務をRepository層に委譲

```python
def add_tag_batch(self, image_ids: list[int], tag: str) -> bool:
    model_id = self.db_manager.get_manual_edit_model_id()
    success, added_count = self.db_manager.repository.add_tag_to_images_batch(
        image_ids=image_ids,
        tag=tag,
        model_id=model_id,
    )
    return success
```

### 3. テストの更新

**ファイル**: [tests/unit/gui/services/test_image_db_write_service.py](tests/unit/gui/services/test_image_db_write_service.py:197-262)

**変更内容**:
- 旧モックを削除: `get_image_annotations`, `save_annotations`
- 新モックを追加: `add_tag_to_images_batch.return_value = (True, N)`
- 5つの単体テスト全てを新しいAPIに適合

## 技術的改善点

### パフォーマンス向上
- **旧実装**: N回のクエリ（各画像で `get_image_annotations` + `save_annotations`）
- **新実装**: 1回のクエリ（全画像の既存タグを一括取得）

### アーキテクチャの明確化
- **Repository層**: データベース操作とトランザクション管理
- **Service層**: GUIラッパー、Signal/Slotサポート

### データ一貫性の保証
- 全件成功 or 全件失敗（部分的成功は不可能）
- SQLAlchemy sessionトランザクションで保証

## テスト結果

### Unit Tests（5 tests）
```bash
uv run pytest tests/unit/gui/services/test_image_db_write_service.py -k "add_tag_batch"
# ✅ 5 passed in 0.89s
```

**テストケース**:
- `test_add_tag_batch_success` - 成功ケース（3枚追加）
- `test_add_tag_batch_duplicate_skip` - 重複スキップ（0枚追加）
- `test_add_tag_batch_empty_image_ids` - 空リストバリデーション
- `test_add_tag_batch_empty_tag` - 空タグバリデーション
- `test_add_tag_batch_exception_handling` - 例外時の False 返却

### Integration Tests（11 tests）
```bash
uv run pytest tests/integration/gui/test_batch_tag_add_integration.py
# ✅ 11 passed in 0.97s
```

**既存の統合テストは変更なしで合格** - Repository層の変更がService層の契約を維持していることを確認。

## コミット情報

**Commit**: 22599de
**Message**: "fix: Implement atomic transaction for batch tag addition"
**Date**: 2026-01-06

**変更統計**:
- `src/lorairo/database/db_repository.py`: +95 lines（新メソッド追加）
- `src/lorairo/gui/services/image_db_write_service.py`: +22 -37 lines（簡素化）
- `tests/.../test_image_db_write_service.py`: +21 -16 lines（モック更新）

## 残存する既知の制限

None - 原子性は完全に実装されました。

## 関連ドキュメント

- Hook Feedback: `.serena/memories/batch_tag_addition_ui_redesign_completion_2026_01_05.md`
- Implementation Plan: `/home/vscode/.claude/plans/robust-skipping-hopper.md`
- Repository Pattern: `docs/services.md` - ImageRepository

## 次のステップ

この修正により、バッチタグ追加機能は完全に実装されました:
- ✅ Phase 1: UI Foundation
- ✅ Phase 2: Service Layer & Selection Sync
- ✅ Phase 3: Integration & Testing
- ✅ Atomic Transaction Fix（このコミット）

**実装完了** - Ready to merge into main branch.
