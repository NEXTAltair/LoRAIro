import sqlite3  # SQLite3データベースを扱うためのライブラリをインポート
import uuid  # ユニークIDを生成するためのライブラリをインポート
from datetime import datetime  # 日時情報を扱うためのライブラリからdatetimeクラスをインポート

class ImageDatabase:
    """画像データを管理するためのデータベース操作クラス"""

    def __init__(self, db_name='image_dataset.db'):
        """データベース接続の準備。"""
        self.db_name = db_name  # データベースファイル名を指定
        self.conn = None  # データベース接続オブジェクトを初期化

    def connect(self):
        """データベースに接続。"""
        if self.conn is None:  # まだ接続していない場合のみ接続
            self.conn = sqlite3.connect(self.db_name)  # データベースに接続
            self.conn.row_factory = sqlite3.Row  # クエリ結果を辞書のように扱えるように設定
        return self.conn  # 接続オブジェクトを返す

    def close(self):
        """データベース接続を閉じます。"""
        if self.conn:  # 接続している場合のみ
            self.conn.close()  # データベース接続を閉じる
            self.conn = None  # 接続オブジェクトをNoneに戻す

    def __enter__(self):
        """with文を使用した際に自動的に接続を開くためのメソッド。"""
        return self.connect()  # データベースに接続

    def __exit__(self, exc_type, exc_val, exc_tb):
        """with文を使用した際に自動的に接続を閉じるためのメソッド。"""
        self.close()  # データベース接続を閉じる

def create_tables(self):
    with self.connect() as conn:
        conn.execute('''
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
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_images (
                id INTEGER PRIMARY KEY,
                image_id INTEGER,
                processed_path TEXT NOT NULL,
                processed_width INTEGER NOT NULL,
                processed_height INTEGER NOT NULL,
                processed_format TEXT NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images (id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                image_id INTEGER,
                model_id INTEGER,
                tag TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images (id),
                FOREIGN KEY (model_id) REFERENCES models (id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS captions (
                id INTEGER PRIMARY KEY,
                image_id INTEGER,
                model_id INTEGER,
                caption TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images (id),
                FOREIGN KEY (model_id) REFERENCES models (id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY,
                image_id INTEGER,
                model_id INTEGER,
                score FLOAT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images (id),
                FOREIGN KEY (model_id) REFERENCES models (id)
            )
        ''')

    def add_image(self, width: int, height: int, format: str, file_path: str) -> int:
        """画像情報をデータベースに追加。"""
        image_uuid = str(uuid.uuid4())  # ユニークIDを生成
        with self.connect():  # データベースに接続
            cursor = self.connect().execute('''
                INSERT INTO images (uuid, width, height, format)  -- imagesテーブルにデータを追加
                VALUES (?, ?, ?, ?)  -- プレースホルダーに値をバインド
            ''', (image_uuid, width, height, format))
        return cursor.lastrowid, image_uuid  # 追加した画像のIDとUUIDを返す

    def get_image(self, image_id):
        """指定されたIDの画像情報を取得。"""
        with self.connect():  # データベースに接続
            cursor = self.connect().execute('SELECT * FROM images WHERE id = ?', (image_id,))
            return cursor.fetchone()  # 最初の1行を取得

    def update_image(self, image_id, **kwargs):
        """指定されたIDの画像情報を更新。"""
        allowed_fields = {'width', 'height', 'format'}  # 更新可能なフィールド
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}  # 更新対象のフィールドを抽出
        if not update_fields:  # 更新対象のフィールドがない場合は何もしない
            return False

        set_clause = ', '.join(f"{k} = ?" for k in update_fields)
        query = f"UPDATE images SET {set_clause}, updated_at = ? WHERE id = ?"
        values = list(update_fields.values()) + [datetime.now(), image_id]
        with self.connect():  # データベースに接続
            self.connect().execute(query, values)  # SQL文を実行
        return True  # 更新が成功したことを返す

    def delete_image(self, image_id):
        """指定されたIDの画像情報を削除。"""
        with self.connect():  # データベースに接続
            self.connect().execute("DELETE FROM images WHERE id = ?", (image_id,))
        return True  # 削除が成功したことを返す

    def get_all_images(self):
        """すべての画像情報を取得。"""
        with self.connect():  # データベースに接続
            cursor = self.connect().execute("SELECT * FROM images")
            return cursor.fetchall()  # 全ての行を取得