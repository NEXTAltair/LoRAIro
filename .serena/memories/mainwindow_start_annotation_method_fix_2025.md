# MainWindow start_annotation Method Implementation

## Issue Resolution
**Date**: 2025-01-08  
**Status**: ✅ RESOLVED

## Problem Description
- **Issue**: Qt Designer UI file (`MainWindow.ui`) references `start_annotation()` method in signal connections (line 964)
- **Error**: AttributeError when `pushButtonAnnotate.clicked.connect(MainWindow.start_annotation)` is executed
- **Root Cause**: MainWindow class was missing the `start_annotation()` method that UI file expected

## UI File Signal Connection
In `MainWindow.ui` at line 961-975:
```xml
<connection>
 <sender>pushButtonAnnotate</sender>
 <signal>clicked()</signal>
 <receiver>MainWindow</receiver>
 <slot>start_annotation()</slot>
</connection>
```

This gets converted by pyuic to:
```python
self.pushButtonAnnotate.clicked.connect(MainWindow.start_annotation)
```

## Solution Implementation
Added missing `start_annotation()` method to MainWindow class at lines 845-900:

```python
def start_annotation(self) -> None:
    """アノテーション処理を開始"""
    try:
        # WorkerServiceの存在確認
        if not self.worker_service:
            QMessageBox.warning(
                self,
                "サービス未初期化",
                "WorkerServiceが初期化されていないため、アノテーション処理を開始できません。",
            )
            return

        # TODO: 実際の実装では、選択された画像とモデルを取得する必要があります
        # 現在は仮実装として空のリストを使用
        images = []  # 実際には選択された画像リストを取得
        phash_list = []  # 実際にはpHashリストを取得
        models = ["gpt-4o-mini"]  # 実際には選択されたモデルリストを取得
        
        if not images:
            QMessageBox.information(
                self,
                "画像未選択",
                "アノテーション処理を行う画像を選択してください。",
            )
            return
        
        if not models:
            QMessageBox.warning(
                self,
                "モデル未選択", 
                "アノテーション処理に使用するモデルを選択してください。",
            )
            return

        # アノテーション処理開始
        worker_id = self.worker_service.start_annotation(images, phash_list, models)
        
        if worker_id:
            logger.info(f"アノテーション処理開始: {len(images)}画像, {len(models)}モデル (ID: {worker_id})")
            QMessageBox.information(
                self,
                "アノテーション開始",
                f"アノテーション処理を開始しました。\n画像: {len(images)}件\nモデル: {', '.join(models)}",
            )
        else:
            logger.error("アノテーション処理の開始に失敗しました")
            QMessageBox.critical(
                self,
                "アノテーション開始エラー",
                "アノテーション処理の開始に失敗しました。",
            )
            
    except Exception as e:
        error_msg = f"アノテーション処理の開始に失敗しました: {e}"
        logger.error(error_msg, exc_info=True)
        QMessageBox.critical(self, "アノテーションエラー", error_msg)
```

## Technical Integration
- **WorkerService Integration**: Uses existing `self.worker_service.start_annotation()` method
- **Parameter Validation**: Checks for required images and models
- **Error Handling**: Comprehensive exception handling with user feedback
- **User Feedback**: Informational dialogs for success/error states
- **Future Extensibility**: TODO markers for actual image/model selection integration

## Qt Designer Workflow Understanding
1. **UI Definition**: Signal connections defined in `MainWindow.ui`
2. **Code Generation**: pyuic converts UI to `MainWindow_ui.py` with connect statements
3. **Implementation**: MainWindow class must provide all referenced slot methods
4. **Integration**: UI generation should be part of build process

## Common Qt Designer Patterns
- UI files define signal-slot connections declaratively
- Generated _ui.py files contain the connect() calls
- Implementation classes must provide all referenced methods
- Missing methods result in AttributeError at runtime

## Future Improvements
- Implement actual image selection from ThumbnailSelectorWidget
- Implement actual model selection from ModelSelectionWidget  
- Add progress feedback during annotation processing
- Integrate with annotation result display widgets

## Files Modified
- `src/lorairo/gui/window/main_window.py`: Added `start_annotation()` method

## Related UI Elements
- `pushButtonAnnotate`: Annotation trigger button (line 697-707 in MainWindow.ui)
- `pushButtonSettings`: Settings button (uses `open_settings()` method)  
- Signal connections defined in `<connections>` section (lines 911-991)
- Slot definitions in `<slots>` section (lines 993-999)