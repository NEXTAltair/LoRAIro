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
    """URLからダウンロード
    スコアモデルが増えたとき用に関数化しておく"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(model_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"保存完了 {model_path}")

def load_laion_model():
    model_path = Path("score_module/score_models/sac+logos+ava1-l14-linearMSE.pth")
    if not model_path.exists():
        print("LAION モデルダウンロード...")
        download_model(LAION_MODEL_URL, model_path)

    model = AestheticPredictor(768)  # 768はCLIPの出力次元数
    model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
    model.eval()
    processor = clip.load("ViT-L/14", device='cpu')[1]
    return model, processor

def load_cafe_model():
    pipe_aesthetic = pipeline("image-classification", "cafeai/cafe_aesthetic")
    return pipe_aesthetic

def calculate_laion_score(image: Path, model, processor):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    # CLIPモデルの読み込み
    clip_model, clip_preprocess = clip.load("ViT-L/14", device=device)

    image_tensor = clip_preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        image_features = clip_model.encode_image(image_tensor)

    image_features = image_features.float().cpu().detach().numpy()
    image_features = torch.from_numpy(normalized(image_features)).to(device).type(torch.cuda.FloatTensor)
    prediction = model(image_features)

    score = prediction.data.cpu().item()
    return score

def calculate_cafe_score(image: Path, pipe):
    data = pipe(image, top_k=1)
    score = data[0]['score'] if data else 0.0
    return score

def normalized(a, axis=-1, order=2):
    l2 = np.atleast_1d(np.linalg.norm(a, order, axis))
    l2[l2 == 0] = 1
    return a / np.expand_dims(l2, axis)

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

@dataclass
class AestheticScorer:
    laion_model: torch.nn.Module
    laion_processor: clip
    cafe_pipe: pipeline
    device: str

    def score(self, image: Image.Image, model_type="laion") -> float:
        if model_type == "laion":
            model, processor = self.laion_model, self.laion_processor
            score = calculate_laion_score(image, model, processor)
        else:
            pipe = self.cafe_pipe
            score = calculate_cafe_score(image, pipe)
        return score
