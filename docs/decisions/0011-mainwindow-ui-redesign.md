---
type: ADR
title: MainWindow UI Redesign
status: Accepted
timestamp: 2026-01-04
tags: []
---
# ADR 0011: MainWindow UI Redesign

## Context

`MainWindow` が 1,645 行まで膨張し、UI の変更が困難になっていた。また、`SelectedImageDetailsWidget` が編集機能も兼ねていたため、表示と編集の責務が混在していた。

## Decision

次の内容で**フェーズ分割リデザイン**を実施する。

1. `SelectedImageDetailsWidget` から編集用コントロールを削除し、読み取り専用ラベルを追加して表示専用コンポーネントへ変換する。
2. `QStackedWidget`(`stackedWidgetDetail`)を導入し、表示モードと編集モードを切り替える構成にする。
   - Index 0: `SelectedImageDetailsWidget`(表示モード)
   - Index 1: `ImageEditPanelWidget`(編集モード)
3. `actionEditImage`(`Ctrl+E`)でモードを切り替え、150ms のフェードアニメーションを適用する。

あわせて**5 段階初期化パターン**を採用し、`MainWindow` の初期化処理を 5 フェーズに分割して各フェーズを Service ヘルパーへ委譲する。

## Rationale

- モノリシックな `MainWindow` を、役割分担された小さなコンポーネント群へ分解できる。
- 表示と編集を明確に分離することで、各コンポーネントの責務が単純になる。
- `InOutCubic` イージングを用いたフェードアニメーションにより、滑らかな UX を提供できる。

## Consequences

- `MainWindow` の行数を 1,645 行から 688 行へ削減した(58.2% 削減)。
- `SelectedImageDetailsWidget` から 3 つの Signal(`rating_updated`、`score_updated`、`save_requested`)を削除した。
- 編集用ウィジェット(`comboBoxRating`、`sliderScore`、`pushButtonSaveRating`、`pushButtonSaveScore`)を削除した。
- `HybridAnnotationController` を完全に除去した。
