
## Relations
@structure/application_architecture

As part of the repository refactor, all call sites currently using `get_default_repository` must be updated to use a new `get_default_reader` function. This affects several key services and modules, including `TagSearchService`, `TagStatisticsService`, and `TagCoreService` in `app_services.py`, as well as `cli.py`, `tag_search.py`, and `tag_statistics.py`.
