# MainWindow初期化エラー調査結果 (2025-10-03)

## エラー概要
```
2025-10-03 19:46:30.767 | ERROR | __main__:__init__ - MainWindow初期化失敗: name 'FilterSearchPanel' is not defined
```

## 根本原因の特定

### 1. MainWindow.uiの`<customwidgets>`セクションが空
- **Line 828**: `<customwidgets/>`と記述されており、カスタムウィジェット定義が完全に欠落
- **使用されているカスタムウィジェット（5個）**:
  - Line 275: FilterSearchPanel
  - Line 286: SelectedImageDetailsWidget  
  - Line 334: ThumbnailSelectorWidget
  - Line 511: ImagePreviewWidget
  - Line 533: ModelSelectionWidget

### 2. MainWindow_ui.pyにインポート文が生成されていない
- PySide6標準ウィジェットのみがインポート
- カスタムウィジェットのインポート文が完全に欠落
- pyside6-uicが警告を出力:
  ```
  WriteImports::add(): Unknown Qt class FilterSearchPanel
  WriteImports::add(): Unknown Qt class SelectedImageDetailsWidget
  WriteImports::add(): Unknown Qt class ThumbnailSelectorWidget
  WriteImports::add(): Unknown Qt class ImagePreviewWidget
  WriteImports::add(): Unknown Qt class ModelSelectionWidget
  ```

### 3. 正常動作している例（SelectedImageDetailsWidget.ui）
- **Line 401-408**: 正しい`<customwidgets>`セクション定義:
  ```xml
  <customwidgets>
   <customwidget>
    <class>AnnotationDataDisplayWidget</class>
    <extends>QWidget</extends>
    <header>..widgets.annotation_data_display_widget</header>
    <container>1</container>
   </customwidget>
  </customwidgets>
  ```
- **結果**: `SelectedImageDetailsWidget_ui.py`の Line 22 に正しくインポート文が生成:
  ```python
  from ..widgets.annotation_data_display_widget import AnnotationDataDisplayWidget
  ```

## カスタムウィジェットの実装ファイルパス

| クラス名 | ファイルパス | 親クラス |
|---------|------------|---------|
| FilterSearchPanel | src/lorairo/gui/widgets/filter_search_panel.py | QScrollArea |
| SelectedImageDetailsWidget | src/lorairo/gui/widgets/selected_image_details_widget.py | QScrollArea |
| ThumbnailSelectorWidget | src/lorairo/gui/widgets/thumbnail.py | QWidget, Ui_ThumbnailSelectorWidget |
| ImagePreviewWidget | src/lorairo/gui/widgets/image_preview.py | QWidget, Ui_ImagePreviewWidget |
| ModelSelectionWidget | src/lorairo/gui/widgets/model_selection_widget.py | QWidget, Ui_ModelSelectionWidget |

## 修正方針

MainWindow.uiの`<customwidgets/>`セクションを以下のように修正:

```xml
<customwidgets>
 <customwidget>
  <class>FilterSearchPanel</class>
  <extends>QScrollArea</extends>
  <header>..widgets.filter_search_panel</header>
  <container>1</container>
 </customwidget>
 <customwidget>
  <class>SelectedImageDetailsWidget</class>
  <extends>QScrollArea</extends>
  <header>..widgets.selected_image_details_widget</header>
  <container>1</container>
 </customwidget>
 <customwidget>
  <class>ThumbnailSelectorWidget</class>
  <extends>QWidget</extends>
  <header>..widgets.thumbnail</header>
  <container>1</container>
 </customwidget>
 <customwidget>
  <class>ImagePreviewWidget</class>
  <extends>QWidget</extends>
  <header>..widgets.image_preview</header>
  <container>1</container>
 </customwidget>
 <customwidget>
  <class>ModelSelectionWidget</class>
  <extends>QWidget</extends>
  <header>..widgets.model_selection_widget</header>
  <container>1</container>
 </customwidget>
</customwidgets>
```

## 修正手順

1. MainWindow.uiの`<customwidgets/>`セクション（Line 828）を上記の完全な定義に置換
2. `scripts/generate_ui.py`を実行してMainWindow_ui.pyを再生成
3. 生成されたMainWindow_ui.pyにカスタムウィジェットのインポート文が含まれることを確認
4. アプリケーションを起動してエラーが解消されたことを確認

## 過去の状況
- コミットe24b47fでも既に`<customwidgets/>`は空だった
- この問題は以前から存在していた可能性が高い
- Qt Designerでの編集時に`<customwidgets>`定義が失われた可能性がある
