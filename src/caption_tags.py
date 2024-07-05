import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from PIL import Image
import logging
from module.api_utils import OpenAIApi, APIError
from module.cleanup_txt import clean_format, clean_tags, clean_caption

class ImageAnalyzer:
    """
    タグ、キャプション、スコアリングなどの画像分析タスクを実行します。

    このクラスは、画像のキャプション生成、タグ生成、スコアリングなどの
    画像分析タスクを実行します。OpenAI APIを使用して画像分析を行います。
    """

    def __init__(self, models: List[Dict[str, str]]):
        """
        ImageAnalyzerクラスのコンストラクタ。

        Args:
            config (Dict): アプリケーションの設定情報を含む辞書
        """
        self.logger = logging.getLogger(__name__)
        self.api_client = None
        self.batch_payloads = []

    def _initialize_openai_api(self, prompt: str, additional_prompt: str, apikey: str, model: str) -> OpenAIApi:
        """
        OpenAI APIクライアントを初期化します。

        Returns:
            OpenAIApi: 初期化されたAPIクライアントオブジェクト
        """
        if additional_prompt:
            prompt = prompt + "\n\n" + additional_prompt

        return OpenAIApi(
            apikey,
            model,
            prompt,
            image_data=None
        )

    def initialize(self, prompt: str, additional_prompt: str, apikey: str, model: str, models_config: List[Dict[str, str]]):
        """
        ImageAnalyzerクラスを初期化します。

        Args:
            prompt (str): APIリクエストのプロンプト
            additional_prompt (str): 追加のAPIリクエストプロンプト
            apikey (str): OpenAI APIキー
            model (str): 使用するOpenAIモデル
            models_config (List[Dict[str, str]]): モデル設定のリスト。各辞書は'name'と'type'キーを含む。
        """
        self.models = {model['name']: model['type'] for model in models_config}
        self.vision_model = next((name for name, type in self.models.items() if type == 'vision'), None)
        self.score_models = [name for name, type in self.models.items() if type == 'score']

        if not self.vision_model:
            raise ValueError("Vision modelが設定ファイルで指定されていません。")

        if not self.score_models:
            self.logger.warning("Score modelが設定ファイルで指定されていません。スコア計算は行われません。")

        try:
            self.api_client = self._initialize_openai_api(prompt, additional_prompt, apikey, model)
        except Exception as e:
            self.logger.error(f"OpenAI APIクライアントの初期化中にエラーが発生しました: {str(e)}")
            raise

    def get_existing_annotations(self, image_path: Path) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """
        画像の参照元ディレクトリから既存のタグとキャプションを取得。

        Args:
            image_path (Path): 画像ファイルのパス

        Returns:
            Dict[str, List[Dict[str, str]]]: 'tags'と'captions'をキーとする辞書。
            None : 既存のアノテーションが見つからない場合
        例:
        {
            'tags': [
                {'tag': 'nature'},
                {'tag': 'mountain'}
            ],
            'captions': [
                {'caption': 'A beautiful mountain landscape'}
            ]
        }
        """
        existing_annotations = {'tags': [],
                                'captions': []
                                }
        tag_path = image_path.with_suffix('.txt')
        caption_path = image_path.with_suffix('.caption')

        try:
            if tag_path.exists():
                existing_annotations['tags'] = self._read_annotations(tag_path, 'tag')
            if caption_path.exists():
                existing_annotations['captions'] = self._read_annotations(caption_path, 'caption')

            if not existing_annotations['tags'] and not existing_annotations['captions']:
                self.logger.info(f"既存アノテーション無し: {image_path}")
                return None

        except Exception as e:
            self.logger.warning(f"アノテーションファイルの読み込み中にエラーが発生しました: {str(e)}")

        return existing_annotations

    def _read_annotations(self, file_path: Path, key: str) -> List[Dict[str, str]]:
        """
        指定されたファイルからアノテーションを読み込み、辞書のリストとして返す。

        Args:
            file_path (Path): 読み込むファイルのパス
            key (str): 辞書のキー ('tag' または 'caption')

        Returns:
            List[Dict[str, str]]: アノテーションの辞書リスト
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            clean_data = clean_format(f.read())
            items = clean_data.strip().split(',')
            annotations = []
            for item in items:
                stripped_item = item.strip()
                if stripped_item:
                    annotations.append({key: stripped_item})
            return annotations

    def create_batch_request(self, image_path: Path):
        """#imageを走査してBachAPIのリクエストjsonlを生成

        Args:
            image_path (Path): 処理済み画像のパス

        Returns:
            batch_payload (List[Dict[str, Any]): バッチリクエストのペイロード
        """
        self.api_client.set_image_data(image_path)
        payload = self.api_client.generate_payload(image_path, batch_jsonl_flag=True)
        return payload

    def analyze_image(self, image_path: Path) -> Dict[str, Any]:
        """
        指定された画像を分析し、結果を返します。
        Args:
            image_path (Path): 分析する画像のファイルパス
        Returns:
            Dict[str, Any]: 分析結果を含む辞書（タグ、キャプション、スコア）
        """
        try:
            self.api_client.set_image_data(image_path)
            headers, payload = self.api_client.generate_payload()
            response = self.api_client.analyze_single_image(payload, headers)
            analysis_result = self._process_response(response, image_path)
            return analysis_result
        except APIError as e:
            self.logger.error("API処理中にエラーが発生しました（画像: %s）: %s", image_path, str(e))
            return {'error': str(e), 'image_path': str(image_path)}
        except Exception as e:
            self.logger.error("画像処理中に予期せぬエラーが発生しました（画像: %s）: %s", image_path, str(e))
            return {'error': str(e), 'image_path': str(image_path)}

    def _process_response(self, image_path: Path, content: str) -> Dict[str, Any]:
        """APIレスポンスを処理し、タグ、キャプション、抽出します。"""
        try:
            content = clean_format(content)
            tags_str, caption = self._extract_tags_and_caption(content, str(image_path))

            # タグを分割し、各タグをトリムして空のタグを除外
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            return {
                'tags': [{'tag': tag, 'model': self.vision_model} for tag in tags],
                'captions': [{'caption': caption, 'model': self.vision_model}],
                'image_path': str(image_path)
            }
        except Exception as e:
            self.logger.error("レスポンス処理中にエラーが発生しました（画像: %s）: %s", image_path, str(e))
            raise

    def _extract_tags_and_caption(self, content: str, image_key: str) -> Tuple[str, str]:
        """
        APIレスポンスからタグとキャプションを抽出します。

        Args:
            content (str): APIレスポンスの内容
            image_key (str): 画像のキー（ファイルパス）

        Returns:
            Tuple[List[str], str]: 抽出されたタグのリストとキャプション
        """
        tags_index = content.lower().find('tags:')
        caption_index = content.lower().find('caption:')

        if tags_index == -1 and caption_index == -1:
            self.logger.error("画像 %s の処理に失敗しました。タグまたはキャプションが見つかりません。", image_key)
            return "", ""

        tags_text = content[tags_index + len('tags:'):caption_index].strip() if tags_index != -1 else ""
        caption_text = content[caption_index + len('caption:'):].strip() if caption_index != -1 else ""

        return clean_tags(tags_text), clean_caption(caption_text)

    def _calculate_score(self, tags: List[str], caption: str) -> float:
        """
        タグとキャプションに基づいて画像スコアを計算します。

        Args:
            tags (List[str]): 画像のタグリスト
            caption (str): 画像のキャプション

        Returns:
            float: 計算されたスコア（0.0から1.0の範囲）
        """
        # ここにスコアリングロジックを実装
        # これは簡単な例で、より洗練された方法に置き換えることができます
        tag_score = len(tags) * 0.1  # タグ1つにつき0.1ポイント
        caption_score = len(caption.split()) * 0.05  # キャプションの単語1つにつき0.05ポイント
        return min(tag_score + caption_score, 1.0)  # スコアの上限を1.0に設定 TODO: そのうちやる

    def load_batch_data(self, batch_response_dir: Path) -> dict:
        """
        バッチ処理されたJSONLファイルを読み込む

        Args:
            batch_response_dir (Path): バッチ処理結果のJSONLファイルが格納されているディレクトリ

        Returns:
            dict: custom_idをキー、分析結果を値とする辞書
        """
        batch_data = {}
        if batch_response_dir.is_dir():
            for jsonl_file in batch_response_dir.glob('*.jsonl'):
                with open(jsonl_file, 'r') as f:
                    for line in f:
                        data = json.loads(line)
                        if 'custom_id' in data and 'response' in data and 'body' in data['response']:
                            custom_id = data['custom_id']
                            content = data['response']['body']['choices'][0]['message']['content']
                            batch_data[custom_id] = content
        return batch_data

    def get_batch_analysis(self, batch_data: dict[str, str], processed_path: Path) -> dict:
        """

        Args:
            batch_data (dict): バッチ処理結果のデータ
            processed_path (Path): 処理後の画像のパス

        Returns:
            dict: 画像の分析結果（タグとキャプション）
        """
        # processed_pathから custom_id を取得
        custom_id = processed_path.stem
        for batch_data in batch_data:
            if custom_id in batch_data['custom_id']:
                content = batch_data['response']['body']['choices'][0]['message']['content']
                return self._process_response(processed_path, content)
        return None


# 画像処理のテスト
if __name__ == "__main__":
    import toml
    config = toml.load('processing.toml')
    image_path = Path(r'testimg\1_img\file02.png')
    Ia = ImageAnalyzer()
    Ia.initialize(config['prompts']['main'], config['prompts']['additional'], config['api']['openai_api_key'], config['api']['openai_model'])
    result = Ia.analyze_image(image_path)
    print(f"キャプション: {result['caption']}")
    print(f"タグ: {result['tags']}")
    print(f"スコア: {result['score']}")