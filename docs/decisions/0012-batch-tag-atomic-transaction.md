# ADR 0012: Batch Tag Atomic Transaction Fix

- **日付**: 2026-01-06
- **ステータス**: Accepted

## Context

`add_tag_batch()` の Docstring に「全件一括コミット、エラー時は自動ロールバック」と記載されていたが、実装は画像ごとに `save_annotations()` を個別呼び出しており、各回で個別コミットされていた（部分的成功が可能な状態）。

## Decision

**Repository 層に原子的バッチメソッドを追加**:

```python
# db_repository.py に新メソッド
def add_tag_to_images_batch(image_ids, tag, model_id) -> tuple[bool, int]:
    with self.session_factory() as session:
        try:
            # 全画像の既存タグを1回のクエリで取得（効率化）
            existing_tags = session.execute(
                select(Tag).where(Tag.image_id.in_(image_ids))
            ).scalars().all()
            # ... 重複チェック、タグ作成 ...
            session.commit()  # 全件まとめて1回のみ
            return (True, added_count)
        except SQLAlchemyError:
            session.rollback()  # エラー時は全件ロールバック
            raise
```

## Rationale

Hook feedback により問題が発見された。Docstring と実装の乖離は典型的な技術的負債パターン。単一セッションで処理することで原子性と効率性（N+1 → 1 クエリ）を同時に解決。

## Consequences

- バッチ操作が全件成功 or 全件ロールバックの原子性を保証
- N 枚の画像に対して N 回のクエリ → 2 回のクエリ（既存タグ一括取得 + commit）に削減
- Service 層の `add_tag_batch()` も新しい Repository メソッドを呼ぶよう更新
