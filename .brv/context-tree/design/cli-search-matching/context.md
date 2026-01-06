
The command-line interface (CLI) for searching tags now supports an `--exact` flag. When this flag is used, it forces the search to use exact matching. If the flag is not provided, the search defaults to partial matching.

---

The `cmd_search` function in the `cli.py` file was updated to support the `--exact` flag. This flag is used to set the `partial` field in the `TagSearchRequest` to `False` when the flag is present.
