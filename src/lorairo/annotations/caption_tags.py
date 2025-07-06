import re
from pathlib import Path
from typing import Any

from genai_tag_db_tools.utils.cleanup_str import TagCleaner

from ..utils.log import logger


class ImageAnalyzer:
    """
    画像のキャプション生成、タグ生成などの
    画像分析タスクを実行
    """

    def __init__(self):
        self.tag_cleaner = TagCleaner()
        self.format_name = "unknown"

    def initialize(self, models_config: tuple[dict, dict]):
        """
        ImageAnalyzerクラスのコンストラクタ。

        Args:
            api_client_factory (APIClientFactory): API名とAPIクライアントの対応辞書
            models_config (tuple[dict, dict]): (vision_models, score_models) のタプル
        """
        self.vision_models, self.score_models = models_config

    # NOTE: get_existing_annotations メソッドは削除されました
    # ExistingFileReader クラスを使用してください

    # NOTE: _read_annotations メソッドは削除されました
    # ExistingFileReader クラスを使用してください

    # NOTE: analyze_image メソッドは削除されました
    # image-annotator-lib を直接使用してください

    # NOTE: _process_response メソッドは削除されました
    # image-annotator-lib が構造化データを直接返すため不要

    # TODO: アノテーターライブラリはバッチAPIには非対応なので対応方法を考える
    # def create_batch_request(self, image_path: Path, model_name: str) -> dict[str, Any]:
    #     """単一の画像に対するバッチリクエストデータを生成します。

    #     Args:
    #         image_path (Path): 処理済み画像のパス
    #         model_name (str): 使用するモデル名

    #     Returns:
    #         dict[str, Any]: バッチリクエスト用のデータ
    #     """
    #     api_client, api_provider = self.api_client_factory.get_api_client(model_name)
    #     if not api_client:
    #         raise ValueError(f"APIクライアント '{api_provider}' が見つかりません。")

    #     api_client.set_image_data(image_path)
    #     api_client.generate_payload(image_path, model_name)
    #     return api_client.create_batch_request(image_path)

    # NOTE: _extract_tags_and_caption メソッドは削除されました
    # image-annotator-lib が構造化データを直接返すため不要

    def get_batch_analysis(self, batch_results: dict[str, str], processed_path: Path):
        """
        バッチ処理結果から指定された画像の分析結果を取得します。

        Args:
            batch_results (dict[str, str]): バッチ処理結果 (画像パスをキー、分析結果を値とする辞書)
            processed_path (Path): 処理後の画像のパス

        Returns:
            dict: 画像の分析結果(タグとキャプション)
        """
        # processed_pathから custom_id を取得
        custom_id = processed_path.stem
        content = batch_results.get(custom_id)
        if content:
            # NOTE: _process_response メソッドが削除されたため、
            # この機能は image-annotator-lib を直接使用するように変更が必要
            logger.warning("get_batch_analysis は削除されたメソッドを使用しているため動作しません")
            return None
