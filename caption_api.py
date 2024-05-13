import configparser
from pathlib import Path
import base64
import json
import math
import requests


# 設定
MODEL = "gpt-4-turbo"
GENERATE_BATCH_JSONL = True #バッチ処理用JSONを生成するか
SPLIT_JSONL_UPLOADS = True #分割したJSONLファイルをアップロードするか
NSFW_IMAGE = True #

IMAGE_FOLDER = Path(r'H:\lora\asscutout-XL\img_Processed')

config = configparser.ConfigParser()
config.read('apikey.ini')
api_key = config['KEYS']['openai_api_key']

def encode_image(image_path):
    '''画像をBase64エンコードして返す'''
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


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


def upload_bach_jsonl(jsonl_path, api_key):
    """JSONファイルをOpenAI APIにアップロードする"""
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


def generate_caption_openai(headers, payload):
    """キャプションを即時生成する
    Args:
        model (model name): 使用するモデル名
        base64img (str): 画像のBase64エンコード文字列
    Returns (str): 生成されたキャプション
    """
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    response_data = response.json()
    try:
        # choices 配列の最初の要素からキャプションを取得
        caption = response_data["choices"][0]["message"]["content"]
        return caption
    except KeyError:
        # エラーがあればその内容を表示
        return "Error generating caption: " + response.text


def save_tags_and_caption(input_text, base_filename, output_dir):
    """入力テキストからタグとキャプションを抽出し、別々のファイルに保存する。
    Args:
        input_text (str): 'Tags:' と 'Caption:' を含むテキスト。
        image_filename (str): 画像ファイルの名前。
        output_dir (str): 出力フォルダのパス。
    """
    # 'Tags:' と 'Caption:' のインデックスを見つける
    tags_index = input_text.find('Tags:')
    caption_index = input_text.find('Caption:')

    # タグとキャプションのテキストを抽出
    tags_text = input_text[tags_index + len('Tags:'):caption_index].strip()
    caption_text = input_text[caption_index + len('Caption:'):].strip()

    # ファイル名の準備
    tags_filename = f"{base_filename}.txt"
    caption_filename = f"{base_filename}.caption"

    # タグをテキストファイルに保存
    with open(output_dir / tags_filename, 'w', encoding='utf-8') as file:
        file.write(tags_text)

    # キャプションをキャプションファイルに保存
    with open(output_dir / caption_filename, 'w', encoding='utf-8') as file:
        file.write(caption_text)

    print(f"Tags saved to {tags_filename}")
    print(f"Caption saved to {caption_filename}")


def caption_gpt4(input_dir):
    """#フォルダ内の画像に対応した.captionがない場合OpenAI API GTP-4を使って生成
    Args:
        input_dir (Path): 入力フォルダ
    """
    # フォルダを走査してキャプションの生成
    for filename in input_dir.rglob('*'):
        # 拡張子を除去したファイル名の取得
        base_filename = filename.stem
        if filename.lower().endswith(('webp')): #webp以外の画像の場合はリサイズ等の処理がされてないから無視
            image_path = input_dir / filename
            caption_path = input_dir / f'{base_filename}.caption'
            # キャプションファイルが存在しない場合のみ処理を行う
            if not caption_path.exists():
                print(f'Processing {filename}...')
                # 画像をBase64エンコードでロード
                base64img = encode_image(image_path)
                #キャプションの生成
                caption = generate_caption_openai(MODEL, base64img)
                print(caption)
                # キャプションをファイルに保存
                save_tags_and_caption(caption, base_filename, input_dir)


if __name__ == "__main__":
    if GENERATE_BATCH_JSONL:
        caption_batch(input_dir, MODEL)

    # GPT-4でキャプション生成
    caption_gpt4(input_dir)