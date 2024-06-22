import unittest
from pathlib import Path
from PIL import Image
from module.db import ImageDatabase
import time
import re
import os

class TestImageDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_path = Path('test_image_dataset.db')
        cls.image_folder = Path(r'testimg\1_img')
        if not cls.image_folder.exists():
            raise ValueError(f"Test image folder does not exist: {cls.image_folder}")
        # 正規表現パターン: .jpg, .jpeg, .png, .webp で終わるファイル
        image_pattern = r'.*\.(jpg|jpeg|png|webp)$'
        cls.image_files = [
            p for p in cls.image_folder.glob('**/*')
            if re.search(image_pattern, str(p), re.IGNORECASE)
        ]
        if not cls.image_files:
            raise ValueError(f"No image files (jpg, jpeg, png, webp) found in {cls.image_folder}")
        print(f"Found {len(cls.image_files)} image files in {cls.image_folder}")
        for file in cls.image_files[:5]:  # 最初の5つのファイルのみを表示
            print(f"  - {file.name}")

    def setUp(self):
        if self.test_db_path.exists():
            os.remove(self.test_db_path)
        self.db = ImageDatabase(str(self.test_db_path))
        self.db.create_tables()

    def tearDown(self):
        self.db.close()
        if self.test_db_path.exists():
            try:
                os.remove(self.test_db_path)
            except PermissionError:
                print(f"Warning: Unable to delete {self.test_db_path}. It may be in use.")

    def test_single_image_registration(self):
        image_path = self.image_files[0]
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower()

        image_id, image_uuid = self.db.add_image(width, height, format)
        image_data = self.db.get_image(image_id)

        self.assertIsNotNone(image_data)
        self.assertEqual(image_data['width'], width)
        self.assertEqual(image_data['height'], height)
        self.assertEqual(image_data['format'], format)

    def test_multiple_image_registration(self):
        added_images = []
        for image_file in self.image_files[:5]:
            with Image.open(image_file) as img:
                width, height = img.size
                format = img.format.lower()
            image_id, _ = self.db.add_image(width, height, format)
            added_images.append(image_id)

        for image_id in added_images:
            self.assertIsNotNone(self.db.get_image(image_id))

    def test_update_image(self):
        image_path = self.image_files[0]
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower()

        image_id, _ = self.db.add_image(width, height, format)
        self.db.update_image(image_id, width=width+100, height=height+100)
        updated_image = self.db.get_image(image_id)

        self.assertEqual(updated_image['width'], width+100)
        self.assertEqual(updated_image['height'], height+100)

    def test_delete_image(self):
        image_path = self.image_files[0]
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower()

        image_id, _ = self.db.add_image(width, height, format)
        self.assertTrue(self.db.delete_image(image_id))
        self.assertIsNone(self.db.get_image(image_id))

    def test_get_nonexistent_image(self):
        self.assertIsNone(self.db.get_image(9999))

    def test_get_all_images(self):
        for image_file in self.image_files[:5]:
            with Image.open(image_file) as img:
                width, height = img.size
                format = img.format.lower()
            self.db.add_image(width, height, format)

        all_images = self.db.get_all_images()
        self.assertEqual(len(all_images), 5)

    def test_performance(self):
        image_path = self.image_files[0]
        with Image.open(image_path) as img:
            width, height = img.size
            format = img.format.lower()

        start_time = time.time()
        for _ in range(1000):
            self.db.add_image(width, height, format)
        end_time = time.time()

        print(f"Time taken to add 1000 images: {end_time - start_time} seconds")
        self.assertLess(end_time - start_time, 10)  # 10秒以内に完了すべき

if __name__ == '__main__':
    unittest.main()