"""
LIONとCAFEのモデルを用いて評価するスクリプト
"""
# test_scorer.py
from pathlib import Path
from score_module.scorer import AestheticScorer
from PIL import Image
def test_scorer(scorer: AestheticScorer):
    image_path = Path("testimg\\1_img\\1-370.jpg")  # テスト用の画像パスを指定
    img = Image.open(image_path)
    laion_aesthetic = scorer.score(img, model_type="laion")
    cafe_aesthetic = scorer.score(img, model_type="cafe")
    print(f"LAION Aesthetic score: {laion_aesthetic}")

    print(f"CAFE Aesthetic score: {cafe_aesthetic}")

if __name__ == "__main__":
    score = AestheticScorer()
    test_scorer(score)
