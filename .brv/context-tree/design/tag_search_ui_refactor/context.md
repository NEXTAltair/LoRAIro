
## Relations
@@design/tag_search_translation_panel

The `TagSearchWidget` UI has been refactored to improve usability and functionality. The right translation panel now includes an inline language dropdown, which allows users to change the translation language independently of the main search language filter. This dropdown is populated with available tag languages and defaults to 'ja'. The `_setup_results_view` method in `tag_search.py` is responsible for creating the new UI components, including the `_translation_language_combo` QComboBox.
