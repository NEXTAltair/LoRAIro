
# tests/conftest.py
# Mock genai-tag-db-tools initialization to prevent RuntimeError during db_core import

import unittest.mock
from pathlib import Path as _MockPath

# Mock ensure_databases to return successful result
_mock_ensure_result = unittest.mock.Mock()
_mock_ensure_result.db_path = str(_MockPath("/tmp/test_tag_db.db"))

# Mock runtime functions
_runtime_patches = [
    unittest.mock.patch(
        "genai_tag_db_tools.ensure_databases",
        return_value=[_mock_ensure_result],
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.set_base_database_paths",
        return_value=None,
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.init_engine",
        return_value=None,
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.init_user_db",
        return_value=_MockPath("/tmp/test_user_tag_db.db"),
    ),
]

# Start all patches at module level
for _patch in _runtime_patches:
    _patch.start()

---

In `tests/conftest.py`, module-level patches are applied to the `genai-tag-db-tools` initialization functions (`ensure_databases`, `runtime.set_base_database_paths`, `init_engine`, `init_user_db`). This is a crucial workaround to prevent a `RuntimeError` that occurs from `db_core` when tests are being initialized. These patches are activated at import time and persist for the entire test suite, ensuring a stable environment for database-related tests.
