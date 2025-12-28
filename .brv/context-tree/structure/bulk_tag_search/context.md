
class TagRepository:
    ...
    def search_tags_bulk(
        self,
        keywords: list[str],
        *,
        format_name: str | None = None,
        resolve_preferred: bool = False,
    ) -> dict[str, TagSearchRow]:
        ...

---

class TagSearchQueryBuilder:
    ...
    def initial_tag_ids_for_keywords(self, keywords: list[str]) -> dict[str, set[int]]:
        ...
