
Added partial matching control to TagSearchRequest and core_api.search_tags so API callers can switch between partial and exact matching. TagSearchService now passes the partial flag through, and CLI search supports --exact to force exact matching (default remains partial).

---

The `TagSearchRequest` model now includes a `partial` boolean field, which defaults to `True`. This allows API callers to specify whether the search should use partial or exact matching. The `core_api.search_tags` function now accepts this `partial` flag and passes it to the `repo.search_tags` method.

---

The `TagSearchService` was updated to pass the `partial` flag from the `TagSearchRequest` to the `core_api.search_tags` function.
