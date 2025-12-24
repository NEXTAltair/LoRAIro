
## Relations
@@structure/tag_search_data_model

tests updated mock DataFrame columns.

---

self.mock_search_tags = MagicMock(
            return_value=pl.DataFrame(
                [
                    {
                        "tag": "cat",
                        "translations": {"ja": ["猫"]},
                        "format_statuses": {
                            "danbooru": {
                                "alias": False,
                                "deprecated": False,
                                "usage_count": 50,
                                "type_id": 0,
                                "type_name": "general",
                            }
                        },
                    }
                ]
            )
        )
