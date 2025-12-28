
## Relations
@structure/tag_search_data_model
@structure/tag_search_data_flow

Removed paging from tag search: dropped limit/offset fields from TagSearchRequest, removed CLI args and all limit/offset plumbing across core_api/services/worker/repository, and removed pagination slicing in TagRepository.search_tags.
