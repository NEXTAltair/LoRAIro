"""
OpenAIのAPIを利用して取得したJSONLファイルから、メタデータを生成するスクリプト
メタデータは、画像のファイル名、パス、キャプション、タグの情報を含む辞書のリストを作成する
メタデータは、meta_clean.jsonとして保存される
"""
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_captions_to_metadata.py
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_dd_tags_to_metadata.py
import configparser
from pathlib import Path
import base64
import json
import math
import requests
from cleanup_txt import clean_format, clean_tags, clean_caption
import google.generativeai as genai

#Path
#学習元画像ファイルがあるディレクトリ
IMAGE_FOLDER = Path(r'H:\lora\Sadamitsu-XL\img_v04')
#分割されてないjsonlファイルのパス
JSONL_FILE_PATH = Path(r"")
#分割されたjsonlファイルがある場合のディレクトリ
JSONL_FILE_FOLDER = Path(r'')
#出力ディレクトリ(結合されたjsonlファイル、meta_clean.json､APIエラーを起こした画像の保存先)
#TagとCaptionを別々に保存する場合は画像の存在するフォルダに保存されるので指定不要
output_dir =  Path(r'H:\lora\素材リスト\スクリプト\Testoutput')

# 設定
MODEL = "gpt-4o"
GENERATE_BATCH_JSONL = False #バッチ処理用JSONを生成するか
JSONL_UPLOADS = False #JSONLファイルをアップロードとバッチ処理を開始するか
NSFW_IMAGE = False #

#オプション設定
GERERATE_META_CLEAN = False # meta_clean.jsonを生成するかどうか
GERERATE_TAGS_AND_CAPTIONS_TXT = True # タグとキャプションを別々にしたテキストファイルを生成するかどうか
JOIN_EXISTING_TXT = False # 既存のタグとキャプションがある場合新規のものとを結合するかどうか,その後クリーニングもする

ADDITIONAL_PROMPT = "sadamitsu, 1girl, kimono" #AIが理解しにくい画像の特徴やタグを追加する場合に使用
VISIONPROMPT = "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \
                Each image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. For images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \
                For landscapes or objects, focus on the material, historical context, and any significant features. Always use precise and specific tags—prefer \"gothic cathedral\" over \"building.\" Avoid duplicative tags. Each set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. Use tags that adhere to DANBOORU or e621 tagging conventions. Also, provide a concise 1-2 sentence caption that captures the image's narrative or essence. \
                Ensure that the tags accurately reflect the content of the image. Avoid including tags for elements not present in the image. Focus on the visible details and specific characteristics of the character and setting. \
                High-quality tagging and captioning will be compensated at $10 per image, rewarding exceptional clarity and precision that enhance image recreation."

prompt = f"{ADDITIONAL_PROMPT}\n\n{VISIONPROMPT}"

config = configparser.ConfigParser()
config.read('apikey.ini')
openai_api_key = config['KEYS']['openai_api_key']
google_api_key = config['KEYS']['google_api_key']


class ImageData:
    def __init__(self, image_folder):
        self.image_folder = Path(image_folder)
        self.data = self._load_images()

    def _load_images(self):
        image_data = {}
        for image_path in self.image_folder.rglob("*.webp"):
            image_key = str(image_path.resolve())
            image_name = image_path.stem
            txt_file = image_path.with_suffix('.txt')
            caption_file = image_path.with_suffix('.caption')

            # バイナリ化された画像
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

            # 既存テキストの読み込み
            existing_tags = ""
            existing_caption = ""
            if txt_file.exists():
                existing_tags = self._read_file(txt_file)
            if caption_file.exists():
                existing_caption = self._read_file(caption_file)

            image_data[image_key] = {
                "path": image_key,
                "name": image_name,
                "image": encoded_image,
                "existing_tags": existing_tags, # 既存のタグ
                "existing_caption": existing_caption # 既存のキャプション
            }
        return image_data

    def _read_file(self, file_path):
        """ファイルの内容を読み込む"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

class Metadata:
    def __init__(self, img_data):
        self.metadata = img_data

    def _read_file(self, file_path):
        """ファイルの内容を読み込む"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    def create_data(Self, json_input, file=None):
        """
        JSONLから読み込んだデータを基に、ファイル名、パス、キャプション、タグの情報を追加する
        Args:
            json_input (list or dict): JSONオブジェクトのリストまたは辞書。各オブジェクトは読み込んだJSONLの一行から得られる。
        Returns:
            list of dict: ファイル名、パス、キャプション、タグ情報を含む辞書のリスト。
        """
        # json_inputが辞書の場合はリストに変換
        if isinstance(json_input, dict):
            json_list = [json_input]
        else:
            json_list = json_input

        for data in json_list:
            if file:
                content = json_list[0]['choices'][0]['message']['content']
                image_key = Path(file)
                custom_id = image_key.stem
                image_key = str(image_key.resolve())

            elif 'custom_id' in data:
                custom_id = data.get('custom_id')
                # self.metadata.data と照合する
                matching_image = None
                for image_key, value in Self.metadata.data.items():
                    if value['name'] == custom_id or value['path'] == custom_id:
                        matching_image = value
                        break

                if not matching_image:
                    print(f"画像ディレクトリに{custom_id}が存在しない\n"
                            "IMAGE_FOLDERの指定ミスか学習からハネた")
                    continue

                # Path オブジェクトに変換
                image_path = Path(image_key)
                # 画像ファイルが存在するフォルダのパスを取得
                file_path = image_path.parent

                # JSONデータからタグとキャプションとタグを抽出して保存
                content = json_list[1]['response']['body']['choices'][0]['message']['content']
                image_key = file

            content = clean_format(content)

            # 'Tags:' と 'Caption:' が何番目に含まれているかを見つける
            tags_index = content.find('Tags:')
            caption_index = content.find('Caption:')

            # 'Tags:' か 'Caption:'が含まれていない場合はAPIエラーか弾かれているので例外処理
            # APIの処理のブレでたまに｢### Tsgs,｣や｢###Captin,｣で始まることがあるのでそれも弾く
            # 数は多くないので手動で処理してくれることを期待
            if tags_index == -1 or caption_index == -1:
                print(f"Error Information:\n"
                    f"Image Key: {file_path}\n"
                    f"Content: {content}\n"
                    f"-----")
                error_image_path = move_error_images(file_path)
                print(f"Moved error image to {error_image_path}")
                continue

            # タグとキャプションのテキストを抽出
            tags_text = content[tags_index + len('Tags:'):caption_index].strip()
            caption_text = content[caption_index + len('Caption:'):].strip()

            # タグとキャプションをクリーンアップ
            tags = clean_tags(tags_text)
            caption = clean_caption(caption_text)

            # self.metadata.data に情報を追加
            Self.metadata.data[image_key].update({
                "path": image_key,
                "name": custom_id,
                "existing_tags": Self.metadata.data[image_key]['existing_tags'],  # 既存のタグ
                "existing_caption": Self.metadata.data[image_key]['existing_caption'],  # 既存のキャプション
                "tags": tags,
                "caption": caption
            })

        return Self.metadata.data

    def json_to_metadata(Self):
        """ImageDataオブジェクトの変数からKohya/sd-scripts用メタデータを生成する

        return: metadata (dict): メタデータ
        """
        metadata_clean = {}

        # metadataからimage_key､tags, captionを取得
        for image_key, value in Self.metadata.data:
            tags = value['tags']
            caption = value['caption']

            # metadataからimage_key､tags, captionをmetadata_clene.jsonに保存
            # image_key をキーとしてメタデータを格納
            metadata_clean[image_key] = {
                'tags': tags,
                'caption': caption
                }

        with open(output_dir / 'meta_clean.json', 'w', encoding='utf-8') as file:
            json.dump(metadata_clean, file, ensure_ascii=False, indent=4)

        return metadata

    def save_metadata(self, filename):
        """メタデータを指定された形式でファイルに保存する"""
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(self.metadata, file, ensure_ascii=False, indent=4)
        print(f"Metadata saved to {filename}")

    def load_metadata(self, filename):
        """指定された形式のファイルからメタデータをロードする"""
        with open(filename, 'r', encoding='utf-8') as file:
            self.metadata = json.load(file)
        print(f"Metadata loaded from {filename}")

    def get_tags(self, image_key):
        """指定された画像キーのタグを取得する"""
        return self.metadata.get(image_key, {}).get("tags", "")

    def get_caption(self, image_key):
        """指定された画像キーのキャプションを取得する"""
        return self.metadata.get(image_key, {}).get("caption", "")


class OpenAIApi:
    def __init__(self, image_data):
        self.openai_api_key = openai_api_key
        self.model = MODEL
        self.image_data = image_data

    def generate_payload(self, image_key):
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
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/webp;base64,{self.image_data.data[image_key]['image']}",
                            "detail": "high"
                        }}
                    ]
                }
            ],
            "max_tokens": 3000
        }

        if GENERATE_BATCH_JSONL:
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
        """#imageを走査してBachAPIのリクエストを生成

        Args:
            img (instance): ImageData インスタンス
        """
        batch_payloads = []
        for image_key in oai.image_data.data:
            path = self.image_data.data[image_key]['path']
            path = Path(path)
            name = self.image_data.data[image_key]['name']
            if path.suffix == ".webp": #webp以外の画像の場合はリサイズ等の処理がされてないから無視
                print(f'Processing {name}...')
                payload = self.generate_payload(image_key)
                batch_payloads.append(payload)

        jsonl_path = save_jsonline_to_file(batch_payloads, f"{path.parent.name}.jsonl")

        # サイズチェックしてjsonlが96MB[OpenAIの制限]を超えないようにするために分割する
        jsonl_size = jsonl_path.stat().st_size
        if jsonl_size > 100663296:
            print("JSONLファイル大きすぎ分割")
            split_jsonl(jsonl_path, jsonl_size, JSONL_UPLOADS)
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
    def __init__(self, google_api_key):
        """
        Google AI Studioとのインターフェースを作成

        Args:
            google_api_key (str): Google AI StudioのAPIキー。
        """
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
        image = encode_image(image_path)

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
            f"ADDITIONAL_PROMPT: {ADDITIONAL_PROMPT}",
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


def process_jsonl_files(input_path, join_files=False):
    """
    JSONLファイルを処理し、内容を読み込むか、複数のファイルを結合する。
    Args:
        input_path (Path): JSONLファイルのパスまたは結合するファイルが格納されたディレクトリ。
        join_files (bool): 複数のファイルを結合するかどうか。
    Returns:
        list or list: JSONオブジェクトのリスト、または結合した場合の行のリスト。
    """
    if join_files:
        # ディレクトリからすべてのJSONLファイルを結合
        jsonl_files = list(input_path.glob('*.jsonl'))
        combined_lines = []
        for jsonl_file in jsonl_files:
            with open(jsonl_file, 'r', encoding='utf-8') as infile:
                combined_lines.extend(infile.readlines())
        data = [json.loads(line.strip()) for line in combined_lines]
    else:
        # 単一のファイルを読み込む
        with open(input_path, 'r', encoding='utf-8') as file:
            data = [json.loads(line.strip()) for line in file]
        return data


def save_jsonline_to_file(batch_payload, jsonl_filename):
    """一行JSONファイルを纏めてJSONLines形式でファイルに保存する

    Args:
        batch_payloads (str): 一行のJSONファイル

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
    # TODO: 読み込み先保存先は別々にしたほうがいいか?

    Args:
        jsonl_path (_type_): _description_
    """
    # jsonl_sizeに基づいてファイルを分割
    split_size = math.ceil(jsonl_size / 100663296)
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    lines_per_file = math.ceil(len(lines) / split_size)  # 各ファイルに必要な行数
    for i in range(split_size):
        split_filename = f'instructions_{i}.jsonl'
        split_path = jsonl_path / split_filename
        with open(split_path, 'w', encoding='utf-8') as f:
            f.writelines(lines[i * lines_per_file:(i + 1) * lines_per_file])


def move_error_images(file_path):
    """APIがエラーを出した画像をエラー画像フォルダに移動する
    Args:
        image_key (str): エラーを出したwebpのフルパス
        filename (stt): エラーを出したwebpのファイル名
    """
    # エラー画像を保存するフォルダを作成
    error_images_folder = output_dir / 'API_error_images'

    if not error_images_folder.exists():
        error_images_folder.mkdir(parents=True)

    error_image_path = error_images_folder / file_path.name
    Path(file_path).rename(error_image_path)
    return error_image_path


def save_tags_and_captions(metadata, filename=None):
    """ImageDataオブジェクトの変数から.txtと.captionファイルを生成する
    Args:
        metadata (list): JSONオブジェクトのリスト
    """
    # metadataからimage_key､tags, captionを取得
    for data in metadata.data:
        if data!= 'id':
            filename = metadata.data[data]['name']
            image_folder = Path(metadata.data[data]['path']).parent
            tags = metadata.data[data]['tags']
            caption = metadata.data[data]['caption']
        else:
            image_folder = Path(filename).parent
            tags = metadata.data[data]['tags']
            caption = metadata.data[data]['caption']

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        if JOIN_EXISTING_TXT:
            # 既存のタグとキャプションを取得
            existing_tags = metadata.data[data]['existing_tags']
            existing_caption = metadata.data[data]['existing_caption']

            # 既存のタグとキャプションを新しいものと結合とクリーンアップ
            tags = existing_tags + tags
            caption = existing_caption + caption
            tags = clean_tags(tags)
            caption = clean_caption(caption)

        # タグをテキストファイルに保存
        with open((image_folder / tags_filename), 'w', encoding='utf-8') as tags_file:
            tags_file.write(tags)

        # キャプションをキャプションファイルに保存
        with open((image_folder / caption_filename), 'w', encoding='utf-8') as cap_file:
            cap_file.write(caption)

        print(f"Saved tags to {tags_filename}")
        print(f"Saved caption to {caption_filename}")


def write_to_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)


def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        return file.read()


def caption_gpt4(img, data, oai):
    """#フォルダ内の画像に対応した.captionがない場合OpenAI API GTP-4を使って生成

    Args:
    """
    # フォルダを走査してキャプションの生成
    for file in img.data:
        print(f'Processing {file}...')

        header, payload = oai.generate_payload(file)
        #キャプションの生成
        response = oai.generate_immediate_response(payload, header)
        # responseを基にImagesDataの更新
        data.create_data(response, file)
    save_tags_and_captions(img, file) # TODO:保存は一括じゃなくて個別にしたほうがいいかも


if __name__ == "__main__":
    img = ImageData(IMAGE_FOLDER)
    data = Metadata(img)
    oai = OpenAIApi(img)
    if GENERATE_BATCH_JSONL:
        jsonl_path = oai.caption_batch()
        if JSONL_UPLOADS:
            uplode_file_id = oai.upload_jsonl_file(jsonl_path)
            oai.start_batch_processing(uplode_file_id)
            exit() #バッチ処理が開始されたら終了
    else:
        # GPT-4で即時
        caption_gpt4(img, data, oai)
        exit()

    if JSONL_FILE_FOLDER != Path('.') and JSONL_FILE_FOLDER.is_dir():
        # 指定されている場合はJSONLファイルを結合するとみなす
        response_jsonl_data = process_jsonl_files(JSONL_FILE_FOLDER, join_files=True)
    else:
        response_jsonl_data = process_jsonl_files(JSONL_FILE_PATH)

    if GERERATE_META_CLEAN:
        metadata = json_to_metadata(response_jsonl_data)
    if GERERATE_TAGS_AND_CAPTIONS_TXT:
        metadata = data.create_data(response_jsonl_data)
        save_tags_and_captions(metadata)



