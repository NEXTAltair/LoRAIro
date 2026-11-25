---
type: ADR
title: Batch Tag Atomic Transaction Fix
status: Accepted
timestamp: 2026-01-06
tags: []
---
# ADR 0012: Batch Tag Atomic Transaction Fix

## Context

`add_tag_batch()` の Docstring には「全件一括コミット、エラー時は自動ロールバック」と記載されていた。しかし実際の実装では、画像ごとに `save_annotations()` を個別に呼び出しており、1 件ずつコミットしていた。そのため、処理の途中でエラーが発生すると一部の画像だけが更新される状態になっていた。

## Decision

Repository 層に原子的なバッチ処理メソッド `add_tag_to_images_batch()` を追加する。

```python
# db_repository.py に新メソッド
def add_tag_to_images_batch(image_ids, tag, model_id) -> tuple[bool, int]:
    with self.session_factory() as session:
        try:
            # 全画像の既存タグを1回のクエリで取得(効率化)
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

Hook のフィードバックにより、この問題が発見された。Docstring と実装の乖離は、典型的な技術的負債である。

単一のセッションで全件をまとめて処理することで、トランザクションの原子性とクエリ効率(N+1 回から 1 回への削減)を同時に解決できる。

## Consequences

- バッチ操作において、全件成功または全件ロールバックの原子性が保証される。
- N 枚の画像に対するクエリ回数が、N 回から 2 回(既存タグの一括取得とコミット)に削減される。
- Service 層の `add_tag_batch()` も、新しい Repository メソッドを呼び出すように更新する。
