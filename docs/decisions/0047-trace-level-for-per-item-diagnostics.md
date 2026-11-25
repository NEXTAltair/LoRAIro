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

`logs/lorairo.log` を `level = "DEBUG"` で取得したところ、`DEBUG` ログが全体の約 92% を占めていた。本来の診断情報が項目ごとの大量ログに埋もれ、デバッグ用途としても読めない状態になっていた。

1 セッションの実測で確認された主なノイズ源は以下のとおりである。

- `ModelCheckboxWidget` の初期化系ログ:ウィジェット 1 個の生成ごとに 4 行 × 約 698 回 ≈ 2,792 行
- `db_core.resolve_stored_path` の「パス解決」ログ:画像ごと × 857 回
- `dataset_state.get_image_by_id` の「正常な状態」ログ:1 ルックアップごと × 671 回
- `model_selection_service.load_models` のモデル別ループログ:211 件 × 複数回
- `image._format_annotations_for_metadata` のログ:画像ごと × 395 回

既存の `.claude/rules/logging.md` では「項目ごとの詳細は DEBUG」と定義していた。しかし、1 回の操作で数百〜数千件が出力される大量ログ(firehose)を `DEBUG` に置くと、`DEBUG` 自体の可読性が損なわれる。

一方、ロギング基盤(`utils/log.py`)は `[log.levels]` によるモジュール別のレベル制御をすでにサポートしている。しかし、`LEVEL_NAME_TO_NO` に Loguru の `TRACE`(`level.no=5`)が未登録だったため、設定から `TRACE` を有効化できなかった。

## Decision

`DEBUG` より下位の **`TRACE` レベル**を、項目ごとの大量ログ専用として導入する。

### 1. ロギング基盤への `TRACE` 登録

- `utils/log.py` の `LEVEL_NAME_TO_NO` に `"TRACE": 5` を追加し、`[log] level` および `[log.levels]` から有効化できるようにする。
- シンクはすでに `level=0` でフィルタ関数に委譲しているため、追加の変更は不要である。

### 2. ログレベルの役割の再定義

`.claude/rules/logging.md` の定義を以下のように更新する。

- **TRACE**:1 回の操作で数百件以上出力される項目ごとの詳細ログ(パス解決、アノテーション整形、モデル別ループ、チェックボックスごとの選択変化など)。既定の `DEBUG` 実行では抑制し、明示的に有効化した場合のみ出力する。
- **DEBUG**:操作単位・コンポーネント単位の診断ログ(1 回の操作で多くとも十数件程度)。1 回の選択イベントや 1 ページの描画などを対象とする。

### 3. 診断価値の低い項目ごとログの削除

項目ごとの診断ログのうち、診断価値が低い以下の 2 種類は `TRACE` へ移動せず**削除**する。

- オブジェクト生成のたびに出力される初期化ログ(`ModelCheckboxWidget initialized` など)。
- 正常系を毎回確認するログ(`画像ID … を発見(正常な状態)` など)。異常系と未検出(not-found)のログのみ残す。

## Consequences

`level = "DEBUG"` での通常デバッグ時は、操作単位の有用な情報が中心となり可読性が回復する。項目ごとの詳細な追跡が必要な場合は、`level = "TRACE"` または `[log.levels]` でモジュール別に `TRACE` を有効化することで大量ログを取得できる。

`.claude/rules/logging.md` における「項目ごとの詳細は DEBUG」という旧定義は、本 ADR により「項目ごとの大量ログは TRACE」へ更新される。なお、`INFO`、`WARNING`、`ERROR` の運用方針(ADR 0045 を含む)は変更しない。

本 ADR はログレベルの規約変更を扱う。ログの呼び出し回数そのものを減らす根本原因の修正(モデル再構築の抑制、`get_image_by_id` の O(1) 化、`resolve_stored_path` のキャッシュ導入)は、同じ Issue #584 で別途実施した。
