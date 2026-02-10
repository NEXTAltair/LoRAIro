# tests/integration/conftest.py
"""
統合テスト層の共有フィクスチャ

責務:
- DB 初期化（test_engine_with_schema）
- ストレージ管理（fs_manager）
- リポジトリ・マネージャーフィクスチャ
- トランザクション/ロールバック処理

このファイルは tests/conftest.py (ルート) に依存します。
ルート conftest では genai-tag-db-tools モックと Qt 設定が済みです。
"""

import pytest
import shutil
import tempfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from lorairo.database.schema import Base, ModelType
from lorairo.database.db_repository import ImageRepository
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.storage.file_system import FileSystemManager


# ===== Database Fixtures =====

@pytest.fixture(scope="function")
def test_db_url() -> str:
    """テストDB URL（インメモリ SQLite）"""
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine_with_schema(test_db_url: str):
    """
    DB エンジン + スキーマ作成 + 初期データ

    Args:
        test_db_url: テストDB URL

    Yields:
        SQLAlchemy Engine（スキーマ作成済み）
    """
    engine = create_engine(test_db_url, echo=False)

    # スキーマ作成
    Base.metadata.create_all(engine)

    # 初期 ModelType データ挿入
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SessionLocal() as session:
        # 標準的なモデルタイプを挿入
        initial_model_types = [
            "tagger",
            "multimodal",
            "score",
            "rating",
            "captioner",
            "upscaler",
            "llm",
        ]

        for type_name in initial_model_types:
            if not session.query(ModelType).filter_by(name=type_name).first():
                model_type = ModelType(name=type_name)
                session.add(model_type)

        session.commit()

    yield engine

    # クリーンアップ
    engine.dispose()


@pytest.fixture(scope="function")
def db_session_factory(test_engine_with_schema):
    """DB セッション ファクトリ"""
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine_with_schema,
    )


@pytest.fixture(scope="function")
def test_session(db_session_factory) -> Session:
    """DB セッション"""
    session = db_session_factory()
    yield session
    session.close()


# ===== Repository & Manager Fixtures =====

@pytest.fixture(scope="function")
def test_repository(test_session) -> ImageRepository:
    """ImageRepository インスタンス"""
    return ImageRepository(test_session)


@pytest.fixture(scope="function")
def test_db_manager(test_engine_with_schema) -> ImageDatabaseManager:
    """ImageDatabaseManager インスタンス"""
    SessionLocal = sessionmaker(bind=test_engine_with_schema)
    return ImageDatabaseManager(SessionLocal)


# ===== Storage Fixtures =====

@pytest.fixture(scope="function")
def temp_storage_dir():
    """テンポラリストレージディレクトリ"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(scope="function")
def fs_manager(temp_storage_dir) -> FileSystemManager:
    """
    FileSystemManager インスタンス

    Args:
        temp_storage_dir: テンポラリディレクトリ

    Yields:
        FileSystemManager（初期化済み）
    """
    # ディレクトリをクリア
    if temp_storage_dir.exists():
        shutil.rmtree(temp_storage_dir)
    temp_storage_dir.mkdir(parents=True)

    # FileSystemManager を初期化
    manager = FileSystemManager()
    manager.initialize(temp_storage_dir)

    yield manager

    # クリーンアップ
    if temp_storage_dir.exists():
        shutil.rmtree(temp_storage_dir)


# ===== Integration Test Data Fixtures =====

@pytest.fixture(scope="function")
def integration_test_images(temp_storage_dir):
    """統合テスト用のサンプル画像"""
    from PIL import Image
    import numpy as np

    images = []
    for i in range(3):
        img = Image.new("RGB", (256, 256), color=f"#{i*100:06x}")
        img_path = temp_storage_dir / f"test_image_{i}.png"
        img.save(img_path)
        images.append(img_path)

    return images


@pytest.fixture(scope="function")
def integration_test_project(temp_storage_dir):
    """統合テスト用のプロジェクトディレクトリ"""
    project_dir = temp_storage_dir / "test_project_20260210_001"
    project_dir.mkdir(parents=True)
    (project_dir / "image_dataset").mkdir()
    return project_dir


# ===== Transaction & Rollback Helpers =====

@pytest.fixture(scope="function")
def transactional_session(test_engine_with_schema):
    """
    トランザクション付きセッション
    テスト後に自動的にロールバック
    """
    connection = test_engine_with_schema.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ===== Automatic Marker Application =====

def pytest_collection_modifyitems(config, items):
    """tests/integration 配下のテストに @pytest.mark.integration を自動付与"""
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
