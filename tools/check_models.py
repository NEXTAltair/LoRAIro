"""データベースのモデル関連テーブルの確認用"""

import sqlite3
from collections import defaultdict
from pathlib import Path

# --- 設定 ---
# ワークスペースルートからの相対パスでデータベースファイルを指定
# ユーザー指定のパス形式に合わせる
DB_RELATIVE_PATH = "Image_database/image_database.db"
EXPECTED_MODEL_TYPES = {"tagger", "score", "captioner", "upscaler", "llm"}
# ---

# スクリプトの場所からワークスペースルートを取得 (tools ディレクトリにある想定)
workspace_root = Path.cwd()
db_path = workspace_root / DB_RELATIVE_PATH
print(f"データベースファイルパス: {db_path}")

if not db_path.exists():
    print(f"エラー: データベースファイルが見つかりません: {db_path}")
    print("DB_RELATIVE_PATH の設定を確認してください。")
    exit(1)

print("\n--- スキーマ構造チェック ---")
schema_ok = True
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    print("データベース接続成功")

    # 1. models テーブルのカラムチェック
    cursor.execute("PRAGMA table_info(models);")
    models_columns = {column[1] for column in cursor.fetchall()}
    if "type" in models_columns:
        print("エラー: 'models' テーブルに古い 'type' カラムがまだ存在します。")
        schema_ok = False
    else:
        print("OK: 'models' テーブルに 'type' カラムはありません。")
    if "discontinued_at" not in models_columns:
        print("エラー: 'models' テーブルに 'discontinued_at' カラムが存在しません。")
        schema_ok = False
    else:
        print("OK: 'models' テーブルに 'discontinued_at' カラムが存在します。")

    # 2. model_types テーブルの存在と内容チェック
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_types';")
    if not cursor.fetchone():
        print("エラー: 'model_types' テーブルが存在しません。")
        schema_ok = False
    else:
        print("OK: 'model_types' テーブルが存在します。")
        cursor.execute("SELECT name FROM model_types;")
        found_types = {row[0] for row in cursor.fetchall()}
        if found_types == EXPECTED_MODEL_TYPES:
            print(f"OK: 'model_types' テーブルに期待されるタイプ {EXPECTED_MODEL_TYPES} が含まれています。")
        else:
            print("エラー: 'model_types' の内容が期待値と異なります。")
            print(f"  期待値: {EXPECTED_MODEL_TYPES}")
            print(f"  実際値: {found_types}")
            schema_ok = False

    # 3. model_function_associations テーブルの存在チェック
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='model_function_associations';"
    )
    if not cursor.fetchone():
        print("エラー: 'model_function_associations' テーブルが存在しません。")
        schema_ok = False
    else:
        print("OK: 'model_function_associations' テーブルが存在します。")

except sqlite3.Error as e:
    print(f"スキーマチェック中に SQLite エラーが発生しました: {e}")
    schema_ok = False
    exit(1)
except Exception as e:
    print(f"スキーマチェック中に予期せぬエラーが発生しました: {e}")
    schema_ok = False
    exit(1)
finally:
    if "conn" in locals() and conn:
        conn.close()
        print("データベース接続を閉じました (スキーマチェック)。")

if not schema_ok:
    print("\nスキーマ構造に問題があるため、データ内容の確認をスキップします。")
    exit(1)

print("\n--- データ内容チェック (モデルとタイプの関連付け) ---")
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    print("データベース接続成功 (データチェック)")

    # モデル名と関連付けられたタイプ名を取得 (JOINを使用)
    query = """
    SELECT m.name, mt.name
    FROM models m
    JOIN model_function_associations mfa ON m.id = mfa.model_id
    JOIN model_types mt ON mfa.type_id = mt.id
    ORDER BY m.name, mt.name;
    """
    cursor.execute(query)
    results = cursor.fetchall()

    if not results:
        print("モデル情報または関連付けが見つかりません。")
    else:
        model_types_dict = defaultdict(list)
        for model_name, type_name in results:
            model_types_dict[model_name].append(type_name)

        print("\n現在のモデルとタイプの関連付け:")
        for model_name, types in sorted(model_types_dict.items()):
            print(f"- {model_name}: {', '.join(types)}")

        print(f"\n合計 {len(model_types_dict)} 個のモデルに関連付けが見つかりました。")

except sqlite3.Error as e:
    print(f"データチェック中に SQLite エラーが発生しました: {e}")
except Exception as e:
    print(f"データチェック中に予期せぬエラーが発生しました: {e}")
finally:
    if "conn" in locals() and conn:
        conn.close()
        print("データベース接続を閉じました (データチェック)。")
