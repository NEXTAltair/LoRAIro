---
type: ADR
title: Workspace Export Target = Staging Set / Selection-Source Unification
status: Accepted
timestamp: 2026-06-04
tags: []
---
# ADR 0055: Workspace Export Target = Staging Set / Selection-Source Unification

- **関連 Issue**: #610 (epic), #611 (S1 入口), #612 (S2 接続), #613 (S3 picker), #614 (S4 changed-since), #615 (S5 解像度UI)
- **一部改訂**: ADR 0074 — 統一対象であるステージング集合の SSoT を `StagingWidget` から `StagingStateManager` へ移管した。3 者が同一集合を指すという統一の意図は不変である。

## Context

GUI の画像エクスポート導線が使いにくいという報告があった(#610)。調査の結果、本質的な原因は画面遷移ではなく、**エクスポート対象が何であるか曖昧になっている意味論上の問題**だった。

検証で確認された現状の課題は以下の 3 点である。

1. **入口がメニューの奥にしかない**:エクスポートは `MainWindow.actionExport`(ツール → エクスポート、`Ctrl+Shift+E`)からしか起動できず、3 カラム構成の作業画面に出口が存在しない。
2. **対象解決の挙動が機能間で分裂している**:
   - アノテーション(`SelectionStateService.get_selected_images_for_annotation`)は「選択画像があればそれを使い、なければ表示中の全画像を使う」というフォールバックを持つ。
   - エクスポート(`SelectionStateService.get_current_selected_images`)は `DatasetStateManager.selected_image_ids` **のみ**を参照し、フォールバックを持たない。
   - そのため、フィルタで絞り込んで画面へ表示した状態でエクスポートを押しても、サムネイルを明示的にクリックしていなければ「0 件」として弾かれる。
3. **非推奨 API の使用**:`export_with_criteria` の `image_ids` 引数は非推奨であり `DeprecationWarning` を発火するが、GUI はこの経路を使い続けている。一方、`ImageFilterCriteria` には明示 ID を指定するフィールドが存在しない。

さらに、既存の設計判断として以下の制約がある。

- **ADR 0019(Export Filter Required Design)**:LoRA 学習データの作成では「全件エクスポート」という正常ケースは存在しない。GUI は「明示選択を暗黙フィルタとする」方針を維持し、フィルタ結果や全件の直接エクスポートは大量誤エクスポート(21k 件事故、Issue #166)を防ぐため**意図的に避ける**。
- **ADR 0072(`0072-workspace-stage-selection-source.md`、Workspace stage button selection source)**:`DatasetStateManager` を唯一の選択ソースとする。新しいワークスペース入口では別の選択解決パスを追加せず、`QPushButton.clicked(bool)` のペイロードを ID と誤認しないようにする(Issue #570 のバグ原因)。なお、かつて番号 0043 が `0043-db-core-logging-loguru-unification.md` と重複していたため、#777 で 0072 へ採番し直した。
- **lesson #178**:`DatasetExportService.export_with_criteria()` を GUI・CLI・API の 3 経路における ID 解決の SSoT として集約済みである。各経路で個別に実装すると二重クエリや整合性のズレが生じる。

したがって、ADR 0019 に違反することなく「フィルタで絞り込んだ集合をエクスポートしたい」というユーザーの要望を満たす設計が必要である。

## Decision

**エクスポート対象を「ステージング集合」に統一し、ワークスペースの入口とダイアログ内表示で対象を常に明示する。フィルタ結果は「ステージングへ投入」という明示操作を介してのみ対象化する。**

### 1. 対象解決の統一(S2 / #612)

- エクスポート対象を `StagingWidget.get_image_ids()` とする。これは明示的かつ最大件数で有界であり、画面上で可視化される名前付きの集合である。
- ステージングは `staged_images_changed` シグナルと `connect_shared_staging` による共有 `OrderedDict` を持ち、`BatchTag` や `ProviderBatch` と同一の実体を共有する。
- フィルタ結果はサムネイルで確認した後、**明示的に「ステージングへ投入」**してからエクスポート対象とする。生の `filtered_images` への暗黙フォールバックは**行わない**(ADR 0019 と整合し、大量誤エクスポートを防ぐため)。

### 2. 入口の対象は常にステージング集合とする(S1 / #611)

- 新設する入口(ツールバー常設ボタンおよびサムネイルグリッド下部バー)のエクスポートボタンは、サムネイル選択ではなく **`StagingWidget.get_image_ids()` を参照する**。これにより、ステージング後にサムネイル選択を変更またはクリアしても対象がズレない(Codex review #617 の「選択を読むと対象が再び曖昧になる」という指摘を回避)。
- 下部バーの件数表示は `StagingWidget.staged_images_changed` を購読し、**ステージング件数**を表示する。
- サムネイル選択をエクスポート対象へ加えたい場合は、まず明示的な「選択をステージングへ」アクションを経由する。このアクション**のみ**が `DatasetStateManager` を読み取り、ADR 0072(`0072-workspace-stage-selection-source.md`)の `clicked(bool)` 規約に従う。新規入口に別の選択解決パスは追加しない。

### 3. `ImageFilterCriteria` への明示 ID 統合

- `ImageFilterCriteria` に `image_ids: list[int] | None = None` を追加し、`get_images_by_filter` で `WHERE id IN (...)` として解決する。
- `image_ids` を指定した場合は**正確な集合を選ぶ exact-set selector** として扱い、他のフィルタ条件(`include_nsfw`、`manual_rating_filter`、`ai_rating_filter`、`tags`、`score` など)を**バイパス**する。`get_images_by_filter` は `image_ids` 指定時に NSFW 除外などを適用せず、明示された ID をそのまま返す。
  - **理由**:現行の明示 ID エクスポート経路は「指定された ID をそのまま出力する」契約になっている。`include_nsfw` は既定値が `False` であり、通常の条件検索では NSFW が除外される。そのため、単純に `ImageFilterCriteria(image_ids=...)` へ移行すると、**明示的にステージングした NSFW 画像が黙って除外される回帰バグ**を引き起こす(Codex review #617 の指摘)。exact-set バイパスにより、ステージング集合とエクスポート結果の一致を保証する。
- GUI は `export_with_criteria(criteria=ImageFilterCriteria(image_ids=staged_ids))` を呼び出す。これにより、非推奨の `image_ids` 直接渡し(`DeprecationWarning`)を GUI から排除し、`export_with_criteria` を唯一の SSoT として維持する(lesson #178 と整合)。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. ステージング集合に統一 | 対象を可視・有界・明示の名前付き集合とする | **採用** |
| B. エクスポートを `filtered_images` へフォールバック | アノテーションと挙動を揃える | 却下(ADR 0019 違反:大量誤エクスポートを再導入する) |
| C. 現状維持と入口追加のみ | `selected_image_ids` のみ継続する | 却下(対象の曖昧さが残る) |

### 選択肢 A を採用した理由

- **ADR 0019 との整合性**:ステージングへの投入はユーザーの明示的な操作であり、「意図の明示」を満たす。また、最大件数によって有界であるため、21k 件規模の誤エクスポートを構造的に防げる。
- **ADR 0072 との整合性**:`DatasetStateManager` を唯一の選択ソースに保ち、ステージングはその下流の明示集合として扱う。新規入口で選択解決パスを増やさずに済む。
- **対象の可視化**:「現在選択中」という不可視の概念ではなく、名前付きの集合(ステージング)を対象とすることで、対象が不明瞭になる問題を構造的に解消できる。

### `ImageFilterCriteria.image_ids` を追加した理由

明示 ID を `ImageFilterCriteria` の 1 次元として扱うことで、GUI が非推奨警告を出さずに SSoT(`export_with_criteria(criteria=)`)を利用できる。これにより、CLI・API・GUI の全経路で `image_ids` 直接渡し経路の非推奨化を一貫させられる。

## Consequences

### 良い点

- エクスポート対象が常に可視・明示・有界になり、対象が不明瞭になる問題を構造的に解消できる。
- ADR 0019(誤エクスポート防止)と ADR 0072(単一選択ソース)の双方を不変に保てる。
- `export_with_criteria` を唯一の ID 解決 SSoT として維持できる(lesson #178)。

### トレードオフ

- ユーザーはエクスポート前に「ステージングへ投入」という 1 ステップを踏む必要がある。この手間は、フィルタ結果を一括投入する導線で軽減する。
- `ImageFilterCriteria.image_ids` の追加に伴い、`get_images_by_filter` の ID リスト経路と、その単体テストを追加する必要がある。

### 適用範囲

- 本 ADR は epic #610 のサブ Issue である #611 および #612 を対象とする。#613(picker の配線バグ)と #615(解像度 UI)はダイアログ内の修正であるため、本 ADR の対象外とする。
- #614(changed-since 注釈アクティビティフィルタ)は**エクスポートダイアログ内に限定**し、解決済み `image_ids` に対する後段フィルタ(post-filter)として実装する。永続化やスキーマ変更を伴わず対象解決とは疎結合であるため、本 ADR の対象外とする。

## Related

- ADR 0019: Export Filter Required Design(GUI 選択を暗黙フィルタとする設計、誤エクスポート防止)
- ADR 0072(`0072-workspace-stage-selection-source.md`): Workspace stage button selection source(単一選択ソース、`clicked(bool)` の注意点。旧番号 0043 の db_core ログ ADR との重複を #777 で解消し 0072 へ採番)
- ADR 0001 / 0009: Two-Tier Service Architecture / Qt Decoupling(Qt 非依存の対象解決ロジック)
- lesson #178: `export_with_criteria` を 3 経路の ID 解決 SSoT に集約
- Issue #610 (epic), #611, #612, #614
