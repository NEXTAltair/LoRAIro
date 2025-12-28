
class TagSearchPreloader:
    """Preload related tag data to avoid N+1 queries during search."""

    def __init__(self, session) -> None:
        self.session = session

    def load(self, tag_ids: set[int]) -> dict[str, object]:
        # ... implementation ...

Added TagSearchPreloader in db/query_utils.py to preload status/format/type/usage/tag/translation mappings. This class is designed to prevent N+1 query problems during tag searches by fetching all necessary related data in a batch operation. The `load` method takes a set of tag IDs and returns a dictionary of preloaded data, including statuses, formats, types, usage counts, tags, and translations.
