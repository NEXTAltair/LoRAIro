
## Relations
@structure/TagRepository
@structure/MergedTagReader

`MergedTagReader` currently delegates read operations to `TagRepository`. If read methods (e.g., `get_*`, `list_*`, `search_*`) are removed from `TagRepository` as part of a refactor, `MergedTagReader` will break. To address this, a new read-only repository class (e.g., `TagReader`) should be introduced. `MergedTagReader` would then use this new `TagReader` for both base and user repositories, decoupling it from the write-focused `TagRepository`.
