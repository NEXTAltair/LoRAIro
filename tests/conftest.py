# tests/conftest.py
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy import inspect as sql_inspect
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import AnnotationsDict, Base, ImageDict, Model, ModelType, ProcessedImageDict
from lorairo.storage.file_system import FileSystemManager

# --- pytest-qt Configuration ---


def _detect_gui_markers(items: list["pytest.Item"]) -> bool:
    """収集済みテスト項目からGUIマーカーの存在を検出"""
    try:
        for item in items:
            if getattr(item, "keywords", None):
                if "gui" in item.keywords or "gui_show" in item.keywords:
                    return True
    except Exception:
        pass
    return False


def _is_headless_environment() -> bool:
    """ヘッドレス環境かを判定"""
    if not sys.platform.startswith("linux"):
        return False
    return not os.getenv("DISPLAY")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish(session: "pytest.Session") -> None:
    """GUIテスト用の環境変数を自動設定"""
    if os.getenv("LORAIRO_PYTEST_QT_ENV_DISABLE") == "1":
        return

    items = list(getattr(session, "items", []) or [])
    if not _detect_gui_markers(items):
        return

    # Windows: オフスクリーン描画設定
    if sys.platform.startswith("win"):
        if not os.getenv("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        if not os.getenv("QT_OPENGL"):
            os.environ["QT_OPENGL"] = "software"

    # Linux: ヘッドレス環境でのオフスクリーン設定
    elif sys.platform.startswith("linux") and _is_headless_environment():
        if not os.getenv("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp_args():
    """
    pytest-qt用のQApplicationパラメータ設定
    ヘッドレス環境（Linuxコンテナ）向けの設定を含む
    """
    # ヘッドレス環境の設定
    args = ["LoRAIro", "--platform", "offscreen"]

    # 環境変数による追加設定
    if os.getenv("QT_QPA_PLATFORM") == "offscreen":
        args.extend(["--platform", "offscreen"])

    return args


@pytest.fixture(scope="session")
def qapp(qapp_args):
    """
    pytest-qt用のQApplicationインスタンス
    Windows環境でのDLLエラーを回避するための設定
    """
    from PySide6.QtWidgets import QApplication

    # 既存のQApplicationインスタンスがある場合は削除
    app = QApplication.instance()
    if app is not None:
        app.quit()

    # 新しいQApplicationインスタンスを作成
    app = QApplication(qapp_args)

    yield app

    # テスト終了後にクリーンアップ
    app.quit()


@pytest.fixture(scope="session", autouse=True)
def configure_qt_for_tests():
    """
    Qt環境をテスト用に自動設定する（全テストで自動実行）
    """
    # Windows環境でのQt設定
    if sys.platform.startswith("win"):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
        # Windows環境でのDLLエラー回避
        os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
        os.environ.setdefault("QT_SCALE_FACTOR", "1")

    # Linuxコンテナ環境でのヘッドレス設定
    elif sys.platform.startswith("linux") and os.getenv("DISPLAY") is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.xcb.warning=false")

    # macOS環境での設定
    elif sys.platform.startswith("darwin"):
        os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

    return True


@pytest.fixture(scope="function")
def qt_main_window_mock_config():
    """
    Qt MainWorkspaceWindow テスト用の基本モック設定
    """
    from unittest.mock import Mock, patch

    mock_config = {
        "config_service": Mock(),
        "fsm": Mock(),
        "db_manager": Mock(),
        "worker_service": Mock(),
        "dataset_state": Mock(),
        "image_repo": Mock(),
    }

    # デフォルトのモック動作設定
    mock_config["config_service"].get_setting.return_value = None
    mock_config["db_manager"].get_all_images.return_value = []
    mock_config["fsm"].get_image_files.return_value = []
    mock_config["worker_service"].get_active_worker_count.return_value = 0
    mock_config["worker_service"].cancel_all_workers.return_value = True

    return mock_config


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
        print("[test_engine_with_schema] Creating tables using Base.metadata.create_all...")
        Base.metadata.create_all(engine)
        print("[test_engine_with_schema] Tables created.")

        # --- 初期 ModelType および Model データの挿入 ---
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        with SessionLocal() as session:
            # --- ModelType の初期データ挿入 ---
            print("[test_engine_with_schema] Inserting initial model types...")
            # schema.py やマイグレーションスクリプトで定義されているタイプ名を列挙
            initial_model_types = [
                "tagger",
                "multimodal",
                "score",
                "rating",
                "captioner",
                "upscaler",
                "llm",
            ]
            type_map: dict[str, ModelType] = {}
            for type_name in initial_model_types:
                exists = session.query(ModelType).filter_by(name=type_name).first()
                if not exists:
                    model_type = ModelType(name=type_name)
                    session.add(model_type)
                    print(f"  Added model type: {type_name}")
                    type_map[type_name] = model_type  # Map the name to the object
                else:
                    type_map[type_name] = exists  # If already exists (e.g., due to previous run), map it
            session.commit()  # Commit types first
            print("[test_engine_with_schema] Initial model types inserted/verified.")

            # --- 初期 Model データの挿入 ---
            print("[test_engine_with_schema] Inserting initial model data...")
            # 関連付けるタイプ名をリストで持つように変更
            initial_models_data: list[dict[str, Any]] = [
                {"name": "wd-vit-large-tagger-v3", "provider": "SmilingWolf", "type_names": ["tagger"]},
                # 修正: 'multimodal' は llm も兼ねるケースが多いので llm も追加、または要件に応じて調整
                {
                    "name": "GPT-4o",
                    "provider": "OpenAI",
                    "type_names": ["multimodal", "llm", "captioner"],
                },  # 複数のタイプを持つ例
                {"name": "cafe_aesthetic", "provider": "cafe", "type_names": ["score"]},
                {"name": "classification_ViT-L-14_openai", "provider": "openai", "type_names": ["rating"]},
                # 他のテストで必要になる可能性のあるモデルタイプも追加
                {"name": "RealESRGAN_x4plus", "provider": "esrgan", "type_names": ["upscaler"]},
                {"name": "wd-swinv2-tagger-v3", "provider": "SmilingWolf", "type_names": ["tagger"]},
                # 必要に応じて他のデフォルトモデルを追加
            ]

            for model_data in initial_models_data:
                # 既に存在するか確認
                exists = session.query(Model).filter_by(name=model_data["name"]).first()
                if not exists:
                    # type_namesリストを除いた辞書を作成してModelオブジェクトを初期化
                    model_kwargs = {k: v for k, v in model_data.items() if k != "type_names"}
                    # discontinued_at が指定されていなければ None を設定 (Nullableなので)
                    if "discontinued_at" not in model_kwargs:
                        model_kwargs["discontinued_at"] = None
                    model = Model(**model_kwargs)

                    # ModelTypeオブジェクトを取得してリレーションに追加
                    type_names_to_link = model_data.get("type_names", [])
                    linked_types_str = []  # For logging
                    for type_name in type_names_to_link:
                        model_type_obj = type_map.get(type_name)
                        if model_type_obj:
                            # type_map から取得したオブジェクトを使用
                            model.model_types.append(model_type_obj)
                            # --- flush() を追加 ---
                            try:
                                session.flush()  # 中間テーブルへの変更をDBに送信
                                print(f"    Flushed association for {model.name} <-> {model_type_obj.name}")
                            except Exception as flush_err:
                                print(
                                    f"    Error flushing association for {model.name} <-> {model_type_obj.name}: {flush_err}"
                                )
                            # --------------------
                            linked_types_str.append(type_name)
                        else:
                            # ログ出力など(通常は type_map に存在するはず)
                            print(
                                f"Warning: ModelType '{type_name}' not found in type_map for model '{model.name}' during test setup."
                            )

                    session.add(model)
                    print(f"  Added model: {model_data['name']} with types: {linked_types_str}")
                else:
                    print(f"  Model already exists: {model_data['name']}")  # 既存の場合のログ
            session.commit()
            print("[test_engine_with_schema] Initial model data inserted.")

        # --- テーブルとデータの確認 ---
        with engine.connect():
            inspector = sql_inspect(engine)
            tables_after = inspector.get_table_names()
            print(f"[test_engine_with_schema] Tables after creation: {tables_after}")
            assert "images" in tables_after, "images table not found after create_all!"
            assert "models" in tables_after, "models table not found after create_all!"
            # 初期データが挿入されたか確認
            with SessionLocal() as session:
                model_count = session.query(Model).count()
                print(f"[test_engine_with_schema] Found {model_count} models in DB.")
                assert model_count >= len(initial_models_data), "Initial model data not inserted correctly!"
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
def mock_config_service():
    """Provides a mock ConfigurationService for tests."""
    from unittest.mock import Mock

    mock = Mock()
    mock.get_database_dir.return_value = Path("/test/db")
    mock.get_database_base_dir.return_value = Path("/test/base")
    # アップスケーラーテスト用の設定を追加
    mock.get_image_processing_config.return_value = {
        "upscaler": "RealESRGAN_x4plus",
        "target_resolution": 512,
        "preferred_resolutions": [(512, 512)],
    }
    return mock


@pytest.fixture(scope="function")
def test_db_manager(test_repository, mock_config_service) -> ImageDatabaseManager:
    """Provides an instance of ImageDatabaseManager using the test repository."""
    # Inject the test repository and config service into the manager
    return ImageDatabaseManager(repository=test_repository, config_service=mock_config_service)


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
    # NOTE: テスト実行環境によっては絶対パスでないと画像が見つからない場合があるため resolve() を追加検討
    # image_path = (test_image_dir / "file01.webp").resolve()
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
            # RGBAをRGBに変換する必要があるか確認 (例: test_image が RGBA の場合)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            arrays.append(np.array(img))
        except Exception as e:
            pytest.fail(f"Failed to convert image to NumPy array: {e}")
    return arrays


@pytest.fixture
def sample_image_data(test_image_path) -> ImageDict:
    """テスト用の画像メタデータを作成 (キー名を schema.ImageDict に合わせる)"""
    # schema.py の ImageDict 型に合わせてキー名を修正
    # UUID, stored_image_path, phash は登録時に生成される想定
    # width, height, format, mode, has_alpha なども登録時に抽出される想定
    return {
        "uuid": "will-be-generated",  # 登録時に生成
        "original_image_path": str(test_image_path.resolve()),
        "stored_image_path": "will-be-generated",  # 登録時に生成
        "width": 100,  # 登録時に抽出
        "height": 100,  # 登録時に抽出
        "format": "WEBP",  # 登録時に抽出
        "mode": "RGB",  # 登録時に抽出
        "has_alpha": False,  # 登録時に抽出
        "filename": test_image_path.name,
        "extension": test_image_path.suffix,
        "color_space": "sRGB",  # 登録時に抽出
        "icc_profile": None,  # 登録時に抽出
        "phash": "will-be-calculated",  # 登録時に計算
        "manual_rating": None,  # 新しいカラム、デフォルトはNone
        # created_at, updated_at はDB側で自動設定
    }


@pytest.fixture
def sample_processed_image_data() -> ProcessedImageDict:
    """テスト用の処理済み画像メタデータを作成 (キー名を schema.ProcessedImageDict に合わせる)"""
    # schema.py の ProcessedImageDict 型に合わせてキー名を修正
    return {
        # image_id は動的に設定される
        "stored_image_path": "will-be-generated",  # 保存時に生成
        "width": 50,  # 保存時に抽出
        "height": 50,  # 保存時に抽出
        "mode": "RGB",  # 保存時に抽出
        "has_alpha": False,  # 保存時に抽出
        "filename": "will-be-generated",  # 保存時に生成
        "color_space": "sRGB",  # 保存時に抽出
        "icc_profile": None,  # 保存時に抽出
        # created_at, updated_at はDB側で自動設定
    }


@pytest.fixture
def sample_annotations() -> AnnotationsDict:
    """テスト用のアノテーションデータを作成 (新しいスキーマに合わせる)"""
    # schema.py の各 AnnotationData TypedDict に合わせて修正
    # model_id は test_engine_with_schema で投入されるモデルのIDを想定
    # (例: tagger=1, multimodal/llm=2, score=3, rating=4)
    # 実際のテストでは、`test_session` を使ってモデルIDを動的に取得する方が堅牢
    return {
        "tags": [
            {
                "tag": "person",
                "model_id": 1,  # wd-vit-large-tagger-v3 (想定)
                "confidence_score": 0.9,  # 新しいカラム
                "existing": False,
                "is_edited_manually": None,  # Nullable boolean
                "tag_id": 101,  # 外部キーではない
                # created_at, updated_at は自動
            },
            {
                "tag": "outdoor",
                "model_id": 1,
                "confidence_score": 0.8,
                "existing": False,
                "is_edited_manually": None,
                "tag_id": 102,
            },
        ],
        "captions": [
            {
                "caption": "a person outside",
                "model_id": 2,  # GPT-4o (想定)
                "existing": False,
                "is_edited_manually": None,  # Nullable boolean
                # created_at, updated_at は自動
            }
        ],
        "scores": [
            {
                "score": 0.95,
                "model_id": 3,  # cafe_aesthetic (想定)
                "is_edited_manually": False,  # NOT NULL boolean
                # created_at, updated_at は自動
            }
        ],
        "ratings": [
            {
                "raw_rating_value": "R",
                "normalized_rating": "R",
                "confidence_score": 0.98,  # Nullable float
                "model_id": 4,  # classification_ViT-L-14_openai (想定)
                # created_at, updated_at は自動
            }
        ],
    }


@pytest.fixture
def current_timestamp():
    """現在のタイムスタンプを取得"""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def past_timestamp():
    """過去のタイムスタンプを取得(1日前)"""
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")


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


# --- QThread Registry for GUI tests ---
from typing import List
from PySide6.QtCore import QThread


class _ThreadRegistry:
    """QThreadの安全な終了処理を管理するレジストリ"""
    
    def __init__(self, timeout_ms: int = 5000) -> None:
        self._threads: List[QThread] = []
        self._timeout_ms = timeout_ms

    def register_thread(self, thread: QThread) -> None:
        if thread and isinstance(thread, QThread):
            self._threads.append(thread)

    def finalize_threads(self) -> None:
        for thread in self._threads:
            try:
                if thread.isRunning():
                    thread.quit()
                thread.wait(self._timeout_ms)
            except Exception:
                pass
        self._threads.clear()


@pytest.fixture(scope="function")
def threads_registry(request) -> _ThreadRegistry:
    """QThread終了処理を自動化するレジストリ"""
    registry = _ThreadRegistry(timeout_ms=5000)
    request.addfinalizer(registry.finalize_threads)
    return registry
