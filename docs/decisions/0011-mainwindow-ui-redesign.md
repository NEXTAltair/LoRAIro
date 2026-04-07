# ADR 0011: MainWindow UI Redesign

- **日付**: 2026-01-04
- **ステータス**: Accepted

## Context

MainWindow が 1,645 行に膨張し、UI の変更が困難だった。SelectedImageDetailsWidget が編集機能を持っており、表示と編集の責任が混在していた。

## Decision

**フェーズ分割リデザイン**:
1. `SelectedImageDetailsWidget` を読み取り専用に変換（edit controls 削除、read-only labels 追加）
2. `QStackedWidget` (`stackedWidgetDetail`) で view/edit モードを切り替え:
   - Index 0: SelectedImageDetailsWidget（表示モード）
   - Index 1: ImageEditPanelWidget（編集モード）
3. `actionEditImage` (Ctrl+E) でモード切り替え、150ms フェードアニメーション

**5段階初期化パターン**: MainWindow の初期化を5フェーズに分け、各フェーズを Service ヘルパーに委譲。

## Rationale

- モノリシック MainWindow → 役割分担された小コンポーネント群へ
- 表示と編集の明確な分離で各コンポーネントの責任が単純化
- フェードアニメーション（InOutCubic easing）でスムーズな UX

## Consequences

- MainWindow: 1,645 → 688 行（58.2% 削減）
- `SelectedImageDetailsWidget` から Signal 3つ (`rating_updated`, `score_updated`, `save_requested`) を削除
- 削除されたウィジェット: `comboBoxRating`, `sliderScore`, `pushButtonSaveRating`, `pushButtonSaveScore`
- `HybridAnnotationController` を完全除去
