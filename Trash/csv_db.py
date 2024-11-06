#tagcompleat用csvをsqliteに変換するスクリプト
import pandas as pd
import sqlite3
from pathlib import Path
import csv
from module.cleanup_txt import clean_format, clean_underscore

def sprit_csv_value(value):
    """CSVの値を分割してリストに変換"""
    if isinstance(value, str):
        return value.split(",") if value else []
    return []

def expand_dataframe(df):
    """データフレームのカラム値をカンマで分割して行を展開"""
    if "aliases" in df.columns:
        df["aliases"] = df["aliases"].apply(sprit_csv_value)
        df = df.explode("aliases").reset_index(drop=True)
    if "translation" in df.columns:
        df["translation"] = df["translation"].apply(sprit_csv_value)
        df = df.explode("translation").reset_index(drop=True)
    return df

def load_csv_to_dataframe(csv_path):
    """CSVファイルからデータフレームを読み込む"""
    #csvのカラム数をカウント
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        num_cols = len(next(reader))
    if num_cols == 4: #タグ 分類 ポスト数 別名
        df = pd.read_csv(csv_path, header=None, names=["name", "type", "postCount", "aliases"])
    elif num_cols == 2: #タグ 翻訳 #翻訳用csv
        df = pd.read_csv(csv_path, header=None, names=["name", "translation"])
    elif num_cols == 3 or 5:  #derpi-tac-a1111の色データだったり､よくわからんCSVなので飛ばす
        print(f"多分必要ないファイル {csv_path}")
        return None
    else:
        raise ValueError(f"想定してないカラム数 {csv_path}")
    # clean_format関数を各列に適用してフォーマットをクリーンナップ
    for col in df.columns:
        df[col] = df[col].map(clean_format)
        df[col] = df[col].map(clean_underscore)
    return df

def save_dataframe_to_sqlite(df, db_path, table_name):
    """データフレームをSQLiteデータベースに保存"""
    try:
        conn = sqlite3.connect(db_path)  # SQLiteデータベースに接続
        cursor = conn.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} (name TEXT)")
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = [col[1] for col in cursor.fetchall()]
        for column in df.columns:
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} TEXT")
        conn.commit()
        df.to_sql(table_name, conn, if_exists='append', index=False)  # データフレームを指定されたテーブルに追加
    except sqlite3.Error as e:
        print(f"データベースへの保存中にエラーが発生: {e}")
    finally:
        if conn:
            conn.close()  # データベース接続を閉じる

if __name__ == "__main__":
    # 入力ファイルフォルダ
    input_dir= Path(r"imagetag_data")
    # 出力SQLiteデータベースファイルパス
    output_db = "tags.db"
    table_name = "tags"

    for input_csv in input_dir.rglob("*.csv"):
        # CSVファイルの読み込み
        tags_df = load_csv_to_dataframe(input_csv)

        # データフレームをSQLiteデータベースに保存
        if tags_df is not None:
            tags_df = expand_dataframe(tags_df)
            save_dataframe_to_sqlite(tags_df, output_db, table_name)

            print(f"Tags data saved to {output_db} in table {table_name}")
