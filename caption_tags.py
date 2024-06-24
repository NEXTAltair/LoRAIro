from pathlib import Path
from PIL import Image
from typing import Dict, List, Tuple, Optional, Any
from module.api_utils import OpenAIApi, APIError
from module.log import setup_logger, get_logger
from module.cleanup_txt import clean_format, clean_tags, clean_caption
class CaptionTagGenerator:
    def __init__(self, api_client, config: Dict):
        """
        キャプションとタグ生成器の初期化

        Args:
            api_client: 初期化済みのAPIクライアント（OpenAIApiまたはGoogleAI）
        """
        self.api_client = api_client
        self.config = config
        self._setup_logger()
        self.logger = get_logger(__name__)

    def _setup_logger(self):
        # log.pyのsetup_logger関数を呼び出す
        setup_logger(
            log_level=self.config.get('log_level', 'INFO'),
            log_file=self.config.get('log_file', 'caption_tag_generator.log')
        )

    def process_image(self, image_path: Path) -> Tuple[str, str]:
        """画像を処理してキャプションとタグを生成する"""
        try:
            self.api_client.set_image_data(image_path)
            return self._generate_caption_and_tags(image_path)
        except APIError as e:
            self.logger.error(f"API Error processing image {image_path}: {str(e)}")
            return {'error': str(e), 'image_path': str(image_path)}
        except Exception as e:
            self.logger.error(f"API Error processing image {image_path}: {str(e)}")
            return {'error': str(e), 'image_path': str(image_path)}

    def _generate_caption_and_tags(self, image_path: Path) -> Tuple[str, str]:
        """APIを使用してキャプションとタグを生成"""
        # ペイロードの生成（画像データは既に設定済み）
        headers, payload = self.api_client.generate_payload()
        response = self.api_client.generate_immediate_response(payload, headers)
        # レスポンスの処理
        result = self._parse_response(response, image_path)
        return result         # APIリクエストの実行

    def _parse_response(self, response: Dict, image_path: Path) -> Tuple[str, str]:
        """API応答を解析してキャプションとタグを抽出"""
        image_key = str(image_path)
        if isinstance(self.api_client, OpenAIApi):
            content = response['choices'][0]['message']['content']
            content = clean_format(content)
            return self._extract_tags_and_caption(content, image_key)
        # elif isinstance(self.api_client, GoogleAI):
        #     return response
        else:
            raise ValueError("Unsupported API response format")

    def _extract_tags_and_caption(self, content: str, image_key: str) -> Tuple[str, str]:
        """タグとキャプションを抽出する
        'Tags:' か 'Caption:'が含まれていない場合は弾かれているので例外処理
        """
        # 'tags:' と 'caption:' が何番目に含まれているかを見つける
        tags_index = content.find('tags:')
        caption_index = content.find('caption:')
        if tags_index == -1 and caption_index == -1:
            error_msg = (
                f"画像 {image_key} の処理失敗。"
                "考えられる原因: 不適切なコンテンツ（エロ画像やグロ画像など）、"
            )
            self.logger.error(f"{error_msg}\nAPI response: {content}")
            return [], "" # タグとキャプションが見つからない場合は空のリストと空の文字列を返す

        # タグとキャプションのテキストを抽出
        tags_text = content[tags_index + len('tags:'):caption_index].strip()
        caption_text = content[caption_index + len('caption:'):].strip()
        return clean_tags(tags_text), clean_caption(caption_text)

    @staticmethod
    def _image_to_base64(img: Image.Image) -> str:
        """画像をBase64エンコードされた文字列に変換"""
        import io
        import base64
        buffered = io.BytesIO()
        img.save(buffered, format="WEBP")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

def initialize_api(config: Dict):
    """設定に基づいてAPIクライアントを初期化"""
    prompt = config['prompts']['main'] + "\n\n" + config['prompts']['additional']

    if config: #['api']['type'] == 'openai':
        return OpenAIApi(
            config['api']['openai_api_key'],
            config['api']['openai_model'],
            prompt,
            None  # image_dataは後で設定します
        )
    # TODO: 他のAPIタイプをサポートする場合は、ここに追加
    # elif self.config['api_type'] == 'google':
    #     return GoogleAI(
    #         self.config['google_api_key'],
    #         None,  # image_dataは後で設定します
    #         self.config.get('additional_prompt', '')
    #     )
    else:
        raise ValueError(f"Unsupported API type: {config['api_type']}")

def process_image(image_path: Path, config: Dict) -> Dict[str, Any]:
    """
    単一画像を処理するためのヘルパー関数

    Args:
        image_path (Path): 処理する画像のパス
        config (Dict): 設定情報

    Returns:
        Dict[str, Any]: 処理結果を含む辞書
    """
    api_client = initialize_api(config)
    generator = CaptionTagGenerator(api_client, config)
    tags, caption = generator.process_image(image_path)
    return tags, caption

# 単一画像の処理テスト
if __name__ == "__main__":
    import toml
    # 設定ファイルを読み込む
    config = toml.load('processing.toml')
    image_path = Path(r'testimg\10_shira\1149_599.webp')

    tags, caption = process_image(image_path, config)
    print(f"Caption: {caption}")
    print(f"Tags: {tags}")
