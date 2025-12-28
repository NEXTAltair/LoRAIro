
Extracted min_usage/max_usage branching in TagSearchQueryBuilder.apply_usage_filter into helper methods (_query_usage_tag_ids, _should_include_missing_usage, _include_missing_usage_tag_ids) to reduce complexity while preserving behavior.

---

def apply_usage_filter(
    self,
    tag_ids: set[int],
    format_id: int,
    min_usage: int | None,
    max_usage: int | None,
) -> set[int]:
    if min_usage is None and max_usage is None:
        return tag_ids

    usage_tag_ids = self._query_usage_tag_ids(format_id, min_usage, max_usage)
    if self._should_include_missing_usage(min_usage, max_usage):
        usage_tag_ids = self._include_missing_usage_tag_ids(tag_ids, format_id, usage_tag_ids)

    return tag_ids & usage_tag_ids

---

def _query_usage_tag_ids(
    self,
    format_id: int,
    min_usage: int | None,
    max_usage: int | None,
) -> set[int]:
    usage_query = self.session.query(TagUsageCounts.tag_id)
    if format_id:
        usage_query = usage_query.filter(TagUsageCounts.format_id == format_id)
    if min_usage is not None:
        usage_query = usage_query.filter(TagUsageCounts.count >= min_usage)
    if max_usage is not None:
        usage_query = usage_query.filter(TagUsageCounts.count <= max_usage)
    return {row[0] for row in usage_query.all()}

---

def _should_include_missing_usage(
    self,
    min_usage: int | None,
    max_usage: int | None,
) -> bool:
    return (min_usage is None or min_usage <= 0) and (max_usage is None or max_usage >= 0)

---

def _include_missing_usage_tag_ids(
    self,
    tag_ids: set[int],
    format_id: int,
    usage_tag_ids: set[int],
) -> set[int]:
    usage_all_query = self.session.query(TagUsageCounts.tag_id)
    if format_id:
        usage_all_query = usage_all_query.filter(TagUsageCounts.format_id == format_id)
    usage_all_tag_ids = {row[0] for row in usage_all_query.all()}
    return usage_tag_ids | (tag_ids - usage_all_tag_ids)
