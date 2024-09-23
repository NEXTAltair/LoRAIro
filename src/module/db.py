import sqlite3
import threading
import uuid
import imagehash
from PIL import Image

from contextlib import contextmanager
from typing import Any, Union, Optional
from datetime import datetime
from module.log import get_logger
from pathlib import Path

from module.file_sys import FileSystemManager

def calculate_phash(image_path: str) -> str:
    with Image.open(image_path) as img:
        return str(imagehash.phash(img))

class SQLiteManager:
    def __init__(self, img_db_path: Path, tag_db_path: Path):
        self.logger = get_logger("SQLiteManager")
        self.img_db_path = img_db_path
        self.tag_db_path = tag_db_path
        self._connection = None
        self._local = threading.local()

    @staticmethod
    def dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def connect(self):
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.img_db_path, check_same_thread=False)
            self._local.connection.execute(f"ATTACH DATABASE '{self.tag_db_path}' AS tag_db")
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.row_factory = self.dict_factory
        return self._local.connection

    def close(self):
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None

    @contextmanager
    def get_connection(self):
        conn = self.connect()
        try:
            yield conn
        except Exception as e:
            self.logger.error(f"Database operation failed: {e}")
            conn.rollback()
            raise
        else:
            conn.commit()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> Optional[tuple[Any, ...]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def create_tables(self):
        with self.get_connection() as conn:
            conn.executescript('''
                -- images テーブル：オリジナル画像の情報を格納
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    uuid TEXT UNIQUE NOT NULL,
                    phash TEXT,
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (uuid, phash)
                );

                -- processed_images テーブル：処理済み画像の情報を格納
                CREATE TABLE IF NOT EXISTS processed_images (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER NOT NULL,
                    stored_image_path TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    mode TEXT NULL,
                    has_alpha BOOLEAN NOT NULL,
                    filename TEXT NULL,
                    color_space TEXT,
                    icc_profile TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    UNIQUE (image_id, width, height, filename)
                );

                -- models テーブル：モデル情報を格納
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    provider TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- tags テーブル：画像に関連付けられたタグを格納
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    tag TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
                    UNIQUE (image_id, tag, model_id)
                );

                -- captions テーブル：画像に関連付けられたキャプションを格納
                CREATE TABLE IF NOT EXISTS captions (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    caption TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
                    UNIQUE (image_id, caption, model_id)
                );

                -- scores テーブル：画像に関連付けられたスコアを格納
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    score FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
                    UNIQUE (image_id, score, model_id)
                );

            -- インデックスの作成
            CREATE INDEX IF NOT EXISTS idx_images_uuid ON images(uuid);
            CREATE INDEX IF NOT EXISTS idx_processed_images_image_id ON processed_images(image_id);
            CREATE INDEX IF NOT EXISTS idx_tags_image_id ON tags(image_id);
            CREATE INDEX IF NOT EXISTS idx_captions_image_id ON captions(image_id);
            CREATE INDEX IF NOT EXISTS idx_scores_image_id ON scores(image_id);
            ''')

    def insert_models(self) -> None:
        """
        モデル情報の初期設定がされてない場合データベースに追加

        Args:
            model_name (str): モデルの名前。
            model_type (str): モデルのタイプ。
            provider (str): モデルのプロバイダ。
        """
        query = """
        INSERT OR IGNORE INTO models (name, type, provider) VALUES (?, ?, ?)
        """
        models = [
            ('gpt-4o', 'vision', 'OpenAI'),
            ('gpt-4-turbo', 'vision', 'OpenAI'),
            ('laion', 'score', ''),
            ('cafe', 'score', ''),
            ('gpt-4o-mini', 'vision', 'OpenAI'),
            ('gemini-1.5-pro-exp-0801', 'vision', 'Google'),
            ('gemini-1.5-pro-preview-0409', 'vision', 'Google'),
            ('gemini-1.0-pro-vision', 'vision', 'Google'),
            ('claude-3-5-sonnet-20240620', 'vision', 'Anthropic'),
            ('claude-3-opus-20240229', 'vision', 'Anthropic'),
            ('claude-3-sonnet-20240229', 'vision', 'Anthropic'),
            ('claude-3-haiku-20240307', 'vision', 'Anthropic'),
            ('RealESRGAN_x4plus', 'upscaler', 'xinntao')
        ]
        for model in models:
            self.execute(query, model)

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
        self.logger = get_logger("ImageRepository")
        self.db_manager = db_manager

    def add_original_image(self, info: dict[str, Any]) -> int:
        """
        オリジナル画像のメタデータを images テーブルに追加します。

        Args:
            info (dict[str, Any]): 画像情報を含む辞書。

        Returns:
            int: 挿入された画像のID。

        Raises:
            ValueError: 必須情報が不足している場合。
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """

        # pHashの計算と重複チェック
        try:
            phash = calculate_phash(Path(info['stored_image_path']))
            info['phash'] = phash
            duplicate = self.find_duplicate_image(phash)
            if duplicate:
                self.logger.warning(f"画像が既に存在します: ID {duplicate}")
                return duplicate
        except Exception as e:
            self.logger.error(f"pHashの処理中にエラーが発生しました: {e}")
            raise

        required_keys = ['uuid', 'stored_image_path', 'width', 'height', 'format', 'mode',
                         'has_alpha', 'filename', 'extension', 'color_space', 'icc_profile', 'phash']
        if not all(key in info for key in required_keys):
            missing_keys = [key for key in required_keys if key not in info]
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        query = """
        INSERT INTO images (uuid, stored_image_path, width, height, format, mode, has_alpha,
                            filename, extension, color_space, icc_profile, phash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            created_at = datetime.now().isoformat()
            updated_at = created_at
            params = (
                info['uuid'],
                info['stored_image_path'],
                info['width'],
                info['height'],
                info['format'],
                info['mode'],
                info['has_alpha'],
                info['filename'],
                info['extension'],
                info['color_space'],
                info['icc_profile'],
                info['phash'],
                created_at,
                updated_at
            )
            cursor = self.db_manager.execute(query, params)
            self.logger.info(f"オリジナル画像をDBに追加しました: UUID={info['uuid']}")
            return cursor.lastrowid
        except sqlite3.Error as e:
            self.logger.error(f"オリジナル画像の追加中にエラーが発生しました: {e}")
            raise

    def add_processed_image(self, info: dict[str, Any]) -> int:
        """
        処理済み画像のメタデータを images テーブルに追加します。

        Args:
            info (dict[str, Any]): 処理済み画像情報を含む辞書。

        Returns:
            int: 挿入された処理済み画像のID。

        Raises:
            ValueError: 必須情報が不足している場合。
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        required_keys = ['stored_image_path', 'width', 'height', 'format', 'mode',
                         'has_alpha', 'filename', 'color_space', 'icc_profile', 'image_id']
        if not all(key in info for key in required_keys):
            missing_keys = [key for key in required_keys if key not in info]
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        query = """
        INSERT INTO processed_images (image_id, stored_image_path, width, height, mode, has_alpha,
                                filename, color_space, icc_profile, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            created_at = datetime.now().isoformat()
            updated_at = created_at
            params = (
                info['image_id'],
                info['stored_image_path'],
                info['width'],
                info['height'],
                info['mode'],
                info['has_alpha'],
                info['filename'],
                info['color_space'],
                info['icc_profile'],
                created_at,
                updated_at
            )
            cursor = self.db_manager.execute(query, params)
            self.logger.info(f"処理済み画像をDBに追加しました: 親画像ID={info['image_id']}")
            return cursor.lastrowid
        except sqlite3.Error as e:
            self.logger.error(f"処理済み画像の追加中にエラーが発生しました: {e}")
            raise

    def get_image_metadata(self, image_id: int) -> Optional[dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        query = "SELECT * FROM images WHERE id = ?"
        try:
            metadata = self.db_manager.fetch_one(query, (image_id,))
            return metadata
        except sqlite3.Error as e:
            raise sqlite3.Error(f"画像メタデータの取得中にエラーが発生しました: {e}")

    def save_annotations(self, image_id: int, annotations: dict[str, Union[list[str], float, int]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (dict): アノテーションデータ。
            {
                'tags': list[str],
                'caption': list[str],
                'score': float,
                'model_id': int
            }

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
            ValueError: 必要なデータが不足している場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定されたimage_id {image_id} は存在しません。")

        model_id = annotations.get('model_id', None)

        if model_id is None:
            self.logger.warning("model_idはすべてNoneで保存されます。")

        try:
            self._save_tags(image_id, annotations.get('tags', []), model_id)
            self._save_captions(image_id, annotations.get('captions', []), model_id)
            self._save_score(image_id, annotations.get('score', 0), model_id)
        except sqlite3.Error as e:
            raise sqlite3.Error(f"アノテーションの保存中にエラーが発生しました: {e}")

    def _save_tags(self, image_id: int, tags: list[str], model_id: Optional[int]) -> None:
        """タグを保存する内部メソッド

        Args:
            image_id (int): タグを追加する画像のID。
            tags (list[str]): タグのリスト。
            model_id (Optional[int]): タグ付けに使用されたモデルのID。Noneの場合は既存タグとして扱う。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        if not tags:
            self.logger.info(f"画像ID {image_id} のタグリストが空のため、保存をスキップします。")
            return

        query = "INSERT OR IGNORE INTO tags (image_id, tag, model_id, existing) VALUES (?, ?, ?, ?)"
        data = []

        for tag in tags:
            existing = 1 if model_id is None else 0
            data.append((image_id, tag, model_id, existing))
            self.logger.debug(f"ImageRepository._save_tags: {tag}")

        try:
            self.db_manager.executemany(query, data)
            self.logger.info(f"画像ID {image_id} に {len(data)} 個のタグを保存しました")
        except sqlite3.Error as e:
            self.logger.error(f"タグの保存中にエラーが発生しました: {e}")
            raise

    def _save_captions(self, image_id: int, captions: list[str], model_id: Optional[int]) -> None:
        """キャプションを保存する

        Args:
            image_id (int): キャプションを追加する画像のID。
            captions (list[str]): キャプションのリスト。
            model_id (Optional[int]): キャプションに関連付けられたモデルのID。Noneの場合は既存キャプションとして扱う。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        if not captions:
            self.logger.info(f"画像ID {image_id} のキャプションリストが空のため、保存をスキップします。")
            return

        query = "INSERT OR IGNORE INTO captions (image_id, caption, model_id, existing) VALUES (?, ?, ?, ?)"
        data = []

        for caption in captions:
            existing = 1 if model_id is None else 0
            data.append((image_id, caption, model_id, existing))
            self.logger.debug(f"ImageRepository._save_captions: {caption} ")

        try:
            self.db_manager.executemany(query, data)
            self.logger.info(f"画像ID {image_id} に {len(data)} 個のキャプションを保存しました")
        except sqlite3.Error as e:
            self.logger.error(f"キャプションの保存中にエラーが発生しました: {e}")
            raise

    def _save_score(self, image_id: int, score: float, model_id: int) -> None:
        """スコアを保存

        Args:
            image_id (int): スコアを追加する画像のID。
            score (float): スコアの値。
            model_id (int): スコアに関連付けられたモデルのID。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
            ValueError: 必要なデータが不足している場合。
        """
        if score == 0:
            self.logger.info(f"スコアが0のため、保存をスキップします。")
            return

        query = "INSERT OR IGNORE INTO scores (image_id, score, model_id) VALUES (?, ?, ?)"
        data = (image_id, score, model_id)

        try:
            self.db_manager.execute(query, data)
            self.logger.debug(f"Score saved: image_id={image_id}, score={score}, model_id={model_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to save score: {e}")
            raise

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

    def find_duplicate_image(self, phash: str) -> int:
        """
        指定されたpHashに一致する画像をデータベースから検索しImage IDを返します。

        Args:
            phash (str): 検索するpHash。

        Returns:
            Optional[int]: 重複する画像のメタデータ。見つからない場合はNone。
        """
        query = "SELECT * FROM images WHERE phash = ?"
        try:
            duplicate = self.db_manager.fetch_one(query, (phash,))
            image_id = duplicate['id'] if duplicate else None
            if duplicate:
                self.logger.info(f"重複画像が見つかりました: ID {duplicate['id']}, UUID {duplicate['uuid']}")
            return image_id
        except sqlite3.Error as e:
            self.logger.error(f"重複画像の検索中にエラーが発生しました: {e}")
            return None

    def get_image_annotations(self, image_id: int) -> dict[str, Union[list[dict[str, Any]], float, int]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            dict[str, list[dict[str, Any]]]: アノテーションデータを含む辞書。
            画像が存在しない場合は空の辞書を返します。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        try:
            # 画像の存在確認
            if not self._image_exists(image_id):
                self.logger.warning(f"指定されたimage_id {image_id} の画像が存在しません。")
                return {'tags': [], 'captions': [], 'scores': []}

            # アノテーションの取得
            annotations = {
                'tags': self._get_tags(image_id),
                'captions': self._get_captions(image_id),
                'scores': self._get_scores(image_id)
            }
            return annotations

        except sqlite3.Error as e:
            self.logger.error(f"アノテーションの取得中にデータベースエラーが発生しました: {e}")
            raise
        except Exception as e:
            self.logger.error(f"予期せぬエラーが発生しました: {e}")
            raise

    def _get_tags(self, image_id: int) -> list[dict[str, Any]]:
        """image_idからタグを取得する内部メソッド"""
        query = "SELECT tag, model_id FROM tags WHERE image_id = ?"
        try:
            self.logger.debug(f"タグを取得するimage_id: {image_id}")
            result = self.db_manager.fetch_all(query, (image_id,))
            if not result:
                self.logger.info(f"Image_id: {image_id} にタグは登録されていません。")
            return result
        except sqlite3.Error as e:
            self.logger.error(f"image_id: {image_id} のタグを取得中にデータベースエラーが発生しました: {e}")
            raise

    def _get_captions(self, image_id: int) -> list[dict[str, Any]]:
        """image_idからキャプションを取得する内部メソッド"""
        query = "SELECT caption, model_id FROM captions WHERE image_id = ?"
        try:
            self.logger.debug(f"キャプションを取得するimage_id: {image_id}")
            result = self.db_manager.fetch_all(query, (image_id,))
            if not result:
                self.logger.info(f"Image_id: {image_id} にキャプションは登録されていません。")
            return result
        except sqlite3.Error as e:
            self.logger.error(f"image_id: {image_id} のキャプションを取得中にデータベースエラーが発生しました: {e}")
            raise

    def _get_scores(self, image_id: int) -> list[dict[str, Any]]:
        """image_idからスコアを取得する内部メソッド"""
        query = "SELECT score, model_id FROM scores WHERE image_id = ?"
        try:
            self.logger.debug(f"スコアを取得するimage_id: {image_id}")
            result = self.db_manager.fetch_all(query, (image_id,))
            if not result:
                self.logger.info(f"Image_id: {image_id} にスコアは登録されていません。")
            return result
        except sqlite3.Error as e:
            self.logger.error(f"image_id: {image_id} のスコアを取得中にデータベースエラーが発生しました: {e}")
            raise

    def get_images_by_tag(self, tag: str) -> list[int]:
            """
            指定されたタグを持つ画像のIDリストを取得する

            Args:
                tag (str): 検索するタグ

            Returns:
                list[int]: タグを持つ画像IDのリスト か 空リスト
            """
            query = """
            SELECT DISTINCT i.id
            FROM images i
            JOIN tags t ON i.id = t.image_id
            WHERE t.tag = ?
            """
            rows = self.db_manager.fetch_all(query, [tag])
            if not rows:
                self.logger.info("%s を含む画像はありません", tag)
                return []
            else:
                return [row['id'] for row in rows]

    def get_images_by_caption(self, caption: str) -> list[int]:
        """
        指定されたキャプションを含む画像のIDリストを取得する

        Args:
            caption (str): 検索するキャプション

        Returns:
            list[int]: 加工済み画像IDのリスト か 空リスト
        """
        query = """
        SELECT DISTINCT i.id
        FROM images i
        JOIN captions c ON i.id = c.image_id
        WHERE c.caption LIKE ?
        """
        rows = self.db_manager.fetch_all(query, ['%' + caption + '%'])
        if not rows:
            self.logger.info("'%s' を含むキャプションを持つ画像はありません", caption)
            return []
        else:
            return [row['id'] for row in rows]

    def get_processed_image(self, image_id: int) -> list[dict[str, Any]]:
        """
        image_idから関連する全ての処理済み画像のメタデータを取得します。

        Args:
            image_id (int): 元画像のID。

        Returns:
            dict[str, Any]]: 処理済み画像のメタデータのリスト。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        query = """
        SELECT * FROM processed_images
        WHERE image_id = ?
        """
        try:
            metadata = self.db_manager.fetch_all(query, (image_id,))
            self.logger.debug("ID %s の処理済み画像メタデータを取得しました: %s", image_id, metadata)
            return metadata
        except sqlite3.Error as e:
            raise sqlite3.Error(f"処理済み画像の取得中にエラーが発生しました: {e}")

    def get_total_image_count(self) -> int:
        try:
            query = "SELECT COUNT(*) FROM images"
            result = self.db_manager.fetch_one(query)
            return result['COUNT(*)'] if result else 0
        except Exception as e:
            self.logger.error(f"総画像数の取得中にエラーが発生しました: {e}")
            return 0

    def get_image_id_by_name(self, image_name: str) -> Optional[int]:
        """
        オリジナル画像の重複チェック用 画像名からimage_idを取得

        Args:
            image_name (str): 画像名

        Returns:
            Optional[int]: image_id。画像が見つからない場合はNone。
        """
        query = "SELECT id FROM images WHERE filename = ?"
        try:
            result = self.db_manager.fetch_one(query, (image_name,))
            if result:
                image_id = result['id']
                self.logger.info(f"画像名 {image_name} のimage_id {image_id} を取得しました")
                return image_id
            self.logger.info(f"画像名 {image_name} のimage_idを取得できませんでした")
            return None
        except Exception as e:
            self.logger.error(f"画像IDの取得中にエラーが発生しました: {e}")
            return None

    def update_image_metadata(self, image_id: int, updated_info: dict[str, Any]) -> None:
        """
        指定された画像IDのメタデータを更新します。

        Args:
            image_id (int): 更新する画像のID。
            updated_info (dict[str, Any]): 更新するメタデータの辞書。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        if not updated_info:
            self.logger.warning("更新する情報が提供されていません。")
            return
        fields = ", ".join(f"{key} = ?" for key in updated_info.keys())
        values = list(updated_info.values())
        query = f"UPDATE images SET {fields}, updated_at = ? WHERE id = ?"
        values.append(datetime.now().isoformat())  # updated_atを追加
        values.append(image_id)  # image_idを追加
        try:
            self.db_manager.execute(query, tuple(values))
            self.logger.info(f"画像ID {image_id} のメタデータを更新しました。")
        except sqlite3.Error as e:
            self.logger.error(f"画像メタデータの更新中にエラーが発生しました: {e}")
            raise

    def delete_image(self, image_id: int) -> None:
        """
        指定された画像IDの画像と関連するデータを削除します。

        Args:
            image_id (int): 削除する画像のID。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        query = "DELETE FROM images WHERE id = ?"
        try:
            self.db_manager.execute(query, (image_id,))
            self.logger.info(f"画像ID {image_id} と関連するデータを削除しました。")
        except sqlite3.Error as e:
            self.logger.error(f"画像の削除中にエラーが発生しました: {e}")
            raise

class ImageDatabaseManager:
    """
    画像データベース操作の高レベルインターフェースを提供するクラス。
    このクラスは、ImageRepositoryを使用して、画像メタデータとアノテーションの
    保存、取得、更新などの操作を行います。
    """
    def __init__(self):
        self.logger = get_logger("ImageDatabaseManager")
        img_db_path = Path("Image_database") / "image_database.db"
        tag_db_path = Path("src") / "module" / "genai-tag-db-tools" / "tags_v3.db"
        self.db_manager = SQLiteManager(img_db_path, tag_db_path)
        self.repository = ImageRepository(self.db_manager)
        self.db_manager.create_tables()
        self.db_manager.insert_models()
        self.logger.debug("初期化")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, _):
        self.db_manager.close()
        if exc_type:
            self.logger.error("ImageDatabaseManager使用中にエラー: %s", exc_value)
        return False  # 例外を伝播させる

    def register_original_image(self, image_path: Path, fsm: FileSystemManager) -> Optional[tuple]:
        """オリジナル画像を保存し、メタデータをデータベースに登録

        Args:
            image_path (Path): 画像パス
            fsm (FileSystemManager): FileSystemManager のインスタンス

        Returns:
            Optional[tuple]: 登録成功時は (image_id, original_metadata)、失敗時は None
        """
        try:
            original_image_metadata = fsm.get_image_info(image_path)
            db_stored_original_path = fsm.save_original_image(image_path)
            # UUIDの生成
            image_uuid = str(uuid.uuid4())
            # メタデータにUUIDと保存パスを追加
            original_image_metadata.update({
                'uuid': image_uuid,
                'stored_image_path': str(db_stored_original_path)
            })
            # データベースに挿入
            image_id = self.repository.add_original_image(original_image_metadata)
            return image_id, original_image_metadata
        except Exception as e:
            self.logger.error(f"オリジナル画像の登録中にエラーが発生しました: {e}")
            return None


    def register_processed_image(self, image_id: int, processed_path: Path, info: dict[str, Any]) -> Optional[int]:
        """
        処理済み画像を保存し、メタデータをデータベースに登録します。

        Args:
            image_id (int): 元画像のID。
            processed_path (Path): 処理済み画像の保存パス。
            info (dict[str, Any]): 処理済み画像のメタデータ。

        Returns:
            Optional[int]: 保存された処理済み画像のID。失敗時は None。
        """
        try:
            # 必須情報を確認
            required_keys = ['width', 'height', 'mode', 'has_alpha',
                             'filename', 'color_space', 'icc_profile']
            if not all(key in info for key in required_keys):
                missing_keys = [key for key in required_keys if key not in info]
                raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

            # メタデータに親画像IDを追加
            info.update({
                'image_id': image_id,
                'stored_image_path': str(processed_path),
            })

            # データベースに挿入
            processed_image_id = self.repository.add_processed_image(info)
            return processed_image_id
        except Exception as e:
            self.logger.error(f"処理済み画像メタデータの保存中にエラーが発生しました: {e}")
            return None

    def save_annotations(self, image_id: int, annotations: dict[str, list[Any, Any]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (dict[str, list[Any, Any]]): アノテーションデータ。
                'tags', 'captions', 'score' をキーとし、それぞれリストを値とする辞書。
                各リストの要素は {'value': str, 'model': str} の形式。
        Raises:
            Exception: アノテーションの保存に失敗した場合。
        """
        try:
            self.repository.save_annotations(image_id, annotations)
            self.logger.info(f"画像 ID {image_id} のアノテーション{annotations}を保存しました")
        except Exception as e:
            self.logger.error(f"アノテーションの保存中にエラーが発生しました: {e}")
            raise

    def save_score(self, image_id: int, score_dict: dict[str, Any]) -> None:
        """
        画像のスコアを保存します。

        Args:
            image_id (int): スコアを追加する画像のID。
            score (dict[str, Any]): スコアの値と算出に使ったモデルのID
        """
        score_float = score_dict['score']
        model_id = score_dict['model_id']
        try:
            self.repository.save_score(image_id, score_float, model_id)
            self.logger.info(f"画像 ID {image_id} のスコア{score_float}を保存しました")
        except Exception as e:
            self.logger.error(f"スコアの保存中にエラーが発生しました: {e}")
            raise

    def get_low_res_image(self, image_id: int) -> Optional[str]:
        """
        指定されたIDで長辺が最小の処理済み画像のパスを取得します。

        Args:
            image_id (int): 取得する元画像のID。

        Returns:
            Optional[str]: 長辺が最小の処理済み画像のパス。見つからない場合はNone。
        """
        try:
            processed_images = self.get_processed_image(image_id)
            if not processed_images:
                self.logger.warning(f"画像ID {image_id} に対する処理済み画像が見つかりません。")
                return None

            # 長辺が最小の画像を見つける
            min_long_edge = float('inf')
            min_image_path = None

            for image in processed_images:
                width = image['width']
                height = image['height']
                long_edge = max(width, height)

                if long_edge < min_long_edge:
                    min_long_edge = long_edge
                    min_image_path = image['stored_image_path']

            if min_image_path:
                self.logger.info(f"画像ID {image_id} の最小長辺画像（{min_long_edge}px）を取得しました。")
                return min_image_path
            else:
                self.logger.warning(f"画像ID {image_id} に対する適切な低解像度画像が見つかりません。")
                return None

        except Exception as e:
            self.logger.error(f"低解像度画像の取得中にエラーが発生しました: {e}")
            return None

    def get_image_metadata(self, image_id: int) -> Optional[dict[str, Any]]:
        """
        指定されたIDの画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。

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

    def get_processed_metadata(self, image_id: int) -> list[dict[str, Any]]:
        """
        指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            image_id (int): 元画像のID。

        Returns:
            list[dict[str, Any]]: 処理済み画像のメタデータのリスト。

        Raises:
            Exception: メタデータの取得に失敗した場合。
        """
        try:
            processed_images = self.repository.get_processed_image(image_id)
            if not processed_images:
                self.logger.info(f"ID {image_id} の元画像に関連する処理済み画像が見つかりません。")
            return processed_images
        except Exception as e:
            self.logger.error(f"処理済み画像メタデータ取得中にエラーが発生しました: {e}")
            raise

    def get_image_annotations(self, image_id: int) -> dict[str, list[dict[str, Any]]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            dict[str, list[dict[str, Any]]]: アノテーションデータを含む辞書。

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

    def get_models(self) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
        """
        TODO: データベースに問い合わせるのでImageRepositoryに移動したほうがキレイ その時処理は分割する
        データベースに登録されているモデルの情報を取得します。

        Returns:
            tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]: (vision_models, score_models) のタプル。
            vision_models: {model_id: {'name': model_name, 'provider': provider}},
            upscaler_models: {model_id: {'name': model_name, 'provider': provider}}
            score_models: {model_id: {'name': model_name, 'provider': provider}}
        """
        query = "SELECT id, name, provider, type FROM models"
        try:
            models = self.db_manager.fetch_all(query)
            vision_models = {}
            score_models = {}
            upscaler_models = {}
            for model in models:
                model_id = model['id']
                name = model['name']
                provider = model['provider']
                model_type = model['type']
                if model_type == 'vision':
                    vision_models[model_id] = {'name': name, 'provider': provider}
                elif model_type == 'score':
                    score_models[model_id] = {'name': name, 'provider': provider}
                elif model_type == 'upscaler':
                    upscaler_models[model_id] = {'name': name, 'provider': provider}
            return vision_models, score_models, upscaler_models
        except sqlite3.Error as e:
            self.logger.error(f"モデルの取得中にエラーが発生しました: {e}")
            raise

    def get_images_by_filter(self, tags: list[str] = None, caption: str = None, resolution: int = 0, use_and: bool = True) -> tuple[list[dict[str, Any]], int]:
        if not tags and not caption:
            self.logger.info("タグもキャプションも指定されていない")
            return None, 0

        image_ids = set()

        # タグによるフィルタリング
        if tags:
            tag_results = [set(self.repository.get_images_by_tag(tag)) for tag in tags]
            if tag_results:
                image_ids = set.intersection(*tag_results) if use_and else set.union(*tag_results)

        # キャプションによるフィルタリング
        if caption:
            caption_results = set(self.repository.get_images_by_caption(caption))
            image_ids = image_ids.intersection(caption_results) if image_ids else caption_results

        # 画像メタデータの取得
        metadata_list = []
        for image_id in image_ids:
            metadata = self.repository.get_processed_image(image_id)
            metadata_list.extend(metadata)

        # 解像度によるフィルタリング
        if resolution != 0:
            filtered_metadata_list = self._filter_by_resolution(metadata_list, resolution)
        else:
            filtered_metadata_list = metadata_list

        list_count = len(filtered_metadata_list)
        self.logger.info(f"フィルタリング後の画像数: {list_count}")

        return filtered_metadata_list, list_count

    def _filter_by_resolution(self, metadata_list: list[dict[str, Any]], resolution: int) -> list[dict[str, Any]]:
        filtered_list = []
        for metadata in metadata_list:
            width, height = metadata['width'], metadata['height']
            long_side, short_side = max(width, height), min(width, height)

            if long_side == resolution:
                filtered_list.append(metadata)
            else:
                target_area = resolution * resolution
                actual_area = long_side * short_side
                error_ratio = abs(target_area - actual_area) / target_area

                if error_ratio <= 0.2:
                    filtered_list.append(metadata)
        return filtered_list

    def get_image_id_by_name(self, image_name: str) -> Optional[int]:
        """オリジナル画像の重複チェック用 画像名からimage_idを取得

        Args:
            image_name (str): 画像名

        Returns:
            int: image_id
        """
        image_id = self.repository.get_image_id_by_name(image_name)
        return image_id

    def get_total_image_count(self):
        """データベース内に登録された編集前画像の総数を取得"""
        count = self.repository.get_total_image_count()
        return count

    def check_processed_image_exists(self, image_id: int, target_resolution: int) -> Optional[dict]:
        """
        指定された画像IDと目標解像度に一致する処理済み画像が存在するかチェックします。

        Args:
            image_id (int): 元画像のID
            target_resolution (int): 目標解像度

        Returns:
            Optional[dict]: 処理済み画像が存在する場合はそのメタデータ、存在しない場合はNone
        """
        try:
            processed_images = self.repository.get_processed_image(image_id)

            for processed_image in processed_images:
                width = processed_image['width']
                height = processed_image['height']
                if width == target_resolution or height == target_resolution:
                    return processed_image

            return None
        except Exception as e:
            self.logger.error(f"処理済み画像のチェック中にエラーが発生しました: {e}")
            return None