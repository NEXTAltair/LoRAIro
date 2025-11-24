# Phase 2 UI レスポンシブ変換による回帰バグ記録

**日付**: 2025-11-21  
**対象**: Phase 2 Qt Designer レスポンシブレイアウト自動変換（commit 6fa0f75）

## 概要

Phase 2 UI 変換スクリプト（`scripts/phase2_ui_responsive_conversion.py`）実行により、GUI が起動不能になる4つの致命的な回帰バグが発生。

---

## 回帰バグ一覧

### 1. Container vsizetype="Fixed" 問題

**コミット**: 修正済み (34960af)  
**影響**: 15 UI ファイル  
**症状**: パネルが縦方向に拡張できず、レイアウト崩壊

**原因**:
```python
# UIResponsiveConversionService (line 97)
"container_frames": ResponsivePattern(
    conversion_rules={"hsizetype": "Expanding", "vsizetype": "Fixed"}  # ✗
)
```

**修正**:
```python
conversion_rules={"hsizetype": "Expanding", "vsizetype": "Preferred"}  # ✓
```

**対象ファイル**: 15 designer/*.ui ファイル

---

### 2. Unicode サロゲートペア問題

**コミット**: 修正済み (04836bc)  
**影響**: ModelSelectionWidget  
**症状**: `UnicodeEncodeError: 'utf-8' codec can't encode surrogates`

**原因**:
pyside6-uic が絵文字（📋🎯🏷️⭐）を UTF-16 サロゲートペア（`\ud83d\udccb`）として生成。

**修正**:
```xml
<!-- ModelSelectionWidget.ui -->
📋 → [✓]
🎯 → [*]
🏷️ → [#]
⭐ → [★]
```

---

### 3. tableWidgetTags 欠落問題

**コミット**: 修正済み (04836bc)  
**影響**: AnnotationDataDisplayWidget  
**症状**: `AttributeError: 'AnnotationDataDisplayWidget' object has no attribute 'tableWidgetTags'`

**原因**:
Phase 2 変換が commit 0a82966 で追加された QTableWidget を QTextEdit に戻した（バックアップからの誤復元）。

**修正**:
```bash
# commit 0a82966 から復元
git show 0a82966:src/lorairo/gui/designer/AnnotationDataDisplayWidget.ui > src/lorairo/gui/designer/AnnotationDataDisplayWidget.ui
```

**重要**: AnnotationResultsWidget と AnnotationDataDisplayWidget は重複ではなく補完的。
- AnnotationResultsWidget: リアルタイムワークフロー結果比較
- AnnotationDataDisplayWidget: 保存済みアノテーションデータ表示

---

### 4. dynamicContentLayout リネーム問題

**コミット**: 未修正（現在の問題）  
**影響**: ModelSelectionWidget  
**症状**: `'ModelSelectionWidget' object has no attribute 'dynamicContentLayout'`

**原因**:
Phase 2 変換が UI 要素名を変更したが、Python コードは未更新。

```
Commit 0a82966: name="dynamicContentLayout" ✓
         ↓
Commit 6fa0f75: name="scrollLayout" ✗
```

**Python コード参照箇所（5箇所）**:
- `model_selection_widget.py` line 61: 型ヒント
- `model_selection_widget.py` line 219: プロバイダーラベル追加
- `model_selection_widget.py` line 230: チェックボックス追加
- `model_selection_widget.py` line 252: レイアウト数取得
- `model_selection_widget.py` line 257: ウィジェット削除

**修正計画**:
```xml
<!-- ModelSelectionWidget.ui line 64 -->
<!-- 変更前 -->
<layout class="QVBoxLayout" name="scrollLayout">

<!-- 変更後 -->
<layout class="QVBoxLayout" name="dynamicContentLayout">
```

**手順**:
1. `ModelSelectionWidget.ui` line 64 を編集
2. `uv run python scripts/generate_ui.py` で再生成
3. GUI 起動確認
4. コミット

---

## 根本原因分析

### Phase 2 変換スクリプトの問題点

1. **UI 要素名の無断変更**: Python コードとの整合性を検証しない
2. **バックアップからの誤復元**: 最新の変更が失われる
3. **サイズポリシー一括変更**: Container Widget の特性を無視
4. **Unicode エンコーディング**: pyside6-uic の出力を後処理しない

### 不足していた検証

```python
# 必要だった検証ロジック
CRITICAL_ELEMENTS = {
    "ModelSelectionWidget.ui": ["dynamicContentLayout"],
    "AnnotationDataDisplayWidget.ui": ["tableWidgetTags"]
}

def validate_critical_elements(ui_file: Path):
    """重要要素が変換後も保持されているか検証"""
    pass
```

---

## 教訓

1. **自動変換は慎重に**: UI 要素名変更時は Python コードも同期変更
2. **バックアップ検証**: 復元前に最新コミットとの差分確認
3. **段階的適用**: 全ファイル一括変換ではなく、少数ファイルでテスト
4. **起動テスト必須**: 変換後は必ず GUI 起動確認

---

## 関連コミット

- `6fa0f75`: Phase 2 UI conversion（問題発生）
- `34960af`: vsizetype 修正
- `04836bc`: Unicode + tableWidgetTags 修正
- 未実施: dynamicContentLayout 修正

---

## 参照

- スクリプト: `scripts/phase2_ui_responsive_conversion.py`
- サービス: `src/lorairo/services/ui_responsive_conversion_service.py`
- 影響範囲: 16 UI ファイル（Phase 1 除外の4ファイルを除く全 UI）
