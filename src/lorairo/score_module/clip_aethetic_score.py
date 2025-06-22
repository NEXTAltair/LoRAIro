
import torch
import pytorch_lightning
import os
import clip
import numpy as np

from PIL import Image
from torchvision.transforms import Compose, Resize, CenterCrop, ToTensor, Normalize
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

def normalized(a, axis=-1, order=2):
    l2 = np.atleast_1d(np.linalg.norm(a, order, axis))
    l2[l2 == 0] = 1
    return a / np.expand_dims(l2, axis)

def get_property(version, model_name):
    if version == 0:
        scale_size = 1
        image_size = 1
        output = model_name
        npy_dot = ".npy"
        add_word = ""
    elif version == 1:
        scale_size = 2
        image_size = 1 + (scale_size * scale_size)
        output = model_name + "_x4"
        npy_dot = "_x4.npy"
        add_word = "x4"
    elif version == 2:
        scale_size = 3
        image_size = 1 + (scale_size * scale_size)
        output = model_name + "_x9"
        npy_dot = "_x9.npy"
        add_word = "x9"
    return scale_size, image_size, output, npy_dot, add_word

class MLP(pytorch_lightning.LightningModule):
    def __init__(self, input_size, xcol='emb', ycol='avg_rating', base_size=768):
        super().__init__()
        if input_size == base_size:
            self.append_flag = False
            self.base_size = input_size
            self.append_size = input_size
        else:
            self.append_flag = True
            self.base_size = base_size
            self.append_size = input_size - base_size
        self.input_size = input_size
        self.hidden_size = max(self.input_size//2, 1024)
        self.xcol = xcol
        self.ycol = ycol
        
        self.persona_0 = torch.nn.Sequential(
            torch.nn.Linear(self.base_size, self.hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size, self.hidden_size//16),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size//16, self.hidden_size//64),
            torch.nn.Linear(self.hidden_size//64, 1)
        )
        self.persona_1 = torch.nn.Sequential(
            torch.nn.Linear(self.append_size, self.hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size, self.hidden_size//16),
            torch.nn.ReLU(),
            torch.nn.Linear(self.hidden_size//16, 1)
        )
        self.persona_2 = torch.nn.Sequential(
            torch.nn.Linear(self.input_size, self.hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size, self.hidden_size//8),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size//8, self.hidden_size//16),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.1),
            torch.nn.Linear(self.hidden_size//16, self.hidden_size//32),
            torch.nn.Linear(self.hidden_size//32, 1)
        )
        self.output = torch.nn.Linear(3, 1)
    def forward(self, x):
        if self.append_flag:
            h0 = self.persona_0(x[:,:self.base_size])
            h1 = self.persona_1(x[:,self.base_size:])
        else:
            h0 = self.persona_0(x)
            h1 = self.persona_1(x)
        h2 = self.persona_2(x)
        return self.output(torch.concat([h0,h1,h2], dim=1))

class Score_Manager():
    def __init__(self, model_path, device, score_max, args=None) -> None:
        score_args = {}
        if args is not None:
            for net_arg in args:
                key, value = net_arg.split("=")
                if key == "version":
                    version = int(value)
        if args.version == 0:
            self.scale_size = 1
            self.image_size = 1
            self.npy_dot = ".npy"
        elif args.version == 1:
            self.scale_size = 2
            self.image_size = 1 + (self.scale_size * self.scale_size)
            #args.output = args.output + "_x4"
            self.npy_dot = "_x4.npy"
        elif args.version == 2:
            self.scale_size = 3
            self.image_size = 1 + (self.scale_size * self.scale_size)
            #args.output = args.output + "_x9"
            self.npy_dot = "_x9.npy"
        
        self.image_preprocess = None
        self.clip_model, self.clip_preprocess = clip.load("ViT-L/14", device="cpu")  #RN50x64
        self.preprocess_size = self.clip_model.visual.input_resolution
        if version >= 1:
            self.image_preprocess = get_image_preprocess(self.preprocess_size, self.scale_size)
        self.tokenizer = clip.tokenize
        self.mlp = MLP(768*self.image_size)
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
    
    def get_score(self, raw_image, prompt):
        with torch.no_grad():
            #txt_id = self.tokenizer(prompt, truncate=True).to(self.device)
            #if txt_id.size(1) > 77:
            #    print(f"too long token({txt_id.size()}): {prompt}")
            image = self.clip_preprocess(raw_image).unsqueeze(0).to(self.device)
            image_features = self.clip_model.encode_image(image)
            if self.image_size > 1:
                image = self.image_preprocess(raw_image).unsqueeze(0).to(self.device)
                for i in range(self.scale_size):
                    for j in range(self.scale_size):
                        image_features = torch.concat([image_features,self.clip_model.encode_image(image[:,:,i*self.preprocess_size:(i+1)*self.preprocess_size,j*self.preprocess_size:(j+1)*self.preprocess_size])], dim=1)
                
            #txt_features = self.clip_model.encode_text(txt_id)
        
        return self.mlp(image_features).data.cpu()[0][0]/self.score_max
