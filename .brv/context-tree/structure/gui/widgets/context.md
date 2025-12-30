
## Relations
@@bug_fixes/mypy-fixes-gui-services

The GUI is composed of several QWidgets. Recent mypy fixes involved adding Optional annotations to widget attributes in `TagSearchWidget` that are initialized post-construction (e.g., `_results_view: QTableView | None = None`). This handles cases where widgets are not immediately available. In `TagCleanerWidget`, `findText` was updated to use `Qt.MatchFlag.MatchFixedString` to prevent partial matches when selecting a default format like 'danbooru'.

---

In `MainWindow`, the service attributes (`tag_search_service`, `tag_cleaner_service`, etc.) are now typed as `Optional` because they are only instantiated after the database has been successfully initialized, which happens after the main window's `__init__` is called.
