# score_module/scorer.py
import torch
import requests
import numpy as np
from pathlib import Path
from PIL import Image
from transformers import pipeline
import clip
from dataclasses import dataclass
from typing import Dict, List

# モデルのURL
LAION_MODEL_URL = "https://github.com/grexzen/SD-Chad/blob/main/sac+logos+ava1-l14-linearMSE.pth?raw=true"
CAFE_MODEL_URL = "https://huggingface.co/cafeai/cafe_aesthetic/resolve/main/model.safetensors?download=true"

def download_model(url: str, model_path: Path):
    """URLからモデルをダウンロードする
    スコアモデルが増えたとき用に関数化しておく
    Args:
        url (str): ダウンロードするモデルのURL
        model_path (Path): 保存先のパス
    """
    response = requests.get(url, stream=True)
    response.raise_for_status() # HTTPリクエストが失敗した場合、例外を発生させる
    with open(model_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192): # データをチャンクごとに読み込む
            f.write(chunk) # ファイルに書き込む
    print(f"保存完了 {model_path}")

# モデルの読み込み部分をクラスの初期化時に移動
@dataclass
class AestheticScorer:
    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    def __post_init__(self):
        # LAIONモデルの読み込み
        self.laion_model, self.laion_processor = self._load_laion_model()
        # CAFEモデルの読み込み
        self.cafe_pipe = self._load_cafe_model()
        # CLIPモデルの読み込み
        self.clip_model, _ = clip.load("ViT-L/14", device=self.device)

    def _load_laion_model(self):
        model_path = Path("score_module/score_models/sac+logos+ava1-l14-linearMSE.pth")
        if not model_path.exists():
            print("LAION モデルダウンロード...")
            download_model(LAION_MODEL_URL, model_path)

        model = AestheticPredictor(768)  # 768はCLIPの出力次元数
        model.load_state_dict(torch.load(model_path, map_location=self.device))
        model.eval()
        model.to(self.device) # モデルを適切なデバイスに移動
        processor = clip.load("ViT-L/14", device=self.device)[1]
        return model, processor

    def _load_cafe_model(self):
        pipe_aesthetic = pipeline("image-classification", "cafeai/cafe_aesthetic", device=self.device)
        return pipe_aesthetic


    def score(self, image: Image.Image, model_type) -> float:
        if model_type == "laion":
            score = self._calculate_laion_score(image)
        elif model_type == "cafe":
            score = self._calculate_cafe_score(image)
        else:
            raise ValueError(f"model_type が不正: {model_type}")
        return score

    def _calculate_laion_score(self, image: Image.Image):
        """LAIONモデルを使って美的スコアを計算する
        Args:
            image (Image.Image): スコアを計算する画像
        Returns:
            float: 美的スコア
        """
        image_tensor = self.laion_processor(image).unsqueeze(0).to(self.device) # 画像をテンソルに変換し、デバイスに移動

        with torch.no_grad(): # 勾配計算を行わない
            image_features = self.clip_model.encode_image(image_tensor) # CLIPモデルで画像の特徴量を抽出
            # 特徴量を正規化し、型とデバイスを調整
            image_features = torch.from_numpy(normalized(image_features.cpu().detach().numpy())).to(self.device).float() 

        prediction = self.laion_model(image_features) # LAIONモデルでスコアを予測

        score = prediction.data.cpu().item() # スコアをCPUに移動し、Pythonの数値に変換
        return score

    def _calculate_cafe_score(self, image: Image.Image):
        """CAFEモデルを使って美的スコアを計算する
        Args:
            image (Image.Image): スコアを計算する画像
        Returns:
            float: 美的スコア
        """
        data = self.cafe_pipe(image, top_k=1) # CAFEモデルでスコアを予測
        score = data[0]['score'] if data else 0.0 # スコアを取得
        return score

def normalized(a, axis=-1, order=2):
    """ベクトルを正規化する関数
    Args:
        a (np.array): 正規化するベクトル
        axis (int, optional): 正規化する軸. Defaults to -1.
        order (int, optional): ノルムの次数. Defaults to 2.
    Returns:
        np.array: 正規化されたベクトル
    """
    l2 = np.atleast_1d(np.linalg.norm(a, order, axis)) # ベクトルaのノルムを計算
    l2[l2 == 0] = 1 # ノルムが0の場合は1にする
    return a / np.expand_dims(l2, axis) # 正規化

@dataclass
class AestheticPredictor(torch.nn.Module):
    input_size: int

    def __post_init__(self):
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(self.input_size, 1024),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(1024, 128),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(128, 64),
            torch.nn.Dropout(0.1),
            torch.nn.Linear(64, 16),
            torch.nn.Linear(16, 1),
        )

    def forward(self, x):
        return self.layers(x)