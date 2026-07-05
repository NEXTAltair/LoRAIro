"""DBコア設定、エンジン、セッション管理

このモジュールは、SQLAlchemy を使用したデータベース接続の初期化とセッション管理を行います。
設定値（データベースパス、タグDB情報など）は `src/lorairo/utils/config.py` を介して
`config/lorairo.toml` から読み込まれます。
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# SQLAlchemy imports
from sqlalchemy import StaticPool, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..utils.config import get_config
from ..utils.log import logger

# --- Configuration --- #

# Load configuration using the central config utility
config = get_config()
db_config = config.get("database", {})
dir_config = config.get("directories", {})

# SQLite 書き込みロック競合時の待機時間 (ミリ秒)。GUI/CLI 併用時の一時的な
# `database is locked` を即時失敗させず、この時間まで再試行待機する (Issue #767)。
BUSY_TIMEOUT_MS: int = int(db_config.get("busy_timeout_ms", 30000))


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
def _next_project_dir_path(base_dir_name: str, project_name: str) -> Path:
    """Return the next auto project directory path without creating it."""
    from datetime import datetime

    base_dir = Path(base_dir_name)
    today = datetime.now().strftime("%Y%m%d")
    safe_name = sanitize_project_name(project_name)
    pattern = f"{safe_name}_{today}_"

    existing: list[str] = []
    if base_dir.exists():
        existing = [d.name for d in base_dir.iterdir() if d.is_dir() and d.name.startswith(pattern)]

    numbers = []
    for name in existing:
        parts = name.split("_")
        if len(parts) >= 3 and parts[-1].isdigit():
            numbers.append(int(parts[-1]))
    next_num = max(numbers, default=0) + 1
    return base_dir / f"{safe_name}_{today}_{next_num:03d}"


def _resolve_configured_db_dir() -> Path | None:
    """Return configured database_dir, or None when auto project creation is configured."""
    database_dir = dir_config.get("database_dir")
    if database_dir:
        return Path(database_dir).resolve()
    return None


def _resolve_auto_project_dir(create: bool) -> Path:
    """Resolve the default auto project directory, creating it only when requested."""
    base_dir_name = dir_config.get("database_base_dir", "lorairo_data")
    project_name = dir_config.get("database_project_name", "main_dataset")
    if create:
        return get_project_dir(base_dir_name, project_name).resolve()
    return _next_project_dir_path(base_dir_name, project_name).resolve()


_default_db_dir_materialized: bool = False


def ensure_default_db_dir() -> Path:
    """Ensure and return the default DB directory for explicit default DB use."""
    global _default_db_dir_materialized
    configured_dir = _resolve_configured_db_dir()
    if configured_dir is not None:
        configured_dir.mkdir(parents=True, exist_ok=True)
        return configured_dir
    if _default_db_dir_materialized:
        return DB_DIR
    materialized_dir = _resolve_auto_project_dir(create=True)
    _default_db_dir_materialized = True
    return materialized_dir


DB_DIR = _resolve_configured_db_dir() or _resolve_auto_project_dir(create=False)
IMG_DB_FILENAME = db_config.get(
    "image_db_filename", "image_database.db"
)  # Keep default if not in db_config
# Note: TAG_DB_PACKAGE and TAG_DB_FILENAME were removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API (initialize_databases)

# 相対パスを絶対パスに解決（stored_image_path のパス二重結合を防止）
DB_DIR = DB_DIR.resolve()

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


# resolve_stored_path のキャッシュ (Issue #584 / D3)。
# 同一 stored_path はサムネイル/プレビュー/ファイルサイズ/パスリストなど複数経路から
# 繰り返し解決されるため結果を再利用する。project root は init_db_core で実行時に
# 変わりうるので、root 変更を検知したら clear する (別プロジェクトの stale パス返却を防ぐ)。
_resolve_cache: dict[str, Path] = {}
_resolve_cache_root: Path | None = None


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

    # 既に絶対パスの場合はそのまま返す（キャッシュ不要）
    if path.is_absolute():
        return path

    # 相対パスの場合、現在のプロジェクトルートと結合
    project_root = get_current_project_root()

    # project root が変わったらキャッシュを破棄（stale-free）
    global _resolve_cache_root
    if _resolve_cache_root != project_root:
        _resolve_cache.clear()
        _resolve_cache_root = project_root

    cached = _resolve_cache.get(stored_path)
    if cached is not None:
        return cached

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
            # per-item firehose のため TRACE (通常デバッグでは抑制、ADR 0047)
            logger.trace(f"パス解決（プレフィックス正規化）: {stored_path} -> {resolved}")
            _resolve_cache[stored_path] = resolved
            return resolved
    except ValueError:
        pass

    resolved = project_root / path  # バックスラッシュ正規化済みの path を使う (Issue #707)
    logger.trace(f"パス解決: {stored_path} -> {resolved}")
    _resolve_cache[stored_path] = resolved
    return resolved


# --- Tag DB Path --- #
# Note: get_tag_db_path() was removed (2026-01-02)
# Tag databases are now managed via genai-tag-db-tools public API:
# - Base DBs: ensure_databases() downloads from HuggingFace
# - User DB: init_user_db() creates user_tags.sqlite in project directory


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

    global _tag_db_initialized, DB_DIR, USER_TAG_DB_PATH
    if _tag_db_initialized:
        return
    DB_DIR = ensure_default_db_dir()
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
        logger.opt(exception=True).error(f"Failed to initialize tag databases: {e}.")
        raise RuntimeError("Tag database initialization failed") from e


def get_user_tag_db_path() -> Path | None:
    """タグDBパスを返す（ensure_tag_db_initialized() 呼び出し後に設定される）。"""
    return USER_TAG_DB_PATH


DATABASE_URL = f"sqlite:///{IMG_DB_PATH.resolve()}?check_same_thread=False"


def create_db_engine(database_url: str | None = None) -> Engine:
    """指定された URL で SQLAlchemy エンジンを作成し、イベントリスナーを設定します。"""
    if database_url is None:
        database_url = DATABASE_URL
    logger.info(f"Creating SQLAlchemy engine for: {database_url}")
    # StaticPool は 1 本の生コネクションを全セッションで共有するため、GUI メインスレッドと
    # RefinementWorker (QThread) が同一エンジンを共有すると sqlite3 の真の同時アクセスで
    # "bad parameter or other API misuse" を招く (Issue #1002)。実ファイル DB では
    # SQLAlchemy 既定の QueuePool (スレッドごとに独立コネクション) に委ね、
    # 接続ごとに別 DB になる :memory: のときだけ単一コネクション保持の StaticPool を使う。
    engine_kwargs: dict[str, Any] = {
        "connect_args": {"check_same_thread": False},  # SQLite に必要
        "echo": False,  # SQL 文のデバッグ用に True に設定
    }
    if ":memory:" in database_url:
        engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_kwargs)

    # --- イベントリスナー設定 ---
    # リスナー関数をエンジン作成時に動的に定義・登録する

    @event.listens_for(engine, "connect")
    def configure_sqlite_listener(dbapi_connection: Any, connection_record: Any) -> None:
        """SQLite の外部キー制約と低 I/O 向け PRAGMA を設定します。"""
        if engine.url.get_backend_name() != "sqlite":
            return

        cursor = dbapi_connection.cursor()
        try:
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                logger.debug("PRAGMA foreign_keys=ON executed.")
            except Exception:
                logger.opt(exception=True).warning("Failed to configure PRAGMA foreign_keys")

            try:
                # busy_timeout は synchronous より先に、かつ単独の try/except で設定する
                # (Issue #767 の待機が他 PRAGMA の失敗で無効化されるのを防ぐ、Issue #1002)。
                cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
                logger.debug(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS} executed.")
            except Exception:
                logger.opt(exception=True).warning("Failed to configure PRAGMA busy_timeout")

            # Note: journal_mode=WAL は per-connection では設定しない (Issue #1165)。
            # WAL は DB ヘッダに永続化されるため、接続ごとに再設定する必要はない。毎接続で
            # PRAGMA journal_mode=WAL を実行すると、GUI/CLI 併用時 (9p bind mount) にその
            # 一瞬の排他取得が busy_timeout の効かないまま database is locked / disk I/O error
            # になり、接続セットアップ自体がクラッシュしていた。WAL の設定は DB 準備時に
            # 1 回だけ _ensure_wal_journal_mode() で行う。

            try:
                cursor.execute("PRAGMA synchronous=NORMAL")
                logger.debug("PRAGMA synchronous=NORMAL executed.")
            except Exception:
                logger.opt(exception=True).warning("Failed to configure PRAGMA synchronous")
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


def _ensure_wal_journal_mode(engine: Engine) -> None:
    """file-backed な project DB に WAL journal mode を 1 回だけ永続化する (Issue #1165)。

    journal_mode=WAL は DB ヘッダに永続化されるため、接続ごとに設定する必要はない。
    毎接続で ``PRAGMA journal_mode=WAL`` を実行すると、GUI/CLI 併用時 (9p bind mount) に
    その一瞬の排他取得が busy_timeout の効かないまま ``database is locked`` /
    ``disk I/O error`` になり接続セットアップがクラッシュする。そこで DB 準備時に一度だけ
    設定し、かつ既に WAL の場合は書き換え (ロック取得) を避けて読み取りだけで済ませる。

    Args:
        engine: 対象の SQLAlchemy エンジン。``:memory:`` DB では何もしない。
    """
    if ":memory:" in str(engine.url):
        return
    try:
        with engine.connect() as connection:
            current = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
            if current is not None and str(current).lower() == "wal":
                return
            result = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
            logger.debug(f"journal_mode set to WAL at DB preparation: {result}")
    except SQLAlchemyError:
        logger.opt(exception=True).warning("Failed to set WAL journal mode at DB preparation")


def _ensure_model_types_seeded(engine: Engine) -> None:
    """Ensure canonical model type rows exist after create_all().

    Alembic migrations seed these rows for migrated databases, but project DBs
    created with ``Base.metadata.create_all()`` need the same baseline data.
    """
    from sqlalchemy import select

    from .schema import ModelType

    canonical_model_types = ("tags", "scores", "caption", "upscaler", "multimodal", "ratings")
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        existing = set(session.execute(select(ModelType.name)).scalars())
        missing = [ModelType(name=name) for name in canonical_model_types if name not in existing]
        if not missing:
            return
        session.add_all(missing)
        session.commit()
        logger.info(f"Seeded model_types rows: {', '.join(model.name for model in missing)}")


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
    # WAL は接続ごとではなく DB 準備時に 1 回だけ永続化する (Issue #1165)。
    _ensure_wal_journal_mode(engine)

    if not _user_table_names(engine):
        Base.metadata.create_all(engine)
        _ensure_model_types_seeded(engine)
        _stamp_alembic_head(project_db_path)
        logger.info(f"Initialized new project DB schema and stamped Alembic head: {project_db_path}")
        return engine

    if _has_alembic_version_table(engine):
        _upgrade_alembic_head(project_db_path)
        logger.info(f"Applied pending Alembic migrations for project DB: {project_db_path}")
    else:
        logger.warning(
            "Project DB has existing tables but no alembic_version table; "
            f"leaving migration state unchanged: {project_db_path}"
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
default_engine: Engine | None = None
_default_session_factory: sessionmaker[Session] | None = None


def _get_default_session_factory() -> sessionmaker[Session]:
    """Prepare the default project DB lazily and return its session factory."""
    global DB_DIR, IMG_DB_PATH, DATABASE_URL, default_engine, _default_session_factory
    if _default_session_factory is None:
        if IMG_DB_PATH == DB_DIR / IMG_DB_FILENAME:
            DB_DIR = ensure_default_db_dir()
            IMG_DB_PATH = DB_DIR / IMG_DB_FILENAME
        DATABASE_URL = f"sqlite:///{IMG_DB_PATH.resolve()}?check_same_thread=False"
        default_engine = _prepare_project_database(IMG_DB_PATH)
        _default_session_factory = create_session_factory(default_engine)
        # 初期化ログは import 時 (= initialize_logging 前) ではなく、実際に default DB を
        # 準備したこのタイミングで出力する。これにより loguru file sink に確実に乗る (#572)。
        logger.info(
            f"データベースコアが初期化されました。画像DB: {IMG_DB_PATH} (タグDBは公開API経由で管理)"
        )
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
        logger.opt(exception=True).error(f"Transaction failed in DB session {id(db)}. Rolling back.")
        db.rollback()
        raise  # 例外を再発生させて上位に伝播
    finally:
        # logger.debug(f"Closing DB session {id(db)}.")
        db.close()
