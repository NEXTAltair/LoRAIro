"""DBコア設定、エンジン、セッション管理"""

import importlib.resources
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import toml

# SQLAlchemy imports
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration --- #

CONFIG_FILE_PATH = Path("config.toml")  # プロジェクトルートを想定

# Default values
DEFAULT_DB_DIR = Path("./Image_database")
DEFAULT_IMG_DB_FILENAME = "image_database.db"
DEFAULT_TAG_DB_PACKAGE = "genai_tag_db_tools.data"
DEFAULT_TAG_DB_FILENAME = "tags_v4.db"


def load_config() -> dict:
    """Load configuration from TOML file."""
    if CONFIG_FILE_PATH.exists():
        # テキストモードで開く
        with open(CONFIG_FILE_PATH, "rt", encoding="utf-8") as f:
            try:
                # ファイルオブジェクトをそのまま渡す
                return toml.load(f)
            # 正しい例外クラス名に修正
            except toml.TomlDecodeError as e:
                print(f"Error decoding config file {CONFIG_FILE_PATH}: {e}")
                # エラー時はデフォルト値を使うために空の辞書を返すか、例外を発生させるか選択
                return {}
    return {}


config = load_config()
db_config = config.get("database", {})

# Use config values or defaults
DB_DIR = Path(db_config.get("directory", DEFAULT_DB_DIR))
IMG_DB_FILENAME = db_config.get("image_db_filename", DEFAULT_IMG_DB_FILENAME)
TAG_DB_PACKAGE = db_config.get("tag_db_package", DEFAULT_TAG_DB_PACKAGE)
TAG_DB_FILENAME = db_config.get("tag_db_filename", DEFAULT_TAG_DB_FILENAME)

# Ensure DB_DIR exists
DB_DIR.mkdir(parents=True, exist_ok=True)

IMG_DB_PATH = DB_DIR / IMG_DB_FILENAME

# --- Tag DB Path --- #


def get_tag_db_path() -> Path:
    """インストールされたパッケージからタグデータベースファイルへのフルパスを取得します。"""
    try:
        tag_db_resource = importlib.resources.files(TAG_DB_PACKAGE).joinpath(TAG_DB_FILENAME)
        # リソースが存在し、ファイルであることを確認してからパスを返す
        if tag_db_resource.is_file():
            return Path(str(tag_db_resource))
        else:
            logger.error(f"タグDBリソースが見つからないか、ファイルではありません: {tag_db_resource}")
            raise FileNotFoundError(f"タグDBが見つかりません: {tag_db_resource}")

    except (FileNotFoundError, TypeError) as e:
        # .files() が特定のエッジケースで発生させる可能性があるため、TypeError も捕捉
        logger.exception(
            f"importlib.resources.files を使用したタグDBパス ({TAG_DB_PACKAGE}/{TAG_DB_FILENAME}) の取得に失敗しました。エラー: {e}",
            exc_info=True,
        )
        raise


# --- SQLAlchemy エンジンとセッション設定 ---

TAG_DB_PATH = get_tag_db_path()
TAG_DATABASE_ALIAS = "tag_db"

# デフォルトの画像DBパス
DEFAULT_IMG_DB_PATH = DB_DIR / IMG_DB_FILENAME
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_IMG_DB_PATH.resolve()}?check_same_thread=False"


def create_db_engine(database_url: str) -> Engine:
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
    def enable_foreign_keys_listener(dbapi_connection, connection_record):
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
    def attach_tag_db_listener(dbapi_connection, connection_record):
        """メインDB接続時にタグデータベースをアタッチします (インメモリDBを除く)。"""
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
default_engine = create_db_engine(DEFAULT_DATABASE_URL)
DefaultSessionLocal = create_session_factory(default_engine)
logger.info(f"Default database core initialized. Image DB: {DEFAULT_IMG_DB_PATH}, Tag DB: {TAG_DB_PATH}")


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

logger.info(f"データベースコアが初期化されました。画像DB: {IMG_DB_PATH}, タグDB: {TAG_DB_PATH}")
