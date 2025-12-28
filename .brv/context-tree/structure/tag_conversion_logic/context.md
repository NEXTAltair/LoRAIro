
## Relations
@@structure/bulk_tag_search

def convert_tags(repo: MergedTagReader, tags: str, format_name: str, separator: str = ", ") -> str:
    """Convert comma-separated tags to the specified format.
    - Normalize input before lookup
    - Use batch lookup when available
    """
    if not tags.strip():
        return tags

    format_id = repo.get_format_id(format_name)
    if format_id is None:
        return tags

    normalized_tags = _normalize_prompt_tags(tags)
    if not normalized_tags:
        return tags

    tag_map = _lookup_tags(repo, normalized_tags, format_name)
    word_map: dict[str, str] = {}
    converted_list: list[str] = []

    for tag in normalized_tags:
        converted = tag_map.get(tag)
        if converted:
            converted_list.append(converted)
            continue

        if " " in tag:
            words = [word for word in tag.split(" ") if word]
            missing = [word for word in words if word not in word_map]
            if missing:
                word_map.update(_lookup_tags(repo, missing, format_name))
            converted_list.extend([word_map.get(word, word) for word in words])
            continue

        converted_list.append(tag)

    return separator.join(converted_list)
