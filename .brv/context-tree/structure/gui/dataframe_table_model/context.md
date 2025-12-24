
## Relations
@design/ui_components/tag_search_results

The `DataFrameTableModel` has been enhanced to better support master/detail views. It now accepts a `display_columns` argument, allowing the table to show a subset of columns from the full DataFrame. The model also provides a `get_row` method to expose the complete row data, which is used by the detail panel to display additional information not shown in the main table.
