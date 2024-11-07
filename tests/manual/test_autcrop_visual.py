import pytest
import numpy as np
from editor.image_processor import AutoCrop
import matplotlib.pyplot as plt
import cv2


def display_images(original_img, cropped_img, title="Original and Cropped Images"):
    """
    元の画像とクロップ後の画像を並べて表示します。

    Args:
        original_img (PIL.Image.Image): 元の画像。
        cropped_img (PIL.Image.Image): クロップ後の画像。
        title (str): グラフ全体のタイトル。
    """
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))

    # 元の画像を表示
    axes[0].imshow(original_img)
    axes[0].set_title("Original Image")
    axes[0].axis("off")

    # クロップ後の画像を表示
    axes[1].imshow(cropped_img)
    axes[1].set_title("Cropped Image")
    axes[1].axis("off")

    # 全体のタイトルを設定
    plt.suptitle(title)
    plt.show()


def test_image_cropping(crop_test_images):
    """
    テスト用画像のすべてのパターンをイテレートし、クロップ前後の画像を表示して比較する。
    """
    for pattern, original_img in crop_test_images.items():
        # クロップ処理を行う
        cropped_img = AutoCrop.auto_crop_image(original_img)

        # クロップ前後の画像を表示して比較
        display_images(original_img, cropped_img, title=f"{pattern.capitalize()} Cropping Test")


import cv2


def debug_get_crop_area(np_image: np.ndarray):
    """
    各ステップでの画像を収集し、後でまとめて表示する。
    :param np_image: OpenCV形式の画像
    :return: クロップ領域と各ステップの画像のリスト
    """
    images = {}
    try:
        # ステップ 1: 元画像
        images["Original Image"] = np_image

        # ステップ 2: グレースケール変換
        gray_image = cv2.cvtColor(np_image, cv2.COLOR_BGR2GRAY)
        images["Gray Image"] = gray_image

        # ステップ 3: 補色背景の生成
        complementary_color = [255 - np.mean(np_image[..., i]) for i in range(3)]
        background = np.full(np_image.shape, complementary_color, dtype=np.uint8)
        images["Complementary Background"] = background

        # ステップ 4: 差分計算
        diff = cv2.absdiff(np_image, background)
        images["Difference Image"] = diff

        # ステップ 5: 差分をグレースケール化
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        images["Gray Difference"] = gray_diff

        # ステップ 6: ブラー処理 (カーネルサイズを調整)
        blurred_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)
        images["Blurred Difference"] = blurred_diff

        # ステップ 7: 適応的しきい値処理
        thresh = cv2.adaptiveThreshold(
            blurred_diff,  # グレースケール化された差分画像を使う
            255,  # 最大値（白）
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # 適応的しきい値の種類（ガウス法）
            cv2.THRESH_BINARY,  # 2値化（白か黒）
            11,  # ピクセル近傍のサイズ (奇数で指定)
            2,  # 平均値または加重平均から減算する定数
        )
        images["Threshold Image"] = thresh  # 適応的しきい値画像を保存

        # ステップ 8: エッジ検出
        edges = cv2.Canny(thresh, threshold1=30, threshold2=100)
        images["Edge Detection"] = edges

        # ステップ 9: 輪郭検出
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour_image = np_image.copy()
        cv2.drawContours(contour_image, contours, -1, (0, 255, 0), 2)
        images["Detected Contours"] = contour_image

        if contours:
            # 輪郭が見つかった場合
            x_min, y_min, x_max, y_max = np_image.shape[1], np_image.shape[0], 0, 0
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                x_min, y_min = min(x_min, x), min(y_min, y)
                x_max, y_max = max(x_max, x + w), max(y_max, y + h)

            # マスクを作成し、内側領域のみを残す
            mask = np.zeros(np_image.shape[:2], dtype=np.uint8)
            for contour in contours:
                cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

            # 内側の領域を取り出す
            masked_image = cv2.bitwise_and(np_image, np_image, mask=mask)
            images["Masked Image"] = masked_image

            # クロップ領域を計算
            y_coords, x_coords = np.where(mask == 255)
            if len(x_coords) > 0 and len(y_coords) > 0:
                x, y = np.min(x_coords), np.min(y_coords)
                w, h = np.max(x_coords) - x + 1, np.max(y_coords) - y + 1

                extra_crop_margin = 5
                # クロップ領域に余分なピクセルを削る
                x_min = max(0, x + extra_crop_margin)
                y_min = max(0, y + extra_crop_margin)
                x_max = min(np_image.shape[1], x + w - extra_crop_margin)
                y_max = min(np_image.shape[0], y + h - extra_crop_margin)

                # クロップ領域を可視化
                crop_visualization = np_image.copy()
                cv2.rectangle(crop_visualization, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
                images["Crop Area"] = crop_visualization

                # 領域でクロップ
                cropped_image = np_image[y_min:y_max, x_min:x_max]
                images["Cropped Image"] = cropped_image

                return (x_min, y_min, x_max - x_min, y_max - y_min), images
            else:
                print("No valid crop region found.")
        else:
            print("No contours found")

        # 輪郭が見つからない場合や適切な輪郭がない場合は元の画像を返す
        images["Cropped Image"] = np_image
        return None, images

    except Exception as e:
        print(f"Error during cropping: {e}")
        return None, images


# テスト関数
def test_debug_get_crop_area(crop_test_images):
    """
    各画像に対してクロップ処理を実行し、結果を一つのウィンドウに表示する。
    """
    images_dict = crop_test_images
    for image_name, image in images_dict.items():
        np_image = np.array(image)
        crop_area, images = debug_get_crop_area(np_image)

        # 画像を一つのウィンドウに表示
        num_steps = len(images)
        cols = 5  # 列数
        rows = (num_steps + cols - 1) // cols  # 行数計算
        plt.figure(figsize=(15, 5 * rows))
        for i, (title, img) in enumerate(images.items()):
            plt.subplot(rows, cols, i + 1)
            if len(img.shape) == 2:
                plt.imshow(img, cmap="gray")
            else:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                plt.imshow(img_rgb)
            plt.title(title)
            plt.axis("off")
        plt.suptitle(f"Processing Steps for {image_name}", fontsize=16)
        plt.tight_layout()
        plt.show()

        if crop_area:
            print(f"{image_name}: Crop Area - {crop_area}")
        else:
            print(f"{image_name}: No crop area detected.")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
