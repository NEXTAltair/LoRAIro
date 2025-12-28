
## Relations
@structure/tag_search_data_flow

Tag search translations are retrieved directly from the database without language code normalization. The `get_tag_languages()` method in the `TagRepository` returns a list of distinct language codes present in the `TagTranslation` table. The user interface, specifically the `TagSearchWidget`, then uses these exact language codes to look up the corresponding translations from a dictionary.

---

The database currently contains specific Chinese language codes like `zh`, `zh-cn`, and `zh-hk`, but not broader codes like `zh-tw` or `zh-hans`. As a result, when a user selects a specific variant like `zh-cn` or `zh-hk` in the UI, the translation list will only show values if an exact match for that language code is found in the tag's translation data. If no exact match exists, the list will appear empty, even if other `zh-` prefixed translations are available. There is a special handling for 'zh' to show all zh prefixed translations.

---

Relevant code can be found in `C:\LoRAIro\local_packages\genai-tag-db-tools\src\genai_tag_db_tools\db\repository.py` (specifically `get_tag_languages` method) and `C:\LoRAIro\local_packages\genai-tag-db-tools\src\genai_tag_db_tools\gui\widgets\tag_search.py` (specifically `_update_translation_details` method).
