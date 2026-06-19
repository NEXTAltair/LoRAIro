---
type: ADR
title: TRACE Level for Per-Item Diagnostics
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0047: TRACE Level for Per-Item Diagnostics

- **関連 Issue**: [NEXTAltair/LoRAIro#584](https://github.com/NEXTAltair/LoRAIro/issues/584)
- **関連 ADR**: [ADR 0043](0043-db-core-logging-loguru-unification.md), [ADR 0045](0045-large-search-result-log-level.md)

## Context

`logs/lorairo.log` を `level = "DEBUG"` で取得すると、DEBUG が全体の約 92% を占め、
本来の診断情報が per-item の大量ログに埋もれて「デバッグ用途としても読めない」状態だった。

主なノイズ源 (1 セッション実測):

- `ModelCheckboxWidget` の初期化系ログ: widget 1 個生成ごとに 4 行 × 約 698 回 ≈ 2,792 行
- `db_core.resolve_stored_path`「パス解決」: 画像ごと × 857 回
- `dataset_state.get_image_by_id`「正常な状態」: 1 ルックアップごと × 671 回
- `model_selection_service.load_models` のモデル別ループ: 211 件 × 複数回
- `image._format_annotations_for_metadata`: 画像ごと × 395 回

既存 `.claude/rules/logging.md` は「per-item 詳細は DEBUG」と定義していたが、
1 操作で数百〜数千件出る firehose を DEBUG に置くと、DEBUG の可読性が崩壊する。

ロギング基盤 (`utils/log.py`) は `[log.levels]` でモジュール別レベル制御を既にサポートする
一方、`LEVEL_NAME_TO_NO` に loguru の TRACE (level.no=5) が未登録で、config から TRACE を
有効化できなかった。

## Decision

DEBUG より下位の **TRACE レベル** を per-item firehose 専用に導入する。

- `utils/log.py` の `LEVEL_NAME_TO_NO` に `"TRACE": 5` を追加し、`[log] level` / `[log.levels]`
  から有効化可能にする。sink は `level=0` でフィルタ関数に委譲済みのため追加変更は不要。
- ログレベルの役割を再定義する (`.claude/rules/logging.md` に反映):
  - **TRACE**: 1 操作で数百件以上出る per-item 詳細 (パス解決・annotation 整形・モデル別ループ・
    チェックボックスごとの選択変化)。既定の `DEBUG` 実行では抑制され、明示有効化時のみ出力。
  - **DEBUG**: 操作・コンポーネント単位の診断 (1 操作で高々十数件)。1 選択イベント / 1 ページ描画など。
- 「per-item 診断」のうち診断価値が低い 2 種は TRACE ですらなく **削除** する:
  - オブジェクト生成のたびに出る初期化ログ (`ModelCheckboxWidget initialized` 等)。
  - 正常系を毎回確認するログ (`画像ID … を発見（正常な状態）`)。異常系・not-found のみ残す。

## Consequences

`level = "DEBUG"` での通常デバッグは「操作単位の有用情報」中心になり可読性が回復する。
per-item の深掘りが必要なときは `level = "TRACE"` または `[log.levels]` でモジュール別に
TRACE を有効化して firehose を得られる。

`.claude/rules/logging.md` の「per-item は DEBUG」という旧定義は本 ADR で更新される
(per-item firehose は TRACE)。INFO / WARNING / ERROR の方針 (ADR 0045 含む) は不変。

本 ADR はログレベルの規約変更であり、ログの呼び出し回数を減らす root-cause 修正
(モデル再構築の抑制・`get_image_by_id` の O(1) 化・`resolve_stored_path` のキャッシュ) は
同 Issue #584 で別途実施した。