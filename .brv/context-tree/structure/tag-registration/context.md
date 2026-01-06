
''LoRAIro registers missing tags via `ImageRepository._get_or_create_tag_id_external`. The process involves several steps:
1.  **Normalization**: The input tag string is first normalized using `TagCleaner.clean_format`.
2.  **Search**: It searches for the normalized tag using `search_tags` with a `MergedTagReader`. If found, the existing tag_id is returned.
3.  **Registration**: If the tag is not found, it proceeds to register it. It initializes `TagRegisterService` if it hasn't been already.
4.  **Service Call**: It calls `TagRegisterService.register_tag` with a `TagRegisterRequest`, providing the normalized tag, the original source tag, and setting `format_name` to "Lorairo" and `type_name` to "unknown".
5.  **Error Handling**: The registration process includes robust error handling. If an `IntegrityError` occurs (e.g., a race condition where another process registers the tag simultaneously), it retries the search to fetch the newly created tag_id.
6.  **Fallback**: If the `MergedTagReader` or `TagRegisterService` is unavailable or fails to initialize, the function gracefully falls back, returning `tag_id=None`. This ensures that tag operations can continue without relying on the external tag database.

This entire mechanism is encapsulated within `_get_or_create_tag_id_external`, which is called by `_save_tags` when processing annotations for an image. The `TagRegisterService` itself handles the logic of creating format and type entries in the database if they do not already exist.
'''
