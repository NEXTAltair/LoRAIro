"""
OpenAIのAPIを利用して取得したJSONLファイルから、メタデータを生成するスクリプト
メタデータは、画像のファイル名、パス、キャプション、タグの情報を含む辞書のリストを作成する
メタデータは、meta_clean.jsonとして保存される
"""
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_captions_to_metadata.py
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_dd_tags_to_metadata.py
import os
import json
from pathlib import Path
from cleanup_txt import clean_format, clean_tags, clean_caption

#Path
#学習元画像ファイルがあるディレクトリ
train_images_dir = Path(r'H:\lora\素材リスト\スクリプト\testimg')
#分割されたjsonlファイルがある場合のディレクトリ
jsonl_file_dir = Path(r'H:\lora\素材リスト\スクリプト\jsonl')
#分割されてないjsonlファイルのパス
jsonl_file_path = Path(r'')
#出力ディレクトリ(結合されたjsonlファイル、meta_clean.json､APIエラーを起こした画像の保存先)
#TagとCaptionを別々に保存する場合は画像の存在するフォルダに保存されるので指定不要
output_dir =  Path(r'H:\lora\素材リスト\スクリプト\Testoutput')

#オプション設定
GERERATE_META_CLEAN = True # meta_clean.jsonを生成するかどうか
GERERATE_TAGS_AND_CAPTIONS_TXT = True # タグとキャプションを別々にしたテキストファイルを生成するかどうか
JOIN_EXISTING_TXT = True # 既存のタグとキャプションがある場合新規のものとを結合するかどうか

def joined_jsonl(jsonl_dir, joined_output_dir):
    """分割されたJSONLファイルを結合して一つのJSONLファイルにする
    Args:
        jsonl_file_dir (Path): 結合するJSONLファイルが格納されたディレクトリ
        joined_output_dir (Path): 結合されたJSONLファイルを保存するディレクトリ
    Returns:
        Path: 結合されたJSONLファイルのパス
    """
    jsonl_files = list(jsonl_dir.glob('*.jsonl'))
    joined = joined_output_dir / 'joined.jsonl'
    with open(joined, 'w', encoding='utf-8') as outfile:
        for jsonl_file in jsonl_files:
            with open(jsonl_file, 'r', encoding='utf-8') as infile:
                for line in infile:
                    outfile.write(line)
    return joined

def read_jsonl(jsonl_path):
    """JSONLファイルを読み込み、各行をJSONオブジェクトとして返す。
    Args:
        jsonl_path (Path): JSONLファイルのパス
    Returns:
        list: JSONオブジェクトのリスト
    """
    data = []
    with open(jsonl_path, 'r', encoding='utf-8') as file:
        for line in file:
            data.append(json.loads(line.strip()))
    return data

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

    error_image_path = error_images_folder / filename + '.webp'
    Path(image_key).rename(error_image_path)

def create_data(json_list):
    """
    JSONLから読み込んだデータリストを基に、ファイル名、パス、キャプション、タグの情報を含む辞書のリストを作成する
    Args:
        data_list (list): JSONオブジェクトのリスト。各オブジェクトは読み込んだJSONLの一行から得られる。
    Returns:
        list of dict: ファイル名、パス、キャプション、タグ情報を含む辞書のリスト。
    """
    data_list = []
    for data in json_list:
        custom_id = data.get('custom_id')
        #custom_idから拡張子を含まないファイル名を取得
        if '\\' in custom_id or '/' in custom_id:
            filename = Path(custom_id).name
        else:
            filename = custom_id

        #image_keyを取得はstr型
        #webp以外は画像処理してないとみなして扱わない
        image_key = next((str(p) for p in Path(train_images_dir).rglob(f"{filename}.webp")), None)
        if not image_key:
            print(f"train_images_dirに{filename}.webpが存在しません.skipします。\n"
                "train_images_dirの指定ミスか学習からハネた")
            continue

        # Path オブジェクトに変換
        image_path = Path(image_key)
        # 画像ファイルが存在するフォルダのパスを取得
        file_path = image_path.parent

        # JSONデータからタグとキャプションとタグを抽出して保存
        content = json_list[1]['response']['body']['choices'][0]['message']['content']
        content = clean_format(content)

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

        #train_images_dirに既存の.txtや.captionファイルがある場合にその情報を取得
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"
        if (file_path / tags_filename).exists():
            with open(file_path / tags_filename, 'r', encoding='utf-8') as tags_file:
                existing_tags = tags_file.read()
        if (file_path / caption_filename).exists():
            with open(file_path / caption_filename, 'r', encoding='utf-8') as cap_file:
                existing_caption = cap_file.read()

        if JOIN_EXISTING_TXT:
            # 既存のタグとキャプションがある場合は結合
            tags = existing_tags + tags
            caption = existing_caption + caption

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

def json_to_metadata(json_list):
    """jsonオブジェクトリストからKohya-ss用のmeta_clean.json���生成する
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


def save_tags_and_captions(json_list):
    """
    jsonオブジェクトリストから画像の存在するフォルダにタグ(.txt)とキャプション(.caption)を保存する

    Args:
        json_list (list): 結果が格納されたJSONファイルのパス。
    """
    metadata = create_data(json_list)

    # metadataからimage_key､tags, captionを取得
    for data in metadata:
        filename = data['filename']
        image_folder = data['path']
        tags = data['tags']
        caption = data['caption']

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        # タグをテキストファイルに保存
        with open(os.path.join(image_folder, tags_filename), 'w', encoding='utf-8') as tags_file:
            tags_file.write(tags)

        # キャプションをキャプションファイルに保存
        with open(os.path.join(image_folder, caption_filename), 'w', encoding='utf-8') as cap_file:
            cap_file.write(caption)

        print(f"Saved tags to {tags_filename}")
        print(f"Saved caption to {caption_filename}")


if __name__ == "__main__":
    if jsonl_file_dir.is_dir():
        jsonl_file_path = joined_jsonl(jsonl_file_dir, output_dir)
    json_file = read_jsonl(jsonl_file_path)
    if GERERATE_META_CLEAN:
        json_to_metadata(json_file)
    if GERERATE_TAGS_AND_CAPTIONS_TXT:
        save_tags_and_captions(jsonl_file_path)

