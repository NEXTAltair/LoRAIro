
## Relations
@structure/TagRepository

After refactoring `TagRepository` to focus on write operations, methods like `create_tag` and `ensure_tag_with_id` will still need to perform read checks (e.g., to see if a tag already exists). To solve this, the new `TagReader` instance should be injected into `TagRepository`. The `get_default_repository` function should be updated to handle this wiring, ensuring that write instances of the repository have access to a reader.
