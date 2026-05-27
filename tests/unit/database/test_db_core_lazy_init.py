"""db_core の遅延初期化（ensure_tag_db_initialized）のユニットテスト。"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestDefaultDbDirectoryLazyInit:
    """デフォルト DB ディレクトリの遅延作成を検証する。"""

    def test_import_does_not_create_repo_root_project_dir(self):
        """db_core import だけでは repo 直下 lorairo_data に自動プロジェクトを作らない。"""
        repo_root = Path(__file__).resolve().parents[3]
        data_root = repo_root / "lorairo_data"
        before = set(data_root.glob("main_dataset_*")) if data_root.exists() else set()
        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
        script = (
            "import lorairo.database.db_core as db_core; print(db_core.DB_DIR); print(db_core.IMG_DB_PATH)"
        )

        try:
            subprocess.run(
                [sys.executable, "-c", script],
                cwd=repo_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            after = set(data_root.glob("main_dataset_*")) if data_root.exists() else set()
            assert after == before
        finally:
            after_cleanup = set(data_root.glob("main_dataset_*")) if data_root.exists() else set()
            for created_path in after_cleanup - before:
                if created_path.is_dir() and not any(created_path.iterdir()):
                    shutil.rmtree(created_path)

    def test_default_session_local_creates_auto_project_dir_for_empty_database_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """database_dir が空なら DefaultSessionLocal() の明示利用時にだけ自動作成する。"""
        import lorairo.database.db_core as db_core

        session = object()
        data_root = tmp_path / "lorairo_data"
        monkeypatch.setattr(
            db_core,
            "dir_config",
            {
                "database_dir": "",
                "database_base_dir": str(data_root),
                "database_project_name": "main_dataset",
            },
        )
        preview_dir = db_core._resolve_auto_project_dir(create=False)
        monkeypatch.setattr(db_core, "DB_DIR", preview_dir)
        monkeypatch.setattr(db_core, "IMG_DB_PATH", preview_dir / db_core.IMG_DB_FILENAME)
        monkeypatch.setattr(
            db_core,
            "DATABASE_URL",
            f"sqlite:///{(preview_dir / db_core.IMG_DB_FILENAME).resolve()}?check_same_thread=False",
        )
        monkeypatch.setattr(db_core, "_default_session_factory", None)
        monkeypatch.setattr(db_core, "_default_db_dir_materialized", False)
        monkeypatch.setattr(db_core, "_prepare_project_database", lambda db_path: object())
        monkeypatch.setattr(db_core, "create_session_factory", lambda engine: lambda: session)

        assert not data_root.exists()

        assert db_core.DefaultSessionLocal() is session

        assert data_root.exists()
        assert db_core.DB_DIR.exists()
        assert db_core.DB_DIR.parent == data_root
        assert db_core.DB_DIR.name.startswith("main_dataset_")
        assert db_core.IMG_DB_PATH == db_core.DB_DIR / db_core.IMG_DB_FILENAME

    def test_default_session_local_recomputes_auto_project_dir_when_preview_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """import 時の候補が先に作られていても、明示利用時に次の連番を採番する。"""
        import lorairo.database.db_core as db_core

        session = object()
        data_root = tmp_path / "lorairo_data"
        monkeypatch.setattr(
            db_core,
            "dir_config",
            {
                "database_dir": "",
                "database_base_dir": str(data_root),
                "database_project_name": "main_dataset",
            },
        )
        preview_dir = db_core._resolve_auto_project_dir(create=False)
        preview_dir.mkdir(parents=True)
        monkeypatch.setattr(db_core, "DB_DIR", preview_dir)
        monkeypatch.setattr(db_core, "IMG_DB_PATH", preview_dir / db_core.IMG_DB_FILENAME)
        monkeypatch.setattr(db_core, "_default_session_factory", None)
        monkeypatch.setattr(db_core, "_default_db_dir_materialized", False)
        monkeypatch.setattr(db_core, "_prepare_project_database", lambda db_path: object())
        monkeypatch.setattr(db_core, "create_session_factory", lambda engine: lambda: session)

        assert db_core.DefaultSessionLocal() is session

        assert db_core.DB_DIR != preview_dir
        assert db_core.DB_DIR.parent == data_root
        assert db_core.DB_DIR.name > preview_dir.name
        assert db_core.IMG_DB_PATH == db_core.DB_DIR / db_core.IMG_DB_FILENAME

    def test_default_session_local_reuses_materialized_auto_project_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """タグ DB 初期化などで作成済みの自動プロジェクトは default session でも再利用する。"""
        import lorairo.database.db_core as db_core

        session = object()
        data_root = tmp_path / "lorairo_data"
        monkeypatch.setattr(
            db_core,
            "dir_config",
            {
                "database_dir": "",
                "database_base_dir": str(data_root),
                "database_project_name": "main_dataset",
            },
        )
        monkeypatch.setattr(db_core, "_default_db_dir_materialized", False)

        materialized_dir = db_core.ensure_default_db_dir()
        monkeypatch.setattr(db_core, "DB_DIR", materialized_dir)
        monkeypatch.setattr(db_core, "IMG_DB_PATH", materialized_dir / db_core.IMG_DB_FILENAME)
        monkeypatch.setattr(db_core, "_default_session_factory", None)
        monkeypatch.setattr(db_core, "_prepare_project_database", lambda db_path: object())
        monkeypatch.setattr(db_core, "create_session_factory", lambda engine: lambda: session)

        assert db_core.DefaultSessionLocal() is session

        assert db_core.DB_DIR == materialized_dir
        assert db_core.IMG_DB_PATH == materialized_dir / db_core.IMG_DB_FILENAME
        assert len(list(data_root.glob("main_dataset_*"))) == 1
