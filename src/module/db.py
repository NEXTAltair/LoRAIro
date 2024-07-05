import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import logging
from pathlib import Path
import uuid


class SQLiteManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection = None
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def connect(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = self.dict_factory
        return self._connection

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def get_connection(self):
        conn = self.connect()  # 明示的に接続を開く
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor

    def executemany(self, query: str, params: List[Tuple[Any, ...]]) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            conn.commit()
            return cursor

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Tuple[Any, ...]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    @contextmanager
    def transaction(self):
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def create_tables(self):
        with self.get_connection() as conn:
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
                    existing BOOLEAN NOT NULL DEFAULT 0,
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
                    existing BOOLEAN NOT NULL DEFAULT 0,
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

    def register_models(self, models: List[Dict[str, str]]):
        query = "INSERT OR IGNORE INTO models (name, type) VALUES (?, ?)"
        try:
            with self.transaction() as conn:
                conn.executemany(query, [(model['name'], model['type']) for model in models])
        except sqlite3.Error as e:
            self.logger.error(f"モデルの登録中にエラーが発生しました: {e}")
            raise
class ImageRepository:
    """
    画像関連のデータベース操作を担当するクラス。
    このクラスは、画像メタデータの保存、取得、アノテーションの管理などを行います。
    """

    def __init__(self, db_manager: SQLiteManager):
        """
        ImageRepositoryクラスのコンストラクタ。

        Args:
            db_manager (SQLiteManager): データベース接続を管理するオブジェクト。
        """
        self.db_manager = db_manager

    def add_image(self, info: Dict[str, Any]) -> int:
        """
        画像情報をデータベースに追加します。

        Args:
            info (Dict[str, Any]): 画像情報を含む辞書。
                必須キー: 'stored_image_path', 'width', 'height', 'format', 'mode', 'has_alpha', 'filename', 'created_at'
                オプションキー編集前: 'UUID', 'extension', 'updated_at'
                オプションキー編集後: 'image_id'

        Returns:
            int: 挿入された画像のID。

        Raises:
            ValueError: 必須情報が不足している場合。
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        original = """
        INSERT INTO images (uuid, stored_image_path, width, height, format, mode, has_alpha, filename, extension, created_at, updated_at)
        VALUES (:uuid, :stored_image_path, :width, :height, :format, :mode, :has_alpha, :filename, :extension, :created_at, :updated_at)
        """
        processed = """
        INSERT INTO processed_images (image_id, stored_image_path, width, height, format, mode, has_alpha, filename, created_at)
        VALUES (:image_id, :stored_image_path, :width, :height, :format, :mode, :has_alpha, :filename, :created_at)
        """

        current_time = datetime.now().isoformat()
        info['created_at'] = current_time
        #info Dict に uuid が含まれているかで 編集前､編集後を判定してSQL文を変更
        if 'uuid' in info:
            info['updated_at'] = current_time
            query = original
        else:
            query = processed
        try:
            cursor = self.db_manager.execute(query, info)
            return cursor.lastrowid
        except sqlite3.Error as e:
            raise sqlite3.Error(f"画像情動の追加中にエラーが発生しました: {e}")

    def get_image_metadata(self, image_id: int) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[Dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        query = "SELECT * FROM images WHERE id = ?"
        try:
            metadata = self.db_manager.fetch_one(query, (image_id,))
            return metadata
        except sqlite3.Error as e:
            raise sqlite3.Error(f"画像メタデータの取得中にエラーが発生しました: {e}")

    def save_existing_annotations(self, image_id: int, annotations: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        既存の画像アノテーション（タグ、キャプション）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (Dict[str, List[Dict[str, Any]]]): アノテーションデータ。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定されたimage_id {image_id} は存在しません。")
        try:
            self._save_tags(image_id, annotations.get('tags', []), existing=True)
            self._save_captions(image_id, annotations.get('captions', []), existing=True)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"既存のアノテーションの保存中にエラーが発生しました: {e}")

    def save_processed_annotations(self, image_id: int, annotations: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        処理済みの画像アノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (Dict[str, List[Dict[str, Any]]]): アノテーションデータ。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
            ValueError: 必要なデータが不足している場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定されたimage_id {image_id} は存在しません。")
        if 'scores' not in annotations:
            raise ValueError("処理済みアノテーションには 'scores' が含まれている必要があります。")

        try:
            self._save_tags(image_id, annotations.get('tags', ""), existing=False)
            self._save_captions(image_id, annotations.get('captions', []), existing=False)
            self._save_scores(image_id, annotations['scores'])
        except sqlite3.Error as e:
            raise sqlite3.Error(f"処理済みアノテーションの保存中にエラーが発生しました: {e}")

    def _save_tags(self, image_id: int, tags: List[Dict[str, str]], existing: bool) -> None:
        """タグを保存する内部メソッド"""
        data = []
        for tag in tags:
            if existing:
                model_id = None
            else:
                if 'model' not in tag:
                    raise ValueError("モデル情報が必要です。")
                model_id = self._get_model_id(tag['model'])
                logging.error(f"model_id: {model_id}")
            data.append((image_id, tag['tag'], model_id, existing))
        query = "INSERT INTO tags (image_id, tag, model_id, existing) VALUES (?, ?, ?, ?)"
        try:
            self.db_manager.executemany(query, data)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"_save_tagsメソッド内のクエリエラー: {e}")

    def _save_captions(self, image_id: int, captions: List[Dict[str, str]], existing: bool) -> None:
        """キャプションを保存する内部メソッド"""
        data = []
        for caption in captions:
            if existing:
                model_id = None
            else:
                if 'model' not in caption:
                    raise ValueError("モデル情報が必要です。")
                model_id = self._get_model_id(caption['model'])
            data.append((image_id, caption['caption'], model_id, existing))
        query = "INSERT INTO captions (image_id, caption, model_id, existing) VALUES (?, ?, ?, ?)"
        try:
            self.db_manager.executemany(query, data)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"_save_captionsメソッド内のクエリエラー: {e}")

    def _save_scores(self, image_id: int, scores: List[Dict[str, float]]) -> None:
        """スコアを保存する内部メソッド"""
        query = "INSERT INTO scores (image_id, score, model_id) VALUES (?, ?, ?)"
        data = []
        for score in scores:
            if 'model' not in score:
                raise ValueError("モデル情報が必要です。")
            model_id = self._get_model_id(score['model'])
            data.append((image_id, score['score'], model_id))
        try:
            self.db_manager.executemany(query, data)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"_save_scoresメソッド内のクエリエラー: {e}")

    def _get_model_id(self, model_name: str) -> int:
        """モデル名からモデルIDを取得するメソッド"""
        query = "SELECT id FROM models WHERE name = ?"
        try:
            cursor = self.db_manager.execute(query, (model_name,))
            row = cursor.fetchone()
            if row:
                return row['id']
            else:
                raise ValueError(f"モデル名 '{model_name}' が見つかりません。")
        except sqlite3.Error as e:
            raise sqlite3.Error(f"_get_model_idメソッド内のクエリエラー: {e}")

    def _image_exists(self, image_id: int) -> bool:
        """
        指定された画像IDが存在するかを確認します。

        Args:
            image_id (int): 確認する画像のID。

        Returns:
            bool: 画像が存在する場合はTrue、存在しない場合はFalse。
        """
        query = "SELECT 1 FROM images WHERE id = ?"
        result = self.db_manager.fetch_one(query, (image_id,))
        return result is not None

    def get_image_annotations(self, image_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            Dict[str, List[Dict[str, Any]]]: アノテーションデータを含む辞書。
            形式: {
                'tags': [{'tag': str, 'model': str}, ...],
                'captions': [{'caption': str, 'model': str}, ...],
                'scores': [{'score': float, 'model': str}, ...]
            }

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        try:
            cursor = self.db_manager.execute("SELECT id FROM images WHERE id = ?", (image_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"指定されたimage_id {image_id} は存在しません。")
            annotations = {
                'tags': self._get_tags(image_id),
                'captions': self._get_captions(image_id),
                'scores': self._get_scores(image_id)
            }
            return annotations

        except sqlite3.Error as e:
            logging.error(f"アノテーションの取得中にデータベースエラーが発生しました: {e}")
            raise sqlite3.Error(f"アノテーションの取得中にエラーが発生しました: {e}")

    def _get_tags(self, image_id: int) -> List[Dict[str, str]]:
        """タグを取得する内部メソッド"""
        query = "SELECT tag, model_id FROM tags WHERE image_id = ?"
        return self.db_manager.fetch_all(query, (image_id,))

    def _get_captions(self, image_id: int) -> List[Dict[str, str]]:
        """キャプションを取得する内部メソッド"""
        query = "SELECT caption, model_id FROM captions WHERE image_id = ?"
        return self.db_manager.fetch_all(query, (image_id,))

    def _get_scores(self, image_id: int) -> List[Dict[str, Any]]:
        """スコアを取得する内部メソッド"""
        query = "SELECT score, model_id FROM scores WHERE image_id = ?"
        return self.db_manager.fetch_all(query, (image_id,))

    def get_processed_images(self, original_image_id: int) -> List[Dict[str, Any]]:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            original_image_id (int): 元画像のID。

        Returns:
            Dict[str, Any]]: 処理済み画像のメタデータのリスト。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        query = """
        SELECT * FROM processed_images
        WHERE image_id = ?
        """
        try:
            metadata = self.db_manager.fetch_all(query, (original_image_id,))
            return metadata
        except sqlite3.Error as e:
            raise sqlite3.Error(f"処理済み画像の取得中にエラーが発生しました: {e}")
class ImageDatabaseManager:
    """
    画像データベース操作の高レベルインターフェースを提供するクラス。
    このクラスは、ImageRepositoryを使用して、画像メタデータとアノテーションの
    保存、取得、更新などの操作を行います。
    """
    def __init__(self, db_path: Path, models: Dict[str, str]):
        self.db_manager = SQLiteManager(db_path)
        self.repository = ImageRepository(self.db_manager)
        self.db_manager.create_tables()
        self.db_manager.register_models(models)
        self.logger = logging.getLogger(__name__)
        self.logger.info("データベーステーブルが初期化されました。")

    def save_original_metadata(self, stored_image_path: Path, info: Dict[str, Any]) -> Tuple[int, str]:
        """
        元の画像のメタデータを保存します。

        Args:
            stored_image_path (Path): 保存された画像のパス。
            info (Dict[str, Any]): 画像のメタデータ。

        Returns:
            Tuple[int, str]: 保存された画像のID、生成されたUUID。

        Raises:
            ValueError: 必要な情報が不足している場合。
            Exception: データベース操作に失敗した場合。
        """
        try:
            # UUIDを生成
            image_uuid = str(uuid.uuid4())

            # infoディクショナリにUUIDと保存パスを追加
            info['uuid'] = image_uuid
            info['stored_image_path'] = str(stored_image_path)

            # リポジトリを使用して画像メタデータを保存
            image_id = self.repository.add_image(info)

            self.logger.info(f"元画像のメタデータをDBに保存しました: ID {image_id}, UUID {image_uuid}")
            return image_id, image_uuid

        except Exception as e:
            self.logger.error(f"元画像のメタデータ登録中に予期せぬエラーが発生しました: {e}")
            raise

    def save_processed_metadata(self, image_id: int, processed_path: Path, info: Dict[str, Any]) -> int:
        """
        処理済み画像のメタデータを保存します。

        Args:
            image_id (int): 元画像のID。
            processed_path (Path): 処理済み画像の保存パス。
            info (Dict[str, Any]): 処理済み画像のメタデータ。

        Returns:
            int: 保存された処理済み画像のID。

        Raises:
            ValueError: 必要な情報が不足している場合。
            Exception: データベース操作に失敗した場合。
        """
        try:
            # infoディクショナリに元画像IDと保存パスを追加
            info['image_id'] = image_id
            info['stored_image_path'] = str(processed_path)

            # リポジトリを使用して処理済み画像メタデータを保存
            processed_image_id = self.repository.add_image(info)

            self.logger.info(f"処理済み画像メタデータをDBに保存しました: ID {processed_image_id}, 元画像ID {image_id}")
            return processed_image_id

        except Exception as e:
            self.logger.error(f"処理済み画像メタデータの保存中にエラーが発生しました: {e}")
            raise

    def save_annotations(self, image_id: int, annotations: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        渡されたano_dict の トップレベルのキーによってアノテーションの種類を判定し､保存処理を行う

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (Dict[str, List[Dict[str, Any]]]): アノテーションデータ。

        Raises:
            Exception: アノテーションの保存に失敗した場合。
        """
        try:
            # annotations の中にmodel が含まれているかでアノテーションタイプを判定
            if 'scores' in annotations:
                self.repository.save_processed_annotations(image_id, annotations)
            else:
                self.repository.save_existing_annotations(image_id, annotations)

            self.logger.info(f"画像 ID {image_id} のアノテーションを保存しました")
        except Exception as e:
            self.logger.error(f"アノテーションの保存中にエラーが発生しました: {e}")
            raise

    def get_image_metadata(self, image_id: int) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[Dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            Exception: メタデータの取得に失敗した場合。
        """
        try:
            metadata = self.repository.get_image_metadata(image_id)
            if metadata is None:
                self.logger.info(f"ID {image_id} の画像が見つかりません。")
            return metadata
        except Exception as e:
            self.logger.error(f"画像メタデータ取得中にエラーが発生しました: {e}")
            raise

    def get_processed_metadata(self, original_image_id: int) -> List[Dict[str, Any]]:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            original_image_id (int): 元画像のID。

        Returns:
            List[Dict[str, Any]]: 処理済み画像のメタデータのリスト。

        Raises:
            Exception: メタデータの取得に失敗した場合。
        """
        try:
            processed_images = self.repository.get_processed_images(original_image_id)
            if not processed_images:
                self.logger.info(f"ID {original_image_id} の元画像に関連する処理済み画像が見つかりません。")
            return processed_images
        except Exception as e:
            self.logger.error(f"処理済み画像メタデータ取得中にエラーが発生しました: {e}")
            raise

    def get_image_annotations(self, image_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            Dict[str, List[Dict[str, Any]]]: アノテーションデータを含む辞書。

        Raises:
            Exception: アノテーションの取得に失敗した場合。
        """
        try:
            annotations = self.repository.get_image_annotations(image_id)
            if not any(annotations.values()):
                self.logger.info(f"ID {image_id} の画像にアノテーションが見つかりません。")
            return annotations
        except Exception as e:
            self.logger.error(f"画像アノテーション取得中にエラーが発生しました: {e}")
            raise

def initialize_database(db_path: Path, models: List[Dict[str, str]]) -> ImageDatabaseManager:
    return ImageDatabaseManager(db_path, models)