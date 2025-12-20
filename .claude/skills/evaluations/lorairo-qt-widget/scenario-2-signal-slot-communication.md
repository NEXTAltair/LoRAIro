# Scenario: Signal/Slot Communication Between Widgets

## Input
**User request:** "I have an ImageListWidget and a MetadataDisplayWidget. When a user selects an image in the list, the metadata widget should update. Show me the correct signal/slot pattern."

**Context:**
- Two widgets need to communicate:
  - ImageListWidget (source): Emits image selection signal
  - MetadataDisplayWidget (target): Updates display
- Parent widget (MainWindow) coordinates communication
- Should use Direct Widget Communication pattern (LoRAIro standard)
- Type-safe signal/slot connections required

## Expected Behavior
1. Skill `lorairo-qt-widget` should be invoked automatically
2. Should demonstrate signal/slot pattern:

   **Phase 1: Pattern Research**
   - Check existing widget communication examples
   - Search memory for signal/slot patterns
   - Review Direct Communication principles

   **Phase 2: Implementation**
   - Show ImageListWidget signal definition:
     ```python
     class ImageListWidget(QWidget):
         image_selected = Signal(int)  # Emits image_id

         def _on_item_clicked(self, item: QListWidgetItem) -> None:
             image_id = item.data(Qt.ItemDataRole.UserRole)
             self.image_selected.emit(image_id)
     ```

   - Show MetadataDisplayWidget slot:
     ```python
     class MetadataDisplayWidget(QWidget):
         @Slot(int)
         def update_metadata(self, image_id: int) -> None:
             # Fetch and display metadata
             ...
     ```

   - Show MainWindow connection:
     ```python
     class MainWindow(QMainWindow):
         def _setup_connections(self) -> None:
             self.image_list_widget.image_selected.connect(
                 self.metadata_widget.update_metadata
             )
     ```

   **Phase 3: Best Practices**
   - Type safety: Signal and Slot types must match
   - Decoupling: Widgets don't know about each other
   - Parent coordinates: MainWindow owns connection
   - Error handling: Slot should handle invalid IDs

3. Should produce:
   - Complete signal/slot example
   - Type-safe connections
   - Direct Communication pattern
   - Best practices explanation

4. Should NOT:
   - Use service layer for widget communication
   - Create tight coupling (widgets knowing each other)
   - Skip type matching
   - Forget error handling in slots

## Success Criteria
- [x] Correct skill invoked (lorairo-qt-widget)
- [x] Pattern research done (existing examples, memory)
- [x] Signal types match Slot types
- [x] Direct Communication pattern used
- [x] Widgets are decoupled (coordinated by parent)
- [x] @Slot decorator with type hint
- [x] Error handling in slot
- [x] Completes without errors

## Model Variations
- **Haiku:** Should show basic signal/slot connection; may need guidance on type matching
- **Sonnet:** Should demonstrate complete pattern with type safety; good decoupling explanation
- **Opus:** May suggest additional patterns (signal chaining, signal transformation); may discuss error handling strategies in depth

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-qt-widget` in metadata
2. Check signal definition:
   - Defined at class level: `image_selected = Signal(int)`
   - Type matches data being emitted
   - Emitted in appropriate method
3. Check slot definition:
   - `@Slot(int)` decorator present
   - Type hint matches signal: `def update_metadata(self, image_id: int)`
   - Handles invalid IDs gracefully
4. Verify connection:
   - Done in parent widget (MainWindow)
   - Type-safe: `image_selected.connect(update_metadata)`
   - Widgets don't reference each other directly
5. Test Direct Communication:
   - No service layer involved
   - Parent coordinates communication
   - Widgets remain decoupled
6. Check error handling:
   - Slot handles None or invalid image_id
   - Doesn't crash on edge cases

## Edge Cases to Test
- Image list is empty (no selection)
- Invalid image_id emitted (should handle gracefully)
- Multiple widgets connected to same signal
- Disconnection when widget is destroyed
