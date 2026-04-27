"""db_core の遅延初期化（ensure_tag_db_initialized）のユニットテスト。"""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


class TestEnsureTagDbInitialized:
    """ensure_tag_db_initialized の遅延初期化動作を検証する。"""

    @pytest.fixture(autouse=True)
    def reset_init_flag(self):
        """各テスト前後に _tag_db_initialized フラグと USER_TAG_DB_PATH をリセットする。"""
        import lorairo.database.db_core as db_core

        original_flag = db_core._tag_db_initialized
        original_path = db_core.USER_TAG_DB_PATH
        db_core._tag_db_initialized = False
        db_core.USER_TAG_DB_PATH = None
        yield
        db_core._tag_db_initialized = original_flag
        db_core.USER_TAG_DB_PATH = original_path

    def test_import_does_not_call_initialize_databases(self):
        """db_core をインポートしただけでは initialize_databases は呼ばれない。"""
        import lorairo.database.db_core as db_core

        assert db_core._tag_db_initialized is False
        assert db_core.USER_TAG_DB_PATH is None

    def test_ensure_calls_initialize_databases_once(self):
        """ensure_tag_db_initialized() を呼ぶと initialize_databases が1回だけ実行される。"""
        mock_result = [MagicMock()]
        with patch("genai_tag_db_tools.initialize_databases", return_value=mock_result) as mock_init:
            import lorairo.database.db_core as db_core

            db_core.ensure_tag_db_initialized()

            mock_init.assert_called_once()
            assert db_core._tag_db_initialized is True
            assert db_core.USER_TAG_DB_PATH is not None

    def test_ensure_idempotent_on_repeated_calls(self):
        """ensure_tag_db_initialized() を2回呼んでも initialize_databases は1回だけ実行される。"""
        mock_result = [MagicMock()]
        with patch("genai_tag_db_tools.initialize_databases", return_value=mock_result) as mock_init:
            import lorairo.database.db_core as db_core

            db_core.ensure_tag_db_initialized()
            db_core.ensure_tag_db_initialized()

            assert mock_init.call_count == 1

    def test_hf_token_env_var_passed_to_initialize(self, monkeypatch):
        """HF_TOKEN 環境変数が token 引数として渡される。"""
        monkeypatch.setenv("HF_TOKEN", "test-token-value")
        mock_result = [MagicMock()]
        with patch("genai_tag_db_tools.initialize_databases", return_value=mock_result) as mock_init:
            import lorairo.database.db_core as db_core

            db_core.ensure_tag_db_initialized()

            _, kwargs = mock_init.call_args
            assert kwargs.get("token") == "test-token-value"

    def test_huggingface_token_env_var_passed_to_initialize(self, monkeypatch):
        """HUGGINGFACE_TOKEN 環境変数が token 引数として渡される（HF_TOKEN 未設定時）。"""
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf-token-value")
        mock_result = [MagicMock()]
        with patch("genai_tag_db_tools.initialize_databases", return_value=mock_result) as mock_init:
            import lorairo.database.db_core as db_core

            db_core.ensure_tag_db_initialized()

            _, kwargs = mock_init.call_args
            assert kwargs.get("token") == "hf-token-value"

    def test_failure_does_not_set_initialized_flag(self):
        """initialize_databases が失敗した場合、_tag_db_initialized は True にならない。"""
        with patch("genai_tag_db_tools.initialize_databases", side_effect=OSError("network error")):
            import lorairo.database.db_core as db_core

            with pytest.raises(RuntimeError, match="Tag database initialization failed"):
                db_core.ensure_tag_db_initialized()

            assert db_core._tag_db_initialized is False

    def test_get_user_tag_db_path_returns_none_before_init(self):
        """初期化前は get_user_tag_db_path() が None を返す。"""
        import lorairo.database.db_core as db_core

        assert db_core.get_user_tag_db_path() is None

    def test_get_user_tag_db_path_returns_path_after_init(self):
        """初期化後は get_user_tag_db_path() が Path を返す。"""
        mock_result = [MagicMock()]
        with patch("genai_tag_db_tools.initialize_databases", return_value=mock_result):
            import lorairo.database.db_core as db_core

            db_core.ensure_tag_db_initialized()

            path = db_core.get_user_tag_db_path()
            assert isinstance(path, Path)
            assert path.name == "user_tags.sqlite"
