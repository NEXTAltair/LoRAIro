
import os

import clip
import numpy as np
import pytorch_lightning
import torch
from PIL import Image
from torchvision.transforms import CenterCrop, Compose, Normalize, Resize, ToTensor

try:
    from torchvision.transforms import InterpolationMode
    BICUBIC = InterpolationMode.BICUBIC
except ImportError:
    BICUBIC = Image.BICUBIC
def _convert_image_to_rgb(image):
    return image.convert("RGB")
def _transform(n_px):
    return Compose([
        Resize(n_px, interpolation=BICUBIC),
        CenterCrop(n_px),
        _convert_image_to_rgb,
        ToTensor(),
        Normalize((0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)),
    ])
def get_image_preprocess(preprocess_size, scale=1):
    return _transform(preprocess_size*scale)

class MLP(pytorch_lightning.LightningModule):
    def __init__(self, input_size, xcol='emb', ycol='avg_rating'):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = max(self.input_size//2, 1024)
        self.xcol = xcol
        self.ycol = ycol
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(self.input_size, self.hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size, 1)
        )

    def forward(self, x):
        return self.layers(x)

class Score_Manager:
    def __init__(self, model_path, device, score_max, args=None) -> None:
        score_args = {}
        if args is not None:
            for net_arg in args:
                key, value = net_arg.split("=")
                if key == "version":
                    version = int(value)
        if version == 0:
            self.image_size = 1
            self.max_tokens = 77
        elif version == 1:
            self.image_size = 1
            self.max_tokens = 231
        elif version == 2:
            self.image_size = 5
            self.max_tokens = 77
        elif version == 3:
            self.image_size = 5
            self.max_tokens = 231

        self.token_chunk = 77
        self.token_split_num = self.max_tokens // self.token_chunk

        self.image_preprocess = None
        self.clip_model, self.clip_preprocess = clip.load("ViT-L/14", device="cpu")  #RN50x64
        self.preprocess_size = self.clip_model.visual.input_resolution
        if version >= 2:
            self.image_preprocess = get_image_preprocess(self.preprocess_size, 2)
        self.tokenizer = clip.tokenize
        self.mlp = MLP(768*(self.image_size+self.token_split_num))
        self.device = device
        if score_max is not None:
            self.score_max = score_max
        else:
            self.score_max = 1.
        if os.path.splitext(model_path)[-1]!=".pth":
            model_path = f"{model_path}.pth"
        s = torch.load(model_path)

        self.mlp.load_state_dict(s)

    def to_gpu(self):
        self.mlp.to(self.device)
        self.mlp.requires_grad_(False)
        self.mlp.eval()
        self.clip_model.to(self.device)
        self.clip_model.eval()
    def to_cpu(self):
        self.mlp.to("cpu")
        self.clip_model.to("cpu")

    def _get_txt_id(self, prompt):
        txt_id = self.tokenizer(prompt, context_length=self.max_tokens, truncate=True).to(self.device)
        if txt_id.size(1) > self.max_tokens:
            print(f"too long token({txt_id.size()}): {prompt}")
        txt_features_list = []
        for i in range(self.token_split_num):
            txt_features = self.clip_model.encode_text(txt_id[:,i*self.token_chunk:(i+1)*self.token_chunk])
            txt_features_list.append(txt_features)
        if self.token_split_num>1:
            txt_features = torch.concat(txt_features_list, dim=1)
        return txt_id, txt_features

    def get_score(self, raw_image, prompt):
        with torch.no_grad():
            #txt_id = self.tokenizer(prompt, truncate=True).to(self.device)
            #if txt_id.size(1) > 77:
            #    print(f"too long token({txt_id.size()}): {prompt}")
            txt_id, txt_features = self._get_txt_id(prompt)
            image = self.clip_preprocess(raw_image).unsqueeze(0).to(self.device)
            image_features = self.clip_model.encode_image(image)
            if self.image_size == 5:
                image = self.image_preprocess(raw_image).unsqueeze(0).to(self.device)
                for i in range(2):
                    for j in range(2):
                        image_features = torch.concat([image_features,self.clip_model.encode_image(image[:,:,i*self.preprocess_size:(i+1)*self.preprocess_size,j*self.preprocess_size:(j+1)*self.preprocess_size])], dim=1)

            #txt_features = self.clip_model.encode_text(txt_id)
            input_emb = torch.concat([image_features, txt_features], dim=1)

        return self.mlp(input_emb).data.cpu()[0][0]/self.score_max
