from pathlib import Path
import json
import math
import logging
from typing import Dict, Any
import google.generativeai as genai
import requests
import base64
import time

def save_jsonline_to_file(batch_payload, jsonl_filename):
    """一行JSONファイルを纏めてJSONLines形式でファイルに保存する

    Args:
        batch_payloads (tuple): 一行のJSONファイルのtuple
        jsonl_filename (str): 保存するファイル名

    Returns:
        jsonl_filename (Path): jsonline形式のファイルpath
    """
    with open(jsonl_filename, 'w', encoding='utf-8') as f:
        for item in batch_payload:
            json.dump(item, f)
            f.write('\n')  # 各JSONオブジェクトの後に改行を追加
    print(f"Data saved to {jsonl_filename}")
    return Path(jsonl_filename)

def split_jsonl(jsonl_path, jsonl_size):
    """JSONLが96MB[OpenAIの制限]を超えないようにするために分割して保存する
        保存先はjsonl_pathのサブフォルダに保存される

    Args:
        jsonl_path (Path): 分割が必要なjsonlineファイルのpath
        jsonl_size (int): 分割が必要なjsonlineファイルのサイズ

    """
    # jsonl_sizeに基づいてファイルを分割
    split_size = math.ceil(jsonl_size / 100663296)
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    lines_per_file = math.ceil(len(lines) / split_size)  # 各ファイルに必要な行数
    split_dir = jsonl_path / "split"
    split_dir.mkdir(parents=True, exist_ok=True)
    split_path = split_dir / split_filename
    for i in range(split_size):
        split_filename = f'instructions_{i}.jsonl'
        with open(split_path, 'w', encoding='utf-8') as f:
            f.writelines(lines[i * lines_per_file:(i + 1) * lines_per_file])

class OpenAIApi:
    SUPPORTED_VISION_MODELS = ["gpt-4-turbo", "gpt-4o"]
    def __init__(self, api_key, model, prompt, image_data=None):
        self.logger = logging.getLogger(__name__)
        self.openai_api_key = api_key
        self.model = model
        self.model_name_check()
        self.prompt = prompt
        self.image_data = image_data
        self.last_request_time = 0
        self.min_request_interval = 1  # 1秒間隔でリクエストを制



    def model_name_check(self):
        """モデルがVision対応か確認"""
        if self.model not in self.SUPPORTED_VISION_MODELS:
            raise ValueError(f"そのModelには非対応: {self.model}. Supported models: {', '.join(self.SUPPORTED_VISION_MODELS)}")

    def set_image_data(self, image_path: Path) -> None:
        """
        APIクライアントに画像データを設定します。

        Args:
            image_path (Path): 画像ファイルのパス

        Raises:
            FileNotFoundError: 指定されたパスに画像ファイルが存在しない場合
            IOError: 画像ファイルの読み込み中にエラーが発生した場合
        """
        try:
            if not image_path.exists():
                raise FileNotFoundError(f"画像ファイルが見つかりません: {image_path}")

            with open(image_path, "rb") as image_file:
                image_binary = base64.b64encode(image_file.read()).decode('utf-8')

            self.image_data = image_binary
            self.logger.debug(f"画像データを正常に設定しました: {image_path}")
        except FileNotFoundError as e:
            self.logger.error(f"画像ファイルが見つかりません: {e}")
            raise
        except IOError as e:
            self.logger.error(f"画像ファイルの読み込み中にエラーが発生しました: {e}")
            raise
        except Exception as e:
            self.logger.error(f"予期せぬエラーが発生しました: {e}")
            raise

    def generate_payload(self,image_path: Path, batch_jsonl_flag=False):
        """
        OpenAI APIに送信するペイロードを生成する。

        Args:
            image_path (Path): 画像ファイルのパス
            batch_jsonl_flag (bool):

        Returns:
            tuple: headers（APIリクエストのヘッダー）, payload（APIに送信するペイロード）
        """
        base64_image = self.image_data
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/webp;base64,{base64_image}",
                            "detail": "high"
                        }}
                    ]
                }
            ],
            "max_tokens": 3000
        }

        if batch_jsonl_flag:
            bach_payload = {
                "custom_id": self.image_data.data[image_path].name,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": payload
            }
            return bach_payload
        return headers, payload

    def analyze_single_image(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        self._wait_for_rate_limit()
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            self.last_request_time = time.time()
            self.check_response(response)
            return response.json()
        except requests.exceptions.Timeout:
            raise APIError("リクエストがタイムアウトしました。後でもう一度お試しください。")
        except requests.exceptions.ConnectionError:
            raise APIError("ネットワーク接続エラーが発生しました。インターネット接続を確認してください。")
        except requests.exceptions.RequestException as e:
            raise APIError(f"リクエスト中にエラーが発生しました: {str(e)}")
        except json.JSONDecodeError:
            raise APIError("APIレスポンスの解析に失敗しました。レスポンスが不正な形式である可能性があります。")

    def _wait_for_rate_limit(self):
        elapsed_time = time.time() - self.last_request_time
        if elapsed_time < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed_time)

    def check_response(self, response):
        if response.status_code == 200:
            return

        error_data = response.json().get('error', {})
        error_message = error_data.get('message', '不明なエラー')

        if response.status_code == 400:
            raise APIError(f"不正なリクエスト: {error_message}", error_type=error_data.get('type'), param=error_data.get('param'), code=response.status_code)
        elif response.status_code == 401:
            raise APIError("認証エラー: 無効なAPIキーです", code=response.status_code)
        elif response.status_code == 403:
            raise APIError("アクセス拒否: このリソースにアクセスする権限がありません", code=response.status_code)
        elif response.status_code == 404:
            raise APIError("リソースが見つかりません: 要求されたリソースが存在しません", code=response.status_code)
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            raise APIError(f"リクエスト制限に達しました: {retry_after}秒後に再試行してください", code=response.status_code)
        elif 500 <= response.status_code < 600:
            raise APIError(f"サーバーエラー: OpenAI側で問題が発生しました (ステータスコード: {response.status_code})", code=response.status_code)
        else:
            raise APIError(f"予期しないステータスコード: {response.status_code}", code=response.status_code)

    def upload_jsonl_file(self, jsonl_path):
        """
        JSONLファイルをOpenAI APIにアップロードする。

        Args:
            jsonl_path (str): アップロードするJSONLファイルのパス

        Returns:
            str: アップロードされたファイルのID
        """
        url = "https://api.openai.com/v1/files"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}"
        }
        files = {
            'file': open(jsonl_path, 'rb')
        }
        data = {
            'purpose': 'batch'
        }
        response = requests.post(url, headers=headers, files=files, data=data, timeout=500)
        if response.status_code == 200:
            print("アップロード成功")
            file_id = response.json().get('id')
            return file_id
        else:
            print(f"アップロード失敗: {response.status_code}")
            print(response.text)
            return None

    def start_batch_processing(self, input_file_id):
        """
        アップロードされたJSONLファイルを使ってバッチ処理を開始する。

        Args:
            input_file_id (str): アップロードされたファイルのID

        Returns:
            dict: APIからのレスポンス
        """
        url = "https://api.openai.com/v1/batches"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "input_file_id": input_file_id,
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h"
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            print("バッチ処理の開始")
            return response.json()
        else:
            print(f"バッチ処理実行失敗 {response.status_code}")
            print(response.text)
            return None

class GoogleAI:
    def __init__(self, google_api_key, image_data, add_prompt):
        """
        Google AI Studioとのインターフェースを作成

        Args:
            google_api_key (str): Google AI StudioのAPIキー。
        """
        self.image_data = image_data
        self.add_prompt = add_prompt
        # Set up the model
        generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
        }

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        genai.configure(api_key=google_api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-latest",
            generation_config=generation_config,
            safety_settings=safety_settings
        )

    def generate_prompt_parts(self, image_path):
        """
        Google AI Studioに送信するプロンプトを作成

        Args:
            image_path (str): アップロードされる画像のパス。

        Returns:
            list: プロンプトの各部分をリストで返
        """
        image = self.image_data.data[image_path]['image']

        prompt_parts = [
            "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \nEach image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. \nFor images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \nFor landscapes or objects, focus on the material, historical context, and any significant features. \nAlways use precise and specific tags—prefer \"gothic cathedral\" over \"building.\" Avoid duplicative tags. \nEach set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. \nAlso, provide a concise 1-2 sentence caption that captures the image's narrative or essence.",
            "image/webp: ",
            "",
            "formatJSON: {\"tags\": \"Tag1, Tag2, Tag3\",  \"caption\": \"This is the caption.\"}",
            "ADDITIONAL_PROMPT: Korean girl in a comic book.",
            "TagsANDCaption: {\"tags\": \"dress, long hair, text, sitting, black hair, blue eyes, heterochromia, flower, high heels, two-tone hair, armpits, elbow gloves, red eyes, boots, gloves, white hair, hat flower, nail polish, panties, red rose, pantyshot, purple nails, rose petals, looking at viewer, hat, navel, bare shoulders, choker, petals, red flower, cross-laced clothes, underwear, split-color hair, brown hair\", \"caption\": \"A stylish Korean girl, with heterochromia and a confident gaze, poses amidst scattered roses against a graffiti-marked wall, rendered in a vibrant comic book art style.\" }",
            "image/webp: ",
            "",
            "formatJSON: {\"tags\": \"Tag1, Tag2, Tag3\", \"caption\": \"This is the caption.\"}",
            "ADDITIONAL_PROMPT: japanese idol",
            "TagsANDCaption: {\"tags\": \"1girl, solo, long hair, brown hair, brown eyes, short sleeves, school uniform, white shirt, upper body, collared shirt, hair bobbles, blue bowtie, realistic, japanese, finger frame\", \"caption\": \"A young Japanese idol in a classic school uniform strikes a pose while performing, her energy and focus evident in her expression and hand gestures.\" }",
            "image/webp: ",
            "",
            "formatJSON: {\"tags\": \"Tag1, Tag2, Tag3\", \"caption\": \"This is the caption.\"}",
            "ADDITIONAL_PROMPT: 1boy, tate eboshi, expressionless, fake horns, shoulder armor resembling onigawara with ornamental horns, 3d, full body, a person standing in a circle with their arms spread out., bridge, horizon, lake, mountain, ocean, planet, river, scenery, shore, snow, water, waterfall, solo, weapon, male focus, ornamental horn, white japanese armor, glowing, letterboxed, pillar, full armor, column, tree, outstretched arms, no humans, spread arms, animated character, fantasy setting, mysterious armor, ethereal glow, purple hues, virtual environment, crystals, otherworldly, long black hair, artistic filter, video game graphics, surreal atmosphere, front-facing pose, enigmatic expression, soft focus, virtual costume, obscured eyes, shoulder armor, arm bracers, magical ambiance, An animated fantasy character stands enigmatically in a surreal, crystal-laden environment, exuding a mystical presence as light softly radiates from their ethereal armor.",
            "TagsANDCaption: {\"tags\": \"1boy, solo, tate eboshi, expressionless, fake horns, shoulder armor resembling onigawara with ornamental horns, 3d, full body, a person standing in a circle with their arms spread out., bridge, ornamental horn, white japanese armor, glowing, outstretched arms, fantasy setting, mysterious armor, ethereal glow, purple hues, otherworldly, long black hair, video game graphics, soft focus, obscured eyes, shoulder armor\", \"caption\": \"An animated fantasy character stands enigmatically in a surreal, crystal-laden environment, exuding a mystical presence as light softly radiates from their ethereal armor.\" }",
            "image/webp: ",
            f"{image}",
            "formatJSON: {\"tags\": \"Tag1, Tag2, Tag3\",\n \"caption\": \"This is the caption.\"}",
            f"ADDITIONAL_PROMPT: {self.add_prompt}",
            "TagsANDCaption: ",
            ]

        return prompt_parts

    def generate_caption(self, image_path):
        """
        画像のキャプションを生成

        Args:
            image_path (Path): キャプションを生成する画像のパス。
            safety_settings (dict): 安全設定。

        Returns:
            str: 生成されたキャプション。
        """
        # プロンプトを作成
        prompt_parts = self.generate_prompt_parts(image_path)
        # Google AI Studioにプロンプトを送信して応答を生成
        response = self.model.generate_content(prompt_parts)
        # 応答からキャプションを抽出
        response_text = response.strip()
        data = json.loads(response_text)

        tags = data["tags"]
        caption = data["caption"]

        # 出力
        print(f"Tags: {tags}")
        print(f"Caption: {caption}")
        return tags, caption

class APIError(Exception):
    """API呼び出し時のカスタムエラー"""
    def __init__(self, message, error_type=None, param=None, code=None):
        self.message = message
        self.error_type = error_type
        self.param = param
        self.code = code
        super().__init__(self.message)

    def __str__(self):
        error_details = []
        if self.error_type:
            error_details.append(f"タイプ: {self.error_type}")
        if self.param:
            error_details.append(f"パラメータ: {self.param}")
        if self.code:
            error_details.append(f"コード: {self.code}")
        if error_details:
            return f"{self.message} ({', '.join(error_details)})"
        return self.message