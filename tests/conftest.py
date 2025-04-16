# tests/conftest.py
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy import inspect as sql_inspect
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Base, Model

# 古い実装をインポートしないようにコメントアウトまたは削除
# from lorairo.database.database import ImageDatabaseManager as OldImageDatabaseManager, SQLiteManager
from lorairo.storage.file_system import FileSystemManager

# --- General Test Setup Fixtures ---


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Returns the project root directory."""
    return Path(__file__).parent.parent  # Adjust based on your conftest.py location


@pytest.fixture(scope="function")
def temp_dir():
    """テスト用の一時ディレクトリを作成"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


# storage_dir と fs_manager は既存のものを流用可能か確認
@pytest.fixture(scope="function")
def storage_dir(temp_dir):
    """画像ストレージ用ディレクトリを作成"""
    storage_dir = temp_dir / "storage"
    storage_dir.mkdir(parents=True)
    return storage_dir


@pytest.fixture(scope="function")
def fs_manager(storage_dir):
    """FileSystemManagerのインスタンスを作成"""
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True)

    fsm = FileSystemManager()
    # NOTE: Adjust target_resolution if needed for tests
    fsm.initialize(storage_dir, target_resolution=512)
    yield fsm

    if storage_dir.exists():
        shutil.rmtree(storage_dir)


# --- Database Test Setup Fixtures ---


@pytest.fixture(scope="function")
def test_db_url(temp_dir) -> str:
    """Returns the URL for a temporary file-based test database."""
    # インメモリDBを使用するように変更
    db_url = "sqlite:///:memory:"
    print(f"\n[test_db_url] Using in-memory DB: {db_url}")
    return db_url


@pytest.fixture(scope="function")
def test_engine_with_schema(test_db_url: str):
    """Creates a test engine, creates schema using metadata.create_all, and adds initial data."""
    print(f"\n[test_engine_with_schema] Creating engine for URL: {test_db_url}")
    engine = create_engine(test_db_url, echo=False)  # echo=True にするとSQLが見える

    try:
        print(f"[test_engine_with_schema] Creating tables using Base.metadata.create_all...")
        Base.metadata.create_all(engine)
        print(f"[test_engine_with_schema] Tables created.")

        # --- 初期 Model データの挿入 ---
        print(f"[test_engine_with_schema] Inserting initial model data...")
        # テストに必要なモデルデータを定義
        initial_models = [
            {"name": "wd-vit-large-tagger-v3", "type": "tagger", "provider": "SmilingWolf"},
            {"name": "GPT-4o", "type": "multimodal", "provider": "OpenAI"},  # tests/step_defsで使用
            {"name": "cafe_aesthetic", "type": "score", "provider": "cafe"},  # tests/step_defsで使用
            {
                "name": "classification_ViT-L-14_openai",
                "type": "rating",
                "provider": "openai",
            },  # tests/step_defsで使用
            # 必要に応じて他のデフォルトモデルを追加
        ]
        # セッションを作成してデータを挿入
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        with SessionLocal() as session:
            for model_data in initial_models:
                # 既に存在するか確認 (In-memory DBでは不要だが念のため)
                exists = session.query(Model).filter_by(name=model_data["name"]).first()
                if not exists:
                    model = Model(**model_data)
                    session.add(model)
                    print(f"  Added model: {model_data['name']}")
            session.commit()
            print(f"[test_engine_with_schema] Initial model data inserted.")

        # --- テーブルとデータの確認 ---
        with engine.connect() as connection:
            inspector = sql_inspect(engine)
            tables_after = inspector.get_table_names()
            print(f"[test_engine_with_schema] Tables after creation: {tables_after}")
            assert "images" in tables_after, "images table not found after create_all!"
            assert "models" in tables_after, "models table not found after create_all!"
            # 初期データが挿入されたか確認
            with SessionLocal() as session:
                model_count = session.query(Model).count()
                print(f"[test_engine_with_schema] Found {model_count} models in DB.")
                assert model_count >= len(initial_models), "Initial model data not inserted correctly!"
        print("[test_engine_with_schema] Schema created and initial data verified successfully.")

    except Exception as e:
        print(f"[test_engine_with_schema] Schema creation or initial data insertion failed: {e}")
        import traceback

        traceback.print_exc()
        pytest.fail(f"Test DB setup failed: {e}")

    yield engine

    print(f"[test_engine_with_schema] Disposing test engine for {test_db_url}")
    engine.dispose()


@pytest.fixture(scope="function")
def db_session_factory(test_engine_with_schema):
    """Creates a sessionmaker bound to the test engine with schema."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine_with_schema)


@pytest.fixture(scope="function")
def test_session(db_session_factory):
    """Provides a transactional scope around a test function."""
    Session = db_session_factory
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def test_repository(db_session_factory) -> ImageRepository:
    """Provides an instance of ImageRepository using the test session factory."""
    # Pass the session factory to the repository
    return ImageRepository(session_factory=db_session_factory)


@pytest.fixture(scope="function")
def test_db_manager(test_repository) -> ImageDatabaseManager:
    """Provides an instance of ImageDatabaseManager using the test repository."""
    # Inject the test repository into the manager
    return ImageDatabaseManager(repository=test_repository)


# --- Existing Image/Data Fixtures (mostly reusable) ---


@pytest.fixture
def test_image_dir():
    """テスト用画像ディレクトリのパスを返すフィクスチャ"""
    # Ensure the path is correct relative to conftest.py
    return Path(__file__).parent / "resources" / "img" / "1_img"


@pytest.fixture
def test_image_path(test_image_dir):
    """テスト用画像のパスを返すフィクスチャ"""
    image_path = test_image_dir / "file01.webp"
    if not image_path.exists():
        pytest.skip(f"Test image not found: {image_path}")
    return image_path


@pytest.fixture
def test_image(test_image_path):
    """PIL Imageオブジェクトを返すフィクスチャ"""
    return Image.open(test_image_path)


@pytest.fixture
def test_image_array(test_image):
    """NumPy配列を返すフィクスチャ"""
    return np.array(test_image)


@pytest.fixture
def test_image_paths(test_image_dir):
    """テスト用画像のパスリストを返すフィクスチャ"""
    paths = sorted(test_image_dir.glob("*.webp"))
    if not paths:
        pytest.skip(f"No test images found in {test_image_dir}")
    return paths


@pytest.fixture
def test_images(test_image_paths):
    """PIL Imageオブジェクトのリストを返すフィクスチャ"""
    return [Image.open(path) for path in test_image_paths]


@pytest.fixture
def test_image_arrays(test_images):
    """NumPy配列のリストを返すフィクスチャ"""
    # Ensure images are convertible; handle potential errors
    arrays = []
    for img in test_images:
        try:
            arrays.append(np.array(img))
        except Exception as e:
            pytest.fail(f"Failed to convert image to NumPy array: {e}")
    return arrays


@pytest.fixture
def sample_image_data(test_image_path):
    """テスト用の画像メタデータを作成 (Requires adjustment based on actual needs)"""
    # This data might be less relevant if register_original_image handles extraction
    return {
        "uuid": "test-uuid-1234",  # UUID should be generated by the function
        "original_image_path": str(test_image_path.resolve()),
        "stored_image_path": "/path/to/stored/image.webp",  # This will be determined by fs_manager
        "width": 100,  # Should be extracted from image
        "height": 100,  # Should be extracted from image
        "format": "WEBP",  # Should be extracted from image
        "mode": "RGB",  # Should be extracted from image
        "has_alpha": False,  # Should be extracted from image
        "filename": test_image_path.name,
        "extension": test_image_path.suffix,
        "color_space": "sRGB",  # Should be extracted if possible
        "icc_profile": None,  # Should be extracted if possible
        "phash": "d8e0c4c4c4c4e0f0",  # Example pHash, should be calculated
        "manual_rating": None,  # New field
    }


@pytest.fixture
def sample_processed_image_data():
    """テスト用の処理済み画像メタデータを作成"""
    return {
        # image_id will be set dynamically in tests
        "stored_image_path": "/path/to/processed/image.webp",  # Determined by fs_manager/logic
        "width": 50,
        "height": 50,
        "mode": "RGB",
        "has_alpha": False,
        "filename": "file01_processed.webp",  # Example filename
        "color_space": "sRGB",
        "icc_profile": None,
    }


@pytest.fixture
def sample_annotations():
    """テスト用のアノテーションデータを作成 (Needs update for new schema)"""
    return {
        "tags": [
            {
                "tag": "person",
                "model_id": 1,  # Note: Assumes model with ID 1 exists (inserted by fixture)
                "confidence_score": 0.9,
                "existing": False,
                "is_edited_manually": False,
                "tag_id": 101,  # Example tag_id (may not be realistic if tag_db is not used)
            },
            {
                "tag": "outdoor",
                "model_id": 1,
                "confidence_score": 0.8,
                "existing": False,
                "is_edited_manually": False,
                "tag_id": 102,
            },
        ],
        "captions": [
            {
                "caption": "a person outside",
                "model_id": 2,
                "existing": False,
                "is_edited_manually": False,
            }  # Assumes model ID 2 (GPT-4o)
        ],
        "scores": [
            {"score": 0.95, "model_id": 3, "is_edited_manually": False}
        ],  # Assumes model ID 3 (cafe_aesthetic)
        "ratings": [
            {
                "raw_rating_value": "R",
                "normalized_rating": "R",
                "confidence_score": 0.98,
                "model_id": 4,  # Assumes model ID 4 (classification_ViT-L-14_openai)
            }
        ],
    }


@pytest.fixture
def current_timestamp():
    """現在のタイムスタンプを取得"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def past_timestamp():
    """過去のタイムスタンプを取得（1日前）"""
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")


# --- Helper to override session dependency if using FastAPI style --- #
# If your db_manager or repository uses dependency injection like FastAPI:
# from your_app.main import app # Assuming FastAPI app instance
# from your_app.database import get_session # The dependency function

# @pytest.fixture(scope="function")
# def override_get_session(db_session_factory):
#     """Overrides the FastAPI session dependency for tests."""
#     def get_session_override():
#         session = db_session_factory()
#         try:
#             yield session
#         finally:
#             session.close()
#
#     app.dependency_overrides[get_session] = get_session_override
#     yield
#     app.dependency_overrides.pop(get_session, None)
