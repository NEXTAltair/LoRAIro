"""
APIを利用してtagとcaptionをいい感じに生成するスクリプト
"""
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_captions_to_metadata.py
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_dd_tags_to_metadata.py
import configparser
from pathlib import Path
import base64
import json
from cleanup_txt import clean_format, clean_tags, clean_caption
from api_utils import OpenAIApi

# コンソールからユーザー入力を受け取る関数を追加
def get_input_path(prompt):
    return Path(input(prompt).strip())

# コンソール入力を受け取るように変更
IMAGE_FOLDER = get_input_path("学習元画像ファイルがあるディレクトリ: ")
RESPONSE_FILE_FOLDER = get_input_path("完了したバッチ(jsonl)ファイルのディレクトリ: ")
output_dir = Path("Testoutput") #get_input_path("出力ディレクトリ (結合されたjsonlファイル、meta_clean.json､APIエラーを起こした画像の保存先): ")

# 設定
MODEL = "gpt-4o"
GENERATE_BATCH_JSONL = input("バッチ処理用JSONを生成? (True/False): ").strip().lower() == 'true'
GENERATE = input("即時生成?? (True/False): ").strip().lower() == 'true'
JSONL_UPLOADS = input("JSONLファイルをアップロードとバッチ処理を開始? (True/False): ").strip().lower() == 'true'

# オプション設定
GERERATE_META_CLEAN = input("meta_clean.jsonを生成? (True/False): ").strip().lower() == 'true'
GERERATE_TAGS_AND_CAPTIONS_TXT = bool("true") #input("タグとキャプションを別々にしたテキストファイルを生成? (True/False): ").strip().lower() == 'true'
JOIN_EXISTING_TXT = input("既存のタグとキャプションがある場合新規のものとを結合? Falseは上書き保存(True/False): ").strip().lower() == 'true'

# プロンプトの設定
VISIONPROMPT = "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \
                Each image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. For images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \
                For landscapes or objects, focus on the material, historical context, and any significant features. Always use precise and specific tags—prefer \"gothic cathedral\" over \"building.\" Avoid duplicative tags. Each set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. Use tags that adhere to DANBOORU or e621 tagging conventions. Also, provide a concise 1-2 sentence caption that captures the image's narrative or essence. \
                Ensure that the tags accurately reflect the content of the image. Avoid including tags for elements not present in the image. Focus on the visible details and specific characteristics of the character and setting. \
                High-quality tagging and captioning will be compensated at $10 per image, rewarding exceptional clarity and precision that enhance image recreation."
if GENERATE_BATCH_JSONL or GENERATE:
    ADDITIONAL_PROMPT = input("AIが理解しにくい画像の特徴やタグを追加する場合のプロンプト: ").strip()
    prompt = f"{ADDITIONAL_PROMPT}\n\n{VISIONPROMPT}"
else:
    prompt = VISIONPROMPT

config = configparser.ConfigParser()
config.read('apikey.ini')
openai_api_key = config['KEYS']['openai_api_key']
google_api_key = config['KEYS']['google_api_key']


class ImageData:
    def __init__(self, image_folder):
        self.image_folder = image_folder
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
            dict: ファイル名、パス、キャプション、タグ情報を含む辞書
        """
        # json_inputが辞書の場合はリストに変換
        if isinstance(json_input, dict):
            json_list = [json_input]
        else:
            json_list = json_input

        for data in json_list:
            if data.get('error') is not None:
                file = Path(file)
                move_error_images(file)
                continue

            if file: #即時生成の場合
                content = json_list[0]['choices'][0]['message']['content']
                image_key = Path(file)
                custom_id = image_key.stem
                image_key = str(image_key.resolve())

            elif 'custom_id' in data: #バッチ生成の場合
                custom_id = data.get('custom_id')
                # self.metadata.data と照合する
                matching_image = None
                for _, value in Self.metadata.data.items():
                    if value['name'] == custom_id or value['path'] == custom_id:
                        matching_image = value
                        break
                if not matching_image:
                    print(f"画像ディレクトリに｢ {custom_id} ｣が存在しない\n"
                            "IMAGE_FOLDERの指定ミスか学習からハネた")
                    continue
                image_key = matching_image['path']

                # Path オブジェクトに変換
                image_path = Path(image_key)
                # 画像ファイルが存在するフォルダのパスを取得
                file_path = image_path.parent

                # JSONデータからタグとキャプションとタグを抽出して保存
                content = data['response']['body']['choices'][0]['message']['content']

            else: #API不使用でデータのクリーンナップのみの場合
                image_key = data['path']
                image_path = Path(image_key)
                file_path = image_path.parent
                custom_id = image_path.stem
                content = "Tags: " + Self.metadata.data[image_key]['existing_tags'] + ", Caption: " + Self.metadata.data[image_key]['existing_caption']


            content = clean_format(content)

            # 'Tags:' と 'Caption:' が何番目に含まれているかを見つける
            tags_index = content.find('Tags:')
            caption_index = content.find('Caption:')

            # 'Tags:' か 'Caption:'が含まれていない場合はAPIエラーか弾かれているので例外処理
            # APIの処理のブレでたまに｢### Tsgs,｣や｢###Captin,｣で始まることがあるのでそれも弾く
            # 数は多くないので手動で処理してくれることを期待
            if tags_index == -1 and caption_index == -1:
                print(f"この場合うっかりエロ画像をAPIに投げた可能性がある")
                print(f"Error Information:\n"
                    f"Image Key: {image_key}\n"
                    f"Content: {content}\n"
                    f"-----")
                move_error_images(Path(image_key)) # TODO:
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
        data = Self.metadata.data
        return data

    def json_to_metadata(Self):
        """ImageDataオブジェクトの変数からKohya/sd-scripts用メタデータを生成する

        return: metadata (dict): メタデータ
        """
        metadata_clean = {}
        # metadataからimage_key､tags, captionを取得
        for image_key, value in Self.metadata.data.items():
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

def process_jsonl_files(input_path, file_count):
    """
    JSONLファイルを処理し、内容を読み込むか、複数のファイルを結合する。
    Args:
        input_path (Path): JSONLファイルのパスまたは結合するファイルが格納されたディレクトリ。
        file_count (int): フォルダ内のファイル数
    Returns:
        list or list: JSONオブジェクトのリスト
    """
    # if file_count >= 2:
    # ディレクトリからすべてのJSONLファイルを結合
    jsonl_files = list(input_path.glob('*.jsonl'))
    combined_lines = []
    for jsonl_file in jsonl_files:
        with open(jsonl_file, 'r', encoding='utf-8') as infile:
            combined_lines.extend(infile.readlines())
    data = [json.loads(line.strip()) for line in combined_lines]
    # else:
    #     # 単一のファイルを読み込む
    #     with open(input_path, 'r', encoding='utf-8') as file:
    #         data = [json.loads(line.strip()) for line in file]
    return data

def move_error_images(file_path):
    """APIがエラーを出した画像をエラー画像フォルダに移動する
    Args:
        file_path (Path): エラーを出したwebpのフルパス
    """
    # エラー画像を保存するフォルダを作成
    error_images_folder = output_dir / 'API_error_images'

    if not error_images_folder.exists():
        error_images_folder.mkdir(parents=True)

    error_image_path = error_images_folder / file_path.name
    Path(file_path).rename(error_image_path)
    return error_image_path


def save_tags_and_captions(imagedata, filename=None):
    """instanceの変数から.txtと.captionファイルを生成する
    Args:
        imagedata (instance): JSONオブジェクト
    """
    # TODO: 即時生成とバッチ生成の場合の分岐を追加
    # imagedataからimage_key､tags, captionを取得
    for image_key, value in imagedata.data.items():
        if data!= 'id':
            filename = value['name']
            image_folder = Path(value['path']).parent
            tags = value.get('tags') # きーがない場合はNoneを返す
            caption = value.get('caption') #APIの時やタグ付けせずにクリーンナップのみの時
        else:
            image_folder = Path(filename).parent
            tags = value.get('tags')
            caption = value.get('caption')

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        if tags is None and caption is None:
            break

        if JOIN_EXISTING_TXT and imagedata.data[image_key].get('existing_tags') and imagedata.data[image_key].get('existing_caption'):
            # 既存のタグとキャプションを取得
            existing_tags = imagedata.data[image_key]['existing_tags']
            existing_caption = imagedata.data[image_key]['existing_caption']

            # 既存のタグとキャプションを新しいものと結合とクリーンアップ
            tags = existing_tags + ", " + tags
            caption = existing_caption + ", " + caption
            tags = clean_tags(tags)
            caption = clean_caption(caption)

        # タグをテキストファイルに保存
        if tags is not None:
            tags_file_path = image_folder / tags_filename
            if not tags_file_path.exists():
                with open(tags_file_path, 'w', encoding='utf-8') as tags_file:
                    tags_file.write(tags)
            elif JOIN_EXISTING_TXT:
                with open(tags_file_path, 'a', encoding='utf-8') as tags_file:
                    tags_file.write(tags)
            else:
                # Todo: とりあえずBREAK
                break

        # キャプションをキャプションファイルに保存
        if caption is not None:
            with open((image_folder / caption_filename), 'w', encoding='utf-8') as cap_file:
                cap_file.write(caption)

            print(f"Saved tags to {tags_filename} \n {tags}")
            print(f"Saved caption to {caption_filename} \n {caption}")


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
        # 親フォルダ名にnsfwが含まれる場合はImagesDataの更新をスキップ
        if "nsfw" in Path(file).parent.name:
            return
        print(f'Processing {file}...')
        header, payload = oai.generate_payload(file)
        #キャプションの生成
        response = oai.generate_immediate_response(payload, header)
        print(f"response: {response}")
        # responseを基にImagesDataの更新
        data.create_data(response, file)
    save_tags_and_captions(img, file)

if __name__ == "__main__":
    img = ImageData(IMAGE_FOLDER) #画像データの読み込み
    data = Metadata(img) #画像データを編集するインスタンス
    oai = OpenAIApi(openai_api_key, MODEL, prompt, img)
    if GENERATE_BATCH_JSONL:
        jsonl_path = oai.caption_batch()
        if JSONL_UPLOADS:
            uplode_file_id = oai.upload_jsonl_file(jsonl_path)
            oai.start_batch_processing(uplode_file_id)
            print("バッチ処理が終了したらjsonlパスを指定して再度実行")
            exit() #バッチ処理が開始されたら終了
    elif GENERATE:
        # GPT-4で即時
        caption_gpt4(img, data, oai)
        exit()

    if RESPONSE_FILE_FOLDER != Path('.') and RESPONSE_FILE_FOLDER.is_dir():
        jsonl_count = len(list(RESPONSE_FILE_FOLDER.glob('*.jsonl')))
        file_count = len(list(RESPONSE_FILE_FOLDER.glob('*')))
        if jsonl_count == file_count:
            response_jsonl_data = process_jsonl_files(RESPONSE_FILE_FOLDER, file_count)
        else:
            print("レスポンスのjsonl以外のファイルがある｡Pathをミスってる可能性")
            exit()


    if GERERATE_META_CLEAN:
        metadata = data.json_to_metadata(response_jsonl_data)
    if GERERATE_TAGS_AND_CAPTIONS_TXT:
        try:
            if response_jsonl_data is not None:
                metadata = data.create_data(response_jsonl_data)
        except:
            img_datas = []
            for image_ley, img_data in img.data.items():
                print(f'Processing {image_ley}...')
                #valueをリストに追加
                img_datas.append(img_data)

            metadata = data.create_data(img_datas)
            #metadata(dict)でInstanceの変数を更新
            data.metadata = metadata
        save_tags_and_captions(data)



