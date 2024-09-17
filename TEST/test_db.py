import unittest
import os
from module.db import ImageDatabase

class TestImageDatabase(unittest.TestCase):
    def setUp(self):
        self.db_name = 'test_image_dataset.db'
        self.db = ImageDatabase(self.db_name)
        self.db.create_tables()

    def tearDown(self):
        self.db.close()
        os.remove(self.db_name)

    def test_add_and_get_image(self):
        image_id, image_uuid = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        self.assertIsNotNone(image_id)
        self.assertIsNotNone(image_uuid)

        image = self.db.get_image(image_id)
        self.assertIsNotNone(image)
        self.assertEqual(image['original_width'], 100)
        self.assertEqual(image['original_height'], 100)
        self.assertEqual(image['original_format'], 'png')
        self.assertEqual(image['uuid'], image_uuid)

    def test_update_image(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        updated = self.db.update_image(image_id, original_width=200, original_height=200, original_format='jpg')
        self.assertTrue(updated)

        image = self.db.get_image(image_id)
        self.assertEqual(image['original_width'], 200)
        self.assertEqual(image['original_height'], 200)
        self.assertEqual(image['original_format'], 'jpg')

    def test_delete_image(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        deleted = self.db.delete_image(image_id)
        self.assertTrue(deleted)

        image = self.db.get_image(image_id)
        self.assertIsNone(image)

    def test_get_all_images(self):
        self.db.add_image(width=100, height=100, format='png', file_path='path/to/image1.png', color_profile='sRGB', has_alpha=False)
        self.db.add_image(width=200, height=200, format='jpg', file_path='path/to/image2.jpg', color_profile='sRGB', has_alpha=True)

        images = self.db.get_all_images()
        self.assertEqual(len(images), 2)

    def test_add_processed_image(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        processed_id = self.db.add_processed_image(image_id, 'path/to/processed.jpg', 200, 200, 'jpg')
        self.assertIsNotNone(processed_id)

    def test_add_model(self):
        model_id = self.db.add_model('TestModel', 'Classification')
        self.assertIsNotNone(model_id)

    def test_add_tags(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        model_id = self.db.add_model('TestModel', 'Classification')
        self.db.add_tags(image_id, model_id, ['tag1', 'tag2', 'tag3'])

        annotations = self.db.get_image_annotations(image_id)
        self.assertEqual(len(annotations['tags']), 3)

    def test_add_caption(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        model_id = self.db.add_model('TestModel', 'Caption')
        caption_id = self.db.add_caption(image_id, model_id, 'This is a test caption')
        self.assertIsNotNone(caption_id)

        annotations = self.db.get_image_annotations(image_id)
        self.assertEqual(len(annotations['captions']), 1)
        self.assertEqual(annotations['captions'][0]['caption'], 'This is a test caption')

    def test_add_score(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        model_id = self.db.add_model('TestModel', 'Score')
        score_id = self.db.add_score(image_id, model_id, 0.95)
        self.assertIsNotNone(score_id)

        annotations = self.db.get_image_annotations(image_id)
        self.assertEqual(len(annotations['scores']), 1)
        self.assertAlmostEqual(annotations['scores'][0]['score'], 0.95)

    def test_get_image_annotations(self):
        image_id, _ = self.db.add_image(width=100, height=100, format='png', file_path='path/to/image.png', color_profile='sRGB', has_alpha=False)
        model_id = self.db.add_model('TestModel', 'Mixed')

        self.db.add_tags(image_id, model_id, ['tag1', 'tag2'])
        self.db.add_caption(image_id, model_id, 'Test caption')
        self.db.add_score(image_id, model_id, 0.85)

        annotations = self.db.get_image_annotations(image_id)
        self.assertEqual(len(annotations['tags']), 2)
        self.assertEqual(len(annotations['captions']), 1)
        self.assertEqual(len(annotations['scores']), 1)

if __name__ == '__main__':
    unittest.main()