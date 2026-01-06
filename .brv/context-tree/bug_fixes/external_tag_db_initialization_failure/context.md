
## Relations
@structure/external_tag_db_initialization

LoRAIro now treats external tag DB init failure as fatal. Previously, a failure would result in tag features being disabled. Now, `db_core.py` raises a `RuntimeError` after logging the error, which is a fatal application error. This ensures that the application does not run in a degraded state without access to the external tag database.

---

The following code from `db_core.py` shows the implementation of this change:
'''python
except Exception as e:
    USER_TAG_DB_PATH = None
    logger.error(
        f"Failed to initialize tag databases: {e}. "
        "LoRAIro cannot start without external tag DB access."
    )
    raise RuntimeError("Tag database initialization failed") from e
'''
