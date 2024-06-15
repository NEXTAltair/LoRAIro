from pathlib import Path
from PIL import Image
import toml
from datasets import Dataset, Features, Image as DatasetsImage, Value
from score_module.scorer import load_laion_model, load_cafe_model, calculate_laion_score, calculate_cafe_score
IMAGE_EXTENSIONS = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'] # 処理対象の画像ファイルの拡張子


def read_textfile(file_path: Path) -> str:
    """ファイルを読み込み、その内容を返す"""
    if file_path.exists():
        with file_path.open('r') as f:
            return f.read().strip()
    return ''

def process_image(img_path: Path, laion_model, laion_processor, cafe_pipe) -> dict:
    """画像ファイルから必要なデータを取得して辞書形式で返す"""
    tags_path = img_path.with_suffix('.txt')
    caption_path = img_path.with_suffix('.caption')
    tags = read_textfile(tags_path)
    caption = read_textfile(caption_path)

    if not tags:
        print(f"{img_path.name} が無いのでtagsフィールドは空文字")
    if not caption:
        print(f"{img_path.name} が無いのでcaptionフィールドは空文字")

    if tags or caption:
        # 画像の幅と高さを取得し、画像データを読み込む
        with Image.open(img_path) as img:
            width, height = img.size
            pixels = width * height

        # 画像のスコアを計算
        laion_aesthetic = calculate_laion_score(img, laion_model, laion_processor)
        cafe_aesthetic = calculate_cafe_score(img, cafe_pipe)

        # 結果を辞書に格納
        return {
            "file_name": str(img_path.name),
            "image": str(img_path),  # パスを保持する
            "tags": tags,
            "caption": caption,
            "width": width,
            "height": height,
            "pixels": pixels,
            "LAION_aesthetic": laion_aesthetic,
            "cafe_aesthetic": cafe_aesthetic,
        }

    return None


def create_hfdataset(image_dir: Path) -> Dataset:
    """画像ディレクトリからデータセットを作成する"""
    # モデルとプロセッサをロード
    laion_model, laion_processor = load_laion_model()
    cafe_pipe = load_cafe_model()

    data = []
    for img_path in image_dir.glob('*'):
        if img_path.suffix in IMAGE_EXTENSIONS:
            # 画像処理を行い、結果をリストに追加
            processed_data = process_image(img_path, laion_model, laion_processor, cafe_pipe)
            if processed_data:
                data.append(processed_data)

    # フィールドごとのリストに変換
    dataset_dict = {
        "file_name": [item["file_name"] for item in data],
        "image": [item["image"] for item in data],
        "tags": [item["tags"] for item in data],
        "caption": [item["caption"] for item in data],
        "width": [item["width"] for item in data],
        "height": [item["height"] for item in data],
        "pixels": [item["pixels"] for item in data],
        "LAION_aesthetic": [item["LAION_aesthetic"] for item in data],
        "cafe_aesthetic": [item["cafe_aesthetic"] for item in data],
    }

    # データセットのスキーマを定義
    features = Features({
        "file_name": Value("string"),
        "image": DatasetsImage(),
        "tags": Value("string"),
        "caption": Value("string"),
        "width": Value("int32"),
        "height": Value("int32"),
        "pixels": Value("int32"),
        "LAION_aesthetic": Value("float32"),
        "cafe_aesthetic": Value("float32"),
    })

    # データセットを作成
    dataset = Dataset.from_dict(dataset_dict, features=features)
    print(dataset[:5])
    return dataset

def push_to_hub(dataset: Dataset, repo_name: str, token: str) -> None:
    dataset.push_to_hub(repo_name, token=token)

if __name__ == "__main__":
    # TOMLファイルを読み込む
    config_path = Path("TagDatasetCreat_conf.toml")
    config = toml.load(config_path)

    # 必要な設定を取得
    image_dir = Path(config['paths']['image_dir'])
    output_dir = Path(config['paths']['output_dir'])
    repo_name = config['hf']['repo_name']
    hf_token = config['hf']['token']

    # データセットを作成
    dataset = create_hfdataset(image_dir)

    # Hugging Face Hubにプッシュ
    push_to_hub(dataset, repo_name, hf_token)