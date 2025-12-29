"""DBコア設定、エンジン、セッション管理

このモジュールは、SQLAlchemy を使用したデータベース接続の初期化とセッション管理を行います。
設定値（データベースパス、タグDB情報など）は `src/lorairo/utils/config.py` を介して
`config/lorairo.toml` から読み込まれます。
"""

import importlib.resources
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# SQLAlchemy imports
from sqlalchemy import StaticPool, create_engine, event
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
TAG_DB_PACKAGE = db_config.get(
    "tag_db_package", "genai_tag_db_tools.data"
)  # Keep default if not in db_config
TAG_DB_FILENAME = db_config.get("tag_db_filename", "tags_v4.db")  # Keep default if not in db_config

# Ensure DB_DIR exists
DB_DIR.mkdir(parents=True, exist_ok=True)

IMG_DB_PATH: Path = DB_DIR / IMG_DB_FILENAME

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
    path = Path(stored_path)

    # 既に絶対パスの場合はそのまま返す
    if path.is_absolute():
        return path

    # 相対パスの場合、現在のプロジェクトルートと結合
    project_root = get_current_project_root()
    resolved = project_root / stored_path

    logger.debug(f"パス解決: {stored_path} -> {resolved}")
    return resolved


# --- Tag DB Path --- #


def get_tag_db_path() -> Path:
    """インストールされたパッケージからタグデータベースファイルへのフルパスを取得します。"""
    try:
        # Use configuration values for package and filename
        package_name = TAG_DB_PACKAGE
        filename = TAG_DB_FILENAME
        tag_db_resource = importlib.resources.files(package_name).joinpath(filename)
        # リソースが存在し、ファイルであることを確認してからパスを返す
        if tag_db_resource.is_file():
            return Path(str(tag_db_resource))
        else:
            logger.error(f"タグDBリソースが見つからないか、ファイルではありません: {tag_db_resource}")
            raise FileNotFoundError(f"タグDBが見つかりません: {tag_db_resource}")

    except (FileNotFoundError, TypeError) as e:
        # .files() が特定のエッジケースで発生させる可能性があるため、TypeError も捕捉
        logger.exception(
            f"importlib.resources.files を使用したタグDBパス ({package_name}/{filename}) の取得に失敗しました。エラー: {e}",
            exc_info=True,
        )
        raise


# --- SQLAlchemy エンジンとセッション設定 ---

# TAG_DB_PATH = get_tag_db_path()  # Deprecated: 外部tag_dbは公開API経由で取得
TAG_DB_PATH = None  # 互換性のため残すがNoneで初期化
TAG_DATABASE_ALIAS = "tag_db"

# Construct the database URL from config
IMG_DB_PATH = DB_DIR / IMG_DB_FILENAME
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

    @event.listens_for(engine, "connect")
    def attach_tag_db_listener(dbapi_connection: Any, connection_record: Any) -> None:
        """メインDB接続時にタグデータベースをアタッチします (インメモリDBを除く)。"""
        # Deprecated: タグDBは公開API経由で管理されるため、アタッチ不要
        if TAG_DB_PATH is None:
            logger.debug("Tag DB managed via public API, skipping database attachment.")
            return

        # インメモリDBの場合はアタッチしない
        if database_url == "sqlite:///:memory:":
            logger.debug("In-memory database detected, skipping tag DB attachment.")
            return

        tag_db_path_str = str(TAG_DB_PATH)
        cursor = dbapi_connection.cursor()
        try:
            # パスを安全にSQL文に渡すためにパラメータを使用
            cursor.execute(f"ATTACH DATABASE ? AS {TAG_DATABASE_ALIAS}", (tag_db_path_str,))
            logger.info(f"Attached tag database '{tag_db_path_str}' as {TAG_DATABASE_ALIAS}.")
        except Exception:
            logger.error(f"Failed to attach tag database '{tag_db_path_str}'", exc_info=True)
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """指定されたエンジンにバインドされたセッションファクトリを作成します。"""
    logger.info("Creating SQLAlchemy session factory.")
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- デフォルトの Engine と Session Factory --- #
# 通常のアプリケーション実行時に使用される
default_engine = create_db_engine(DATABASE_URL)
DefaultSessionLocal = create_session_factory(default_engine)
logger.info(f"Default database core initialized. Image DB: {IMG_DB_PATH} (Tag DB managed via public API)")


# --- セッションコンテキストマネージャ (ファクトリを受け取るように変更) --- #
@contextmanager
def get_db_session(
    session_factory: sessionmaker[Session] = DefaultSessionLocal,
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
