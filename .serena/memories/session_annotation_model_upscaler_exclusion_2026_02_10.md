# Session: アノテーション走査でアップスケーラーモデルを非表示化

**Date**: 2026-02-10
**Branch**: feature/annotator-library-integration
**Task**: アノテーション走査のモデル選択項目からアップスケーラーモデルを除外

---

## 問題

アノテーション走査（バッチアノテーション）画面でモデル選択ウィジェットにアップスケーラーモデルが表示されていた。

### 原因

`ModelSelectionWidget` の初期状態では capabilities フィルターが空リストのため、全モデル（upscaler含む）が表示される。
- AnnotationFilterWidget でユーザーがフィルター設定をするまで、アップスケーラーが表示されてしまう

---

## 解決方法

`WidgetSetupService._setup_annotation_group_widgets()` の Signal接続後に、デフォルトフィルターを適用。

**ファイル修正**: `src/lorairo/gui/services/widget_setup_service.py` (Line 357-359)

### 変更内容

```python
# Signal接続後に初期フィルターを適用
main_window.batchModelSelection.apply_filters(
    capabilities=["caption", "tags", "scores"]
)
```

### 効果

1. **初期状態**: Annotation, Tags, Scoresの機能を持つモデルのみ表示
2. **アップスケーラー非表示**: capability="upscaler"のモデルは自動的に除外
3. **ユーザー操作後**: AnnotationFilterWidgetのチェックボックス操作で適切に フィルターが更新される

---

## 設計根拠

### アノテーション走査が必要な機能

- Caption (キャプション生成)
- Tags (タグ生成)
- Scores (画像品質評価)

### 不要な機能

- Upscaler (画像拡大 - アノテーションプロセスに関係なし)

### 修正場所の選択理由

- `WidgetSetupService._setup_annotation_group_widgets()`: アノテーション画面初期化の責任領域
- Signal接続後に適用: 初期化完了後のフィルター設定で、他のロジックに影響なし
- capabilities指定: モデルの型（type）ではなく機能で フィルタリング → 保守性向上

---

## テスト内容

1. アノテーション走査画面を開く
2. モデル選択ウィジェットでアップスケーラーが表示されない
3. AnnotationFilterWidgetでチェック操作時にモデルが適切に更新

---

## 影響範囲

- **対象**: アノテーション走査（バッチアノテーション）のモデル選択
- **非対象**: その他のモデル選択ウィジェット（設定画面等）
- **後方互換性**: フィルター signal の動作は変わらない
