---
type: ADR
title: Manual Rating Storage Unification
status: Accepted
timestamp: 2026-04-18
tags: []
---
# ADR 0015: Manual Rating Storage Unification

## Context

手動レーティングの書き込み処理(`update_manual_rating`)は `Image.manual_rating` カラムを更新する一方、読み込み処理(`_apply_manual_filters`)は `Rating` テーブル(`model_id = MANUAL_EDIT`)を参照していた。書き込み先と読み込み先が異なるテーブルを参照していたため、フィルタ検索が常に空を返す不具合が発生した(Issue #119)。

### 歴史的経緯

1. **2025-04-16**:初期スキーマで `Image.manual_rating` カラムと `Rating` テーブルを並行して追加した。当初は `_apply_manual_filters` も `Image.manual_rating` を直接参照していた。
2. **2025-11-28(Issue #4)**:Rating および Score の更新機能を実装した際、`_apply_manual_filters` の参照先を `Rating(MANUAL_EDIT)` へ変更した。しかし、`update_manual_rating` 側の変更が見落とされた。
3. **2026-04-18(Issue #118)**:NSFW 判定でも同じ構造の書き込み・読み込み乖離が顕在化した。
4. **2026-04-18(Issue #119)**:`manual_rating` フィルタの不整合が BDD テストで確認された。

なお、`Score` テーブルではすでに「`Image` テーブルにスコアカラムを持たず、`Score` テーブルのみで管理する」設計へ統一されている。`Rating` テーブルについても、同様の設計が期待されていた。

## Decision

1. **手動レーティングの保存先を `Rating` テーブル(`model_id = MANUAL_EDIT`)に一元化する。**
2. **`Image.manual_rating` カラムを廃止する。**
3. **レーティングの「解除」操作(`rating=None`)は、既存の `MANUAL_EDIT` レコードを DELETE することで表現する。**

「解除」に DELETE を採用するのは、ADR 0002 の「履歴保持」方針が主に AI モデルの評価結果を対象としているためである。手動評価は「最新の意図」のみが意味を持つため、解除時は既存レコードを削除する方が自然である。この扱いは、ADR 0002 の明示的な例外として本 ADR に記録する。

## Rationale

### なぜ Score テーブルパターンに統一するか

- `Score` テーブルでは、`Image.score` カラムを持たない設計がすでに確立されている。同じパターンを `Rating` および手動レーティングにも適用することで、スキーマの一貫性を保てる。
- カラムとテーブルの二重管理を解消することで、書き込みと読み込みの非対称性による不具合を構造的に防げる。

### なぜ Image.manual_rating 参照に戻さないか (選択肢 B/G)

- `Rating` テーブルにはすでに `MANUAL_EDIT` モデルの概念が実装されており、`_apply_nsfw_filter` も `MANUAL_EDIT` を参照している。読み込み側を `Image.manual_rating` カラム参照へ戻すと、`Score` テーブルとの非対称性が残ってしまう。
- `Image.manual_rating` カラムへ統一すると、将来的な「複数モデルによる評価履歴」機能と相容れなくなる。

### 却下した選択肢

| 選択肢 | 却下理由 |
|--------|---------|
| B:`_apply_manual_filters` をカラム参照に戻す | `Score` テーブルパターンと非対称になる |
| C:OR 検索による暫定移行 | 二重管理を恒久化させてしまう |
| D:SQLAlchemy の `hybrid_property` による仮想カラム化 | カラムが残るため本質的な問題を先送りすることになる |
| E:`ManualRatingService` の新設 | YAGNI に反し、ADR 0001 の Repository 責務分割とも不整合 |
| G:カラム参照への完全統一 | `Score` パターンと非対称になり、将来の拡張性も失われる |

## Consequences

### 良い点

- 書き込み先と読み込み先が同一テーブルに統一され、Issue #119 や Issue #118 に類似した不具合を構造的に防止できる。
- `Score` テーブルパターンとの設計整合性が得られる。
- `_apply_nsfw_filter` の `MANUAL_EDIT` 参照が本修正によって初めて機能する(Issue #118 の未使用コードが有効化される)。
- 手動編集の記録が `Rating` テーブルへ自動的に保存される。

### 悪い点・トレードオフ

- 既存データを `Rating` テーブルへ移行するため、Alembic マイグレーションを 1 回実施する必要がある。
- 「解除」操作が DELETE であるため、過去の手動評価履歴は残らない(ADR 0002 の明示的な例外)。

### 後続 ADR との関係

ADR 0031 では、AI モデルが返すモデル固有のレーティングも同一の `ratings` テーブルへ保存する方針を追加している。これは本 ADR の「手動レーティングを `Rating` テーブルへ一元化する」判断を拡張するものである。手動評価では引き続き `model_id = MANUAL_EDIT` と DELETE による解除を使用する。モデル出力のマッピング・信頼度・生ラベルの扱いについては ADR 0031 に従う。

## Related

- ADR 0002: Database Schema Decisions(履歴保持方針)
- ADR 0031: AI Rating Mapping to Canonical Rating
- Issue #118: NSFW フィルタの類似バグ
- Issue #119: `manual_rating` フィルタのバグ
- `src/lorairo/database/migrations/versions/e4a8f1b2c3d5_remove_image_manual_rating_unify_to_.py`
