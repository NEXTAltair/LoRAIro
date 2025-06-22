"""
説明をかく
"""

import sys
from pathlib import Path
from typing import TypedDict

from sqlalchemy import create_engine, inspect, text

# --- 設定 ---
# 確認したいデータベースファイルのパスを指定してください
# デフォルトではプロジェクトルート "Image_database/image_database.db" を設定
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DB_FILE = PROJECT_ROOT / "Image_database" / "image_database.db"
# --- 設定ここまで ---


# --- 期待されるスキーマ定義 ---
class ExpectedTableSchema(TypedDict):
    columns: set[str]


# 仕様書に基づき、各テーブルに存在するべき全てのカラムを定義
EXPECTED_SCHEMA: dict[str, ExpectedTableSchema] = {
    "images": {
        "columns": {
            "id",
            "uuid",
            "phash",
            "original_image_path",
            "stored_image_path",
            "width",
            "height",
            "format",
            "mode",
            "has_alpha",
            "filename",
            "extension",
            "color_space",
            "icc_profile",
            "manual_rating",
            "created_at",
            "updated_at",
        },
    },
    "processed_images": {
        "columns": {
            "id",
            "image_id",
            "stored_image_path",
            "width",
            "height",
            "mode",
            "has_alpha",
            "filename",
            "color_space",
            "icc_profile",
            "created_at",
            "updated_at",
        },
    },
    "models": {
        "columns": {"id", "name", "type", "provider", "created_at", "updated_at"},
    },
    "tags": {
        "columns": {
            "id",
            "tag_id",
            "image_id",
            "model_id",
            "tag",
            "existing",
            "is_edited_manually",
            "confidence_score",
            "created_at",
            "updated_at",
        },
    },
    "captions": {
        "columns": {
            "id",
            "image_id",
            "model_id",
            "caption",
            "existing",
            "is_edited_manually",
            "created_at",
            "updated_at",
        },
    },
    "scores": {
        "columns": {
            "id",
            "image_id",
            "model_id",
            "score",
            "is_edited_manually",
            "created_at",
            "updated_at",
        },
    },
    "ratings": {
        "columns": {
            "id",
            "image_id",
            "model_id",
            "raw_rating_value",
            "normalized_rating",
            "confidence_score",
            "created_at",
            "updated_at",
        },
    },
}


def check_table_columns(
    table_name: str,
    columns_db: set[str],
    expected_cols: set[str],
) -> bool:
    """テーブルのカラムを仕様書と比較し、結果を表示する"""
    missing_cols = expected_cols - columns_db  # 仕様書にあるがDBにないカラム
    extra_cols = columns_db - expected_cols  # DBにあるが仕様書にないカラム

    ok = True
    if not missing_cols:
        print(f"[OK]   '{table_name}' テーブル: 仕様書定義のカラムは全て存在します。")
    else:
        print(
            f"[NG]   '{table_name}' テーブル: 仕様書に定義されているカラムが不足しています: {missing_cols}"
        )
        ok = False

    if extra_cols:
        print(f"[WARN] '{table_name}' テーブル: 仕様書に定義されていないカラムが存在します: {extra_cols}")
        # 警告は出すが、チェック結果としては OK とする (Optional)
        # ok = False # 仕様外カラムをエラーとする場合はこちらを有効化

    return ok


def check_schema(db_url: str) -> bool:
    """指定されたデータベースURLのスキーマを確認し、仕様書との差分をチェックする"""
    print(f"データベース '{db_url}' のスキーマを仕様書と比較します...")
    all_checks_passed = True
    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # --- 仕様書で定義されている各テーブルをチェック ---
        for table_name, expected_schema in EXPECTED_SCHEMA.items():
            print(f"-- チェック中: '{table_name}' テーブル --")
            if table_name in existing_tables:
                columns_db = {col["name"] for col in inspector.get_columns(table_name)}
                all_checks_passed &= check_table_columns(table_name, columns_db, expected_schema["columns"])
            else:
                print(f"[NG]   テーブル '{table_name}' がデータベースに存在しません。")
                all_checks_passed = False

        # --- 仕様書にないテーブルが存在しないかチェック (Optional) ---
        unexpected_tables = set(existing_tables) - set(EXPECTED_SCHEMA.keys())
        # alembic_version テーブルは無視する
        unexpected_tables.discard("alembic_version")
        if unexpected_tables:
            print("-- 警告: 仕様書に定義されていないテーブルが存在します --")
            for table in unexpected_tables:
                print(f"[WARN] '{table}' テーブルは仕様書に定義されていません。")
            # 警告は出すが、全体の結果には影響させない (Optional)
            # all_checks_passed = False # 仕様外テーブルをエラーとする場合はこちらを有効化

        print("-" * 40)
        if all_checks_passed:
            print("【結論】スキーマチェック完了: データベーススキーマは仕様書と一致しています。")
        else:
            print(
                "【結論】スキーマチェック完了: 仕様書と異なる点が見つかりました。上記ログを確認してください。"
            )

    except Exception as e:
        print(f"\nスキーマの確認中にエラーが発生しました: {e}")
        all_checks_passed = False

    return all_checks_passed


def fetch_table_data(connection, table_name: str, columns: list[str], limit: int) -> None:
    """指定されたテーブルのデータを取得して表示する"""
    print(f"\n--- {table_name} テーブル (先頭{limit}件) ---")
    try:
        result = connection.execute(
            text(f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id DESC LIMIT {limit}")
        )
        rows = result.fetchall()
        if not rows:
            print("  データがありません。")
            return

        # ヘッダー作成
        header = "  " + " | ".join(f"{col:<{len(col)}}" for col in columns)
        print(header)
        print("  " + "-" * (len(header) - 2))

        # データ表示
        for row in rows:
            print("  " + " | ".join(f"{val!s:<{len(col)}}" for val, col in zip(row, columns, strict=True)))
    except Exception as e:
        print(f"  {table_name} テーブルからのデータ取得中にエラー: {e}")


def fetch_sample_data(db_url: str, limit: int = 5) -> None:
    """指定されたデータベースからサンプルデータを取得して表示する"""
    print("\nデータベースからサンプルデータを取得して確認します...")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    with engine.connect() as connection:
        # Images テーブル
        if "images" in existing_tables:
            fetch_table_data(connection, "images", ["id", "manual_rating", "updated_at"], limit)

        # Tags テーブル
        if "tags" in existing_tables:
            tag_columns = ["id", "tag", "model_id", "existing"]
            if "is_edited_manually" in {col["name"] for col in inspector.get_columns("tags")}:
                tag_columns.append("is_edited_manually")
            if "confidence_score" in {col["name"] for col in inspector.get_columns("tags")}:
                tag_columns.append("confidence_score")
            tag_columns.append("updated_at")
            fetch_table_data(connection, "tags", tag_columns, limit)

        # Captions テーブル
        if "captions" in existing_tables:
            caption_columns = ["id", "SUBSTR(caption, 1, 30) AS caption_preview", "model_id", "existing"]
            if "is_edited_manually" in {col["name"] for col in inspector.get_columns("captions")}:
                caption_columns.append("is_edited_manually")
            caption_columns.append("updated_at")
            fetch_table_data(connection, "captions", caption_columns, limit)

        # Scores テーブル
        if "scores" in existing_tables:
            score_columns = ["id", "score", "model_id"]
            if "is_edited_manually" in {col["name"] for col in inspector.get_columns("scores")}:
                score_columns.append("is_edited_manually")
            score_columns.append("updated_at")
            fetch_table_data(connection, "scores", score_columns, limit)

        # Ratings テーブル
        if "ratings" in existing_tables:
            fetch_table_data(
                connection,
                "ratings",
                ["id", "image_id", "model_id", "normalized_rating", "confidence_score", "updated_at"],
                limit,
            )

    print("\nサンプルデータの確認完了。")


if __name__ == "__main__":
    # コマンドライン引数からDBファイルパスを取得、なければデフォルトを使用
    db_file_path_str = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_FILE
    db_file_path = Path(db_file_path_str).resolve()  # 絶対パスに変換

    if not db_file_path.exists():
        print(f"[エラー] データベースファイルが見つかりません: {db_file_path}")
        print(f"スクリプトと同じディレクトリに '{DEFAULT_DB_FILE}' を置くか、")
        print("コマンドライン引数で正しいパスを指定してください。")
        print("例: python check_db_schema.py path/to/your/image_database.db")
    else:
        database_url = f"sqlite:///{db_file_path}"
        # 1. スキーマチェックを実行
        schema_ok = check_schema(database_url)
        # 2. サンプルデータを取得・表示
        fetch_sample_data(database_url)
