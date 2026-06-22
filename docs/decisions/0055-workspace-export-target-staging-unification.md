---
type: ADR
title: Workspace Export Target = Staging Set / Selection-Source Unification
status: Accepted
timestamp: 2026-06-04
tags: []
---
# ADR 0055: Workspace Export Target = Staging Set / Selection-Source Unification

- **関連 Issue**: #610 (epic), #611 (S1 入口), #612 (S2 接続), #613 (S3 picker), #614 (S4 changed-since), #615 (S5 解像度UI)
- **一部改訂**: ADR 0074 — 統一対象 (ステージング集合) の SSoT を `StagingWidget` から `StagingStateManager` へ移管。3 者が同一集合を指す統一の意図は不変。

## Context

GUI の画像エクスポート導線が「悪い」と報告された (#610)。調査の結果、本質は画面遷移ではなく
**「エクスポート対象が何か曖昧」というセマンティクスの問題**であった。

検証で判明した現状:

1. **入口がメニュー奥のみ**: エクスポートは `MainWindow.actionExport`（ツール→エクスポート, Ctrl+Shift+E）
   からしか起動できず、3カラムの作業画面に出口が無い。
2. **対象解決が機能間で分裂**:
   - アノテーション (`SelectionStateService.get_selected_images_for_annotation`) は
     「選択 → 無ければ表示中の全画像」のフォールバックを持つ。
   - エクスポート (`SelectionStateService.get_current_selected_images`) は
     `DatasetStateManager.selected_image_ids` **のみ**でフォールバックなし。
   - フィルタで絞って画面に出した状態でエクスポートを押しても、サムネを明示クリックして
     いなければ「0件」で弾かれる。
3. **`export_with_criteria` の `image_ids` は非推奨**だが GUI はこの経路を使用している
   （`DeprecationWarning` 発火）。`ImageFilterCriteria` に明示 ID フィールドは無い。

既存の制約となる設計判断:

- **ADR 0019 (Export Filter Required Design)**: LoRA 学習データ作成では「全件エクスポート」が
  正常ケースとして存在しない。GUI は「明示選択＝暗黙フィルタ」を維持し、フィルタ結果や全件の
  直エクスポートは大量誤エクスポート（21k 件事故, Issue #166）防止のため**意図的に避ける**。
- **ADR 0072 (`0072-workspace-stage-selection-source.md`, Workspace stage button selection source)**:
  `DatasetStateManager` が唯一の選択ソース。新しいワークスペース入口は別の選択解決パスを足さない。
  `QPushButton.clicked(bool)` ペイロードを ID と誤認しない（Issue #570 のバグ元）。
  ※ かつて番号 0043 が `0043-db-core-logging-loguru-unification.md` と重複していたため、#777 で 0072 へ採番し直した。
- **lesson #178**: `DatasetExportService.export_with_criteria()` を GUI/CLI/API 3 経路の ID 解決
  SSoT として集約済み。各経路で個別実装すると二重クエリ・整合性ズレが起きる。

ユーザーの不満（フィルタで絞った集合をエクスポートしたい）を ADR 0019 に違反せず解く設計が必要。

## Decision

**エクスポート対象を「ステージング集合」に統一し、ワークスペースの入口とダイアログ内表示で
対象を常に明示する。フィルタ結果は明示操作（ステージングへ投入）を介してのみ対象化する。**

### 1. 対象解決の統一 (S2 / #612)

- エクスポート対象 = `StagingWidget.get_image_ids()`（明示的・MAX 件数で有界・可視・名前付きの集合）。
- ステージングは `staged_images_changed` シグナルと `connect_shared_staging` による共有
  OrderedDict を持ち、BatchTag / ProviderBatch と同一実体を共有する。
- フィルタ結果はサムネで確認 → **明示的に「ステージングへ投入」** してから対象化する。
  raw `filtered_images` への暗黙フォールバックは **行わない**（ADR 0019 整合＝大量誤エクスポート防止）。

### 2. 入口の対象は常にステージング集合 (S1 / #611)

- 新規入口（ツールバー常設・サムネグリッド下部バー）のエクスポートボタンは、section 1 の対象＝
  **`StagingWidget.get_image_ids()` を読む**（サムネ選択ではない）。ステージング後にサムネ選択を
  変更・クリアしても対象がズレない（Codex review #617 の指摘=「選択を読むと対象が再び曖昧化する」を回避）。
- 下部バーの件数表示は `StagingWidget.staged_images_changed` を購読し**ステージング件数**を出す。
- サムネ選択をエクスポート対象に入れたい場合は、まず明示の「選択をステージングへ」アクションを経由する。
  このアクション**のみ** `DatasetStateManager` を読み、ADR 0072
  (`0072-workspace-stage-selection-source.md`) の `clicked(bool)` 規約に従う。
  新規入口は別の選択解決パスを足さない（ADR 0072 継承）。

### 3. `ImageFilterCriteria` への明示 ID 統合

- `ImageFilterCriteria` に `image_ids: list[int] | None = None` を追加し、
  `get_images_by_filter` で `WHERE id IN (...)` として解決する。
- `image_ids` 指定時は **正確な集合を選ぶ exact-set selector** として扱い、他のフィルタ次元
  （`include_nsfw` / `manual_rating_filter` / `ai_rating_filter` / `tags` / score 等）を
  **バイパス**する。`get_images_by_filter` は `image_ids` 指定時に NSFW 除外等を適用せず、
  明示された ID をそのまま返す。
  - 理由: 現行の明示 ID エクスポート経路は「与えた ID をそのまま出す」契約。`include_nsfw` は
    既定 `False` で criteria 検索は NSFW を除外するため、素朴に `ImageFilterCriteria(image_ids=...)`
    へ移すと**明示的にステージングした NSFW 画像が黙って落ちる回帰**になる（Codex review #617 指摘）。
    exact-set bypass によりステージング集合とエクスポート結果の一致を保証する。
- GUI は `export_with_criteria(criteria=ImageFilterCriteria(image_ids=staged_ids))` を呼ぶ。
  これにより `image_ids` 直接渡し（非推奨・`DeprecationWarning`）を GUI から排除し、
  `export_with_criteria` を唯一の SSoT として維持する（lesson #178 整合）。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. ステージング集合に統一 | 対象＝可視・有界・明示の名前付き集合 | **採用** |
| B. エクスポートを `filtered_images` へフォールバック | アノテーションと挙動を揃える | 却下: ADR 0019 違反（大量誤エクスポート再導入） |
| C. 現状維持＋入口追加のみ | `selected_image_ids` のみ継続 | 却下: 対象の曖昧さが残る |

A を採用した理由:

- **ADR 0019 整合**: ステージング投入はユーザーの明示操作であり「意図の明示」を満たす。
  有界（MAX 件数）なので 21k 件級の誤エクスポートを構造的に防ぐ。
- **ADR 0072 整合**: `DatasetStateManager` を唯一の選択ソースに保ち、ステージングはその下流の
  明示集合として扱う。新規入口は選択解決パスを増やさない。
- **対象が可視化される**: 「現在選択中」という不可視概念ではなく、名前付きの集合（ステージング）
  を対象にすることで「対象が不明瞭」が構造的に解消する。

`ImageFilterCriteria.image_ids` 追加を選んだ理由:

- 明示 ID を criteria の 1 次元として扱うことで、GUI が SSoT (`export_with_criteria(criteria=)`)
  を非推奨警告なしに利用できる。`image_ids` 直接渡し経路の deprecation を CLI/API/GUI で一貫させる。

## Consequences

### 良い点

- ◎ エクスポート対象が常に可視・明示・有界になり「対象が不明瞭」が構造的に消える。
- ◎ ADR 0019（誤エクスポート防止）と ADR 0072（単一選択ソース）の双方を不変に保つ。
- ◎ `export_with_criteria` を唯一の ID 解決 SSoT として維持（lesson #178）。

### トレードオフ

- △ ユーザーはエクスポート前に「ステージングへ投入」という 1 ステップを踏む必要がある。
  → フィルタ結果一括投入の導線で軽減する。
- △ `ImageFilterCriteria.image_ids` 追加に伴い `get_images_by_filter` の id-list 経路と
  その unit test を追加する必要がある。

### 適用範囲

- 本 ADR は epic #610 のサブ #611 / #612 が対象。#613（picker 配線バグ）/ #615（解像度 UI）は
  ダイアログ内修正で本 ADR の対象外。
- #614（changed-since 注釈アクティビティフィルタ）は **エクスポートダイアログ内に限定** され、
  解決済み `image_ids` への post-filter として実装する。永続化・スキーマ変更を伴わないため
  本 ADR の対象外（対象解決とは疎結合）。

## Related

- ADR 0019: Export Filter Required Design（GUI 選択＝暗黙フィルタ、誤エクスポート防止）
- ADR 0072 (`0072-workspace-stage-selection-source.md`): Workspace stage button selection source
  （単一選択ソース、clicked(bool) 注意）。※ 旧番号 0043 の db_core ログ ADR との重複を #777 で解消し 0072 へ採番。
- ADR 0001 / 0009: Two-Tier Service Architecture / Qt Decoupling（Qt-free な対象解決ロジック）
- lesson #178: `export_with_criteria` を 3 経路の ID 解決 SSoT に集約
- Issue #610 (epic), #611, #612, #614