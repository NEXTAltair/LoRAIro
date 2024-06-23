import sqlite3  # SQLite3データベースを扱うためのライブラリをインポート
import uuid  # ユニークIDを生成するためのライブラリをインポート
from datetime import datetime  # 日時情報を扱うためのライブラリからdatetimeクラスをインポート
from typing import Dict, List, Tuple, Optional, Any  # データ型を定義


class ImageDatabase:
    """画像データを管理するためのデータベース操作クラス"""

    def __init__(self, db_name='image_dataset.db'):
        """
        ImageDatabaseクラスのコンストラクタ

        Args:
            db_name (str): データベースファイルの名前
        """
        self.db_name = db_name  # データベースファイル名を指定
        self.conn = None  # データベース接続オブジェクトを初期化

    def connect(self):
        """
        データベースに接続。
        既に接続が存在する場合は、既存の接続をす。
        Returns:
            sqlite3.Connection: データベース接続オブジェクト
        """
        if self.conn is None:  # まだ接続していない場合のみ接続
            self.conn = sqlite3.connect(self.db_name)  # データベースに接続
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
                    original_path TEXT NOT NULL,
                    original_width INTEGER NOT NULL,
                    original_height INTEGER NOT NULL,
                    original_format TEXT NOT NULL,
                    color_profile TEXT,
                    has_alpha BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- processed_images テーブル：処理済み画像の情報を格納
                CREATE TABLE IF NOT EXISTS processed_images (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    processed_path TEXT NOT NULL,
                    processed_width INTEGER NOT NULL,
                    processed_height INTEGER NOT NULL,
                    processed_format TEXT NOT NULL,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images (id)
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
            ''')

    def add_image(self, width: int, height: int, format: str, file_path: str, color_profile: str, has_alpha: bool) -> Tuple[int, str]:
        """
        新しい画像情報をデータベースに追加します。

        Args:
            width (int): 画像の幅
            height (int): 画像の高さ
            format (str): 画像のフォーマット
            file_path (str): 画像ファイルのパス
            color_profile (str): 画像のカラープロファイル
            has_alpha (bool): アルファチャンネルの有無

        Returns:
            Tuple[int, str]: 挿入された行のID（image_id）とランダムに生成されたUUID
        """
        image_uuid = str(uuid.uuid4())  # ユニークなUUIDを生成
        with self.connect() as conn:
            cursor = conn.execute('''
                INSERT INTO images (uuid, original_path, original_width, original_height, original_format, color_profile, has_alpha)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (image_uuid, file_path, width, height, format, color_profile, has_alpha))
        return cursor.lastrowid, image_uuid

    def get_image(self, image_id: int) -> Optional[Dict[str, Any]]:
        """
        指定されたIDの画像情報を取得します。

        Args:
            image_id (int): 取得する画像のID

        Returns:
            Optional[Dict[str, Any]]: 画像情報を含む辞書。画像が見つからない場合はNone。
        """
        with self.connect() as conn:
            cursor = conn.execute('SELECT * FROM images WHERE id = ?', (image_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_image(self, image_id: int, **kwargs) -> bool:
        """
        指定されたIDの画像情報を更新します。

        Args:
            image_id (int): 更新する画像のID
            **kwargs: 更新するフィールドと値のペア

        Returns:
            bool: 更新が成功した場合はTrue、それ以外はFalse
        """
        allowed_fields = {'original_width', 'original_height', 'original_format', 'color_profile', 'has_alpha'}
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not update_fields:
            return False

        set_clause = ', '.join(f"{k} = ?" for k in update_fields)
        query = f"UPDATE images SET {set_clause}, updated_at = ? WHERE id = ?"
        values = list(update_fields.values()) + [datetime.now(), image_id]
        with self.connect() as conn:
            conn.execute(query, values)
        return True

    def delete_image(self, image_id: int) -> bool:
        """
        指定されたIDの画像情報を削除します。

        Args:
            image_id (int): 削除する画像のID

        Returns:
            bool: 削除が成功した場合はTrue
        """
        with self.connect() as conn:
            conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        return True

    def get_all_images(self) -> List[Dict[str, Any]]:
        """
        すべての画像情報を取得します。

        Returns:
            List[Dict[str, Any]]: 全画像情報のリスト
        """
        with self.connect() as conn:
            cursor = conn.execute("SELECT * FROM images")
            return [dict(row) for row in cursor.fetchall()]

    def add_processed_image(self, image_id: int, processed_path: str, width: int, height: int, format: str) -> int:
        """
        処理済み画像の情報をデータベースに追加します。

        Args:
            image_id (int): 元の画像のID
            processed_path (str): 処理済み画像のファイルパス
            width (int): 処理済み画像の幅
            height (int): 処理済み画像の高さ
            format (str): 処理済み画像のフォーマット

        Returns:
            int: 挿入された行のID
        """
        with self.connect() as conn:
            cursor = conn.execute('''
                INSERT INTO processed_images (image_id, processed_path, processed_width, processed_height, processed_format)
                VALUES (?, ?, ?, ?, ?)
            ''', (image_id, processed_path, width, height, format))
        return cursor.lastrowid

    def add_model(self, name: str, type: str) -> int:
        """
        新しいモデル情報をデータベースに追加します。

        Args:
            name (str): モデルの名前
            type (str): モデルのタイプ

        Returns:
            int: 挿入された行のID
        """
        with self.connect() as conn:
            cursor = conn.execute('''
                INSERT OR IGNORE INTO models (name, type)
                VALUES (?, ?)
            ''', (name, type))
        return cursor.lastrowid

    def add_tags(self, image_id: int, model_id: int, tags: List[str]) -> None:
        """
        画像に関連付けられたタグをデータベースに追加します。

        Args:
            image_id (int): タグを追加する画像のID
            model_id (int): タグを生成したモデルのID
            tags (List[str]): 追加するタグのリスト
        """
        with self.connect() as conn:
            conn.executemany('''
                INSERT INTO tags (image_id, model_id, tag)
                VALUES (?, ?, ?)
            ''', [(image_id, model_id, tag) for tag in tags])

    def add_caption(self, image_id: int, model_id: int, caption: str) -> int:
        """
        画像に関連付けられたキャプションをデータベースに追加します。

        Args:
            image_id (int): キャプションを追加する画像のID
            model_id (int): キャプションを生成したモデルのID
            caption (str): 追加するキャプション

        Returns:
            int: 挿入された行のID
        """
        with self.connect() as conn:
            cursor = conn.execute('''
                INSERT INTO captions (image_id, model_id, caption)
                VALUES (?, ?, ?)
            ''', (image_id, model_id, caption))
        return cursor.lastrowid

    def add_score(self, image_id: int, model_id: int, score: float) -> int:
        """
        画像に関連付けられたスコアをデータベースに追加します。

        Args:
            image_id (int): スコアを追加する画像のID
            model_id (int): スコアを生成したモデルのID
            score (float): 追加するスコア

        Returns:
            int: 挿入された行のID
        """
        with self.connect() as conn:
            cursor = conn.execute('''
                INSERT INTO scores (image_id, model_id, score)
                VALUES (?, ?, ?)
            ''', (image_id, model_id, score))
        return cursor.lastrowid

    def get_image_annotations(self, image_id: int) -> Dict[str, Any]:
        """
        指定された画像IDに関連するすべてのアノテーション（タグ、キャプション、スコア）を取得します。

        Args:
            image_id (int): アノテーションを取得する画像のID

        Returns:
            Dict[str, Any]: 'tags', 'captions', 'scores'キーを持つ辞書。
                            各キーの値はそれぞれのアノテーションのリスト。
        """
        with self.connect() as conn:
            # タグを取得
            tags = conn.execute('''
                SELECT t.tag, m.name as model
                FROM tags t
                JOIN models m ON t.model_id = m.id
                WHERE t.image_id = ?
            ''', (image_id,)).fetchall()

            # キャプションを取得
            captions = conn.execute('''
                SELECT c.caption, m.name as model
                FROM captions c
                JOIN models m ON c.model_id = m.id
                WHERE c.image_id = ?
            ''', (image_id,)).fetchall()

            # スコアを取得
            scores = conn.execute('''
                SELECT s.score, m.name as model
                FROM scores s
                JOIN models m ON s.model_id = m.id
                WHERE s.image_id = ?
            ''', (image_id,)).fetchall()

        return {
            'tags': [dict(tag) for tag in tags],
            'captions': [dict(caption) for caption in captions],
            'scores': [dict(score) for score in scores]
        }