
class TagSearchRow(TypedDict):
    """Internal repository row for tag search results.

    Keys:
        tag_id: Tag id.
        tag: Normalized tag string.
        source_tag: Source tag if present.
        usage_count: Usage count for the active format.
        alias: True if alias.
        deprecated: True if deprecated.
        type_id: Type id if known.
        type_name: Type name for the active format.
        translations: Language to translations mapping.
        format_statuses: Per-format status mapping.
    """

    tag_id: int
    tag: str
    source_tag: str | None
    usage_count: int
    alias: bool
    deprecated: bool
    type_id: int | None
    type_name: str
    translations: dict[str, list[str]]
    format_statuses: dict[str, dict[str, object]]

---

The `TagSearchRow` TypedDict was introduced in `models.py` to provide a stricter, more defined structure for tag search results. This change improves type safety and code clarity within the data access layer. Previously, search results were handled as more generic dictionaries, which made it difficult to ensure data consistency and led to potential runtime errors. By defining the precise keys and their expected types, `TagSearchRow` helps catch data-related issues early and makes the search result data model easier to understand and maintain.
