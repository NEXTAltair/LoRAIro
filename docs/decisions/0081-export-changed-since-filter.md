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

`ExportTab` を 3 ペイン構成へ再設計した際、旧 `DatasetExportWidget` が備えていた changed-since フィルタが一時的に失われた。増分エクスポートでは、ステージング集合のうち指定日時以降にタグが変更された画像だけを抽出して書き出す必要がある。

## Decision

`ExportOverlayBar` に再利用可能な `ChangedSinceFilterWidget` を組み込む。`ExportTab` は検証(validate)およびエクスポート(export)の実行ごとに `DatasetExportService.filter_changed_since(staged_ids, since)` を呼び出し、実際の対象画像を再計算する。出力オーバーレイは、changed-since フィルタで絞り込んだ実対象に対して適用する。

## Rationale

日時入力 UI を `widgets/` 配下の独立した小さなコンポーネントに分離することで、検索パネル系の日付入力と同じ Qt ウィジェット境界で再利用できる。

旧実装のように絞り込み済みの ID リストを状態として保持する方式では、日時変更後に古い対象のまま書き出してしまう危険がある。そのため、ボタン押下時に都度再計算する方式を正準とする。

## Consequences

- `ExportTab` における実際のエクスポート対象は、`current_export_ids()` ではなく `_effective_export_ids()` で解決する。
- changed-since フィルタによる絞り込み結果が空の場合は、出力先選択のステップへ進まない。
- 将来 `SearchPanel` 側の日付 UI を単一日時入力へ統一する際にも、`ChangedSinceFilterWidget` をそのまま再利用できる。
