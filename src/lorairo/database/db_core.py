"""DBコア設定、エンジン、セッション管理

このモジュールは、SQLAlchemy を使用したデータベース接続の初期化とセッション管理を行います。
設定値（データベースパス、タグDB情報など）は `src/lorairo/utils/config.py` を介して
`config/lorairo.toml` から読み込まれます。
"""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# SQLAlchemy imports
from sqlalchemy import StaticPool, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..utils.config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration --- #

# Load configuration using the central config utility
config = get_config()
db_config = config.get("database", {})
dir_config = config.get("directories", {})


def get_project_dir(base_dir_name: str, project_name: str) -> Path:
    """プロジェクトディレクトリを生成（任意名前_日付_連番形式）

    Args:
        base_dir_name: ベースディレクトリ名 (例: "lorairo_data")
        project_name: プロジェクト名 (例: "main_dataset", "猫画像")

    Returns:
        Path: 生成されたプロジェクトディレクトリパス
    """
    from datetime import datetime

    base_dir = Path(base_dir_name)
    base_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")

    # ファイルシステム安全な文字に正規化
    safe_name = sanitize_project_name(project_name)
    pattern = f"{safe_name}_{today}_"

    # 既存プロジェクトから連番を決定
    existing = [d.name for d in base_dir.iterdir() if d.is_dir() and d.name.startswith(pattern)]

    if not existing:
        next_num = 1
    else:
        # 連番部分を抽出（最後のアンダースコア以降）
        numbers = []
        for name in existing:
            parts = name.split("_")
            if len(parts) >= 3 and parts[-1].isdigit():
                numbers.append(int(parts[-1]))
        next_num = max(numbers, default=0) + 1

    project_dir = base_dir / f"{safe_name}_{today}_{next_num:03d}"
    project_dir.mkdir(exist_ok=True)
    logger.info(f"新しいプロジェクトディレクトリを作成しました: {project_dir}")
    return project_dir


def sanitize_project_name(name: str) -> str:
    """プロジェクト名をファイルシステム安全な形式に変換"""
    import re

    # Windows/Linux共通で問題となる文字のみ置換
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, "_", name)


# Get database directory from config, or create new project directory
database_dir = dir_config.get("database_dir")
if database_dir:
    DB_DIR = Path(database_dir)
else:
    base_dir_name = dir_config.get("database_base_dir", "lorairo_data")
    project_name = dir_config.get("database_project_name", "main_dataset")
    DB_DIR = get_project_dir(base_dir_name, project_name)
IMG_DB_FILENAME = db_config.get(
    "image_db_filename", "image_database.db"
)  # Keep default if not in db_config
# Note: TAG_DB_PACKAGE and TAG_DB_FILENAME were removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API (initialize_databases)

# 相対パスを絶対パスに解決（stored_image_path のパス二重結合を防止）
DB_DIR = DB_DIR.resolve()

# Ensure DB_DIR exists
DB_DIR.mkdir(parents=True, exist_ok=True)

IMG_DB_FILENAME_VAR: str = IMG_DB_FILENAME  # 一時保存（後で使用）

# --- Dynamic Project Root Resolution --- #


def get_current_project_root() -> Path:
    """現在接続中のDBパスからプロジェクトルートを動的に取得

    Returns:
        Path: 現在のプロジェクトルートディレクトリ

    Example:
        DB: /workspaces/LoRAIro/lorairo_data/main_dataset_20250707_001/image_database.db
        Root: /workspaces/LoRAIro/lorairo_data/main_dataset_20250707_001/
    """
    return IMG_DB_PATH.parent


def resolve_stored_path(stored_path: str) -> Path:
    """DB内の stored_image_path を実際のファイルパスに解決する。

    Args:
        stored_path: DB内のパス（相対パスまたは絶対パス）

    Returns:
        解決済みの絶対パス
    """
    # バックスラッシュをフォワードスラッシュに正規化（Windows/Linux互換）
    normalized = stored_path.replace("\\", "/")
    path = Path(normalized)

    # 既に絶対パスの場合はそのまま返す
    if path.is_absolute():
        return path

    # 相対パスの場合、現在のプロジェクトルートと結合
    project_root = get_current_project_root()

    # 二重結合防止: stored_path にプロジェクトディレクトリ名が含まれている場合、
    # それ以降の部分のみをプロジェクトルートからの相対パスとして使用
    # (例: "lorairo_data/main_dataset_20250707_001/image_dataset/..." →
    #  "image_dataset/..." を抽出して project_root と結合)
    project_dir_name = project_root.name
    try:
        idx = path.parts.index(project_dir_name)
        remainder_parts = path.parts[idx + 1 :]
        if remainder_parts:
            resolved = project_root.joinpath(*remainder_parts)
            logger.debug(f"パス解決（プレフィックス正規化）: {stored_path} -> {resolved}")
            return resolved
    except ValueError:
        pass

    resolved = project_root / stored_path
    logger.debug(f"パス解決: {stored_path} -> {resolved}")
    return resolved


# --- Tag DB Path --- #
# Note: get_tag_db_path() was removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API:
# - Base DBs: ensure_databases() downloads from HuggingFace
# - User DB: init_user_db() creates user_tags.sqlite in project directory


def _initialize_lorairo_format_mappings() -> None:
    """LoRAIro用のデフォルトtype_nameマッピングを初期化します。

    format_id=1000（LoRAIro専用）に対して、以下のマッピングを作成します：
    - type_id=0: "unknown" (デフォルト)

    Note:
        - この関数はinit_user_db()の後に1回だけ呼び出されます
        - 既に存在する場合はスキップされます（冪等性）
        - type_id=0 のみを unknown にマッピングします
    """
    try:
        from genai_tag_db_tools.db.repository import get_default_repository

        repo = get_default_repository()
        LORAIRO_FORMAT_ID = 1000

        # type_name="unknown"を作成（存在しない場合）
        unknown_type_name_id = repo.create_type_name_if_not_exists("unknown")
        logger.info(f'type_name="unknown" initialized (type_name_id={unknown_type_name_id})')

        # type_id=0: unknownのマッピング（LoRAIroのデフォルト）
        repo.create_type_format_mapping_if_not_exists(
            format_id=LORAIRO_FORMAT_ID,
            type_id=0,
            type_name_id=unknown_type_name_id,
        )
        logger.info(f"LoRAIro mapping created: format_id={LORAIRO_FORMAT_ID}, type_id=0, type_name=unknown")

    except Exception as e:
        logger.warning(f"Failed to initialize LoRAIro format mappings: {e}. Tag registration may fail.")


# --- SQLAlchemy エンジンとセッション設定 ---
# Note: TAG_DB_PATH and TAG_DATABASE_ALIAS were removed (2026-01-02)
# Tag databases no longer use ATTACH DATABASE; managed via genai-tag-db-tools repository pattern

# Construct the database URL from config
IMG_DB_PATH: Path = DB_DIR / IMG_DB_FILENAME

# --- genai-tag-db-tools Database Initialization --- #
# 遅延初期化: モジュール import 時ではなく、最初に DB アクセスが必要になった時点で初期化する。
# CLI --help / version コマンドでは HF Hub に接続しない。
USER_TAG_DB_PATH: Path | None = None
_tag_db_initialized: bool = False


def ensure_tag_db_initialized() -> None:
    """タグDBを遅延初期化する。初回呼び出し時のみ HF Hub に接続する。"""
    import os

    global _tag_db_initialized, USER_TAG_DB_PATH
    if _tag_db_initialized:
        return
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    try:
        from genai_tag_db_tools import initialize_databases

        logger.info("Initializing genai-tag-db-tools databases...")
        results = initialize_databases(
            user_db_dir=DB_DIR,
            format_name="Lorairo",
            token=token,
        )
        USER_TAG_DB_PATH = DB_DIR / "user_tags.sqlite"
        _tag_db_initialized = True
        logger.info(f"Tag databases initialized: {len(results)} base DB(s) + user DB at {USER_TAG_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize tag databases: {e}.", exc_info=True)
        raise RuntimeError("Tag database initialization failed") from e


def get_user_tag_db_path() -> Path | None:
    """タグDBパスを返す（ensure_tag_db_initialized() 呼び出し後に設定される）。"""
    return USER_TAG_DB_PATH


DATABASE_URL = f"sqlite:///{IMG_DB_PATH.resolve()}?check_same_thread=False"


def create_db_engine(database_url: str = DATABASE_URL) -> Engine:
    """指定された URL で SQLAlchemy エンジンを作成し、イベントリスナーを設定します。"""
    logger.info(f"Creating SQLAlchemy engine for: {database_url}")
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},  # SQLite に必要
        poolclass=StaticPool,  # SQLite で推奨
        echo=False,  # SQL 文のデバッグ用に True に設定
    )

    # --- イベントリスナー設定 ---
    # リスナー関数をエンジン作成時に動的に定義・登録する

    @event.listens_for(engine, "connect")
    def enable_foreign_keys_listener(dbapi_connection: Any, connection_record: Any) -> None:
        """SQLite の外部キー制約を有効にします。"""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            logger.debug("PRAGMA foreign_keys=ON executed.")
        except Exception:
            logger.error("Failed to enable foreign keys", exc_info=True)
        finally:
            cursor.close()

    # Note: attach_tag_db_listener was removed (2026-01-02)
    # Tag databases no longer use ATTACH DATABASE; managed via genai-tag-db-tools repository pattern
    # Base DBs + User DB are accessed through public API (search_tags, register_tag, MergedTagReader)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """指定されたエンジンにバインドされたセッションファクトリを作成します。"""
    logger.info("Creating SQLAlchemy session factory.")
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _ensure_model_types_seeded(engine: Engine) -> None:
    """Ensure canonical model type rows exist after create_all().

    Alembic migrations seed these rows for migrated databases, but project DBs
    created with ``Base.metadata.create_all()`` need the same baseline data.
    """
    from sqlalchemy import select

    from .schema import ModelType

    canonical_model_types = ("tags", "scores", "caption", "upscaler", "multimodal")
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        existing = set(session.execute(select(ModelType.name)).scalars())
        missing = [ModelType(name=name) for name in canonical_model_types if name not in existing]
        if not missing:
            return
        session.add_all(missing)
        session.commit()
        logger.info("Seeded model_types rows: %s", ", ".join(model.name for model in missing))


def _make_alembic_config(project_db_path: Path) -> Any:
    """Create an Alembic config pinned to the given project database."""
    from alembic.config import Config

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    alembic_config = Config()
    alembic_config.set_main_option(
        "script_location",
        str(migrations_dir),
    )
    alembic_config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{project_db_path.resolve()}?check_same_thread=False",
    )
    return alembic_config


def _user_table_names(engine: Engine) -> set[str]:
    """Return application table names, excluding Alembic's version table."""
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def _has_alembic_version_table(engine: Engine) -> bool:
    """Return whether this DB is already tracked by Alembic."""
    return inspect(engine).has_table("alembic_version")


def _stamp_alembic_head(project_db_path: Path) -> None:
    """Mark a metadata-created DB as current with the migration graph."""
    from alembic import command

    command.stamp(_make_alembic_config(project_db_path), "head")


def _upgrade_alembic_head(project_db_path: Path) -> None:
    """Apply pending migrations to an Alembic-managed project database."""
    from alembic import command

    command.upgrade(_make_alembic_config(project_db_path), "head")


def _prepare_project_database(project_db_path: Path) -> Engine:
    """Create or migrate a project image DB before repositories use it.

    New DBs are still initialized from SQLAlchemy metadata for compatibility with
    the existing project creation flow, then stamped to the current Alembic head.
    Existing Alembic-managed DBs are upgraded before ``create_all`` can mask
    missing tables, which prevents stale production DBs from failing later during
    search result loading.
    """
    from .schema import Base

    project_db_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{project_db_path.resolve()}?check_same_thread=False"
    engine = create_db_engine(db_url)

    if not _user_table_names(engine):
        Base.metadata.create_all(engine)
        _ensure_model_types_seeded(engine)
        _stamp_alembic_head(project_db_path)
        logger.info("Initialized new project DB schema and stamped Alembic head: %s", project_db_path)
        return engine

    if _has_alembic_version_table(engine):
        _upgrade_alembic_head(project_db_path)
        logger.info("Applied pending Alembic migrations for project DB: %s", project_db_path)
    else:
        logger.warning(
            "Project DB has existing tables but no alembic_version table; "
            "leaving migration state unchanged: %s",
            project_db_path,
        )

    Base.metadata.create_all(engine)
    _ensure_model_types_seeded(engine)
    return engine


def create_project_session_factory(project_db_path: Path) -> sessionmaker[Session]:
    """指定プロジェクト DB 用セッションファクトリを生成。

    新規 DB（touch で空ファイル）の場合はスキーマを初期化する。
    Alembic 管理済みの既存 DB は利用前に head まで migration する。

    Args:
        project_db_path: プロジェクト DB ファイルの絶対パス。

    Returns:
        sessionmaker[Session]: プロジェクト専用セッションファクトリ。
    """
    engine = _prepare_project_database(project_db_path)
    return create_session_factory(engine)


# --- デフォルトの Engine と Session Factory --- #
# 通常のアプリケーション実行時に使用される
default_engine = create_db_engine(DATABASE_URL)
_default_session_factory: sessionmaker[Session] | None = None
logger.info(f"Default database core initialized. Image DB: {IMG_DB_PATH} (Tag DB managed via public API)")


def _get_default_session_factory() -> sessionmaker[Session]:
    """Prepare the default project DB lazily and return its session factory."""
    global default_engine, _default_session_factory
    if _default_session_factory is None:
        default_engine = _prepare_project_database(IMG_DB_PATH)
        _default_session_factory = create_session_factory(default_engine)
    return _default_session_factory


def DefaultSessionLocal() -> Session:
    """Return a session for the default project DB, preparing migrations on first use."""
    return _get_default_session_factory()()


# --- セッションコンテキストマネージャ (ファクトリを受け取るように変更) --- #
@contextmanager
def get_db_session(
    session_factory: Callable[[], Session] = DefaultSessionLocal,
) -> Generator[Session, None, None]:
    """
    指定されたセッションファクトリを使用して、一連の操作に対するトランザクションスコープを提供します。
    セッションのコミット、ロールバック、クローズを処理します。

    Args:
        session_factory: 使用するセッションファクトリ。デフォルトは DefaultSessionLocal。

    Yields:
        SQLAlchemy セッションオブジェクト。
    """
    db = session_factory()
    # logger.debug(f"DB session {id(db)} opened from factory {session_factory}.")
    try:
        yield db
        # logger.debug(f"Committing DB session {id(db)}.")
        db.commit()
    except Exception:
        logger.error(f"Transaction failed in DB session {id(db)}. Rolling back.", exc_info=True)
        db.rollback()
        raise  # 例外を再発生させて上位に伝播
    finally:
        # logger.debug(f"Closing DB session {id(db)}.")
        db.close()


# --- 初期化ログ ---

logger.info(f"データベースコアが初期化されました。画像DB: {IMG_DB_PATH} (タグDBは公開API経由で管理)")
