
## Relations
@structure/TagRepository/get_tag_id_by_name

The `get_tag_id_by_name` function was updated to standardize its search logic. It now uses the `normalize_search_keyword` utility to handle wildcard characters and determine whether a LIKE query or an exact match should be performed. This change eliminates inconsistencies in how matching was handled, preventing issues with duplicate percentage signs and divergence in `use_like` behavior.

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
