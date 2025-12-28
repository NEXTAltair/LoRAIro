
## Relations
@bug_fixes/get_tag_id_by_name-search-logic

The `get_tag_id_by_name` function is responsible for retrieving a tag's ID based on its name. It now incorporates `normalize_search_keyword` to decide between an exact match and a LIKE query, which simplifies the matching logic and ensures consistent behavior. This function is a core part of the `TagRepository` and is used to resolve tag names to their corresponding IDs.

---

def get_tag_id_by_name(self, keyword: str, partial: bool = False) -> int | None:
    """タグ名でtag_idを検索する。'*' はワイルドカードとして扱う。"""
    keyword, use_like = normalize_search_keyword(keyword, partial)

    with self.session_factory() as session:
        query = session.query(Tag)

        if use_like:
            query = query.filter(Tag.tag.like(keyword))
        else:
            query = query.filter(Tag.tag == keyword)

        results = query.all()

        if not results:
            return None
        if len(results) == 1:
            return results[0].tag_id

        if use_like:
            return results[0].tag_id

        raise ValueError(f"複数ヒット: {results}")
