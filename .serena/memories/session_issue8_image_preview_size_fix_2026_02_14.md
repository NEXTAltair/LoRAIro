# Session: Issue #8 ImagePreviewWidget スタンドアロン実行時の画像表示サイズ修正

**Date**: 2026-02-14
**Branch**: main
**Commit**: 5bc73d0
**Status**: completed

---

## 実装結果

**変更ファイル**: `src/lorairo/gui/widgets/image_preview.py` (1ファイルのみ)

1. **`QShowEvent` import追加** - showEventオーバーライドに必要
2. **`showEvent()` メソッド追加** (3行) - widget表示時に `_adjust_view_size()` を再実行
3. **スタンドアロンブロック修正**:
   - `resize(800, 600)` で合理的な初期サイズ設定
   - `show()` → `load_image()` の順序に変更
   - FIXMEコメント削除

## テスト結果

- 既存テスト: 16 failed, 1 passed, 4 errors（変更前後で同一、既存の不整合）
- 今回の変更による回帰なし

## 設計意図

- **根本原因**: `load_image()` → `show()` の順序でwidgetが未表示のままviewport sizeが極小値になる
- **解決策**: `showEvent()` オーバーライドで表示時にfitInView再実行 + 呼び出し順序修正
- **メインアプリへの影響なし**: resizeEventとshowEventが共存、既存のレイアウトパスに影響しない

## 問題と解決

- テストが古いAPI（`_on_current_image_changed`, `set_dataset_state_manager`）を参照しており全滅状態
- 今回のスコープ外のため未修正（別Issue対応が必要）

## 未完了・次のステップ

- ImagePreviewWidgetのテストファイルが現在のwidget実装と乖離 → テスト更新が必要
