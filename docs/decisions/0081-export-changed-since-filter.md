---
type: adr
title: Export Changed-Since Filter Reintroduction
status: Accepted
timestamp: 2026-06-28
tags:
  - gui
  - export
  - staging
  - qt
---

# Export Changed-Since Filter Reintroduction

## Context

ExportTab の 3 ペイン再構成で、旧 DatasetExportWidget が持っていた changed-since フィルタが
一時的に失われた。増分エクスポートでは、ステージング集合のうち指定日時以降にタグ変更が
あった画像だけを書き出す必要がある。

## Decision

ExportOverlayBar に再利用可能な `ChangedSinceFilterWidget` を組み込み、ExportTab は
validate/export のたびに `DatasetExportService.filter_changed_since(staged_ids, since)` で
実対象を再計算する。overlay は changed-since で絞った実対象に対して適用する。

## Rationale

日時 UI を `widgets/` の小さなコンポーネントに分けることで、検索パネル系の日付入力と同じ
Qt ウィジェット境界で再利用できる。旧実装のように絞り込み済み ID を保持する方法は、
日時変更後に stale な対象で書き出す危険があるため、ボタン押下時の再計算を正準にする。

## Consequences

ExportTab の実エクスポート対象は `current_export_ids()` ではなく `_effective_export_ids()` で
解決する。changed-since 結果が空の場合は出力先選択へ進まない。将来 SearchPanel 側の日付 UI
を単一日時入力へ寄せる場合も、`ChangedSinceFilterWidget` を直接再利用する。
