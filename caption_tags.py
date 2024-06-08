"""
APIを利用してtagとcaptionをいい感じに生成するスクリプト
"""
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_captions_to_metadata.py
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_dd_tags_to_metadata.py
import toml
from pathlib import Path
import base64
import json
from cleanup_txt import clean_format, clean_tags, clean_caption
from api_utils import OpenAIApi


config = toml.load("processing.toml")

# APIキーの取得
openai_api_key = config["APIKEYS"]["openai_api_key"]
google_api_key = config["APIKEYS"]["google_api_key"]
# ディレクトリ設定の取得
dataset_dir = Path(config["directories"]["dataset_dir"])
response_file_dir = Path(config["directories"]["response_file_dir"])
output_dir = Path(config["directories"]["output_dir"])
# 設定の取得
model = config["settings"]["openai_model"]
generate_batch_jsonl = bool(config["settings"]["generate_batch_jsonl"])
generate = bool(config["settings"]["generate"])
strt_batch = bool(config["settings"]["strt_batch"])
# オプション設定の取得
generate_meta_clean = bool(config["options"]["generate_meta_clean"])
generate_tags_and_captions_txt = bool(config["options"]["generate_tags_and_captions_txt"])
join_existing_txt = bool(config["options"]["join_existing_txt"])
# プロンプトの設定
prompt = config["prompts"]["prompt"]
if generate_batch_jsonl or generate:
    additional_prompt = config["prompts"]["additional_prompt"]
    prompt = f"{additional_prompt}\n\n{prompt}"
else:
    prompt = prompt


class ImageData:
    def __init__(self, dataset_dir):
        self.dataset_dir = dataset_dir
        self.data = self._load_images()

    def _load_images(self):
        image_data = {}
        for image_path in self.dataset_dir.rglob("*.webp"):
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
                            "dataset_dirの指定ミスか学習からハネた")
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
            dataset_dir = Path(value['path']).parent
            tags = value.get('tags') # きーがない場合はNoneを返す
            caption = value.get('caption') #APIの時やタグ付けせずにクリーンナップのみの時
        else:
            dataset_dir = Path(filename).parent
            tags = value.get('tags')
            caption = value.get('caption')

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        if tags is None and caption is None:
            break

        if join_existing_txt and imagedata.data[image_key].get('existing_tags') and imagedata.data[image_key].get('existing_caption'):
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
            tags_file_path = dataset_dir / tags_filename
            if not tags_file_path.exists():
                with open(tags_file_path, 'w', encoding='utf-8') as tags_file:
                    tags_file.write(tags)
            elif join_existing_txt:
                with open(tags_file_path, 'a', encoding='utf-8') as tags_file:
                    tags_file.write(tags)
            else:
                # Todo: とりあえずBREAK
                break

        # キャプションをキャプションファイルに保存
        if caption is not None:
            with open((dataset_dir / caption_filename), 'w', encoding='utf-8') as cap_file:
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
    img = ImageData(dataset_dir) #画像データの読み込み
    data = Metadata(img) #画像データを編集するインスタンス
    oai = OpenAIApi(openai_api_key, model, prompt, img)
    if generate_batch_jsonl:
        jsonl_path = oai.caption_batch()
        if strt_batch:
            uplode_file_id = oai.upload_jsonl_file(jsonl_path)
            oai.start_batch_processing(uplode_file_id)
            print("バッチ処理が終了したらjsonlパスを指定して再度実行")
            exit() #バッチ処理が開始されたら終了
    elif generate:
        # GPT-4で即時
        caption_gpt4(img, data, oai)
        exit()

    if response_file_dir != Path('.') and response_file_dir.is_dir():
        jsonl_count = len(list(response_file_dir.glob('*.jsonl')))
        file_count = len(list(response_file_dir.glob('*')))
        if jsonl_count == file_count:
            response_jsonl_data = process_jsonl_files(response_file_dir, file_count)
        else:
            print("レスポンスのjsonl以外のファイルがある｡Pathをミスってる可能性")
            exit()


    if generate_meta_clean:
        metadata = data.json_to_metadata(response_jsonl_data)
    if generate_tags_and_captions_txt:
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



