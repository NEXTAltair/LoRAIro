import sqlite3
import threading
import uuid
import imagehash
import inspect
from datetime import datetime, timezone, timedelta
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
            self.logger.error(f"データベース操作に失敗しました: {e}")
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
                    tag_id INTEGER,
                    image_id INTEGER,
                    model_id INTEGER,
                    tag TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
                    UNIQUE (image_id, tag, tag_id, model_id)
                );

                -- captions テーブル：画像に関連付けられたキャプションを格納
                CREATE TABLE IF NOT EXISTS captions (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    model_id INTEGER,
                    caption TEXT NOT NULL,
                    existing BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE SET NULL,
                    UNIQUE (image_id, score, model_id)
                );

            -- インデックスの作成
            CREATE INDEX IF NOT EXISTS idx_images_uuid ON images(uuid);
            CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);
            CREATE INDEX IF NOT EXISTS idx_processed_images_image_id ON processed_images(image_id);
            CREATE INDEX IF NOT EXISTS idx_tags_image_id ON tags(image_id);
            CREATE INDEX IF NOT EXISTS idx_captions_image_id ON captions(image_id);
            CREATE INDEX IF NOT EXISTS idx_scores_image_id ON scores(image_id);
            ''')

    # def migrate_tables(self):
    #     """既存のテーブルに不足しているカラムを追加し、必要に応じてテーブルを再作成する"""
    #     with self.get_connection() as conn:
    #         cursor = conn.cursor()
    #         # テーブルごとの新しい定義
    #         table_definitions = {
    #             'tags': [
    #                 ('id', 'INTEGER PRIMARY KEY'),
    #                 ('tag_id', 'INTEGER'),
    #                 ('image_id', 'INTEGER'),
    #                 ('model_id', 'INTEGER'),
    #                 ('tag', 'TEXT NOT NULL'),
    #                 ('existing', 'BOOLEAN NOT NULL DEFAULT 0'),
    #                 ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('FOREIGN KEY(image_id)', 'REFERENCES images(id) ON DELETE CASCADE'),
    #                 ('FOREIGN KEY(model_id)', 'REFERENCES models(id) ON DELETE SET NULL'),
    #                 ('UNIQUE(image_id, tag, tag_id, model_id)', '')
    #             ],
    #             # 他のテーブルも同様に定義
    #             'captions': [
    #                 ('id', 'INTEGER PRIMARY KEY'),
    #                 ('image_id', 'INTEGER'),
    #                 ('model_id', 'INTEGER'),
    #                 ('caption', 'TEXT NOT NULL'),
    #                 ('existing', 'BOOLEAN NOT NULL DEFAULT 0'),
    #                 ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('FOREIGN KEY(image_id)', 'REFERENCES images(id) ON DELETE CASCADE'),
    #                 ('FOREIGN KEY(model_id)', 'REFERENCES models(id) ON DELETE SET NULL'),
    #                 ('UNIQUE(image_id, caption, model_id)', '')
    #             ],
    #             'scores': [
    #                 ('id', 'INTEGER PRIMARY KEY'),
    #                 ('image_id', 'INTEGER'),
    #                 ('model_id', 'INTEGER'),
    #                 ('score', 'FLOAT NOT NULL'),
    #                 ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
    #                 ('FOREIGN KEY(image_id)', 'REFERENCES images(id) ON DELETE CASCADE'),
    #                 ('FOREIGN KEY(model_id)', 'REFERENCES models(id) ON DELETE SET NULL'),
    #                 ('UNIQUE(image_id, score, model_id)', '')
    #             ]
    #         }

    #         for table_name, columns in table_definitions.items():
    #             # 既存テーブルのカラムを取得
    #             cursor.execute(f"PRAGMA table_info({table_name});")
    #             existing_columns_info = cursor.fetchall()
    #             existing_column_names = {col['name'] for col in existing_columns_info}

    #             # 必要なカラムがすべて存在するか確認
    #             required_columns = [col[0] for col in columns if not col[0].startswith('FOREIGN KEY') and not col[0].startswith('UNIQUE')]
    #             missing_columns = set(required_columns) - existing_column_names

    #             # カラムが不足している場合、テーブルを再作成
    #             if missing_columns or self.need_to_recreate_table(table_name, columns, existing_columns_info):
    #                 self.logger.info(f"テーブル '{table_name}' を再作成します。")
    #                 self.recreate_table(conn, table_name, columns)
    #             else:
    #                 self.logger.info(f"テーブル '{table_name}' は再作成の必要がありません。")

    # def need_to_recreate_table(self, table_name, columns, existing_columns_info):
    #     """テーブルの再作成が必要かどうかを判断する"""
    #     # FOREIGN KEY や UNIQUE 制約の変更が必要かどうかをチェックする
    #     # この例では簡略化のため、常に False を返す
    #     # 必要に応じて実装を追加する
    #     return True  # 常に再作成する

    # def recreate_table(self, conn, table_name, columns):
    #     """テーブルを再作成してデータを移行する"""
    #     cursor = conn.cursor()

    #     # 一時テーブル名を生成
    #     temp_table_name = f"{table_name}_backup"

    #     # テーブルをリネーム（バックアップ）
    #     cursor.execute(f"ALTER TABLE {table_name} RENAME TO {temp_table_name};")
    #     self.logger.info(f"テーブル '{table_name}' を '{temp_table_name}' にリネームしました。")

    #     # 新しいテーブルを作成
    #     columns_definitions = []
    #     for col_name, col_def in columns:
    #         if col_def:  # 制約や FOREIGN KEY も含む
    #             columns_definitions.append(f"{col_name} {col_def}")
    #         else:
    #             columns_definitions.append(f"{col_name}")

    #     create_table_sql = f"CREATE TABLE {table_name} (\n" + ",\n".join(columns_definitions) + "\n);"
    #     cursor.execute(create_table_sql)
    #     self.logger.info(f"テーブル '{table_name}' を新しい定義で作成しました。")

    #     # データを移行
    #     old_columns = [col['name'] for col in cursor.execute(f"PRAGMA table_info({temp_table_name});")]
    #     new_columns = [col[0] for col in columns if not col[0].startswith('FOREIGN KEY') and not col[0].startswith('UNIQUE')]
    #     common_columns = set(old_columns) & set(new_columns)
    #     common_columns_str = ", ".join(common_columns)

    #     cursor.execute(f"INSERT INTO {table_name} ({common_columns_str}) SELECT {common_columns_str} FROM {temp_table_name};")
    #     self.logger.info(f"データを '{temp_table_name}' から '{table_name}' に移行しました。")

    #     # 一時テーブルを削除
    #     cursor.execute(f"DROP TABLE {temp_table_name};")
    #     self.logger.info(f"一時テーブル '{temp_table_name}' を削除しました。")

    #     conn.commit()

    def insert_models(self) -> None:
        """
        モデル情報の初期設定をデータベースに追加

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
            current_method = inspect.currentframe().f_code.co_name
            raise sqlite3.Error(f"{current_method} 画像メタデータの取得中にエラーが発生しました : {e}")

    def save_annotations(self, image_id: int, annotations: dict[str, Union[list[str], float, int]]) -> None:
        """
        画像のアノテーション（タグ、キャプション、スコア）を保存します。

        Args:
            image_id (int): アノテーションを追加する画像のID。
            annotations (dict): アノテーションデータ。
            {
                'tags': list[dict[tag: model_id]],
                'captions': list[caption: model_id],
                'score': dict[score: model_id]
                'model_id': int
                'image_path': str
            }

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
            ValueError: 必要なデータが不足している場合。
        """
        if not self._image_exists(image_id):
            raise ValueError(f"指定されたimage_id {image_id} は存在しません。")

        # 各値を取得
        tags = annotations.get('tags', [])
        captions = annotations.get('captions', [])
        score_data = annotations.get('score', {})
        model_id = annotations.get('model_id', None)
        if model_id is None:
            model_id = next((tag.get('model_id') for tag in tags if tag.get('model_id') is not None), None)
            if model_id is None:
                model_id = next((caption.get('model_id') for caption in captions if caption.get('model_id') is not None), None)
            if model_id is None:
                self.logger.warning("model_idはすべてNoneで保存されます。")

        tags_list = [tag_dict.get('tag') for tag_dict in tags]
        caption_list = [caption_dict.get('caption') for caption_dict in captions]
        try:
            self._save_tags(image_id, tags_list, model_id)
            self._save_captions(image_id, caption_list, model_id)
            if score_data:
                score = score_data.get('score', 0)
                score_model_id = score_data.get('model_id', model_id)
                self.save_score(image_id, score, score_model_id)
        except sqlite3.Error as e:
            current_method = inspect.currentframe().f_code.co_name
            raise sqlite3.Error(f"{current_method} アノテーションの保存中にエラーが発生しました: {e}")

    def _save_tags(self, image_id: int, tags: list[str], model_id: Optional[int]) -> None:
        """タグとそのIDを保存する内部メソッド

        Args:
            image_id (int): タグを追加する画像のID。
            tags (list[str]): タグのリスト。
            model_id (Optional[int]): タグ付けに使用されたモデルのID。Noneの場合は既存タグとして扱う。

        Raises:
            sqlite3.Error: データベース操作でエラーが発生した場合。
        """
        self.logger.debug(f"_save_tags called with image_id: {image_id}, tags: {tags}, model_id: {model_id}")
        self.logger.debug(f"Type of tags: {type(tags)}")
        if not tags:
            self.logger.debug(f"画像ID {image_id} のタグリストが空のため、保存をスキップします。")
            return

        query = """
                INSERT INTO tags (image_id, tag_id, tag, model_id, existing, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(image_id, tag, tag_id, model_id) DO UPDATE SET
                    existing = EXCLUDED.existing,
                    updated_at = CURRENT_TIMESTAMP
                """
        data = []

        for tag in tags:
            tag_id = self.find_tag_id(tag)
            existing = 1 if model_id is None else 0
            if model_id is None:
                # None の場合は明示的に NULL を設定
                data.append((image_id, tag_id, tag, None, existing))
            else:
                data.append((image_id, tag_id, tag, model_id, existing))
        self.logger.debug(f"ImageRepository._save_tags_with_ids: tag={tag}, tag_id={tag_id}")

        try:
            self.db_manager.executemany(query, data)
            self.logger.info(f"画像ID {image_id} に {len(data)} 個のタグとIDを保存しました")
        except sqlite3.Error as e:
            self.logger.error(f"タグとIDの保存中にエラーが発生しました: {e}")
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

        query = """
                INSERT INTO captions (image_id, caption, model_id, existing, created_at, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(image_id, caption, model_id) DO UPDATE SET
                    existing = EXCLUDED.existing,
                    updated_at = CURRENT_TIMESTAMP
                """
        data = []

        for caption in captions:
            existing = 1 if model_id is None else 0
            if model_id is None:
                data.append((image_id, caption, None, existing))
            else:
                data.append((image_id, caption, model_id, existing))
            self.logger.debug(f"ImageRepository._save_captions: {caption} ")

        try:
            self.db_manager.executemany(query, data)
            self.logger.info(f"画像ID {image_id} に {len(data)} 個のキャプションを保存しました")
        except sqlite3.Error as e:
            self.logger.error(f"キャプションの保存中にエラーが発生しました: {e}")
            raise

    def save_score(self, image_id: int, score: float, model_id: int) -> None:
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
            current_method = inspect.currentframe().f_code.co_name
            raise sqlite3.Error(f"{current_method} エラー: {e}")

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
        query = "SELECT tag, model_id, tag_id, updated_at FROM tags WHERE image_id = ?"
        try:
            self.logger.debug(f"タグを取得するimage_id: {image_id}")
            result = self.db_manager.fetch_all(query, (image_id,))
            if not result:
                self.logger.debug(f"Image_id: {image_id} にタグは登録されていません。")
            return result
        except sqlite3.Error as e:
            self.logger.error(f"image_id: {image_id} のタグを取得中にデータベースエラーが発生しました: {e}")
            raise

    def _get_captions(self, image_id: int) -> list[dict[str, Any]]:
        """image_idからキャプションを取得する内部メソッド"""
        query = "SELECT caption, model_id, updated_at FROM captions WHERE image_id = ?"
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

    def escape_special_characters(self, input_string: str) -> str:
        """
        SQLの特殊文字（% と _）をエスケープし、ワイルドカードの * を % に置換する。
        ダブルクオートで囲まれた部分は完全一致として扱う。

        Args:
            input_string (str): エスケープする入力文字列

        Returns:
            str: エスケープされた文字列
        """
        # ダブルクオートで囲まれた部分は完全一致として扱う
        if input_string.startswith('"') and input_string.endswith('"'):
            # ダブルクオートを外してそのまま戻す
            return input_string.strip('"')

        # 特殊文字のエスケープとワイルドカードの置換
        escaped_string = input_string.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')
        return escaped_string.replace('*', '%')

    def get_images_by_tag(self, tag: str, start_date: str, end_date: str) -> list[int]:
        """
        指定された日付の範囲で更新されたタグを持つ画像のIDリストを取得する
        （部分一致とワイルドカードに対応）

        Args:
            tag (str): 検索するタグ（ワイルドカード '*' を含むことができます）
            start_date (str): 検索開始日時（UTCタイムスタンプ）
            end_date (str): 検索終了日時（UTCタイムスタンプ）

        Returns:
            list[int]: タグを持つ画像IDのリスト か 空リスト
        """
        if tag.startswith('"') and tag.endswith('"'):
            # 完全一致検索用のクエリ
            query = """
            SELECT i.id
            FROM images i
            JOIN tags t ON i.id = t.image_id
            WHERE t.tag = ?
            AND t.updated_at BETWEEN ? AND ?
            """
            # ダブルクオートを外したタグで検索
            pattern = tag.strip('"')
        else:
            # ワイルドカードなしでも部分一致検索にする
            pattern = self.escape_special_characters(tag)
            if '*' not in tag:
                # '*' がない場合も部分一致のLIKEを使う
                pattern = f'%{pattern}%'

            query = """
            SELECT i.id
            FROM images i
            JOIN tags t ON i.id = t.image_id
            WHERE t.tag LIKE ? ESCAPE '\\'
            AND t.updated_at BETWEEN ? AND ?
            """
        # タイムスタンプをパラメータに追加
        params = [pattern, start_date, end_date]
        rows = self.db_manager.fetch_all(query, params)
        if not rows:
            self.logger.info("%s を含む画像はありません", tag)
            return []
        else:
            return [row['id'] for row in rows]

    def get_untagged_images(self) -> list[int]:
        query = """
        SELECT id
        FROM images
        WHERE id NOT IN (SELECT DISTINCT image_id FROM tags WHERE image_id)
        """
        return [row['id'] for row in self.db_manager.fetch_all(query, ())]

    def get_images_by_caption(self, caption: str, start_date: int, end_date: int) -> list[int]:
        """
        指定されたキャプションを含む画像のIDリストを取得する（部分一致、ワイルドカード、完全一致に対応）

        Args:
            caption (str): 検索するキャプション（ワイルドカード '*' やダブルクオートを含むことができます）
            start_date (str): 検索開始日時('%Y-%m-%d %H:%M:%S')
            end_date (str): 検索終了日時

        Returns:
            list[int]: キャプションを持つ画像IDのリスト か 空リスト
        """
        # キャプションがダブルクオートで囲まれている場合は完全一致検索を行う
        if caption.startswith('"') and caption.endswith('"'):
            # 完全一致検索用のクエリ
            query = """
            SELECT DISTINCT i.id
            FROM images i
            JOIN captions c ON i.id = c.image_id
            WHERE c.caption = ?
            AND c.updated_at BETWEEN ? AND ?
            """
            # ダブルクオートを外したキャプションで検索
            pattern = caption.strip('"')
        else:
            # 部分一致検索用のパターン作成
            pattern = self.escape_special_characters(caption)
            if '*' not in caption:
                pattern = f'%{pattern}%'
            query = """
            SELECT DISTINCT i.id
            FROM images i
            JOIN captions c ON i.id = c.image_id
            WHERE c.caption LIKE ? ESCAPE '\\'
            AND c.updated_at BETWEEN ? AND ?
            """

        params = [pattern, start_date, end_date]
        rows = self.db_manager.fetch_all(query, params)
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
            current_method = inspect.currentframe().f_code.co_name
            raise sqlite3.Error(f"{current_method} 処理済み画像の取得中にエラーが発生しました: {e}")

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

    def get_image_id_by_phash(self, phash: str) -> Optional[int]:
        """
        pHashからimage_idを取得

        Args:
            phash (str): pHash

        Returns:
            Optional[int]: image_id。画像が見つからない場合はNone。
        """
        THRESHOLD = 5  # この値は調整可能です。小さいほど厳密な一致を要求します。

        query = "SELECT id, phash FROM images"
        try:
            results = self.db_manager.fetch_all(query)

            for row in results:
                db_id, db_phash = row['id'], row['phash']
                if imagehash.hex_to_hash(phash) - imagehash.hex_to_hash(db_phash) <= THRESHOLD:
                    self.logger.info(f"類似画像が見つかりました: ID {db_id}, 元のpHash: {phash}, DB内pHash: {db_phash}")
                    return db_id

            self.logger.info(f"類似画像は見つかりませんでした: pHash {phash}")
            return None
        except Exception as e:
            self.logger.error(f"類似画像の検索中にエラーが発生しました: {e}")
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

    def find_tag_id(self, keyword: str) -> Optional[int]:
        """tags_v3.db TAGSテーブルからタグを完全一致で検索

        Args:
            keyword (str): 検索キーワード
        Returns:
            tag_id (Optional[int]): タグID
        Raises:
            ValueError: 複数または0件のタグが見つかった場合
        """
        query = "SELECT tag_id FROM tag_db.TAGS WHERE tag = ?"
        try:
            result = self.db_manager.fetch_one(query, (keyword,))
            if result:
                if len(result) > 1:
                    self.logger.warning(f"タグ '{keyword}' に対して複数のIDが見つかりました。\n {result}")
                    return result['tag_id'][0]
                else:
                    tag_id = result['tag_id']
                    self.logger.debug(f"タグ '{keyword}' のtag_id {tag_id} を取得しました")
                return tag_id
            self.logger.info(f"タグ '{keyword}' のtag_idを取得できませんでした")
            return None
        except sqlite3.Error as e:
            self.logger.error(f"タグIDの取得中にエラーが発生しました: {e}")
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
        self.logger.debug(f"save_annotations called with image_id: {image_id}, annotations: {annotations}")
        self.logger.debug(f"Type of annotations: {type(annotations)}")

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
            processed_images = self.repository.get_processed_image(image_id)
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

    def get_images_by_filter(self, tags: list[str] = None, caption: str = None, resolution: int = 0, 
                             use_and: bool = True, start_date: str = None, end_date: str = None, 
                             include_untagged: bool = False, include_nsfw: bool = False) -> tuple[list[dict[str, Any]], int]:
        """

        Args:
            tags (list[str], optional): カンマ区切りをリスト化したタグ. Defaults to None.
            caption (str, optional): _キャプション
            resolution (int, optional): 検索する解像度x解像度の値が誤差20%以内の画像を取得. Defaults to 0.
            use_and (bool, optional): _description_. Defaults to True.
            start_date (str): 検索する画像の作成日時の下限('%Y-%m-%d %H:%M:%S')
            end_date (str,): 検索する画像の作成日時の上限
            include_untagged (bool, optional): タグが付いていない画像のみを取得. Defaults to False.
            include_nsfw (bool, optional): NSFW画像を含めるかどうか. Defaults to False.

        Returns:
            tuple[list[dict[str, Any]], int]: 条件にマッチした画像データのリストとその数
            例:([
                {'id': 516, 'image_id': 515, 'stored_image_path': 'psth', 
                'width': 1024, 'height': 768, 'mode': 'RGB', 'has_alpha': 0, 'filename': '1_240925_00304.webp', 'color_space': 'RGB', 'icc_profile': 'Not present', 'created_at': '2024-09-26T20:21:08.451199', 'updated_at': '2024-09-26T20:21:08.451199'},
                {'id': 517, 'image_id': 516, 'stored_image_path': 'psth',...}
                ],
                2)
        """
        if not tags and not caption and not include_untagged:
            self.logger.info("タグもキャプションも指定されていない")
            return None, 0

        # 現在の日付を取得
        current_datetime = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        start_date = start_date or ('2020-01-01 00:00:00')  # 2020年1月1日
        end_date = end_date or current_datetime  # 現在

        image_ids = set()

        if include_untagged:
            if tags or caption:
                self.logger.warning("検索語句とinclude_untaggedが同時に指定されています。検索語句を無視します。")
            untagged_image_ids = set(self.repository.get_untagged_images())
            image_ids.update(untagged_image_ids)

        # タグによるフィルタリング
        if tags and not include_untagged:
            tag_results = [set(self.repository.get_images_by_tag(tag, start_date, end_date)) for tag in tags]
            if tag_results:
                image_ids = set.intersection(*tag_results) if use_and else set.union(*tag_results)

        # キャプションによるフィルタリング
        if caption and not include_untagged:
            caption_results = set(self.repository.get_images_by_caption(caption, start_date, end_date))
            image_ids = image_ids.intersection(caption_results) if image_ids else caption_results

        # image_idsが空の場合は空リストを返す
        if not image_ids:
            self.logger.info("条件に一致する画像が見つかりませんでした")
            return [], 0

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
            """
            解像度に基づいてメタデータのリストをフィルタリングします。

            Args:
                metadata_list (list[dict[str, Any]]): メタデータの辞書のリスト。
                resolution (int): ディレクトリの解像度。

            Returns:
                list[dict[str, Any]]: フィルタリングされたメタデータの辞書のリスト。解像度が条件に一致するか、
                解像度の条件に誤差が0.2以下のメタデータが含まれます。

            """
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

    def detect_duplicate_image(self, image_path: Path) -> Optional[int]:
        """
        画像の重複を検出し、重複する場合はその画像のIDを返す。
        名前による高速な検索と、pHashによる正確な重複検知を組み合わせて使用。

        Args:
            image_path (Path): 検査する画像ファイルのパス

        Returns:
            Optional[int]: 重複する画像が見つかった場合はそのimage_id、見つからない場合はNone
        """
        image_name = image_path.name

        # まず名前で高速に検索
        image_id = self.repository.get_image_id_by_name(image_name)
        if image_id is not None:
            self.logger.info(f"画像名の一致を検出: {image_name}")
            return image_id

        # 名前で見つからない場合、pHashを計算して検索
        try:
            with Image.open(image_path) as img:
                phash = str(imagehash.phash(img))

            image_id = self.repository.get_image_id_by_phash(phash)
            if image_id is not None:
                self.logger.info(f"pHashの一致を検出: {image_name}")
            return image_id
        except Exception as e:
            self.logger.error(f"pHash計算中にエラーが発生: {e}")
            return None

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
            self.logger.info(f"ID {image_id} の画像に解像度 {target_resolution} に一致する処理済み画像が見つかりませんでした")
            return None
        except Exception as e:
            self.logger.error(f"処理済み画像のチェック中にエラーが発生しました: {e}")
            return None