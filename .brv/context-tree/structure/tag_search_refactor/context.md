
def search_tags(
        self,
        keyword: str,
        *,
        partial: bool = False,
        format_name: str | None = None,
        type_name: str | None = None,
        language: str | None = None,
        min_usage: int | None = None,
        max_usage: int | None = None,
        alias: bool | None = None,
        resolve_preferred: bool = False,
    ) -> list[TagSearchRow]:

---

class TagSearchResultBuilder:
    """Build a single search result row from preloaded data."""

    def __init__(
        self,
        *,
        format_id: int,
        resolve_preferred: bool,
        logger: Logger | None = None,
    ) -> None:
        self.format_id = format_id
        self.resolve_preferred = resolve_preferred
        self.logger = logger

    def build_row(self, tag_id: int, preloaded: dict[str, object]) -> TagSearchRow | None:

---

To align with the introduction of the `TagSearchRow` TypedDict, several key components in the tag search functionality were refactored. The `search_tags` methods in both `TagRepository` and `MergedTagReader` now have their return types annotated as `list[TagSearchRow]`, ensuring that their output conforms to the new, stricter data model. Additionally, the `TagSearchResultBuilder`'s `build_row` method was updated to return `TagSearchRow | None`, which makes the entire search data pipeline more robust and type-safe. This refactoring was a necessary step to fully leverage the benefits of the new `TagSearchRow` type and improve the overall quality of the codebase.
