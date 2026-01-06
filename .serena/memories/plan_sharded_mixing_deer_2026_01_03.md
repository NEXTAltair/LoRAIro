# Plan: MainWindow UI Redesign - Side-Sliding Edit Panel

**Created**: 2026-01-03 (current session)
**Source**: plan_mode (manual sync via /sync-plan)
**Original File**: sharded-mixing-deer.md
**Status**: planning

---

## Overview

Redesign MainWindow UI to improve the main workflow (search → thumbnail → preview → edit tags/caption/rating) with minimal visual disruption and maximum editing efficiency.

## Core Design: Side-Sliding Edit Panel

**Approach:** Right column is view-only by default. An "Edit" button opens a side-sliding panel from the right containing a unified editing form. After save, the panel closes and changes are reflected immediately.

**Benefits:**
- View layout stays clean and uncluttered
- Editing area expands only when needed
- Single unified form for all edits (Rating/Score/Tags/Caption)
- Clear separation between viewing and editing modes

## Architecture

### Widget Structure

```
PreviewDetailPanel (Right Panel, 40% width)
├── ImagePreviewWidget (65% height)
└── QStackedWidget (35% height)
    ├── [Index 0] SelectedImageDetailsWidget (View-only mode)
    │   ├── Tab 0: Overview (file info + read-only Rating/Score)
    │   ├── Tab 1: Tags (read-only display)
    │   ├── Tab 2: Captions (read-only display)
    │   └── Tab 3: Metadata (read-only display)
    └── [Index 1] ImageEditPanelWidget (Edit mode) - NEW
        ├── Rating: QComboBox (PG, PG-13, R, X, XXX)
        ├── Score: QSlider (0-1000) + value label
        ├── Tags: QTextEdit (editable)
        ├── Caption: QTextEdit (editable)
        └── Buttons: Save, Cancel
```

### Animation

- **Mechanism:** QPropertyAnimation on QStackedWidget geometry
- **Duration:** 300ms with InOutCubic easing curve
- **Trigger:** "Edit" toolbar button (new action: actionEditImage)
- **Smooth transition** between view and edit modes

### Data Flow

```
User clicks Edit
  ↓
ImageEditPanelWidget populated from current image data (DatasetStateManager)
  ↓
QStackedWidget slides to edit mode (300ms animation)
  ↓
User edits Rating/Score/Tags/Caption
  ↓
User clicks Save
  ↓
ImageDBWriteService updates database
  ↓
DatasetStateManager cache refreshed
  ↓
QStackedWidget slides back to view mode (300ms animation)
  ↓
SelectedImageDetailsWidget shows updated data
```

## Implementation Tasks

### Phase 1: Foundation (Days 1-2)

**1.1 Create ImageEditPanelWidget**
- Create `src/lorairo/gui/designer/ImageEditPanelWidget.ui` in Qt Designer
- Generate `src/lorairo/gui/widgets/image_edit_panel_widget.py`
- Implement:
  - `populate_from_image_data(image_data: dict)` - fills form fields
  - `get_edited_data() -> dict` - returns form values
  - `_mark_dirty()` - tracks unsaved changes
  - Signals: `save_requested(dict)`, `cancel_requested()`

**1.2 Remove Status Labels**
- Delete from `src/lorairo/gui/designer/MainWindow.ui`:
  - `frameThumbnailStatusIndicator`
  - `labelStatusIndicatorTitle`
  - `labelStatusCompleted/Partial/Error/Processing`
- Run `uv run python scripts/generate_ui.py`
- Verify no Python code references these widgets

**1.3 Update Splitter Ratios**
- Modify `src/lorairo/gui/services/widget_setup_service.py`:
  - `splitterMainWorkArea`: setSizes([216, 504, 480]) for 18/42/40 ratio
  - `splitterPreviewDetails`: Keep [650, 350] for 65/35 ratio
- Test on different screen sizes

### Phase 2: View-Only Conversion (Days 3-4)

**2.1 Convert SelectedImageDetailsWidget to Read-Only**
- Edit `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui`:
  - **Remove:** comboBoxRating, sliderScore, pushButtonSaveRating, pushButtonSaveScore
  - **Add:** labelRatingValue (read-only), labelScoreValue (read-only)
  - Set textEditCaptionsContent to read-only mode
  - Set labelTagsContent to read-only mode
- Edit `src/lorairo/gui/widgets/selected_image_details_widget.py`:
  - Remove all edit signal handlers: `_on_rating_changed`, `_on_score_changed`, `_on_save_clicked`
  - Update `_update_details_display()` to populate read-only labels
  - Remove ImageDBWriteService connections

**2.2 Remove groupBoxAnnotationResults**
- Delete from `src/lorairo/gui/designer/MainWindow.ui`:
  - `groupBoxAnnotationResults` (entire widget and all tabs)
  - `groupBoxAnnotationControl` (if redundant)
- Update `src/lorairo/gui/window/main_window.py`:
  - Remove `_setup_tag_management_widget()` method
  - Remove annotation results population logic
- Run `uv run python scripts/generate_ui.py`

### Phase 3: Edit Panel Integration (Days 5-7)

**3.1 Add QStackedWidget to MainWindow**
- Edit `src/lorairo/gui/designer/MainWindow.ui`:
  - Replace SelectedImageDetailsWidget container with QStackedWidget
  - Add SelectedImageDetailsWidget to index 0
  - Add ImageEditPanelWidget to index 1
  - Add toolbar action: `actionEditImage` ("Edit Image", icon: edit icon, shortcut: Ctrl+E)
- Run `uv run python scripts/generate_ui.py`

**3.2 Implement Animation Logic**
- Edit `src/lorairo/gui/window/main_window.py`:
  - Add method: `_transition_to_edit_mode()`:
    - Populate ImageEditPanelWidget from current image data
    - Create QPropertyAnimation (300ms, InOutCubic)
    - Set QStackedWidget currentIndex to 1
  - Add method: `_transition_to_view_mode()`:
    - Create QPropertyAnimation (300ms, InOutCubic)
    - Set QStackedWidget currentIndex to 0
  - Connect toolbar action: `actionEditImage.triggered → _transition_to_edit_mode`
  - Connect panel signals: `save_requested → _handle_edit_save`, `cancel_requested → _transition_to_view_mode`

**3.3 Implement Save Handler**
- Add method: `_handle_edit_save(edited_data: dict)`:
  - Call ImageDBWriteService to update database
  - Refresh DatasetStateManager cache
  - Call `_transition_to_view_mode()`
  - Show success notification

**3.4 Add Auto-Save Draft**
- Implement QTimer-based auto-save every 30s
- Save draft to QSettings
- Restore draft on panel open (if exists)

### Phase 4: Favorite Filters (Days 8-9)

**4.1 Create FavoriteFiltersService**
- Create `src/lorairo/services/favorite_filters_service.py`:
  - Storage: QSettings with JSON serialization
  - Methods:
    - `save_filter(name: str, filter_dict: dict) -> bool`
    - `load_filter(name: str) -> dict | None`
    - `list_filters() -> list[str]`
    - `delete_filter(name: str) -> bool`
  - Validation: Duplicate name checking, JSON schema validation

**4.2 Update FilterSearchPanel UI**
- Edit `src/lorairo/gui/widgets/filter_search_panel.py` (or its .ui file):
  - Add collapsible QGroupBox: "お気に入りフィルタ"
  - Add QListWidget for saved filters
  - Add buttons: "保存", "読込", "削除"
- Implement handlers:
  - `_save_current_filter()` - prompt for name, save to service
  - `_load_selected_filter()` - apply filter from service
  - `_delete_selected_filter()` - remove from service

**4.3 Service Integration**
- Register FavoriteFiltersService in ServiceContainer
- Connect FilterSearchPanel to service
- Test persistence across application restarts

### Phase 5: Testing & Polish (Days 10-11)

**5.1 Unit Tests**
- `tests/unit/gui/widgets/test_image_edit_panel_widget.py`:
  - Test initialization, population, dirty state tracking
  - Test signals (save_requested, cancel_requested)
- `tests/unit/services/test_favorite_filters_service.py`:
  - Test save/load/delete cycles
  - Test JSON serialization edge cases

**5.2 Integration Tests**
- `tests/integration/gui/test_edit_panel_workflow.py`:
  - Test full workflow: select → edit → save → verify DB + UI
  - Test cancel workflow: edit → cancel → verify no changes
  - Test auto-save draft functionality

**5.3 Manual Testing**
- Animation smoothness (60fps target, 300ms ± 50ms)
- Multiple screen sizes (1920x1080, 1366x768, 2560x1440)
- Keyboard navigation (Tab order, Enter/Esc shortcuts)
- Rapid mode switching (edit → cancel → edit → save)

**5.4 Documentation**
- Update `docs/services.md` with FavoriteFiltersService
- Update `CLAUDE.md` if UI architecture changes significantly
- Add inline comments for animation logic

## Critical Files

**New Files:**
- `src/lorairo/gui/designer/ImageEditPanelWidget.ui`
- `src/lorairo/gui/widgets/image_edit_panel_widget.py`
- `src/lorairo/services/favorite_filters_service.py`

**Modified Files:**
- `src/lorairo/gui/designer/MainWindow.ui` (major changes: QStackedWidget, remove status labels, toolbar action)
- `src/lorairo/gui/window/main_window.py` (animation logic, edit handlers)
- `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui` (remove edit controls)
- `src/lorairo/gui/widgets/selected_image_details_widget.py` (convert to read-only)
- `src/lorairo/gui/services/widget_setup_service.py` (splitter ratios)
- `src/lorairo/gui/widgets/filter_search_panel.py` (favorite filters UI)

## Success Criteria

**Functional Requirements:**
- ✅ Edit panel slides smoothly in 300ms with no frame drops
- ✅ Save updates database and refreshes view-only display immediately
- ✅ Favorite filters save/load correctly across sessions
- ✅ Status labels completely removed, no console errors
- ✅ Splitter ratios correct: 18/42/40 (horizontal), 65/35 (vertical)

**Performance Targets:**
- ✅ Animation: 300ms ± 50ms, smooth 60fps
- ✅ Save operation: < 500ms
- ✅ Filter load: < 100ms
- ✅ Auto-save draft: < 50ms (non-blocking)

**Quality Standards:**
- ✅ 75%+ test coverage on new code
- ✅ All pytest tests pass (unit + integration + GUI)
- ✅ Ruff format clean (`uv run ruff format src/`)
- ✅ MyPy type checking clean (`uv run mypy -p lorairo`)
- ✅ No TODO/FIXME tags remaining in production code

## Risk Mitigation

**High Risks:**
1. **Animation Performance on Low-End Hardware**
   - Mitigation: Profile on reference hardware, add fallback to instant switch if lag > 100ms detected
   - Fallback: QSettings option to disable animations

2. **Data Loss During Unsaved Edit**
   - Mitigation: Auto-save draft every 30s to QSettings
   - Recovery: Prompt to restore draft on panel open

3. **UI Generation Failures**
   - Mitigation: Version control all .ui files, maintain backups before regeneration
   - Recovery: Git revert to last working state

**Medium Risks:**
1. **Filter Serialization Edge Cases**
   - Mitigation: JSON schema validation, comprehensive unit tests

2. **Splitter Ratio Inconsistency**
   - Mitigation: Test on multiple screen sizes, add min/max width constraints

3. **Signal Connection Complexity**
   - Mitigation: Add connection verification in debug mode, comprehensive logging

## Timeline

- **Phase 1 (Foundation):** Days 1-2
- **Phase 2 (View-Only):** Days 3-4
- **Phase 3 (Edit Panel):** Days 5-7
- **Phase 4 (Filters):** Days 8-9
- **Phase 5 (Testing):** Days 10-11

**Total Estimated Time:** 11 days

## Next Steps (After Plan Approval)

1. Execute `/implement` command to begin Phase 1
2. Create ImageEditPanelWidget in Qt Designer
3. Remove status labels and update splitter ratios
4. Run tests after each phase to catch issues early

---

**Plan Status:** Ready for Review
**Plan Date:** 2026-01-03
**Target Start:** After user approval
