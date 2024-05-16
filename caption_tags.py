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


#Path
#学習元画像ファイルがあるディレクトリ
IMAGE_FOLDER = Path(r'H:\lora\Fatima-XL\img\1_Fatima_002')

#分割されてないjsonlファイルのパス
JSONL_FILE_PATH = Path(r'')
#分割されたjsonlファイルがある場合のディレクトリ
JSONL_FILE_FOLDER = Path(r'H:\lora\素材リスト\スクリプト\jsonl')

#出力ディレクトリ(結合されたjsonlファイル、meta_clean.json､APIエラーを起こした画像の保存先)
#TagとCaptionを別々に保存する場合は画像の存在するフォルダに保存されるので指定不要
output_dir =  Path(r'H:\lora\素材リスト\スクリプト\Testoutput')

# 設定
MODEL = "gpt-4o"
GENERATE_BATCH_JSONL = False #バッチ処理用JSONを生成するか
SPLIT_JSONL_UPLOADS = False #分割したJSONLファイルをアップロードするか
NSFW_IMAGE = True #

#オプション設定
GERERATE_META_CLEAN = True # meta_clean.jsonを生成するかどうか
GERERATE_TAGS_AND_CAPTIONS_TXT = True # タグとキャプションを別々にしたテキストファイルを生成するかどうか
JOIN_EXISTING_TXT = True # 既存のタグとキャプションがある場合新規のものとを結合するかどうか


config = configparser.ConfigParser()
config.read('apikey.ini')
api_key = config['KEYS']['openai_api_key']

def encode_image(image_path):
    '''画像をBase64エンコードして返す'''
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


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
        return combined_lines
    else:
        # 単一のファイルを読み込む
        with open(input_path, 'r', encoding='utf-8') as file:
            data = [json.loads(line.strip()) for line in file]
        return data


def generate_openai_payload(model, base64img, api_key=None, img_id=None):
    """
    汎用的なペイロードを生成する

    Args:
        model (str): 使用するモデル名
        base64img (str): 画像のBase64エンコード文字列
        api_key (str, optional): APIキー (即レス用)
        img_id (str, optional): イメージID (batchAPI用)

    Returns:
        tuple: headers (if api_key is provided), payload
    """
    prompt = "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \
                    Each image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. \
                    For images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \
                    For landscapes or objects, focus on the material, historical context, and any significant features. \
                    Always use precise and specific tags—prefer \"Gothic cathedral\" over \"building\" Avoid duplicative tags. \
                    Each set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. \
                    Also, provide a concise 1-2 sentence caption that captures the image's narrative or essence. \
                    High-quality tagging and captioning will be compensated at $10 per image, rewarding exceptional clarity and precision that enhance image recreation"
    headers = {}
    if api_key:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/webp;base64,{base64img}",
                        "detail": "high"
                    }}
                ]
            }
        ],
        "max_tokens": 3000
    }

    if img_id:
        bach_payload = {
            "custom_id": img_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": payload
        }

    return headers, payload if api_key else bach_payload


def save_jsonline_to_file(batch_payload, jsonl_filename):
    """一行JSONファイルを纏めてJSONLines形式でファイルに保存する

    Args:
        batch_payloads (str): 一行のJSONファイル
        filename (str): 保存するファイル名
    Returns:
        jsonl_filename (Path): jsonline形式のファイルpath
    """
    with open(jsonl_filename, 'w', encoding='utf-8') as f:
        for item in batch_payload:
            json.dump(item, f)
            f.write('\n')  # 各JSONオブジェクトの後に改行を追加
    print(f"Data saved to {jsonl_filename}")
    return Path(jsonl_filename)


def json_to_metadata(json_list):
    """jsonオブジェクトリストからKohya-ss用のmeta_clean.json生成する

    Args:
        json_list (list): JSONオブジェクトのリスト
    """
    metadata = create_data(json_list)
    metadata_clean = {}

    # metadataからimage_key､tags, captionを取得
    for data in metadata:
        image_key = data['image_key']
        tags = data['tags']
        caption = data['caption']

        # metadataからimage_key､tags, captionをmetadata_clene.jsonに保存
        # image_key をキーとしてメタデータを格納
        metadata_clean[image_key] = {
            'tags': tags,
            'caption': caption
            }

    with open(output_dir / 'meta_clean.json', 'w', encoding='utf-8') as file:
        json.dump(metadata_clean, file, ensure_ascii=False, indent=4)
        print("Saved metadata to meta_clean.json")


def upload_bach_jsonl(jsonl_path, api_key):
    """JSONファイルをOpenAI APIにアップロードする
    """
    url = "https://api.openai.com/v1/files"
    headers = {
        "Authorization": f"Bearer {api_key}"
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


def start_batch_processing(input_file_id, api_key):
    """
    OpenAI APIを使用してバッチ処理を開始する。

    Args:
        input_file_id (str): アップロードされたファイルのID。

    Returns:
        dict: APIからの応答を含む辞書。
    """
    url = "https://api.openai.com/v1/batches"
    headers = {
        "Authorization": f"Bearer {api_key}",
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


def caption_batch(input_dir, MODEL):
    """フォルダ内の画像に対応したバッチ処理用JSONに追加

    Args:
        input_dir (Path): 入力フォルダ
        MODEL (str): 使用するモデル名
    """
    batch_payloads = []
    # フォルダを走査してキャプションの生成
    for filename in input_dir.rglob('*'):
        # 拡張子を除去したファイル名の取得
        base_filename = filename.stem
        if filename.name.lower().endswith(('webp')): #webp以外の画像の場合はリサイズ等の処理がされてないから無視
            image_path = input_dir / filename
            print(f'Processing {filename}...')

            base64img = encode_image(image_path)
            payload = generate_openai_payload(MODEL, base64img, img_id=base_filename)
            batch_payloads.append(payload)

    jsonl_path = save_jsonline_to_file(batch_payloads, 'instructions.jsonl')

    # サイズチェックしてjsonlが96MB[OpenAIの制限]を超えないようにするために分割する
    jsonl_size = jsonl_path.stat().st_size
    if jsonl_size > 100663296:
        print("JSONLファイル大きすぎ分割")
        split_jsonl(jsonl_path, jsonl_size, SPLIT_JSONL_UPLOADS)


def split_jsonl(jsonl_path, jsonl_size, SPLIT_JSONL_UPLOADS):
    """JSONLが96MB[OpenAIの制限]を超えないようにするために分割する

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

        if SPLIT_JSONL_UPLOADS:
            upload_file_id = upload_bach_jsonl(split_path)
            start_batch_processing(upload_file_id)
        else:
            print(f"分割ファイルを保存しました: {split_path}")
            print("分割ファイルをアップロードたバッチ処理を開始するには、sprit_json_uploasをTrueに設定してください。")


def generate_caption_openai(model, base64img):
    """キャプションを即時生成する
    Args:
        model (model name): 使用するモデル名
        base64img (str): 画像のBase64エンコード文字列
    Returns (list): APIのレスポンス
    """
    json_list = []
    headers, payload = generate_openai_payload(model, base64img, api_key)
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    response_data = response.json()
    try:
        # choices 配列の最初の要素からキャプションを取得
        caption = response_data["choices"][0]["message"]["content"]
        print(caption)
        json_list.append(response_data)
        return json_list
    except KeyError:
        # エラーがあればその内容を表示
        return "Error generating caption: " + response.text


def move_error_images(image_key, filename):
    """APIがエラーを出した画像をエラー画像フォルダに移動する
    Args:
        image_key (str): エラーを出したwebpのフルパス
        filename (stt): エラーを出したwebpのファイル名
    """
    # エラー画像を保存するフォルダを作成
    error_images_folder = output_dir / 'API_error_images'

    if not error_images_folder.exists():
        error_images_folder.mkdir(parents=True)

    error_image_path = error_images_folder / f"{filename}.webp"
    Path(image_key).rename(error_image_path)


def create_data(json_list, file=None):
    """
    JSONLから読み込んだデータリストを基に、ファイル名、パス、キャプション、タグの情報を含む辞書のリストを作成する
    Args:
        data_list (list): JSONオブジェクトのリスト。各オブジェクトは読み込んだJSONLの一行から得られる。
    Returns:
        list of dict: ファイル名、パス、キャプション、タグ情報を含む辞書のリスト。
    """
    data_list = []
    for data in json_list:
        if 'custom_id' in data: #custom_idがある場合はbachAPIの結果
            custom_id = data.get('custom_id')
            #custom_idから拡張子を含まないファイル名を取得
            if '\\' in custom_id or '/' in custom_id:
                filename = Path(custom_id).name
            else:
                filename = custom_id

            #image_keyを取得はstr型
            #webp以外は画像処理してないとみなして扱わない
            image_key = next((str(p) for p in Path(IMAGE_FOLDER).rglob(f"{filename}.webp")), None)
            if not image_key:
                print(f"IMAGE_FOLDERに{filename}.webpが存在しません.skipします。\n"
                    "IMAGE_FOLDERの指定ミスか学習からハネた")
                continue

            # Path オブジェクトに変換
            image_path = Path(image_key)
            # 画像ファイルが存在するフォルダのパスを取得
            file_path = image_path.parent

            # JSONデータからタグとキャプションとタグを抽出して保存
            content = json_list[1]['response']['body']['choices'][0]['message']['content']
            content = clean_format(content)

        else:
            content = json_list[0]['choices'][0]['message']['content']
            filename = file.stem
            file_path = file.parent
            image_key = None

        # 'Tags:' と 'Caption:' が何番目に含まれているかを見つける
        tags_index = content.find('Tags:')
        caption_index = content.find('Caption:')

        # 'Tags:' か 'Caption:'が含まれていない場合はAPIエラーか弾かれているので例外処理
        # APIの処理のブレでたまに｢### Tsgs,｣や｢###Captin,｣で始まることがあるのでそれも弾く
        # 数は多くないので手動で処理してくれることを期待
        if tags_index == -1 or caption_index == -1:
            print(f"Error Information:\n"
                f"Filename: {filename}\n"
                f"Image Key: {image_key}\n"
                f"Content: {content}\n"
                f"-----")
            move_error_images(image_key, filename)

        # タグとキャプションのテキストを抽出
        tags_text = content[tags_index + len('Tags:'):caption_index].strip()
        caption_text = content[caption_index + len('Caption:'):].strip()

        #IMAGE_FOLDERに既存の.txtや.captionファイルがある場合にその情報を取得
        existing_tags = ""
        existing_caption = ""
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"
        if (file_path / tags_filename).exists():
            with open(file_path / tags_filename, 'r', encoding='utf-8') as tags_file:
                existing_tags = tags_file.read()
        if (file_path / caption_filename).exists():
            with open(file_path / caption_filename, 'r', encoding='utf-8') as cap_file:
                existing_caption = cap_file.read()

        # タグとキャプションをクリーンアップ
        tags = clean_tags(tags_text)
        caption = clean_caption(caption_text)

        data_dict = {
            'filename': filename,
            "path": file_path,
            "image_key": image_key,
            "tags": tags,
            "existing_tags": existing_tags,
            "caption": caption,
            "existing_caption": existing_caption
        }
        data_list.append(data_dict)

    return data_list


def save_tags_and_captions(json_list, filename=None):
    """
    jsonオブジェクトリストから画像の存在するフォルダにタグ(.txt)とキャプション(.caption)を保存する

    Args:
        json_list (list): 結果が格納されたJSONファイルのパス。
    """
    metadata = create_data(json_list, filename)

    # metadataからimage_key､tags, captionを取得
    for data in metadata:
        filename = data['filename']
        image_folder = data['path']
        tags = data['tags']
        caption = data['caption']

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        if JOIN_EXISTING_TXT:
            # 既存のタグとキャプションを取得
            existing_tags = data['existing_tags']
            existing_caption = data['existing_caption']

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


def caption_gpt4(input_dir):
    """#フォルダ内の画像に対応した.captionがない場合OpenAI API GTP-4を使って生成
    Args:
        input_dir (Path): 入力フォルダ
    """
    # フォルダを走査してキャプションの生成
    for file in input_dir.rglob('*'):
        if file.suffix == '.webp': #webp以外の画像の場合はリサイズ等の処理がされてないから無視
            image_path = input_dir / file
            print(f'Processing {file}...')
            # 画像をBase64エンコードでロード
            base64img = encode_image(image_path)
            #キャプションの生成
            json_list = generate_caption_openai(MODEL, base64img)
            # キャプションをファイルに保存
            save_tags_and_captions(json_list, file)


if __name__ == "__main__":
    if GENERATE_BATCH_JSONL:
        caption_batch(IMAGE_FOLDER, MODEL)

    # GPT-4でキャプション生成
    caption_gpt4(IMAGE_FOLDER)

    # if JSONL_FILE_FOLDER.is_dir():
    #     #指定されてる場合はJSOLファイルを結合するとみなす
    #     jsonl_data = process_jsonl_files(JSONL_FILE_FOLDER, join_files=True)
    # else:
    #     jsonl_data = process_jsonl_files(JSONL_FILE_PATH)

    # if GERERATE_META_CLEAN:
    #     json_to_metadata(jsonl_data)
    # if GERERATE_TAGS_AND_CAPTIONS_TXT:
    #     save_tags_and_captions(JSONL_FILE_PATH)



