from pathlib import Path
from PIL import Image
import toml
import logging
from datasets import Dataset, Features, Image as DatasetsImage, Value, load_dataset, concatenate_datasets
from score_module.scorer import AestheticScorer

# ログ設定 (必要に応じてカスタマイズ)
logging.basicConfig(
    filename='dataset_creation.log',
    level=logging.WARNING,
    encoding='utf-8'  # エンコーディングをUTF-8に設定無いと文字化け
)

IMAGE_EXTENSIONS = ['.jpg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.jpeg', '.webp'] # 処理対象の画像ファイルの拡張子


def read_textfile(file_path: Path) -> str:
    """
    テキストファイルの内容を読み込んで文字列として返す関数

    Parameters:
        file_path (Path): 読み込むテキストファイルのパス

    Returns:
        str: テキストファイルの内容
    """
    if file_path.exists():
        with file_path.open('r', encoding='utf-8') as f:
            return f.read().strip()
    return ''

def process_image(img_path, scorer) -> dict:
    """
    学習用画像ディレクトリの処理を行い、結果を辞書として返す関数

    Args:
        img_path (Path): 画像ファイルのパス
        scorer (AestheticScorer): スコアリングクラスのインスタンス

    Returns:
        dict: 画像の情報を格納した辞書
    """
    tags_path = img_path.with_suffix('.txt')
    caption_path = img_path.with_suffix('.caption')
    tags = read_textfile(tags_path)
    caption = read_textfile(caption_path)

    if not tags:
        print(f"{img_path.stem}.txt が無いのでtagsフィールドは空文字")
    if not caption:
        print(f"{img_path.stem}.caption が無いのでcaptionフィールドは空文字")

    if tags or caption:
        # 画像の幅と高さを取得し、画像データを読み込む
        with Image.open(img_path) as img:
            width, height = img.size
            pixels = width * height

        # 画像のスコアを計算 # TODO: スコアリングメソッドは汚いのでリファクタリングする
        laion_aesthetic = scorer.score(img, model_type="laion")
        cafe_aesthetic = scorer.score(img, model_type="cafe")

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

def create_hfdataset(image_dir: Path, existing_data: Dataset = None) -> Dataset:
    """画像ディレクトリからデータセットを作成する
    Args:
        image_dir (Path): 画像ファイルのあるディレクトリ
        existing_data (Dataset, optional): 既存のデータセット. Defaults to None.
    Returns:
        Dataset: Hugging Face Datasets
    """
    data = []
    # ループ前にスコアリングクラスを初期化してモデルロードしないと処理が遅い
    scorer = AestheticScorer()
    for img_path in image_dir.rglob('*'):
        if img_path.suffix in IMAGE_EXTENSIONS:
            with open(img_path.with_suffix('.txt'), encoding='utf-8') as tags_file:
                tags_lines = tags_file.readlines()  # 全ての行をリストとして読み込む

            if len(tags_lines) > 1:
                error_message = f"Error: タグファイルが複数行: {img_path.name}"
                print(error_message)  # コンソールに出力
                logging.warning(error_message)  # ログファイルに記録
                continue
            tags_text = tags_lines[0].strip()  # 末尾の改行文字を削除
            if existing_data is not None:
                # 既存データに同じタグのデータが存在するか確認
                existing_tags = existing_dataset['train']['tags']
                if tags_text in existing_tags:
                    print(f"Skip (タグが重複): {img_path}")
                    continue

            # 画像処理を行い、結果をリストに追加
            processed_data = process_image(img_path, scorer)
            if processed_data:
                data.append(processed_data)

    # フィールドごとのリストに変換 TODO: リスト化しないとdataset.from_dictでエラーが出るが処理が雑多な気がする
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

    # 既存のデータセットをHugging Face Hubからロード
    try:
        existing_dataset = load_dataset(repo_name, use_auth_token=hf_token)
        existing_files = set(existing_dataset['train']['file_name'])
    except Exception as e:
        print(f"既存のデータセットの読み込みエラー｡新しいhfリポジトリを作るよ: {e}")
        existing_files = set()
        existing_dataset = None

    # 新しいデータセットを作成
    new_dataset = create_hfdataset(image_dir, existing_dataset)

    if not new_dataset:
        message = f"新しいデータセットが空。処理を終了"
        print(message)
        logging.warning(message)
        exit()
    # 既存のデータセットが存在する場合、マージ
    if existing_dataset:
        combined_dataset = concatenate_datasets([existing_dataset['train'], new_dataset])
    else:
        combined_dataset = new_dataset

    # Hugging Face Hubにプッシュ
    push_to_hub(combined_dataset, repo_name, hf_token)