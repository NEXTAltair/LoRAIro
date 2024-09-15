import sqlite3
import threading
import uuid

from contextlib import contextmanager
from typing import Any, Union, Optional
from datetime import datetime
from module.log import get_logger
from pathlib import Path

from module.file_sys import FileSystemManager

class SQLiteManager:
    def __init__(self, db_path: Path):
        self.logger = get_logger("SQLiteManager")
        self.db_path = db_path
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
            self._local.connection = sqlite3.connect(self.db_path)
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
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> Optional[sqlite3.Cursor]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            conn.commit()
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

                -- models テーブル：モデル情報を格納
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    provider TEXT,
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
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL
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
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL
                );

                -- scores テーブル：画像に関連付けられたスコアを格納
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    score FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL
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

    def add_image(self, info: dict[str, Any]) -> int:
        """
        画像情報をデータベースに追加します。

        Args:
            info (dict[str, Any]): 画像情報を含む辞書。
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
        #info dict に uuid が含まれているかで 編集前､編集後を判定してSQL文を変更
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

    def save_annotations(self, image_id: int, annotations: dict[str, list[dict[str, Any]]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (dict[str, list[dict[str, Any]]]): アノテーションデータ。
                'tags', 'captions', 'scores' をキーとし、それぞれリストを値とする辞書。
                各リストの要素は {'value': str, 'model_id': Optional[int]} の形式。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
            ValueError: 必要なデータが不足している場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定されたimage_id {image_id} は存在しません。")

        try:
            self._save_tags(image_id, annotations.get('tags', []))
            self._save_captions(image_id, annotations.get('captions', []))
            self._save_scores(image_id, annotations.get('scores', []))
        except sqlite3.Error as e:
            raise sqlite3.Error(f"アノテーションの保存中にエラーが発生しました: {e}")

    def _save_tags(self, image_id: int, tags: list[dict[str, Any]]) -> None:
        """タグを保存する内部メソッド"""
        query = "INSERT INTO tags (image_id, tag, model_id, existing) VALUES (?, ?, ?, ?)"
        data = []

        for tag in tags:
            tag_value = tag['tag']
            model_id = tag.get('model_id')
            existing = 1 if model_id is None else 0
            data.append((image_id, tag_value, model_id, existing))
            self.logger.debug(f"ImageRepository._save_tags: {tag_value} ")

        self.db_manager.executemany(query, data)

    def _save_captions(self, image_id: int, captions: list[dict[str, Any]]) -> None:
        """キャプションを保存する内部メソッド"""
        query = "INSERT INTO captions (image_id, caption, model_id, existing) VALUES (?, ?, ?, ?)"
        data = []

        for caption in captions:
            caption_value = caption['caption']
            model_id = caption.get('model_id')
            existing = 1 if model_id is None else 0
            data.append((image_id, caption_value, model_id, existing))
            self.logger.debug(f"ImageRepository._save_captions: {caption_value} ")

        self.db_manager.executemany(query, data)


    def _save_scores(self, image_id: int, scores: list[dict[str, Any]]) -> None:
        """スコアを保存する内部メソッド"""
        query = "INSERT INTO scores (image_id, score, model_id) VALUES (?, ?, ?)"
        data = []

        for score in scores:
            score_value = score['score']
            model_id = score.get('model_id')

            if model_id is not None:
                data.append((image_id, score_value, model_id))
                self.logger.debug(f"ImageRepository._save_scores: {score_value} ")
            else:
                self.logger.warning(f"スコア {score_value} にmodel_idが設定されていません。このスコアはスキップされます。")

        if data:
            self.db_manager.executemany(query, data)
        else:
            self.logger.info("保存するスコアがありません。")

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

    def get_image_annotations(self, image_id: int) -> dict[str, list[dict[str, Any]]]:
        """
        指定された画像IDのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID。

        Returns:
            dict[str, list[dict[str, Any]]]: アノテーションデータを含む辞書。
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
                self.logger.error(f"指定されたimage_id {image_id} は存在しません。")
            annotations = {
                'tags': self._get_tags(image_id),
                'captions': self._get_captions(image_id),
                'scores': self._get_scores(image_id)
            }
            return annotations

        except sqlite3.Error as e:
            self.logger.error(f"アノテーションの取得中にデータベースエラーが発生しました: {e}")

    def _get_tags(self, image_id: int) -> list[dict[str, str]]:
        query = "SELECT tag, model_id FROM tags WHERE image_id = ?"
        try:
            self.logger.debug("タグを取得するimage_id: %s", image_id)
            result = self.db_manager.fetch_all(query, (image_id,))
            if not result:
                self.logger.warning(f"Image_id: {image_id} にタグは登録されていません｡")
                raise
            return result
        except sqlite3.Error as e:
            self.logger.error("image_id: %s のタグを取得中にデータベースエラーが発生しました。%s",image_id, e)
            raise

    def _get_captions(self, image_id: int) -> list[dict[str, str]]:
        """image_idからキャプションを取得する内部メソッド"""
        query = "SELECT caption, model_id FROM captions WHERE image_id = ?"
        return self.db_manager.fetch_all(query, (image_id,))

    def _get_scores(self, image_id: int) -> list[dict[str, Any]]:
        """image_idからスコアを取得する内部メソッド"""
        query = "SELECT score, model_id FROM scores WHERE image_id = ?"
        return self.db_manager.fetch_all(query, (image_id,))

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

class ImageDatabaseManager:
    """
    画像データベース操作の高レベルインターフェースを提供するクラス。
    このクラスは、ImageRepositoryを使用して、画像メタデータとアノテーションの
    保存、取得、更新などの操作を行います。
    """
    def __init__(self):
        self.logger = get_logger("ImageDatabaseManager")
        db_path = Path("Image_database") / "image_database.db"
        self.db_manager = SQLiteManager(db_path)
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
            Optional[tuple]: 登録成功時は image_id, original_metadata 失敗時は None
        """
        try:
            original_image_metadata = fsm.get_image_info(image_path)
            db_stored_original_path = fsm.save_original_image(image_path)
            image_id, _ = self.save_original_metadata(db_stored_original_path, original_image_metadata)
            return image_id, original_image_metadata
        except Exception as e:
            self.logger.error(f"オリジナル画像の登録中にエラーが発生しました: {e}")
            return None

    def save_original_metadata(self, stored_image_path: Path, info: dict[str, Any]) -> tuple[int, str]:
        """
        元の画像のメタデータを保存します。

        Args:
            stored_image_path (Path): 保存された画像のパス。
            info (dict[str, Any]): 画像のメタデータ。

        Returns:
            tuple[int, str]: 保存された画像のID、生成されたUUID。

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

    def register_processed_metadata(self, image_id: int, processed_path: Path, info: dict[str, Any]) -> int:
        """
        処理済み画像のメタデータを保存します。

        Args:
            image_id (int): 元画像のID。
            processed_path (Path): 処理済み画像の保存パス。
            info (dict[str, Any]): 処理済み画像のメタデータ。

        Returns:
            int: 保存された処理済み画像のID。

        Raises:
            ValueError: 必要な情報が不足している場合。
            Exception: データベース操作に失敗した場合。
        """
        try:
            # infoディクショナリに元画像IDと保存パスを追加
            info['image_id'] = image_id
            info['stored_image_path'] = str(processed_path) #TODO: これは不要なカラムかも他の部分との整合性を要確認

            # リポジトリを使用して処理済み画像メタデータを保存
            processed_image_id = self.repository.add_image(info)

            self.logger.info(f"処理済み画像メタデータをDBに保存しました: ID {processed_image_id}, 元画像ID {image_id}")
            return processed_image_id

        except Exception as e:
            self.logger.error(f"処理済み画像メタデータの保存中にエラーが発生しました: {e}")
            raise

    def save_annotations(self, image_id: int, annotations: dict[str, list[dict[str, Any]]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (dict[str, list[dict[str, Any]]]): アノテーションデータ。
                'tags', 'captions', 'scores' をキーとし、それぞれリストを値とする辞書。
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

    def get_images_by_filter(self, tags: list[str], caption: str, resolution: int, use_and: bool = True) -> tuple[list[dict[str, Any]], int]:
        image_ids = set()

        if tags:
            tag_results = []
            for tag in tags:
                tag_results.append(set(self.repository.get_images_by_tag(tag)))
            if use_and:
                image_ids = set.intersection(*tag_results)
            else:
                image_ids = set.union(*tag_results)

        if caption:
            caption_results = set(self.repository.get_images_by_caption(caption))
            if caption_results:
                image_ids = image_ids.intersection(caption_results) if image_ids else caption_results

        if image_ids:
            metadata_list = []
            for image_id in image_ids:
                metadata = self.repository.get_processed_image(image_id)
                metadata_list.extend(metadata)
        else:
            return []

        if resolution:
            filtered_metadata_list = []
            for metadata in metadata_list:
                width = metadata['width']
                height = metadata['height']
                long_side = max(width, height)
                short_side = min(width, height)

                # 長辺が resolution と同じ場合は追加
                if long_side == resolution:
                    filtered_metadata_list.append(metadata)
                else:
                    # 面積の誤差を計算 (1216, 832) や (832, 1216)の横長縦長用
                    target_area = resolution * resolution
                    actual_area = long_side * short_side
                    error_ratio = abs(target_area - actual_area) / target_area

                    # 誤差が 20% 以内であれば追加
                    if error_ratio <= 0.2:
                        filtered_metadata_list.append(metadata)
        list_count = len(filtered_metadata_list)
        self.logger.info(f"フィルタリング後の画像数: {list_count}")

        return filtered_metadata_list, list_count

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