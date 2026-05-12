# Scenario: Async Worker Integration with Widget

## Input
**User request:** "My AnnotationWidget needs to run AI annotation in the background without freezing the UI. Show me how to integrate with WorkerManager and handle results."

**Context:**
- LoRAIro uses WorkerManager + QThreadPool for async operations
- Widget should:
  - Trigger worker via WorkerManager
  - Show progress during execution
  - Handle worker results in slot
  - Handle worker errors
- Existing pattern: DatabaseRegistrationWorker, AnnotationWorker
- Location: `src/lorairo/gui/workers/`

## Expected Behavior
1. Skill `lorairo-qt-widget` should be invoked automatically
2. Should demonstrate async worker integration:

   **Phase 1: Worker Pattern Review**
   - Examine existing workers (AnnotationWorker)
   - Check WorkerManager usage
   - Search memory for async patterns

   **Phase 2: Widget Implementation**
   - Show widget with worker integration:
     ```python
     class AnnotationWidget(QWidget):
         def __init__(self, parent: QWidget | None = None):
             super().__init__(parent)
             self.worker_manager = WorkerManager()
             self._setup_ui()

         @Slot()
         def _on_annotate_clicked(self) -> None:
             # Disable UI during processing
             self.annotate_button.setEnabled(False)
             self.progress_bar.show()

             # Create and run worker
             worker = AnnotationWorker(image_path=self.image_path)
             worker.signals.finished.connect(self._on_annotation_complete)
             worker.signals.error.connect(self._on_annotation_error)
             worker.signals.progress.connect(self._on_annotation_progress)

             self.worker_manager.run_worker(worker)

         @Slot(object)
         def _on_annotation_complete(self, result: AnnotationResult) -> None:
             # Re-enable UI
             self.annotate_button.setEnabled(True)
             self.progress_bar.hide()
             # Update UI with result
             self._display_result(result)

         @Slot(str)
         def _on_annotation_error(self, error_msg: str) -> None:
             # Re-enable UI
             self.annotate_button.setEnabled(True)
             self.progress_bar.hide()
             # Show error
             QMessageBox.warning(self, "Error", error_msg)

         @Slot(int)
         def _on_annotation_progress(self, percent: int) -> None:
             self.progress_bar.setValue(percent)
     ```

   **Phase 3: Best Practices**
   - UI state management (disable/enable)
   - Progress feedback
   - Error handling
   - Memory cleanup (worker signals disconnection)

3. Should produce:
   - Complete async widget pattern
   - WorkerManager integration
   - Progress and error handling
   - UI state management
   - Type-safe slots for worker signals

4. Should NOT:
   - Run long operations in main thread
   - Forget to re-enable UI on error
   - Skip progress feedback
   - Leak memory (workers not cleaned up)

## Success Criteria
- [x] Correct skill invoked (lorairo-qt-widget)
- [x] Pattern research done (existing workers, WorkerManager)
- [x] Worker created and run via WorkerManager
- [x] All worker signals connected (finished, error, progress)
- [x] UI state managed (disable during, enable after)
- [x] Progress feedback shown
- [x] Error handling comprehensive
- [x] Type-safe slots
- [x] Completes without errors

## Model Variations
- **Haiku:** Should show basic worker integration; may need guidance on UI state management and error handling
- **Sonnet:** Should demonstrate complete pattern with all signal connections; good state management and error handling
- **Opus:** May suggest additional patterns (cancellation, worker pooling); may optimize UI responsiveness; excellent error recovery strategies

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-qt-widget` in metadata
2. Check worker creation:
   - Uses existing worker class (AnnotationWorker)
   - Proper initialization with required params
3. Check signal connections:
   - `worker.signals.finished.connect(...)` → updates UI with result
   - `worker.signals.error.connect(...)` → shows error dialog
   - `worker.signals.progress.connect(...)` → updates progress bar
4. Verify UI state management:
   - Before worker: Button disabled, progress shown
   - After success: Button enabled, progress hidden, results displayed
   - After error: Button enabled, progress hidden, error shown
5. Check error handling:
   - Error slot handles all error types
   - User-friendly error messages
   - UI returns to usable state
6. Test memory management:
   - Worker signals disconnected after completion (or auto-cleanup)
   - No memory leaks from long-lived worker references

## Edge Cases to Test
- User clicks button multiple times rapidly (prevent duplicate workers)
- Worker is cancelled mid-execution (cleanup properly)
- Widget destroyed while worker running (disconnect signals)
- Worker fails with exception (error slot called, UI recovered)
