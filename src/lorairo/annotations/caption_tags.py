from pathlib import Path

from genai_tag_db_tools.utils.cleanup_str import TagCleaner

from ..utils.log import logger


class ImageAnalyzer:
    """
    画像のキャプション生成、タグ生成などの
    画像分析タスクを実行
    """

    def __init__(self) -> None:
        self.tag_cleaner = TagCleaner()
        self.format_name = "unknown"

    def initialize(self, models_config: tuple[dict, dict]) -> None:
        """
        ImageAnalyzerクラスのコンストラクタ。

        Args:
            api_client_factory (APIClientFactory): API名とAPIクライアントの対応辞書
            models_config (tuple[dict, dict]): (vision_models, score_models) のタプル
        """
        self.vision_models, self.score_models = models_config

    def get_batch_analysis(self, batch_results: dict[str, str], processed_path: Path) -> dict | None:
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
            logger.warning("get_batch_analysis は削除されたメソッドを使用しているため動作しません")
            return None
