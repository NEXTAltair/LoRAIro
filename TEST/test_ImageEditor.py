"""
リサイズの計算が正しいかどうかをテストするためのユニットテスト
"""
import unittest
from ImageEditor import find_matching_resolution

class TestImageEditor(unittest.TestCase):
    def test_find_matching_resolution(self):
        # Test case 1: Matching resolution found
        original_width = 2432
        original_height = 1664
        max_dimension = 1024
        expected_resolution = (1216, 832)
        self.assertEqual(find_matching_resolution(original_width, original_height, max_dimension), expected_resolution)

        # Test case 2: No matching resolution found
        original_width = 1920
        original_height = 1080
        max_dimension = 1024
        expected_resolution = None
        self.assertEqual(find_matching_resolution(original_width, original_height, max_dimension), expected_resolution)

        # Test case 3: Multiple matching resolutions, closest to max_dimension**2
        original_width = 2000
        original_height = 2000
        max_dimension = 1024
        expected_resolution = (1024, 1024)
        self.assertEqual(find_matching_resolution(original_width, original_height, max_dimension), expected_resolution)

        # Test case 4: Multiple matching resolutions, not closest to max_dimension**2
        original_width = 800
        original_height = 600
        max_dimension = 1024
        expected_resolution = None
        self.assertEqual(find_matching_resolution(original_width, original_height, max_dimension), expected_resolution)

if __name__ == '__main__':
    unittest.main()