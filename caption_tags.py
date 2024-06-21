"""
APIを利用してtagとcaptionをいい感じに生成するスクリプト
"""
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_captions_to_metadata.py
#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/merge_dd_tags_to_metadata.py
import toml
import base64
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from module.cleanup_txt import clean_format, clean_tags, clean_caption
from module.api_utils import OpenAIApi


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


@dataclass
class ImageSize:
    width: int
    height: int
    resolution: str
    aspect_ratio: str
    color_profile: Optional[str] = None

@dataclass
class ImageMetadata:
    path: Path
    image: str  # base64 encoded image
    tags: Dict[str, List[str]] = field(default_factory=dict)
    caption: Dict[str, str] = field(default_factory=dict)
    size: Optional[ImageSize] = None
    score: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if "existing" not in self.tags:
            self.tags["existing"] = []
        if "existing" not in self.caption:
            self.caption["existing"] = ""

    @property
    def name(self) -> str:
        return self.path.stem

    def add_tags(self, model: str, new_tags: List[str]):
        if model not in self.tags:
            self.tags[model] = []
        self.tags[model].extend(new_tags)

    def set_caption(self, model: str, new_caption: str):
        self.caption[model] = new_caption

    def set_score(self, model: str, score: float):
        self.score[model] = score

    def set_size(self, width: int, height: int, color_profile: Optional[str] = None):
        resolution = f"{width}x{height}"
        aspect_ratio = f"{width}:{height}"
        self.size = ImageSize(width, height, resolution, aspect_ratio, color_profile)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.name,
            "image": self.image,
            "tags": self.tags,
            "caption": self.caption,
            "size": vars(self.size) if self.size else None,
            "score": self.score
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ImageMetadata':
        path = Path(data['path'])
        metadata = cls(
            path=path,
            image=data['image'],
            tags=data.get('tags', {"existing": []}),
            caption=data.get('caption', {}),
            score=data.get('score', {})
        )
        if data.get('size'):
            metadata.size = ImageSize(**data['size'])
        return metadata

class ImageMetadataLoader:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir

    def load_images(self) -> Dict[str, ImageMetadata]:
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
            existing_tags = self._read_file(txt_file) if txt_file.exists() else ""
            existing_caption = self._read_file(caption_file) if caption_file.exists() else ""

            metadata = ImageMetadata(
                path=image_path,
                image=encoded_image,
                tags={"existing": clean_tags(existing_tags).split(", ")},
                caption={"existing": clean_caption(existing_caption)}
            )

            image_data[image_key] = metadata

        return image_data

    @staticmethod
    def _read_file(file_path: Path) -> str:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

class Metadata:
    def __init__(self, img_data):
        loader = ImageMetadataLoader(dataset_dir)
        self.data = loader.load_images()

    def create_data(self, json_input: List[Dict], file: str = None) -> Dict[str, Dict]:
        """
        JSONLから読み込んだデータを基に、ファイル名、パス、キャプション、タグの情報を追加する
        Args:
            json_input (list or dict): JSONオブジェクトのリストまたは辞書。各オブジェクトは読み込んだJSONLの一行から得られる。
            file (str): 即時生成の場合のファイル名
        Returns:
            dict: ファイル名、パス、キャプション、タグ情報を含む辞書
        """
        for data in json_input:
            if file: #即時生成の場合
                content = data['choices'][0]['message']['content']
                image_key = str(Path(file).resolve())

            elif 'custom_id' in data: #バッチ生成の場合
                custom_id = data.get('custom_id')
                # self.data と照合する
                matching_image = next((v for v in self.data.values() if v.name == custom_id or str(v.path) == custom_id), None)
                if not matching_image:
                    print(f"画像ディレクトリに｢ {custom_id} ｣が存在しない\n"
                            "dataset_dirの指定ミスか学習からハネた")
                    continue
                image_key = str(matching_image.path)
                content = data['response']['body']['choices'][0]['message']['content']

            else: #API不使用でデータのクリーンナップのみの場合
                image_key = data['path']
                content = f"Tags: {', '.join(self.data[image_key].tags['existing'])}, Caption: {self.data[image_key].caption['existing']}"

            content = clean_format(content)
            # 'tags:' と 'caption:' が何番目に含まれているかを見つける
            tags_index = content.find('tags:')
            caption_index = content.find('caption:')

            # 'Tags:' か 'Caption:'が含まれていない場合はAPIエラーか弾かれているので例外処理
            # APIの処理のブレでたまに｢### Tsgs,｣や｢###Captin,｣で始まることがあるのでそれも弾く
            # 数は多くないので手動で処理してくれることを期待
            if tags_index == -1 and caption_index == -1:
                print(f"この場合うっかりエロ画像をAPIに投げた可能性がある")
                print(f"Error Information:\nImage Key: {image_key}\nContent: {content}\n-----")
                move_error_images(Path(image_key)) # TODO:
                continue

            # タグとキャプションのテキストを抽出
            tags_text = content[tags_index + len('Tags:'):caption_index].strip()
            caption_text = content[caption_index + len('Caption:'):].strip()

            # タグとキャプションをクリーンアップ
            self.data[image_key].add_tags(model, clean_tags(tags_text).split(", "))
            self.data[image_key].set_caption(model, clean_caption(caption_text))

        return {k: asdict(v) for k, v in self.data.items()}

    def json_to_metadata(self):
        """ImageDataオブジェクトの変数からKohya/sd-scripts用メタデータを生成する
        """
        metadata_clean = {}
        # metadataからimage_key､tags, captionを取得
        for image_key, value in self.data.items():
            tags = value.tags
            caption = value.caption

            # metadataからimage_key､tags, captionをmetadata_clene.jsonに保存
            # image_key をキーとしてメタデータを格納
            metadata_clean[image_key] = {
                'tags': tags,
                'caption': caption
                }

        with open(output_dir / 'meta_clean.json', 'w', encoding='utf-8') as file:
            json.dump(metadata_clean, file, ensure_ascii=False, indent=4)

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

def process_jsonl_files(input_path):
    """
    JSONLファイルを処理し、内容を読み込むか、複数のファイルを結合する。
    Args:
        input_path (Path): JSONLファイルのパスまたは結合するファイルが格納されたディレクトリ。
    Returns:
        list: JSONオブジェクトのリスト
    """
    jsonl_files = list(input_path.glob('*.jsonl'))
    combined_lines = []
    for jsonl_file in jsonl_files:
        with open(jsonl_file, 'r', encoding='utf-8') as infile:
            combined_lines.extend(infile.readlines())
    data = [json.loads(line.strip()) for line in combined_lines]
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


def save_tags_and_captions(metadata, model_to_save="generated", filename=None):
    """
    インスタンスの変数から.txtと.captionファイルを生成する
    Args:
        metadata (Metadata): Metadataクラスのインスタンス
        model_to_save (str): 保存するタグとキャプションのモデル名（デフォルトは"generated"）
        filename (str, optional): 特定のファイル名を指定する場合に使用
    """
    for image_key, value in metadata.data.items():
        filename = value.name
        dataset_dir = value.path.parent

        # タグの取得と結合
        existing_tags = value.tags.get('existing', [])
        model_tags = value.tags.get(model_to_save, [])
        combined_tags = clean_tags(", ".join(existing_tags + model_tags))

        # キャプションの取得と結合
        existing_caption = value.caption.get('existing', '')
        model_caption = value.caption.get(model_to_save, '')
        combined_caption = clean_caption(f"{existing_caption}, {model_caption}".strip(', '))

        # ファイル名の準備
        tags_filename = f"{filename}.txt"
        caption_filename = f"{filename}.caption"

        # タグをテキストファイルに保存
        if combined_tags:
            with open((dataset_dir / tags_filename), 'w', encoding='utf-8') as tags_file:
                tags_file.write(combined_tags)
            print(f"Saved tags to {tags_filename}\n{combined_tags}")

        # キャプションをキャプションファイルに保存
        if combined_caption:
            with open((dataset_dir / caption_filename), 'w', encoding='utf-8') as cap_file:
                cap_file.write(combined_caption)
            print(f"Saved caption to {caption_filename}\n{combined_caption}")


def write_to_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(content)


def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        return file.read()


def caption_gpt4(data: Metadata, oai: OpenAIApi):
    """
    フォルダ内の画像に対応したキャプションをOpenAI API GPT-4を使って生成し、
    その都度Metadataを更新する

    Args:
        data (Metadata): 処理対象の画像メタデータ
        oai (OpenAIApi): OpenAI APIクライアント
    """
    for image_key, image_metadata in data.data.items():
        # 親フォルダ名にnsfwが含まれる場合はスキップ
        if "nsfw" in Path(image_key).parent.name:
            print(f"エロ･グロはスキップ: {image_key}")
            continue

        print(f'Processing {image_key}...')
        try:
            # APIペイロードの生成
            header, payload = oai.generate_payload(image_key)
            # キャプションの生成
            response = oai.generate_immediate_response(payload, header)
            print(f"Response received for {image_key}")
            # Metadataの更新
            updated_metadata = data.create_data([response], file=image_key, model=oai.model)

            # 更新されたメタデータの確認
            if image_key in updated_metadata:
                print(f"Updated metadata for {image_key}")
                print(f"New tags: {updated_metadata[image_key]['tags'].get(oai.model, [])}")
                print(f"New caption: {updated_metadata[image_key]['caption'].get(oai.model, '')}")
            else:
                print(f"Warning: Metadata not updated for {image_key}")

        except Exception as e:
            print(f"Error processing {image_key}: {e}")

    print("タグ､キャプションの生成完了")

if __name__ == "__main__":
    data = Metadata(dataset_dir)
    oai = OpenAIApi(openai_api_key, model, prompt, data)

    if generate_batch_jsonl:
        jsonl_path = oai.caption_batch()
        if strt_batch:
            upload_file_id = oai.upload_jsonl_file(jsonl_path)
            oai.start_batch_processing(upload_file_id)
            print("バッチ処理が終了したらjsonlパスを指定して再度実行")
            exit()

    if response_file_dir != Path('.') and not response_file_dir.is_dir():
        print("jsonlファイルでなくjsonlを保存しているディレクトリを指定")
        exit()
    if response_file_dir != Path('.') and response_file_dir.is_dir():
        jsonl_count = len(list(response_file_dir.glob('*.jsonl')))
        file_count = len(list(response_file_dir.glob('*')))
        if jsonl_count == file_count:
            response_jsonl_data = process_jsonl_files(response_file_dir)
        else:
            print("レスポンスのjsonl以外のファイルがある｡Pathをミスってる可能性")
            exit()

    if generate_tags_and_captions_txt:
        try:
            if response_jsonl_data is not None:
                metadata = data.create_data()
        except:
            if generate:
                caption_gpt4(data, oai) #Metadataの更新
            img_datas = []
            for image_ley, img_data in data.data.items():
                print(f'Processing {image_ley}...')
                #valueをリストに追加
                img_datas.append(img_data)

        save_tags_and_captions(data)
    if generate_meta_clean:
        data.json_to_metadata()



