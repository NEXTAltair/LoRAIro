"""
タグクリーンナップのテスト
未だにエスケープの処理が甘いかもしれない
    """

import unittest
from cleanup_txt import clean_tags, clean_format, clean_caption

class TestTagCaptionCleaner(unittest.TestCase):
    
    def test_clean_format(self):
        text = "**Tags** :Hello, World! (TEST)\naa\u2014aa. "
        expected = r"Tags :Hello, World! \(TEST\), aa aa, "
        result = clean_format(text)
        self.assertEqual(result, expected, "文字の置き換えができてない")

    def test_remove_duplicates(self):
        tags = "girl, long hair, long hair, blue eyes, blue eyes, white shirt, shirt"
        expected = "girl, long hair, blue eyes, white shirt"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "重複してるタグをちゃんと消せてない")

    def test_handle_special_chars(self):
        tags = "girl, ^_^, long_hair, short hair, ,"
        expected = "girl, ^_^, long hair, short hair"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "特殊文字")

    def test_clean_clor_tags(self):
        tags = "bleu eyes, eyes, white shirt, shirt, green hair, hair, black kimono, kimono"
        expected = "bleu eyes, white shirt, green hair, black kimono"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "色のタグ")

    def test_multiple_patterns(self):
        tags = "2girls, ponytail, braid, braid, red hair, blue eyes, long hair, ,"
        expected = "2girls, long hair"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "複数パターン")

    def test_keep_important_tags(self):
        tags = "girl, bob cut, bob cut, hime cut, ,"
        expected = "girl, bob cut, hime cut"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "重複削除失敗")

    def test_danbooru_tags(self):
        tags = "kitasan black (umamusume)"
        expected = r"kitasan black \(umamusume\)"
        result = clean_tags(tags)
        self.assertEqual(result, expected, "意図した結果ではない")


class TestCaptionCleaning(unittest.TestCase):
    def test_clean_caption(self):
        cases = [
            ("Here is an anime anime scene", "Here is an anime scene"),
            ("This young girl is playing", "This girl is playing"),
            ("The cartoon female is dancing", "The girl is dancing"),
            ("A group of cartoon women are here", "A group of girls are here"),
            ("There are many people in this scene", "There are many girls in this scene"),
            ("Look at this person walking", "Look at this girl walking"),
            ("The lady walks her dog", "The girl walks her dog"),
            ("a cartoon drawing of a landscape", "a drawing of a landscape")
        ]

        for inp, expected in cases:
            self.assertEqual(clean_caption(inp), expected)

if __name__ == '__main__':
    unittest.main()
