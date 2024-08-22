import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import logging
from pathlib import Path
import uuid

from module.file_sys import FileSystemManager

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
                    color_space TEXT,
                    icc_profile TEXT,
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
                    color_space TEXT,
                    icc_profile TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
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
                必須キー: 'stored_image_path', 'width', 'height', 'format', 'mode', 'has_alpha', 'filename', 'created_at', 'color_space', 'icc_profile'
                オプションキー編集前: 'uuid', 'extension', 'updated_at'
                オプションキー編集後: 'image_id'

        Returns:
            int: 挿入された画像のID。

        Raises:
            ValueError: 必須情報が不足している場合。
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        required_keys = ['stored_image_path', 'width', 'height', 'format', 'mode', 'has_alpha', 'filename', 'color_space', 'icc_profile']
        if not all(key in info for key in required_keys):
            missing_keys = [key for key in required_keys if key not in info]
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")
        original = """
        INSERT INTO images (uuid, stored_image_path, width, height, format, mode, has_alpha, filename, extension, color_space, icc_profile, created_at, updated_at)
        VALUES (:uuid, :stored_image_path, :width, :height, :format, :mode, :has_alpha, :filename, :extension, :color_space, :icc_profile, :created_at, :updated_at)
        """
        processed = """
        INSERT INTO processed_images (image_id, stored_image_path, width, height, format, mode, has_alpha, filename, color_space, icc_profile, created_at)
        VALUES (:image_id, :stored_image_path, :width, :height, :format, :mode, :has_alpha, :filename, :color_space, :icc_profile, :created_at)
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
            raise sqlite3.Error(f"画像情報の追加中にエラーが発生しました: {e}")

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
        # TODO: scoreはまた今度
        # if 'scores' not in annotations:
        #     raise ValueError("処理済みアノテーションには 'scores' が含まれている必要があります。")

        try:
            self._save_tags(image_id, annotations.get('tags', ""), existing=False)
            self._save_captions(image_id, annotations.get('captions', []), existing=False)
            # self._save_scores(image_id, annotations['scores'])
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
                    message = "モデル情報が必要です。"
                    logging.error(message)
                    raise ValueError(message)
                model_id = self._get_model_id(tag['model'])
                logging.error("model_id: %s", model_id)
            data.append((image_id, tag['tag'], model_id, existing))
        query = "INSERT INTO tags (image_id, tag, model_id, existing) VALUES (?, ?, ?, ?)"
        try:
            self.db_manager.executemany(query, data)
            logging.info("save_tags: %s", image_id)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"ImageRepository._save_tags: {str(e)}")

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
            logging.info("captions: %s", image_id)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"ImageRepository._save_captions:, {str(e)}")

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
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        db_path = Path("Image_database") / "image_database.db"
        self.db_manager = SQLiteManager(db_path)
        self.repository = ImageRepository(self.db_manager)
        self.db_manager.create_tables()
        self.repository = self.repository
        self.logger.info("データベーステーブルが初期化されました。")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, _):
        self.db_manager.close()
        if exc_type:
            self.logger.error("ImageDatabaseManager使用中にエラー: %s", exc_value)
        return False  # 例外を伝播させる

    def register_original_image(self, image_path: Path, fsm: FileSystemManager) -> Optional[int]:  # fsm を引数に追加
        """オリジナル画像を保存し、メタデータをデータベースに登録

        Args:
            image_path (Path): 画像パス
            fsm (FileSystemManager): FileSystemManager のインスタンス

        Returns:
            Optional[int]: 登録成功時は image_id, 失敗時は None
        """
        try:
            original_metadata = fsm.get_image_info(image_path)
            db_stored_original_path = fsm.save_original_image(image_path)
            image_id, _ = self.save_original_metadata(db_stored_original_path, original_metadata)
            return image_id
        except Exception as e:
            self.logger.error(f"オリジナル画像の登録中にエラーが発生しました: {e}")
            return None

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
            if not annotations.get("model_id"):
                self.repository.save_existing_annotations(image_id, annotations)
            else:
                self.repository.save_processed_annotations(image_id, annotations)

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

    def get_models(self) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """
        データベースに登録されているモデルの情報を取得します。

        Returns:
            Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]: (vision_models, score_models) のタプル。
            vision_models: {model_id: {'name': model_name, 'provider': provider}},
            score_models: {model_id: {'name': model_name, 'provider': provider}}
        """
        query = "SELECT id, name, provider, type FROM models"
        try:
            models = self.db_manager.fetch_all(query)
            vision_models = {}
            score_models = {}
            for model in models:
                model_id = model['id']
                name = model['name']
                provider = model['provider']
                model_type = model['type']
                if model_type == 'vision':
                    vision_models[model_id] = {'name': name, 'provider': provider}
                elif model_type == 'score':
                    score_models[model_id] = {'name': name, 'provider': provider}
            return vision_models, score_models
        except sqlite3.Error as e:
            self.logger.error(f"モデルの取得中にエラーが発生しました: {e}")
            raise

    def get_images_by_filter(self, tag_filter: str, caption_filter: str, min_resolution: int) -> List[Dict[str, Any]]:
        """
        指定されたフィルタ条件に基づいて画像を取得します。

        Args:
            tag_filter (str): タグによるフィルタ文字列
            caption_filter (str): キャプションによるフィルタ文字列
            min_resolution (int): 最小解像度（ピクセル単位）

        Returns:
            List[Dict[str, Any]]: フィルタ条件に合致する画像のリスト
        """
        query = """
        SELECT DISTINCT i.id, i.stored_image_path, i.width, i.height
        FROM images i
        LEFT JOIN tags t ON i.id = t.image_id
        LEFT JOIN captions c ON i.id = c.image_id
        WHERE 1=1
        """
        params = []

        if tag_filter:
            tags = [tag.strip() for tag in tag_filter.split(',')]
            query += " AND t.tag IN ({})".format(','.join(['?'] * len(tags)))
            params.extend(tags)

        if caption_filter:
            query += " AND c.caption LIKE ?"
            params.append(f"%{caption_filter}%")

        query += " AND (i.width >= ? OR i.height >= ?)"
        params.extend([min_resolution, min_resolution])

        try:
            with self.db_manager.transaction():
                rows = self.db_manager.fetch_all(query, tuple(params))

            results = []
            for row in rows:
                results.append({
                    'id': row['id'],
                    'path': Path(row['stored_image_path']),
                    'width': row['width'],
                    'height': row['height']
                })

            return results

        except Exception as e:
            self.logger.error(f"Error in get_images_by_filter: {e}")
            return []

    def get_total_image_count(self) -> int:
        """
        データベース内の総画像数を取得します。

        Returns:
            int: 総画像数
        """
        try:
            query = "SELECT COUNT(*) FROM images"
            result = self.db_manager.fetch_one(query)
            return result[0] if result else 0
        except Exception as e:
            self.logger.error(f"総画像数の取得中にエラーが発生しました: {e}")
            return 0

    def get_id_by_image_name(self, image_name: str) -> Optional[int]:
        """画像名からimage_idを取得

        Args:
            image_na,e (str): 画像名

        Returns:
            int: image_id
        """
        try:
            query = """
            SELECT id FROM images
            WHERE filename = ?
            """
            result = self.db_manager.fetch_one(query, (image_name,))
            return result.get("id") if result else None
        except Exception as e:
            self.logger.error(f"画像IDの取得中にエラーが発生しました: {e}")
            return None
