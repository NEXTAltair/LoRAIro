# Scenario: GUI Test Creation with pytest-qt

## Input
**User request:** "Create GUI tests for the FilterPanelWidget. Test signal emissions, user interactions, and widget state. Use pytest-qt for headless execution."

**Context:**
- LoRAIro GUI testing requirements:
  - pytest-qt framework
  - Headless execution (QT_QPA_PLATFORM=offscreen)
  - AAA pattern
  - Signal/slot testing
  - User interaction simulation (clicks, input)
- Target widget: FilterPanelWidget in `src/lorairo/gui/widgets/filter_panel_widget.py`
- Test location: `tests/integration/gui/widgets/`
- pytest marker: @pytest.mark.gui

## Expected Behavior
1. Skill `lorairo-test-generator` should be invoked automatically
2. Should guide GUI test creation:

   **Phase 1: Pattern Research**
   - Examine existing GUI tests
   - Check memory for pytest-qt patterns
   - Review FilterPanelWidget signals and methods

   **Phase 2: Fixture Creation**
   - Create qtbot fixture (provided by pytest-qt)
   - Create widget instance fixture

   **Phase 3: Test Implementation**
   - Signal emission tests:
     ```python
     @pytest.mark.gui
     def test_filter_changed_signal_emitted(filter_panel_widget, qtbot):
         # Arrange
         with qtbot.waitSignal(filter_panel_widget.filter_changed, timeout=1000):
             # Act
             filter_panel_widget.tag_combo.setCurrentText("landscape")

         # Assert (signal was emitted, verified by waitSignal)
     ```

   - User interaction tests:
     ```python
     @pytest.mark.gui
     def test_apply_button_click(filter_panel_widget, qtbot):
         # Arrange
         filter_panel_widget.tag_combo.setCurrentText("portrait")
         signals = []
         filter_panel_widget.filter_changed.connect(lambda: signals.append(True))

         # Act
         qtbot.mouseClick(filter_panel_widget.apply_button, Qt.MouseButton.LeftButton)

         # Assert
         assert len(signals) == 1
     ```

   - Widget state tests:
     ```python
     @pytest.mark.gui
     def test_reset_button_clears_filters(filter_panel_widget, qtbot):
         # Arrange
         filter_panel_widget.tag_combo.setCurrentText("nature")

         # Act
         qtbot.mouseClick(filter_panel_widget.reset_button, Qt.MouseButton.LeftButton)

         # Assert
         assert filter_panel_widget.tag_combo.currentText() == ""
     ```

   **Phase 4: Headless Execution**
   - Mention QT_QPA_PLATFORM=offscreen
   - Suggest running with: `uv run pytest -m gui`

3. Should produce:
   - Complete GUI test suite
   - pytest-qt usage (qtbot)
   - Signal/slot testing
   - User interaction simulation
   - Widget state verification
   - Headless-compatible

4. Should NOT:
   - Require GUI display (must run headless)
   - Skip signal testing
   - Forget qtbot fixture
   - Mix unit and GUI tests

## Success Criteria
- [x] Correct skill invoked (lorairo-test-generator)
- [x] Pattern research done (existing GUI tests)
- [x] qtbot fixture used correctly
- [x] Signals tested (waitSignal or manual connection)
- [x] User interactions simulated (mouseClick, keyPress)
- [x] Widget state verified
- [x] @pytest.mark.gui marker present
- [x] Tests run headless successfully
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic GUI tests; may need guidance on pytest-qt API and signal testing
- **Sonnet:** Should create comprehensive GUI test suite; good qtbot usage and interaction simulation
- **Opus:** May suggest advanced patterns (async signal testing, complex interactions); excellent state verification strategies

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-test-generator` in metadata
2. Check pytest-qt usage:
   - qtbot fixture used in all tests
   - `qtbot.waitSignal()` for signal testing
   - `qtbot.mouseClick()` / `qtbot.keyPress()` for interactions
3. Verify signal testing:
   - Signals tested with waitSignal or manual connection
   - Timeout specified (e.g., 1000ms)
   - Signal data verified if applicable
4. Check user interaction tests:
   - Button clicks simulated
   - Input field changes tested
   - Combo box selections tested
5. Verify widget state:
   - Initial state checked
   - State after interactions verified
   - Reset/clear functionality tested
6. Check pytest marker:
   - `@pytest.mark.gui` on all GUI tests
7. Run tests headless:
   ```bash
   QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/gui/widgets/test_filter_panel_widget.py -m gui
   ```
8. Verify execution:
   - Tests run without display
   - All tests pass
   - No GUI windows opened

## Edge Cases to Test
- Signal emitted multiple times (debouncing)
- Rapid user interactions (double-click prevention)
- Widget disabled state (interactions ignored)
- Invalid input handling (validation)
