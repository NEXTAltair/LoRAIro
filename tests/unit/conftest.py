# tests/unit/conftest.py
"""
ユニットテスト層の共有フィクスチャ

責務:
- 外部API モック実装（OpenAI, Google等）
- ダミーデータ生成
- サービス/マネージャー用モック

このファイルは tests/conftest.py (ルート) に依存します。
ルート conftest では genai-tag-db-tools モックと Qt 設定が済みです。
"""

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PIL import Image
from sqlalchemy.engine import Engine

# ===== External API Mocks =====


@pytest.fixture
def mock_openai():
    """OpenAI API モック"""
    with patch("openai.ChatCompletion.create") as mock:
        mock.return_value = Mock(choices=[Mock(message=Mock(content="test response"))])
        yield mock


@pytest.fixture
def mock_google_vision():
    """Google Vision API モック"""
    with patch("google.cloud.vision.ImageAnnotatorClient") as mock:
        yield mock


@pytest.fixture
def mock_anthropic():
    """Anthropic Claude API モック"""
    with patch("anthropic.Anthropic") as mock:
        yield mock


# ===== Dummy Data Fixtures =====


@pytest.fixture
def dummy_pil_image() -> Image.Image:
    """ダミー PIL Image（100x100 RGB）"""
    return Image.new("RGB", (100, 100), color="red")


@pytest.fixture
def dummy_image_array() -> np.ndarray:
    """ダミー numpy 配列（100x100x3）"""
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def dummy_image_path(tmp_path):
    """ダミー画像ファイルパス"""
    img = Image.new("RGB", (100, 100), color="blue")
    img_path = tmp_path / "test_image.png"
    img.save(img_path)
    return img_path


# ===== Service Mocks =====


@pytest.fixture
def mock_config_service():
    """ConfigService モック"""
    mock = Mock()
    mock.get_setting.return_value = None
    mock.get_all_settings.return_value = {}
    return mock


@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManager モック"""
    mock = Mock()
    mock.get_all_images.return_value = []
    mock.save_image.return_value = None
    return mock


@pytest.fixture
def mock_file_system_manager():
    """FileSystemManager モック"""
    mock = Mock()
    mock.get_image_files.return_value = []
    mock.create_directory.return_value = None
    return mock


@pytest.fixture
def mock_image_processor():
    """ImageProcessor モック"""
    mock = Mock()
    mock.process.return_value = np.zeros((256, 256, 3))
    return mock


@pytest.fixture
def mock_worker_service():
    """WorkerService モック"""
    mock = Mock()
    mock.get_active_worker_count.return_value = 0
    mock.cancel_all_workers.return_value = True
    return mock


# ===== Test Data Factories =====


@pytest.fixture
def sample_image_metadata():
    """サンプル画像メタデータ"""
    return {
        "id": 1,
        "filename": "test.png",
        "original_path": "/tmp/test.png",
        "phash": "abc123",
        "width": 512,
        "height": 512,
    }


@pytest.fixture
def sample_annotation():
    """サンプルアノテーション"""
    return {
        "text": "a dog running in a field",
        "tags": ["dog", "running", "field"],
        "model": "gpt-4",
    }


# ===== Alembic =====


@pytest.fixture(scope="session", autouse=True)
def _reuse_alembic_script_directory() -> Iterator[None]:
    """同じ migration 設定の ``ScriptDirectory`` をセッション内で使い回す。

    Alembic は command 実行や head 照会のたびに versions を全件読み込み直し、9p 上では
    1 回 1.2 秒前後かかる (大半が stat)。revision ファイルはテスト中に変わらないので、
    DB URL 以外の設定が同じなら読み込み済みのものを返す。upgrade / downgrade / stamp の
    実行と env.py の実行は毎回行われる。
    """
    from alembic.script import ScriptDirectory

    original = ScriptDirectory.from_config.__func__  # classmethod の実体
    cache: dict[tuple[object, ...], ScriptDirectory] = {}

    def from_config(cls: type[ScriptDirectory], config: Any) -> ScriptDirectory:
        options = config.get_section(config.config_ini_section) or {}
        key = (
            cls,
            tuple(sorted((name, value) for name, value in options.items() if name != "sqlalchemy.url")),
            config.messaging_opts.get("quiet"),
        )
        if key not in cache:
            cache[key] = original(cls, config)
        return cache[key]

    patcher = pytest.MonkeyPatch()
    patcher.setattr(ScriptDirectory, "from_config", classmethod(from_config))
    try:
        yield
    finally:
        patcher.undo()


# ===== Prepared Project DB =====


@pytest.fixture(scope="session")
def prepared_project_db_template(tmp_path_factory) -> Path:
    """``_prepare_project_database`` で新規作成した DB を 1 回だけ作る。

    新規作成は create_all + model_types seed + Alembic head への stamp で、stamp が
    versions 全件を読み込むため 1 回 1.3 秒前後かかる。中身は毎回同じなので複製で足りる。
    """
    from lorairo.database import db_core

    path = tmp_path_factory.mktemp("prepared_project_db") / "image_database.db"
    db_core._prepare_project_database(path).dispose()
    # dispose で WAL が checkpoint され、本体ファイルだけで完結していることを確かめる
    assert not path.with_name(path.name + "-wal").exists()
    return path


@pytest.fixture
def prepare_project_db(prepared_project_db_template: Path) -> Callable[[Path], Engine]:
    """``db_core._prepare_project_database(path)`` の新規作成結果を複製で再現する。

    戻り値の関数は template を ``path`` に複製し、``_prepare_project_database`` と同じ URL で
    Engine を返す。既存 DB の upgrade 経路を検証するテストでは使わない。
    """
    from lorairo.database import db_core

    def prepare(path: Path) -> Engine:
        path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        shutil.copyfile(prepared_project_db_template, path)
        return db_core.create_db_engine(f"sqlite:///{path.resolve()}?check_same_thread=False")

    return prepare


# ===== Scope Helpers =====


@pytest.fixture
def isolated_temp_dir(tmp_path):
    """隔離された一時ディレクトリ"""
    return tmp_path


# ===== Automatic Marker Application =====


def pytest_collection_modifyitems(config, items):
    """tests/unit 配下のテストに @pytest.mark.unit を自動付与"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
