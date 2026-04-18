# ADR 0015: Manual Rating Storage Unification

- **日付**: 2026-04-18
- **ステータス**: Accepted

## Context

`Image.manual_rating` カラムへの書き込み (`update_manual_rating`) と、`Rating` テーブル
(`model_id = MANUAL_EDIT`) からの読み込み (`_apply_manual_filters`) が異なるテーブルを
参照しており、フィルタが常に空を返すバグが発生した (Issue #119)。

### 歴史的経緯

1. **2025-04-16**: 初期スキーマで `Image.manual_rating` カラムと `Rating` テーブルを並行追加。当初は `_apply_manual_filters` も `Image.manual_rating` を直接参照していた。
2. **2025-11-28 (Issue #4)**: Rating/Score 更新機能実装時に `_apply_manual_filters` を `Rating(MANUAL_EDIT)` 参照に変更。しかし `update_manual_rating` の対応変更が見落とされた。
3. **2026-04-18 (Issue #118)**: NSFW 判定でも同パターンの書き込み・読み込み乖離が顕在化。
4. **2026-04-18 (Issue #119)**: manual_rating フィルタの不整合が BDD テストで確認。

`Score` テーブルはすでに「`Image` にスコアカラムなし、`Score` テーブルのみ」のパターンで統一されており、`Rating` テーブルも同様の設計が期待されていた。

## Decision

1. **Manual rating を `Rating` テーブル (`model_id = MANUAL_EDIT`) に一元化する。**
2. **`Image.manual_rating` カラムを廃止する。**
3. **「解除」操作 (`rating=None`) は既存 MANUAL_EDIT レコードの DELETE とする。**

「解除」に DELETE を採用する理由: ADR 0002 の「履歴保持」方針は主に AI モデルの評価結果を対象としている。手動評価は「最新の意図」のみが意味を持つため、解除操作は全削除が自然。この例外は本 ADR に明示する。

## Rationale

### なぜ Score テーブルパターンに統一するか

- `Score` テーブルに `Image.score` カラムが存在しないパターンが既に確立されている。同じ設計を `Rating` / manual_rating にも適用することでスキーマの一貫性が得られる。
- カラムとテーブルの二重管理を解消することで、書き込み・読み込みの対称性バグが構造的に発生不能になる。

### なぜ Image.manual_rating 参照に戻さないか (選択肢 B/G)

- `Rating` テーブルに MANUAL_EDIT モデル概念が既に実装されており、`_apply_nsfw_filter` も MANUAL_EDIT を参照している。読み込み側を `Image.manual_rating` カラム参照に戻すと `Score` テーブルパターンとの非対称が残る。
- `Image.manual_rating` カラムへの統一は将来の「複数モデルでの評価履歴」機能と相容れない。

### 却下した選択肢

| 選択肢 | 却下理由 |
|--------|---------|
| B: `_apply_manual_filters` をカラム参照に戻す | Score テーブルパターンと非対称 |
| C: OR 検索（暫定移行） | 二重管理を恒久化する |
| D: SQLAlchemy `hybrid_property` 仮想カラム化 | カラムが残るため本質問題を先送り |
| E: `ManualRatingService` 新設 | YAGNI、ADR 0001 の Repository 責務分割 |
| G: カラム参照に完全統一 | Score パターンとの非対称、将来拡張性なし |

## Consequences

### 良い点

- 書き込み先と読み込み先が同一テーブルに統一され、Issue #119/#118 類似バグが構造的に防止される。
- `Score` テーブルパターンとの設計整合性が得られる。
- `_apply_nsfw_filter` の MANUAL_EDIT 参照が本修正で初めて機能する（Issue #118 の未使用コードが活性化）。
- 手動編集履歴が Rating テーブルに自動的に保存される。

### 悪い点・トレードオフ

- Alembic マイグレーション 1 回が必要（既存データを Rating テーブルへ移行）。
- 「解除」操作が DELETE のため、過去の手動評価履歴は残らない（ADR 0002 の明示例外）。

## Related

- ADR 0002: Database Schema Decisions（履歴保持方針）
- Issue #118: NSFW フィルタの類似バグ
- Issue #119: manual_rating フィルタのバグ
- `src/lorairo/database/migrations/versions/e4a8f1b2c3d5_remove_image_manual_rating_unify_to_.py`
