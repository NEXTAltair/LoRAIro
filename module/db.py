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
        """imagesテーブルを作成。"""
        with self.connect() as conn:  # データベースに接続
            conn.execute('''
                CREATE TABLE IF NOT EXISTS images (  -- imagesテーブルが存在しない場合は作成
                    id INTEGER PRIMARY KEY,  -- 画像ID、自動で増加する番号
                    uuid TEXT UNIQUE NOT NULL,  -- 画像を一意に識別するID
                    width INTEGER NOT NULL,  -- 画像の幅
                    height INTEGER NOT NULL,  -- 画像の高さ
                    format TEXT NOT NULL,  -- 画像のフォーマット（例：png、jpg）
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 画像データの作成日時
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 画像データの更新日時
                )
            ''')

    def add_image(self, width, height, format):
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