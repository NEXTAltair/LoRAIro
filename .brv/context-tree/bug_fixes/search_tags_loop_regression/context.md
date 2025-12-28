
## Relations
@@structure/tag_search_data_flow

Fixed search_tags loop regressions: removed stray tags_by_id assignment, restored safe tag_obj lookup and default initializations for usage/alias/type/preferred/deprecated to avoid KeyError and undefined vars.
