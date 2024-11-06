"""
ふぉるだ内の画像に対応した.captionがない場合バッチ処理用JSONに追加
GPT4でバッチ処置を開始
開始までなので結果は別に確認
    Returns:
        _type_: _description_
    """
import os
import configparser
from pathlib import Path
import base64
import json
import requests
import math

# 設定
input_dir = Path(r'your_imgdir_path')
MODEL = "gpt-4-turbo"
config = configparser.ConfigParser()
config.read('apikey.ini')
api_key = config['KEYS']['openai_api_key']
sprit_json_uploas = True

def encode_image(image_path):
    '''画像をBase64エンコードして返す'''
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def generate_instructions_json(img_id, model, base64img):
    '''バッチ用プロンプトを作成'''
    prompt = "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \
                    Each image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. \
                    For images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \
                    For landscapes or objects, focus on the material, historical context, and any significant features. \
                    Always use precise and specific tags—prefer \"Gothic cathedral\" over \"building\" Avoid duplicative tags. \
                    Each set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. \
                    Also, provide a concise 1-2 sentence caption that captures the image's narrative or essence. \
                    High-quality tagging and captioning will be compensated at $10 per image, rewarding exceptional clarity and precision that enhance image recreation"
    payload = {
        "custom_id": img_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {
                "role": "user",
                "content": [
                    {
                    "type": "text",
                    "text": prompt
                    },
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/webp;base64,{base64img}",
                    "detail": "high"
                }
                }
            ]
            }
        ],
        "max_tokens": 3000
        }
    }
    return payload

def save_jsonline_to_file(batch_payloads, filename):
    """データリストをJSON Lines形式でファイルに保存する"""
    with open(filename, 'w', encoding='utf-8') as f:
        for item in batch_payloads:
            json.dump(item, f)
            f.write('\n')  # 各JSONオブジェクトの後に改行を追加
    print(f"Data saved to {filename}")
    return filename

def upload_json_to_openai(json_path, purpose='batch'):
    """JSONファイルをOpenAI APIにアップロードする"""
    url = "https://api.openai.com/v1/files"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    files = {
        'file': open(json_path, 'rb')
    }
    data = {
        'purpose': purpose
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

def start_batch_processing(input_file_id):
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

def caption_batch(input_dir):
    """#フォルダ内の画像に対応した.captionがない場合バッチ処理用JSONに追加
    Args:
        input_dir (Path): 入力ディレクトリ
    """
    batch_payloads = []
    # ディレクトリを走査してキャプションの生成
    for filename in input_dir.rglob('*'):
        # 拡張子を除去したファイル名の取得
        base_filename = os.path.splitext(filename)[0]
        if filename.name.lower().endswith(('webp')): #webp以外の画像の場合はリサイズ等の処理がされてないから無視
            image_path = os.path.join(input_dir, filename)
            caption_path = os.path.join(input_dir, f'{base_filename}.caption')
            # キャプションファイルが存在しない場合のみ処理を行う
            if not os.path.exists(caption_path):
                print(f'Processing {filename}...')
                base64img = encode_image(image_path)
                payload = generate_instructions_json(base_filename, MODEL, base64img)
                batch_payloads.append(payload)

    jsonl_path = save_jsonline_to_file(batch_payloads, 'instructions.jsonl')

    # サイズチェックしてjsonlが96MB[OpenAIの制限]を超えないようにするために分割する
    jsonl_size = os.path.getsize(jsonl_path)
    if jsonl_size > 100663296:
        print("JSONLファイルが大きすぎます。分割します。")
        # jsonl_sizeに基づいてファイルを分割
        split_size = math.ceil(jsonl_size / 100663296)
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        lines_per_file = math.ceil(len(lines) / split_size)  # 各ファイルに必要な行数
        for i in range(split_size):
            split_filename = f'instructions_{i}.jsonl'
            split_path = os.path.join(os.path.dirname(jsonl_path), split_filename)
            with open(split_path, 'w', encoding='utf-8') as f:
                f.writelines(lines[i * lines_per_file:(i + 1) * lines_per_file])

            if sprit_json_uploas:
                upload_file_id = upload_json_to_openai(split_path)
                start_batch_processing(upload_file_id)
            else:
                print(f"分割ファイルを保存しました: {split_path}")
                print("分割ファイルをアップロードしてバッチ処理を開始するには、sprit_json_uploasをTrueに設定してください。")
    else:
        upload_file_id = upload_json_to_openai(jsonl_path)
        start_batch_processing(upload_file_id)

caption_batch(input_dir)