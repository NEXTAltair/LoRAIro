# 作業記録: source_effects の精度改善（同値上書きを抑止）

## 日付
2025-12-17

## 背景
`source_effects.tsv` は「MITのどのCSVが実際にDBへ影響したか」を判断する根拠として使う。
しかし以前の実装では、`TAG_STATUS` が `INSERT OR REPLACE` だったため、**値が変わっていなくてもREPLACE扱いで更新**され、`db_changes` が増えてしまい、出典判定の意味が薄くなる。

## 変更内容
### 1) TAG_STATUS: 値が変わる時だけ更新
- 追加: `builder.py` に `_TAG_STATUS_UPSERT_IF_CHANGED_SQL`
- `TAG_STATUS` の書き込みを `INSERT ... ON CONFLICT(tag_id, format_id) DO UPDATE ... WHERE (差分がある時だけ)` に変更。
- 差分判定は `IS NOT` を使用（NULLも含めて同値判定が可能）。

### 2) TAG_USAGE_COUNTS: 大きい値のときだけ更新（MAXマージの同値更新抑止）
- 追加: `builder.py` に `_TAG_USAGE_COUNTS_UPSERT_IF_GREATER_SQL`
- 通常のusage counts取り込みで、既存値より大きい場合のみ更新するように変更。
- Danbooru snapshot の `usage_counts_replaced`（DELETE→INSERTでの全置換）は別扱いのまま。

### 3) source_effects.tsv の出力（既存）
- 既に追加済みの `<report_dir>/source_effects.tsv` は、上記変更により `db_changes` が「実際に値が変わった分」に近づく。

## 影響
- `source_effects.tsv` の `db_changes` が、同値上書きによるノイズで膨らみにくくなる。
- 「翻訳だけでも追加されたら表記対象」という運用とも整合。

## テスト
- 追加: `tests/unit/test_idempotent_upserts.py`
  - TAG_STATUS: 同値UPSERTを2回実行して2回目の `total_changes` が増えないこと
  - TAG_USAGE_COUNTS: 同値/小さい値は更新しない、大きい値のみ更新すること
- `pytest local_packages/genai-tag-db-dataset-builder -q` -> 全テスト通過
