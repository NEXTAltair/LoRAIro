
Extracted keyword normalization for LIKE/wildcard handling into db/query_utils.py (normalize_search_keyword) and reused in TagRepository.search_tag_ids/search_tags to centralize wildcard normalization.
