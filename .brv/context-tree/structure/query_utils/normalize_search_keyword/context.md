
def normalize_search_keyword(keyword: str, partial: bool) -> tuple[str, bool]:
    """Normalize a search keyword for SQL LIKE conditions."""
    has_wildcard = "*" in keyword or "%" in keyword or partial
    if "*" in keyword:
        keyword = keyword.replace("*", "%")

    if has_wildcard:
        if not keyword.startswith("%"):
            keyword = "%" + keyword
        if not keyword.endswith("%"):
            keyword = keyword + "%"

    return keyword, has_wildcard
