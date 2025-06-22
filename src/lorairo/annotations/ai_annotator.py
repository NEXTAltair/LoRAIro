from image_annotator_lib import PHashAnnotationResults, annotate, list_available_annotators
from PIL import Image

from lorairo.utils.log import logger


class AiAnnotatorError(Exception):
    """AIアノテーションライブラリ連携時のエラー基底クラス"""

    pass


def get_available_annotator_models() -> list[str]:
    """
    image-annotator-lib から利用可能なアノテーターモデル名のリストを取得する。

    Returns:
        利用可能なモデル名のリスト。

    Raises:
        AiAnnotatorError: ライブラリからのリスト取得中にエラーが発生した場合。
    """
    logger.info("image-annotator-lib から利用可能なアノテーターモデル名リストを取得します。")
    try:
        models = list_available_annotators()
        logger.info(f"利用可能なアノテーターモデル名リストを取得しました: {models}")
        return models
    except Exception as e:
        logger.exception(
            "image-annotator-lib から利用可能なアノテーターモデル名リストの取得中にエラーが発生しました。"
        )
        raise AiAnnotatorError(f"利用可能なアノテーターモデル名リストの取得エラー: {e}") from e


def call_annotate_library(
    images_list: list[Image.Image],
    model_name_list: list[str],
    phash_list: list[str],
) -> PHashAnnotationResults:
    """
    外部の image-annotator-lib を呼び出して画像アノテーションを実行する。

    Args:
        images_list: アノテーション対象の PIL Image オブジェクトのリスト。
        model_name_list: 使用する AI モデル名のリスト。
        phash_list: 画像の pHash 値のリスト。

    Returns:
        アノテーション結果を含む辞書。
        キーは画像の pHash、値はモデル名をキーとした結果辞書の辞書。
        例: {'pHash1': {'modelA': {'tags': [...], 'formatted_output': ..., 'error': None}}}

    Raises:
        ValueError: images_list または model_name_list が空の場合。
        AiAnnotatorError: ライブラリ呼び出し中にエラーが発生した場合。
    """
    if not images_list:
        logger.error("アノテーション対象の画像リストが空です。")
        raise ValueError("images_listは空にすることはできません。")
    if not model_name_list:
        logger.error("使用するモデルリストが空です。")
        raise ValueError("model_name_listは空にすることはできません。")

    logger.info(
        f"{len(images_list)} 件の画像について、モデル {model_name_list} を使用して"
        " image-annotator-lib によるアノテーションを開始します。"
    )

    try:
        results = annotate(
            images_list=images_list,
            model_name_list=model_name_list,
            phash_list=phash_list,
        )
        logger.info("image-annotator-lib によるアノテーションが正常に完了しました。")
        return results
    except Exception as e:
        # image-annotator-lib 内部で発生した予期せぬエラー
        logger.exception("image-annotator-lib の呼び出し中に予期しないエラーが発生しました。")
        raise AiAnnotatorError(f"アノテーションライブラリ実行エラー: {e}") from e


if __name__ == "__main__":
    models = get_available_annotator_models()
    print(models)

    image = Image.open("tests/resources/img/1_img/file01.webp")
    print(call_annotate_library([image], [models[0]], [""]))
