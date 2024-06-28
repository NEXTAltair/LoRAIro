import sqlite3  # SQLite3データベースを扱うためのライブラリをインポート
import uuid  # ユニークIDを生成するためのライブラリをインポート
from pathlib import Path  # ファイルパスを扱うためのライブラリからPathクラスをインポート
from typing import Dict, List, Optional, Any, TypedDict  # データ型を定義
import logging

class DatabaseManager:
    """
    データベース操作を管理するクラス。

    このクラスは、画像メタデータとアノテーションの保存、取得を行うための
    高レベルインターフェースを提供します。

    Attributes:
        config (Dict[str, Any]): アプリケーション設定
        db (ImageDatabase): データベース操作を行うImageDatabaseインスタンス
        logger (logging.Logger): ロギング用のLoggerインスタンス
    """

    def __init__(self, config: Dict[str, Any]):
        """
        DatabaseManagerを初期化します。

        Args:
            config (Dict[str, Any]): アプリケーション設定
        """
        self.config = config
        self.db = None
        self.logger = logging.getLogger(__name__)

    def initialize(self):
        """
        データベースマネージャを初期化し、データベースファイルを設定します。

        Raises:
            Exception: 初期化に失敗した場合
        """
        try:
            db_path = Path(self.config['directories']['output']) / "image_dataset" / self.config["image_database"]

            # ディレクトリが存在することを確認
            db_path.parent.mkdir(parents=True, exist_ok=True)

            self.db = ImageDatabase(db_path)
            self.logger.info(f"データベースマネージャーの初期化 {db_path}")
        except Exception as e:
            self.logger.error(f"データベースマネージャーの初期化に失敗しました: {e}")
            raise

    def connect(self) -> bool:
        """
        データベースに接続します。

        Returns:
            bool: 接続に成功した場合True、失敗した場合False
        """
        try:
            connection_status = self.db.connect()
            self.logger.info("Connected to the database successfully" if connection_status else "Failed to connect to the database")
            return connection_status
        except Exception as e:
            self.logger.error(f"Error connecting to the database: {e}")
            return False

    def disconnect(self):
        """データベース接続を切断します。"""
        try:
            self.db.close()
            self.logger.info("Disconnected from the database")
        except Exception as e:
            self.logger.error(f"Error disconnecting from the database: {e}")

    def save_original_metadata(self, stored_image_path: Path, info: Dict[str, Any]) -> int:
        """
        元の画像のメタデータを保存します。

        Args:
            stored_image_path (Path): 保存された画像のパス
            info (Dict[str, Any]): 画像のメタデータ

        Returns:
            image_id (int:) 保存された画像のID

            uuid (str): UUID

        Raises:
            Exception: メタデータの保存に失敗した場合
        """
        if self.db is None:
            raise RuntimeError("データベースが初期化されていません。initialize()を呼び出してください。")
        try:
            # UUIDを生成し、infoディクショナリに追加
            info['uuid'] = str(uuid.uuid4())
            info['stored_image_path'] = str(stored_image_path)

            image_id = self.db.add_image(info)
            self.logger.info(f"元画像のメタデータをDBに保存しました: {image_id}")
            return image_id, info['uuid']
        except Exception as e:
            self.logger.error(f"元画像のメタデータ登録中エラー: {e}")
            raise

    def save_processed_metadata(self, image_id: int, info: Dict[str, Any]) -> bool:
        """
        処理済み画像のメタデータを保存します。

        Args:
            image_id (int): 画像ID
            info (Dict[str, Any]): 処理済み画像のメタデータ

        Returns:
            bool: 保存に成功した場合True、失敗した場合False

        Raises:
            Exception: メタデータの保存に失敗した場合
        """
        try:
            info['image_id'] = image_id
            success = self.db.add_image(info)
            self.logger.info(f"処理済み画像メタデータをDBに保存: {image_id}")
            return success
        except Exception as e:
            self.logger.error(f"処理済み画像メタデータをDBに保存中にエラー: {e}")
            raise

    def save_annotations(self, image_id: int, annotations: Dict[str, List[str] | List[Dict[str, Any]]]) -> None:
        """
        画像のアノテーション（キャプション、タグ、スコア）を保存します。
        各アノテーションタイプは独立して処理され、存在しない場合はスキップされます。

        Args:
            image_id (int): 画像ID
            annotations (Dict[str, List[str] | List[Dict[str, Any]]): アノテーションデータ

        Raises:
            Exception: アノテーションの保存に失敗した場合
        """
        try:
            self.db.save_annotations(image_id, annotations)
            self.logger.info(f"Saved annotations for image {image_id}")
        except Exception as e:
            self.logger.error(f"Error saving annotations: {e}")
            raise

    def get_image_metadata(self, image_id: int) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID

        Returns:
            Optional[Dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。
        """
        try:
            metadata = self.db.fetch_image_metadata(image_id)
            if metadata is None:
                self.logger.info(f"ID {image_id} の画像が見つかりません。")
            return metadata
        except Exception as e:
            self.logger.error(f"画像メタデータ取得中にエラーが発生: {e}")
            raise

    def get_processed_image_metadata_list(self, image_id: int) -> List[Dict[str, Any]]:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータリストを取得します。

        Args:
            image_id (int): 元画像のID

        Returns:
            List[Dict[str, Any]]: 処理済み画像のメタデータのリスト。
                                  画像が見つからない場合は空のリストを返します。

        Raises:
            Exception: メタデータの取得に失敗した場合
        """
        try:
            metadata_list = self.db.fetch_processed_image_metadata_list(image_id)
            if not metadata_list:
                self.logger.info(f"ID {image_id} の元画像に関連する処理済み画像が見つかりません。")
            return metadata_list
        except Exception as e:
            self.logger.error(f"処理済み画像メタデータ取得中にエラーが発生: {e}")
            raise

    def get_image_annotations(self, image_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): 画像ID

        Returns:
            Dict[str, List[Dict[str, Any]]]: タグ、キャプション、スコアを含む辞書。
            形式: {
                'tags': [{'tag': str, 'model': str}, ...],
                'captions': [{'caption': str, 'model': str}, ...],
                'scores': [{'score': float, 'model': str}, ...],
            }
            画像が見つからない場合は空の辞書を返します。

        Raises:
            Exception: アノテーションの取得に失敗した場合
        """
        try:
            annotations = self.db.fetch_image_annotations(image_id)
            if not any(annotations.values()):
                self.logger.info(f"ID {image_id} の画像にアノテーションが見つかりません。")
            return annotations
        except Exception as e:
            self.logger.error(f"画像アノテーション取得中にエラーが発生: {e}")
            raise

class ImageDict(TypedDict, total=False):
    id: int
    uuid: str
    stored_image_path: str
    width: int
    height: int
    format: str
    mode: str
    has_alpha: bool
    filename: str
    extension: str
    created_at: str
    updated_at: str

class ProcessedImageDict(TypedDict, total=False):
    # id: int
    image_id: int
    processed_path: str
    processed_width: int
    processed_height: int
    processed_format: str
    processed_mode: str
    processed_has_alpha: bool
    saved_filename: str
    created_at: str

class ImageDatabase:
    """画像データを管理するためのデータベース操作クラス"""

    def __init__(self, db_path: Path):
        """
        ImageDatabaseクラスのコンストラクタ

        Args:
            db_path (Path): データベースファイルの名前
        """
        self.db_path = db_path  # データベースファイル名を指定
        self.conn = None  # データベース接続オブジェクトを初期化
        self.create_tables()  # テーブルを作成

    def connect(self):
        """
        データベースに接続。
        既に接続が存在する場合は、既存の接続をす。
        Returns:
            sqlite3.Connection: データベース接続オブジェクト
        """
        if self.conn is None:  # まだ接続していない場合のみ接続
            self.conn = sqlite3.connect(self.db_path)  # データベースに接続
            self.conn.row_factory = sqlite3.Row  # クエリ結果を辞書のように扱えるように設定
        return self.conn  # 接続オブジェクトを返す

    def close(self):
        """データベース接続を閉る。"""
        if self.conn:  # 接続している場合のみ
            self.conn.close()  # データベース接続を閉じる
            self.conn = None  # 接続オブジェクトをNoneに戻す

    def __enter__(self):
        """
        コンテキストマネージャのエントリーポイント
        データベースに接続し、接続オブジェクトを返す
        Returns:
            sqlite3.Connection: データベース接続オブジェクト
        """
        return self.connect()  # データベースに接続

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with文を使用した際に自動的に接続を閉じるためのメソッド。"""
        self.close()  # データベース接続を閉じる

    def create_tables(self):
        """
        必要なテーブルをデータベースに作成します。
        既にテーブルが存在する場合は作成しません。
        """
        with self.connect() as conn:
            conn.executescript('''
                -- images テーブル：オリジナル画像の情報を格納
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    uuid TEXT UNIQUE NOT NULL,
                    stored_image_path TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    format TEXT NOT NULL,
                    mode TEXT NULL,
                    has_alpha BOOLEAN,
                    filename TEXT NULL,
                    extension TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- processed_images テーブル：処理済み画像の情報を格納
                CREATE TABLE IF NOT EXISTS processed_images (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER NOT NULL,
                    stored_image_path TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    format TEXT NOT NULL,
                    mode TEXT NULL,
                    has_alpha BOOLEAN NOT NULL,
                    filename TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
                );

                -- models テーブル：使用されるモデルの情報を格納
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- tags テーブル：画像に関連付けられたタグを格納
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    tag TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images (id),
                    FOREIGN KEY (model_id) REFERENCES models (id)
                );

                -- captions テーブル：画像に関連付けられたキャプションを格納
                CREATE TABLE IF NOT EXISTS captions (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    caption TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images (id),
                    FOREIGN KEY (model_id) REFERENCES models (id)
                );

                -- scores テーブル：画像に関連付けられたスコアを格納
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    score FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images (id),
                    FOREIGN KEY (model_id) REFERENCES models (id)
                );
            -- インデックスの作成
            CREATE INDEX IF NOT EXISTS idx_images_uuid ON images(uuid);
            CREATE INDEX IF NOT EXISTS idx_processed_images_image_id ON processed_images(image_id);
            ''')

    def add_image(self, info: Dict[str, Any]) -> int:
        """
        新しい画像情報をデータベースに追加します。テーブルは自動的に判断されます。

        Args:
            info (Dict[str, Any]): 画像情報を含む辞書

        Returns:
            int: 挿入された行のID

        Raises:
            ValueError: 情報が既知のテーブル構造に一致しない場合
            sqlite3.Error: データベース操作中にエラーが発生した場合
        """
        if 'uuid' in info:
            table = 'images'
        elif 'image_id' in info:
            table = 'processed_images'
        else:
            raise ValueError("Unable to determine the appropriate table. Make sure 'uuid' or 'image_id' is provided.")

        columns = ', '.join(info.keys())
        placeholders = ', '.join('?' * len(info))
        sql = f'INSERT INTO {table} ({columns}) VALUES ({placeholders})'

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, tuple(info.values()))
                return cursor.lastrowid

        except sqlite3.Error as e:
            raise sqlite3.Error(f"データベースエラー: {e}")

    def fetch_image_metadata(self, image_id: int) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID

        Returns:
            Optional[Dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            Exception: データベース操作中にエラーが発生した場合
        """
        query = """
        SELECT id, uuid, stored_image_path, width, height, format, mode, has_alpha, filename, extension, created_at, updated_at
        FROM images
        WHERE id = ?
        """

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, (image_id,))
                row = cursor.fetchone()

                return dict(row) if row else None

        except sqlite3.Error as e:
            raise Exception(f"データベースエラー: {e}")

    def fetch_processed_image_metadata_list(self, image_id: int) -> List[Dict[str, Any]]:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            image_id (int): 元画像のID

        Returns:
            List[Dict[str, Any]]: 処理済み画像のメタデータのリスト。
                                  画像が見つからない場合は空のリストを返します。

        Raises:
            Exception: データベース操作中にエラーが発生した場合
        """
        query = """
        SELECT id, image_id, stored_image_path, width, height,
               format, mode, has_alpha, filename, created_at
        FROM processed_images
        WHERE image_id = ?
        """

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, (image_id,))
                rows = cursor.fetchall()

                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            raise Exception(f"データベースエラー: {e}")

    def fetch_image_annotations(self, image_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        指定された画像IDに関連するすべてのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID

        Returns:
            Dict[str, List[Dict[str, Any]]]: タグ、キャプション、スコアを含む辞書。

        Raises:
            Exception: データベース操作中にエラーが発生した場合
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                annotations = {
                    'captions': [],
                    'scores': []
                }

                # キャプションの取得
                cursor.execute("""
                    SELECT c.caption, COALESCE(m.name, 'default') as model
                    FROM captions c
                    LEFT JOIN models m ON c.model_id = m.id
                    WHERE c.image_id = ?
                """, (image_id,))
                annotations['captions'] = [dict(row) for row in cursor.fetchall()]

                # タグの取得
                cursor.execute("""
                    SELECT t.tag, COALESCE(m.name, 'default') as model
                    FROM tags t
                    LEFT JOIN models m ON t.model_id = m.id
                    WHERE t.image_id = ?
                """, (image_id,))
                annotations['tags'] = [dict(row) for row in cursor.fetchall()]

                # スコアの取得
                cursor.execute("""
                    SELECT s.score, COALESCE(m.name, 'default') as model
                    FROM scores s
                    LEFT JOIN models m ON s.model_id = m.id
                    WHERE s.image_id = ?
                """, (image_id,))
                annotations['scores'] = [dict(row) for row in cursor.fetchall()]

                return annotations
        except sqlite3.Error as e:
            raise Exception(f"データベースエラー: {e}")

    def save_annotations(self, image_id: int, annotations: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        画像のアノテーション（キャプション、タグ、スコア）を保存します。

        Args:
            image_id (int): 画像ID
            annotations (Dict[str, List[Dict[str, Any]]]): アノテーションデータ
                形式: {
                    'captions': [{'caption': str, 'model': str}, ...],
                    'tags': [{'tag': str, 'model': str}, ...],
                    'scores': [{'score': float, 'model': str}, ...]
                }

        Raises:
            Exception: データベース操作中にエラーが発生した場合
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if 'captions' in annotations:
                    self._save_captions(conn, image_id, annotations['captions'])

                if 'tags' in annotations:
                    self._save_tags(conn, image_id, annotations['tags'])

                if 'scores' in annotations:
                    self._save_scores(conn, image_id, annotations['scores'])
        except sqlite3.Error as e:
            raise Exception(f"Database error: {e}")

    def _save_captions(self, conn: sqlite3.Connection, image_id: int, captions: List[Dict[str, Any]]) -> None:
        cursor = conn.cursor()
        query = "INSERT INTO captions (image_id, model_id, caption) VALUES (?, (SELECT id FROM models WHERE name = ?), ?)"

        caption_data = [(image_id, caption.get('model', 'default'), caption['caption']) for caption in captions]
        cursor.executemany(query, caption_data)

    def _save_tags(self, conn: sqlite3.Connection, image_id: int, tags: List[str] | List[Dict[str, Any]]) -> None:
        cursor = conn.cursor()
        query = "INSERT INTO tags (image_id, model_id, tag) VALUES (?, (SELECT id FROM models WHERE name = ?), ?)"

        tag_data = [(image_id, tag.get('model', 'default'), tag['tag']) for tag in tags]
        cursor.executemany(query, tag_data)

    def _save_scores(self, conn: sqlite3.Connection, image_id: int, scores: List[Dict[str, Any]]) -> None:
        cursor = conn.cursor()
        query = "INSERT INTO scores (image_id, model_id, score) VALUES (?, (SELECT id FROM models WHERE name = ?), ?)"

        score_data = [(image_id, score.get('model', 'default'), score['score']) for score in scores]
        cursor.executemany(query, score_data)
