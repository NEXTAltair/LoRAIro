
from pathlib import Path
import json
import math
import google.generativeai as genai
import requests

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
    def __init__(self, openai_api_key, model, prompt, image_data):
        self.openai_api_key = openai_api_key
        self.model = model
        self.prompt = prompt
        self.image_data = image_data

    def generate_payload(self, image_key, batch_jsonl_flag):
        """
        OpenAI APIに送信するペイロードを生成する。

        Args:
            base64img (str): Base64エンコードされた画像データ
            prompt (str): 画像に関連するプロンプトテキスト
            img_id (str, optional): 画像ID（バッチ処理用）

        Returns:
            tuple: headers（APIリクエストのヘッダー）, payload（APIに送信するペイロード）
        """
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
                            "url": f"data:image/webp;base64,{self.image_data.data[image_key]['image']}",
                            "detail": "high"
                        }}
                    ]
                }
            ],
            "max_tokens": 3000
        }

        if batch_jsonl_flag:
            bach_payload = {
                "custom_id": self.image_data.data[image_key]['name'],
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": payload
            }
            return bach_payload

        return headers, payload


    def generate_immediate_response(self, payload, headers):
        """
        OpenAI APIを呼び出して即時にデータを生成する。

        Args:
            payload (dict): APIに送信するペイロード
            headers (dict): APIリクエストのヘッダー

        Returns:
            dict: APIからのレスポンス
        """
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        return response.json()


    def caption_batch(self):
        """#imageを走査してBachAPIのリクエストjsonlを生成

        Args:
            img (instance): ImageData インスタンス
        """
        batch_payloads = []
        for image_key in self.image_data.data:
            path = self.image_data.data[image_key]['path']
            path = Path(path)
            #親フォルダ名を取得して nsfw が含まれるる場合そのフォルダに有る画像はスキップ
            if "nsfw" in path.parent.name:
                continue
            name = self.image_data.data[image_key]['name']
            if path.suffix == ".webp": #webp以外の画像の場合はリサイズ等の処理がされてないから無視
                print(f'Processing {name}...')
                payload = self.generate_payload(image_key, batch_jsonl_flag=False)
                batch_payloads.append(payload)

        jsonl_path = save_jsonline_to_file(batch_payloads, f"{path.parent.name}.jsonl")

        # サイズチェックしてjsonlが96MB[OpenAIの制限]を超えないようにするために分割する
        jsonl_size = jsonl_path.stat().st_size
        if jsonl_size > 100663296:
            print("JSONLファイル大きすぎ分割")
            split_jsonl(jsonl_path, jsonl_size)
        else:
            return jsonl_path


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