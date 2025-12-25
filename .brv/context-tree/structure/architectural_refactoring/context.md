
The `TagSearchWidget` was refactored to move filtering controls from the main search criteria area to a new, dedicated filter bar within the results view. This was achieved by reparenting the format, type, language, and usage widgets.

---

The original `tableWidgetResults` was replaced by a `QSplitter` containing the results table and a new detail panel. A filter bar is inserted at the top of the results tab's vertical layout.

---

'''python
# C:\LoRAIro\local_packages\genai-tag-db-tools\src\genai_tag_db_tools\gui\widgets\tag_search.py
def _setup_results_view(self) -> None:
    # ... splitter and view setup ...
    self._setup_results_filter_bar()
    self.verticalLayout.replaceWidget(self.tableWidgetResults, self._results_splitter)
    self.tableWidgetResults.setParent(None)
    self.tableWidgetResults.deleteLater()
'''
