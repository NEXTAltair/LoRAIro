
The tag database builder integrates tag information from multiple sources into a unified SQLite database. It is designed to handle different data formats and schemas from various sites, normalize the data, and manage conflicts. The builder is orchestrated by the `build_dataset` function in `builder.py`, which processes sources like the existing `tags_v4.db`, CSV files, and `tags.sqlite` files from the `deepghs/site_tags` project.

Related:
- Integrity checks and upstream data damage handling: `.brv/context-tree/structure/tag_database_builder/data_integrity/context.md`
