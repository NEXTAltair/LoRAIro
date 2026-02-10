"""
LoRAIro テストリファクタリング: conftest.py テンプレート集

このファイルは実装テンプレートであり、直接テストで使用するファイルではありません。
各セクションを対応する conftest.py にコピーして使用してください。

テンプレート一覧:
    1. tests/conftest.py（ルート - 最小限）
    2. tests/unit/conftest.py（ユニットテスト用）
    3. tests/integration/conftest.py（統合テスト用）
    4. tests/bdd/conftest.py（BDD テスト用）

関連ドキュメント:
    - docs/new_test_architecture.md: 新テストアーキテクチャ設計
    - docs/migration_roadmap.md: 移行ロードマップ
"""

# ========================================
# Section 1: tests/conftest.py（ルート - 最小限）
# 目標行数: 80-120行
# 責務: genai-tag-db-tools モック、Qt 設定、project_root
# ========================================

# --- [COPY START: tests/conftest.py] ---

# tests/conftest.py

# --- External Tag DB Initialization Mock (MUST BE FIRST) ---
# genai-tag-db-tools の初期化を lorairo import 前にモックする。
# これにより db_core モジュールレベル初期化での RuntimeError を防止。

import unittest.mock
from pathlib import Path as _MockPath

from sqlalchemy.orm import sessionmaker as _sessionmaker

# 3つの外部タグDBに対するモック結果を作成
_mock_result_1 = unittest.mock.Mock()
_mock_result_1.db_path = str(_MockPath("/tmp/test_tag_db_cc4.db"))
_mock_result_2 = unittest.mock.Mock()
_mock_result_2.db_path = str(_MockPath("/tmp/test_tag_db_mit.db"))
_mock_result_3 = unittest.mock.Mock()
_mock_result_3.db_path = str(_MockPath("/tmp/test_tag_db_cc0.db"))

# ユーザーDB用モックセッションファクトリ
_mock_user_db_engine = unittest.mock.Mock()
_mock_user_session_factory = _sessionmaker(bind=_mock_user_db_engine)

# ランタイム関数のパッチ定義
_runtime_patches = [
    unittest.mock.patch(
        "genai_tag_db_tools.initialize_databases",
        return_value=[_mock_result_1, _mock_result_2, _mock_result_3],
    ),
    unittest.mock.patch(
        "genai_tag_db_tools.db.runtime.get_user_session_factory",
        return_value=_mock_user_session_factory,
    ),
]

# モジュールレベルでパッチ開始（lorairo import 前に必須）
for _patch in _runtime_patches:
    _patch.start()

# --- Standard Library Imports ---
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest


# =================================================
# Session Scope Fixtures (autouse)
# =================================================


@pytest.fixture(scope="session", autouse=True)
def mock_genai_tag_db_tools():
    """外部タグDB初期化のモックを管理（全テストで自動実行）

    genai-tag-db-tools の初期化処理をモックし、テスト環境で
    RuntimeError が発生しないようにする。

    Note:
        モジュールレベルで既にパッチ開始済み。
        テストセッション終了時に自動的にパッチを停止。
    """
    yield
    for patch in _runtime_patches:
        patch.stop()


@pytest.fixture(scope="session", autouse=True)
def configure_qt_for_tests():
    """Qt 環境をテスト用に自動設定する（全テストで自動実行）

    Linux コンテナ環境ではヘッドレスモードを設定。
    """
    if sys.platform.startswith("linux") and os.getenv("DISPLAY") is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.xcb.warning=false")
    return True


# =================================================
# Session Scope Fixtures (Qt)
# =================================================


@pytest.fixture(scope="session")
def qapp_args():
    """pytest-qt 用の QApplication パラメータ設定

    Returns:
        list[str]: QApplication コンストラクタ引数
    """
    args = ["LoRAIro", "--platform", "offscreen"]
    if os.getenv("QT_QPA_PLATFORM") == "offscreen":
        args.extend(["--platform", "offscreen"])
    return args


@pytest.fixture(scope="session")
def qapp(qapp_args):
    """pytest-qt 用の QApplication インスタンス

    Args:
        qapp_args: QApplication コンストラクタ引数

    Yields:
        QApplication: テスト用アプリケーションインスタンス
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.quit()
    app = QApplication(qapp_args)
    yield app
    app.quit()


# =================================================
# Common Fixtures
# =================================================


@pytest.fixture(scope="session")
def project_root() -> Path:
    """プロジェクトルートディレクトリのパスを返す

    Returns:
        Path: プロジェクトルートの絶対パス
    """
    return Path(__file__).parent.parent


@pytest.fixture(scope="function")
def qt_main_window_mock_config():
    """Qt MainWorkspaceWindow テスト用の基本モック設定

    Returns:
        dict: MainWindow 依存サービスのモック辞書
    """
    mock_config = {
        "config_service": Mock(),
        "fsm": Mock(),
        "db_manager": Mock(),
        "worker_service": Mock(),
        "dataset_state": Mock(),
        "image_repo": Mock(),
    }
    mock_config["config_service"].get_setting.return_value = None
    mock_config["db_manager"].get_all_images.return_value = []
    mock_config["fsm"].get_image_files.return_value = []
    mock_config["worker_service"].get_active_worker_count.return_value = 0
    mock_config["worker_service"].cancel_all_workers.return_value = True
    return mock_config


@pytest.fixture(scope="function")
def critical_failure_hooks(monkeypatch, request):
    """致命的失敗時の hook をモック（再利用可能版）

    Args:
        monkeypatch: pytest の monkeypatch フィクスチャ
        request: pytest の request フィクスチャ（パラメータ取得用）

    Returns:
        dict: モック呼び出しを記録する辞書
            - "sys_exit": sys.exit() の呼び出し記録
            - "messagebox_instances": QMessageBox 関連の呼び出し記録
            - "logger": モック化された logger
    """
    patch_params = getattr(request, "param", {})
    patch_target = patch_params.get("patch_target", "lorairo.gui.window.main_window")

    calls = {
        "sys_exit": [],
        "messagebox_instances": [],
        "logger": MagicMock(),
    }

    def mock_sys_exit(code):
        calls["sys_exit"].append(code)
        raise SystemExit(code)

    import sys

    monkeypatch.setattr(sys, "exit", mock_sys_exit)

    def _create_mock_messagebox(*_args, **_kwargs):
        instance = Mock()
        calls["messagebox_instances"].append(instance)
        return instance

    mock_messagebox_class = Mock(side_effect=_create_mock_messagebox)
    mock_icon = Mock()
    mock_icon.Critical = Mock()
    mock_messagebox_class.Icon = mock_icon

    monkeypatch.setattr(f"{patch_target}.QMessageBox", mock_messagebox_class)
    monkeypatch.setattr(f"{patch_target}.logger", calls["logger"])

    return calls


# --- [COPY END: tests/conftest.py] ---


# ========================================
# Section 2: tests/unit/conftest.py（ユニットテスト用）
# 目標行数: 120-160行
# 責務: テスト画像、サンプルデータ、タイムスタンプ、共通モック
# ========================================

# --- [COPY START: tests/unit/conftest.py] ---

# tests/unit/conftest.py
"""ユニットテスト用共通フィクスチャ

テスト画像、サンプルデータ、タイムスタンプ、共通モックを提供。
外部依存（DB、ファイルシステム）は最小限に抑える。
"""

import pytest  # noqa: E811 (テンプレートファイルのため重複OK)
import numpy as np  # noqa: E811
from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: E811
from unittest.mock import Mock  # noqa: E811

from PIL import Image

from lorairo.database.schema import AnnotationsDict, ImageDict, ProcessedImageDict


# =================================================
# テスト画像フィクスチャ
# =================================================


@pytest.fixture
def test_image_dir():
    """テスト用画像ディレクトリのパスを返す

    Returns:
        Path: tests/resources/img/1_img ディレクトリのパス
    """
    return Path(__file__).parent.parent / "resources" / "img" / "1_img"


@pytest.fixture
def test_image_path(test_image_dir):
    """テスト用画像のパスを返す

    Args:
        test_image_dir: テスト用画像ディレクトリ

    Returns:
        Path: file01.webp のパス
    """
    image_path = test_image_dir / "file01.webp"
    if not image_path.exists():
        pytest.skip(f"Test image not found: {image_path}")
    return image_path


@pytest.fixture
def test_image(test_image_path):
    """PIL Image オブジェクトを返す

    Args:
        test_image_path: テスト用画像のパス

    Returns:
        PIL.Image.Image: テスト用画像
    """
    return Image.open(test_image_path)


@pytest.fixture
def test_image_array(test_image):
    """NumPy 配列を返す

    Args:
        test_image: PIL Image オブジェクト

    Returns:
        numpy.ndarray: 画像の NumPy 配列表現
    """
    return np.array(test_image)


@pytest.fixture
def test_image_paths(test_image_dir):
    """テスト用画像のパスリストを返す

    Args:
        test_image_dir: テスト用画像ディレクトリ

    Returns:
        list[Path]: .webp ファイルのパスリスト
    """
    paths = sorted(test_image_dir.glob("*.webp"))
    if not paths:
        pytest.skip(f"No test images found in {test_image_dir}")
    return paths


@pytest.fixture
def test_images(test_image_paths):
    """PIL Image オブジェクトのリストを返す

    Args:
        test_image_paths: テスト用画像のパスリスト

    Returns:
        list[PIL.Image.Image]: テスト用画像リスト
    """
    return [Image.open(path) for path in test_image_paths]


@pytest.fixture
def test_image_arrays(test_images):
    """NumPy 配列のリストを返す

    Args:
        test_images: PIL Image オブジェクトのリスト

    Returns:
        list[numpy.ndarray]: 画像の NumPy 配列リスト
    """
    arrays = []
    for img in test_images:
        if img.mode == "RGBA":
            img = img.convert("RGB")
        arrays.append(np.array(img))
    return arrays


# =================================================
# サンプルデータフィクスチャ
# =================================================


@pytest.fixture
def sample_image_data(test_image_path) -> ImageDict:
    """テスト用の画像メタデータを作成

    Args:
        test_image_path: テスト用画像のパス

    Returns:
        ImageDict: 画像メタデータ辞書
    """
    return {
        "uuid": "will-be-generated",
        "original_image_path": str(test_image_path.resolve()),
        "stored_image_path": "will-be-generated",
        "width": 100,
        "height": 100,
        "format": "WEBP",
        "mode": "RGB",
        "has_alpha": False,
        "filename": test_image_path.name,
        "extension": test_image_path.suffix,
        "color_space": "sRGB",
        "icc_profile": None,
        "phash": "will-be-calculated",
        "manual_rating": None,
    }


@pytest.fixture
def sample_processed_image_data() -> ProcessedImageDict:
    """テスト用の処理済み画像メタデータを作成

    Returns:
        ProcessedImageDict: 処理済み画像メタデータ辞書
    """
    return {
        "stored_image_path": "will-be-generated",
        "width": 50,
        "height": 50,
        "mode": "RGB",
        "has_alpha": False,
        "filename": "will-be-generated",
        "color_space": "sRGB",
        "icc_profile": None,
    }


@pytest.fixture
def sample_annotations() -> AnnotationsDict:
    """テスト用のアノテーションデータを作成

    Returns:
        AnnotationsDict: アノテーションデータ辞書
    """
    return {
        "tags": [
            {
                "tag": "person",
                "model_id": 1,
                "confidence_score": 0.9,
                "existing": False,
                "is_edited_manually": None,
                "tag_id": 101,
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
                "model_id": 2,
                "existing": False,
                "is_edited_manually": None,
            }
        ],
        "scores": [
            {
                "score": 0.95,
                "model_id": 3,
                "is_edited_manually": False,
            }
        ],
        "ratings": [
            {
                "raw_rating_value": "R",
                "normalized_rating": "R",
                "confidence_score": 0.98,
                "model_id": 4,
            }
        ],
    }


# =================================================
# タイムスタンプフィクスチャ
# =================================================


@pytest.fixture
def current_timestamp():
    """現在のタイムスタンプを取得

    Returns:
        str: "YYYY-MM-DD HH:MM:SS" 形式のタイムスタンプ
    """
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def past_timestamp():
    """過去のタイムスタンプを取得（1日前）

    Returns:
        str: "YYYY-MM-DD HH:MM:SS" 形式のタイムスタンプ（1日前）
    """
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")


# =================================================
# 共通モックフィクスチャ
# =================================================


@pytest.fixture
def mock_config_service():
    """ConfigurationService のモックを提供

    Returns:
        Mock: ConfigurationService のモック
            - get_database_dir() -> Path("/test/db")
            - get_database_base_dir() -> Path("/test/base")
            - get_image_processing_config() -> dict
    """
    mock = Mock()
    mock.get_database_dir.return_value = Path("/test/db")
    mock.get_database_base_dir.return_value = Path("/test/base")
    mock.get_image_processing_config.return_value = {
        "upscaler": "RealESRGAN_x4plus",
        "target_resolution": 512,
        "preferred_resolutions": [(512, 512)],
    }
    return mock


@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManager のモックを提供

    テスト固有の設定は各テスト内で上書きすること。

    Returns:
        Mock: ImageDatabaseManager のモック
            - get_all_images() -> []
            - get_image_by_id() -> None
    """
    mock = Mock()
    mock.get_all_images.return_value = []
    mock.get_image_by_id.return_value = None
    return mock


# --- [COPY END: tests/unit/conftest.py] ---


# ========================================
# Section 3: tests/integration/conftest.py（統合テスト用）
# 目標行数: 200-280行
# 責務: DB初期化、セッション管理、リポジトリ、ストレージ、タグDB
# ========================================

# --- [COPY START: tests/integration/conftest.py] ---

# tests/integration/conftest.py
"""統合テスト用共通フィクスチャ

データベース初期化、セッション管理、リポジトリ、ファイルシステム、
外部タグDB テストフィクスチャを提供。
"""

import os
import shutil
import tempfile
from pathlib import Path  # noqa: E811
from typing import Any
from unittest.mock import Mock  # noqa: E811

import pytest  # noqa: E811
from sqlalchemy import create_engine
from sqlalchemy import inspect as sql_inspect
from sqlalchemy.orm import sessionmaker  # noqa: E811

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Base, Model, ModelType
from lorairo.storage.file_system import FileSystemManager


# =================================================
# 一時ディレクトリ・ストレージフィクスチャ
# =================================================


@pytest.fixture(scope="function")
def temp_dir():
    """テスト用の一時ディレクトリを作成

    Yields:
        Path: 一時ディレクトリのパス。テスト終了後に自動削除。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(scope="function")
def storage_dir(temp_dir):
    """画像ストレージ用ディレクトリを作成

    Args:
        temp_dir: 一時ディレクトリ

    Returns:
        Path: ストレージディレクトリのパス
    """
    storage_dir = temp_dir / "storage"
    storage_dir.mkdir(parents=True)
    return storage_dir


@pytest.fixture(scope="function")
def fs_manager(storage_dir):
    """FileSystemManager のインスタンスを作成

    Args:
        storage_dir: ストレージディレクトリ

    Yields:
        FileSystemManager: 初期化済みのファイルシステムマネージャー
    """
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True)

    fsm = FileSystemManager()
    fsm.initialize(storage_dir)
    yield fsm

    if storage_dir.exists():
        shutil.rmtree(storage_dir)


# =================================================
# データベースフィクスチャ
# =================================================


@pytest.fixture(scope="function")
def test_db_url() -> str:
    """テストDB URL を返す（in-memory SQLite）

    Returns:
        str: SQLite in-memory DB の接続 URL
    """
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine_with_schema(test_db_url: str):
    """テストエンジンを作成し、スキーマと初期データを投入する

    Args:
        test_db_url: テストDB URL

    Yields:
        Engine: スキーマ作成済みの SQLAlchemy エンジン
    """
    engine = create_engine(test_db_url, echo=False)

    try:
        Base.metadata.create_all(engine)

        # 初期 ModelType / Model データの投入
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        with session_local() as session:
            # ModelType 初期データ
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
                    type_map[type_name] = model_type
                else:
                    type_map[type_name] = exists
            session.commit()

            # Model 初期データ
            initial_models_data: list[dict[str, Any]] = [
                {"name": "wd-vit-large-tagger-v3", "provider": "SmilingWolf", "type_names": ["tagger"]},
                {
                    "name": "GPT-4o",
                    "provider": "OpenAI",
                    "type_names": ["multimodal", "llm", "captioner"],
                },
                {"name": "cafe_aesthetic", "provider": "cafe", "type_names": ["score"]},
                {"name": "classification_ViT-L-14_openai", "provider": "openai", "type_names": ["rating"]},
                {"name": "RealESRGAN_x4plus", "provider": "esrgan", "type_names": ["upscaler"]},
                {"name": "wd-swinv2-tagger-v3", "provider": "SmilingWolf", "type_names": ["tagger"]},
            ]

            for model_data in initial_models_data:
                exists = session.query(Model).filter_by(name=model_data["name"]).first()
                if not exists:
                    model_kwargs = {k: v for k, v in model_data.items() if k != "type_names"}
                    if "discontinued_at" not in model_kwargs:
                        model_kwargs["discontinued_at"] = None
                    model = Model(**model_kwargs)

                    for type_name in model_data.get("type_names", []):
                        model_type_obj = type_map.get(type_name)
                        if model_type_obj:
                            model.model_types.append(model_type_obj)
                            try:
                                session.flush()
                            except Exception:
                                pass

                    session.add(model)
            session.commit()

        # テーブル・データ検証
        with engine.connect():
            inspector = sql_inspect(engine)
            tables = inspector.get_table_names()
            assert "images" in tables, "images table not found!"
            assert "models" in tables, "models table not found!"

    except Exception as e:
        pytest.fail(f"Test DB setup failed: {e}")

    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session_factory(test_engine_with_schema):
    """テストエンジンにバインドされた sessionmaker を作成

    Args:
        test_engine_with_schema: スキーマ作成済みエンジン

    Returns:
        sessionmaker: セッションファクトリ
    """
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine_with_schema)


@pytest.fixture(scope="function")
def test_session(db_session_factory):
    """テスト関数スコープの DB セッションを提供

    Args:
        db_session_factory: セッションファクトリ

    Yields:
        Session: DB セッション。テスト終了後に自動クローズ。
    """
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def test_repository(db_session_factory) -> ImageRepository:
    """テスト用 ImageRepository を提供

    Args:
        db_session_factory: セッションファクトリ

    Returns:
        ImageRepository: テスト用リポジトリ
    """
    return ImageRepository(session_factory=db_session_factory)


@pytest.fixture(scope="function")
def temp_db_repository(db_session_factory) -> ImageRepository:
    """クリーンアップ対応の一時的な ImageRepository を提供

    Args:
        db_session_factory: セッションファクトリ

    Returns:
        ImageRepository: テスト用リポジトリ
    """
    return ImageRepository(session_factory=db_session_factory)


@pytest.fixture(scope="function")
def mock_config_service():
    """統合テスト用 ConfigurationService モック

    Returns:
        Mock: ConfigurationService のモック
    """
    mock = Mock()
    mock.get_database_dir.return_value = Path("/test/db")
    mock.get_database_base_dir.return_value = Path("/test/base")
    mock.get_image_processing_config.return_value = {
        "upscaler": "RealESRGAN_x4plus",
        "target_resolution": 512,
        "preferred_resolutions": [(512, 512)],
    }
    return mock


@pytest.fixture(scope="function")
def test_db_manager(test_repository, mock_config_service) -> ImageDatabaseManager:
    """テスト用 ImageDatabaseManager を提供

    Args:
        test_repository: テスト用リポジトリ
        mock_config_service: ConfigurationService モック

    Returns:
        ImageDatabaseManager: テスト用 DB マネージャー
    """
    return ImageDatabaseManager(repository=test_repository, config_service=mock_config_service)


# =================================================
# 外部タグDB テストフィクスチャ
# =================================================


@pytest.fixture(scope="function")
def test_tag_db_path(temp_dir):
    """外部 tag_db テスト用の一時データベースパスを提供

    環境変数 TEST_TAG_DB_PATH が設定されている場合、そのパスをコピー元として使用。
    未設定の場合はテストをスキップ。

    Args:
        temp_dir: 一時ディレクトリ

    Returns:
        Path: テスト用 tag_db のパス
    """
    source_db_env = os.getenv("TEST_TAG_DB_PATH")
    if not source_db_env:
        pytest.skip("TEST_TAG_DB_PATH not set. Skipping external tag_db integration tests.")

    test_db_path = temp_dir / "tags_test.db"
    source_db_path = Path(source_db_env)

    if source_db_path.exists():
        shutil.copy(source_db_path, test_db_path)
    else:
        prod_tag_db = Path("local_packages/genai-tag-db-tools/src/genai_tag_db_tools/data/tags_v4.db")
        if prod_tag_db.exists():
            shutil.copy(prod_tag_db, test_db_path)
        else:
            test_db_path.touch()

    return test_db_path


@pytest.fixture(scope="function")
def test_tag_repository(test_tag_db_path):
    """テスト用 TagRepository 互換オブジェクトを提供

    公開API（MergedTagReader + register_tags）を使用したテストヘルパー。

    Args:
        test_tag_db_path: テスト用タグDBパス

    Yields:
        TestTagRepositoryHelper: テスト用の TagRepository 互換オブジェクト
    """
    from genai_tag_db_tools import search_tags
    from genai_tag_db_tools.db.repository import MergedTagReader
    from genai_tag_db_tools.models import TagSearchRequest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(f"sqlite:///{test_tag_db_path}", echo=False)
    test_session_factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    merged_reader = MergedTagReader(
        base_session_factory=test_session_factory,
        user_session_factory=None,
    )

    created_tag_ids = []

    class TestTagRepositoryHelper:
        """TagRepository 互換インターフェースを提供するテストヘルパー"""

        def __init__(self, reader: MergedTagReader, session_factory):
            self.merged_reader = reader
            self.session_factory = session_factory

        def create_tag(self, source_tag: str, tag: str) -> int:
            """新規タグを作成して tag_id を返す"""
            from genai_tag_db_tools.data.database_schema import Tag

            with self.session_factory() as session:
                new_tag = Tag(source_tag=source_tag, tag=tag)
                session.add(new_tag)
                session.commit()
                tag_id = new_tag.tag_id
                created_tag_ids.append(tag_id)
                return tag_id

        def get_tag_by_id(self, tag_id: int):
            """tag_id でタグを取得"""
            from genai_tag_db_tools.data.database_schema import Tag

            with self.session_factory() as session:
                return session.query(Tag).filter_by(tag_id=tag_id).first()

        def search_tag_ids(self, query: str, partial: bool = False) -> list[int]:
            """タグを検索して tag_id のリストを返す"""
            request = TagSearchRequest(
                query=query,
                partial=partial,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            result = search_tags(merged_reader, request)
            return [item.tag_id for item in result.items]

    helper = TestTagRepositoryHelper(merged_reader, test_session_factory)
    yield helper

    # クリーンアップ
    try:
        with test_session_factory() as session:
            from genai_tag_db_tools.data.database_schema import Tag

            for tag_id in created_tag_ids:
                tag = session.query(Tag).filter_by(tag_id=tag_id).first()
                if tag:
                    session.delete(tag)
            session.commit()
    except Exception:
        pass
    finally:
        test_engine.dispose()


@pytest.fixture(scope="function")
def test_image_repository_with_tag_db(db_session_factory, test_tag_repository):
    """テスト用 MergedTagReader を使用する ImageRepository を提供

    Args:
        db_session_factory: セッションファクトリ
        test_tag_repository: テスト用 TagRepository

    Returns:
        ImageRepository: テスト用 MergedTagReader を使用する ImageRepository
    """
    image_repo = ImageRepository(session_factory=db_session_factory)
    image_repo.merged_reader = test_tag_repository.merged_reader
    return image_repo


# =================================================
# テスト画像フィクスチャ（統合テストでも必要な場合）
# =================================================
# 注意: unit/conftest.py にも同様のフィクスチャがあるが、
# pytest の conftest.py 探索順序により、統合テストでは
# ルート conftest.py -> integration/conftest.py の順で探索される。
# 統合テストが画像フィクスチャを使用する場合、以下を定義するか、
# ルート conftest.py に画像フィクスチャを残すかを選択する。
# 推奨: 統合テストで画像が必要な場合はここに定義を追加。


@pytest.fixture
def test_image_dir():
    """テスト用画像ディレクトリのパス

    Returns:
        Path: tests/resources/img/1_img ディレクトリのパス
    """
    return Path(__file__).parent.parent / "resources" / "img" / "1_img"


@pytest.fixture
def test_image_path(test_image_dir):
    """テスト用画像のパス

    Args:
        test_image_dir: テスト用画像ディレクトリ

    Returns:
        Path: file01.webp のパス
    """
    image_path = test_image_dir / "file01.webp"
    if not image_path.exists():
        pytest.skip(f"Test image not found: {image_path}")
    return image_path


# --- [COPY END: tests/integration/conftest.py] ---


# ========================================
# Section 4: tests/bdd/conftest.py（BDD テスト用）
# 目標行数: 40-80行
# 責務: BDD ステップコンテキスト、テストデータセットアップ
# ========================================

# --- [COPY START: tests/bdd/conftest.py] ---

# tests/bdd/conftest.py
"""BDD E2E テスト用フィクスチャ

pytest-bdd のステップ間状態管理とテストデータセットアップを提供。
"""

import pytest  # noqa: E811


@pytest.fixture
def bdd_context():
    """BDD ステップ間の状態共有コンテキスト

    各 Scenario の開始時に新しいコンテキストが作成される。
    ステップ定義間でデータを受け渡す際に使用。

    Yields:
        dict: ステップ間で共有される状態辞書

    Example:
        @given("I have a project")
        def given_project(bdd_context):
            bdd_context["project"] = create_test_project()

        @when("I add an image")
        def when_add_image(bdd_context):
            bdd_context["project"].add_image(...)
    """
    context = {}
    yield context


@pytest.fixture
def bdd_test_data_dir():
    """BDD テスト用のデータディレクトリパスを提供

    Returns:
        Path: tests/resources ディレクトリのパス
    """
    from pathlib import Path

    return Path(__file__).parent.parent / "resources"


# --- [COPY END: tests/bdd/conftest.py] ---
