from pathlib import Path
from PIL import Image
from module.db import ImageDatabase

def test_image_registration():
    # テスト用のデータベースファイル名
    test_db = Path('test_image_dataset.db')

    # テスト用のデータベースが既に存在する場合は削除
    if Path.exists(test_db):
        Path.remove(test_db)

    # ImageDatabaseインスタンスを作成
    db = ImageDatabase(test_db)

    # テーブルを作成
    db.create_tables()

    # テスト用の画像ファイルのパス（実際のパスに変更してください）
    image_path = Path(r'testimg\1_img\file01.png')

    # 画像ファイルを開いて情報を取得
    with Image.open(image_path) as img:
        width, height = img.size
        format = img.format.lower()

    # データベースに画像情報を追加
    image_id, image_uuid = db.add_image(width, height, format)

    print(f"Added image: ID={image_id}, UUID={image_uuid}")

    # 追加した画像情報を取得して確認
    image_data = db.get_image(image_id)

    if image_data:
        print("Retrieved image data:")
        print(f"ID: {image_data['id']}")
        print(f"UUID: {image_data['uuid']}")
        print(f"Width: {image_data['width']}")
        print(f"Height: {image_data['height']}")
        print(f"Format: {image_data['format']}")
        print(f"Created at: {image_data['created_at']}")
        print(f"Updated at: {image_data['updated_at']}")

        # データが正しいか確認
        assert image_data['width'] == width, "Width mismatch"
        assert image_data['height'] == height, "Height mismatch"
        assert image_data['format'] == format, "Format mismatch"
        print("All data matches. Test passed!")
    else:
        print("Failed to retrieve image data")

    # データベース接続を閉じる
    db.close()

if __name__ == "__main__":
    test_image_registration()