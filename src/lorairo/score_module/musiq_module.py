# 参考コード
# https://github.com/anse3832/MUSIQ

import glob
import hashlib
import math
import os
import random

import clip
import cv2
import joblib
import numpy as np
import tqdm

try:
    import h5py
except:
    print("大規模データセットを取り扱うためのライブラリ(h5py)がインストールされていません")
import pytorch_lightning
import torch
from einops import repeat
from PIL import Image
from torch.utils.data import Dataset
from torchvision.transforms import Compose, Normalize, transforms

try:
    from torchvision.transforms import InterpolationMode

    BICUBIC = InterpolationMode.BICUBIC
except ImportError:
    BICUBIC = Image.BICUBIC


def _transform():
    return Compose(
        [
            transforms.ToTensor(),
            Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ]
    )


def get_image_preprocess():
    return _transform()


def collate_fn(examples):
    return examples[0]


CONST_STR_KUGIRILINE_LEN = 24


def get_property(
    data_path: str = None,
    batch_size: int = 1,
    max_patches: int = None,
    eval_per: float = 0.0,
    reso_size: int = None,
    hdf5: bool = True,
    hdf5_resume: bool = True,
    hdf5_add_load: bool = True,
    hdf5_path: str = None,
    mode: str = "musiq",
    version: int = 0,
    resnet_dir: str = "./score_module",
    model_name: str = None,
    dataset_resume: list[str] = None,
    dataset_save_name: str = None,
):
    model_params = {
        "n_layer": 14,
        "h_dim": 384,  # clip 768 def 384
        "n_head": 6,
        "d_head": 384,
        "d_ff": 1152,
        "grid_size": 10,
        "dropout": 0.1,
        "layer_norm_epsilon": 1e-12,
        "score_model_dir": resnet_dir,
    }
    dataset_params = {
        "data_path": data_path,
        "reso_size": reso_size if reso_size is not None else 832,
        "divisible": 32,
        "patche_size": 32,
        "patche_stride": 32,
        "grid_size": model_params["grid_size"],
        "scale_list": [384, 224],
        "max_patches": max_patches if max_patches is not None else None,
        "batch_size": batch_size,
        "save_name": f"{dataset_save_name}.hdf5" if dataset_save_name is not None else None,
        "eval_per": eval_per,
        "hdf5": hdf5,
        "hdf5_resume": hdf5_resume,
        "hdf5_add_load": hdf5_add_load,
        "hdf5_path": f"{hdf5_path}.hdf5" if hdf5_path is not None else None,
        "resume": dataset_resume,
    }
    reso_size = dataset_params["reso_size"]
    train_params = {
        "model_name": f"{model_name}_{version}_{reso_size}.pth"
        if model_name is not None
        else f"musiq_score_{version}_{reso_size}.pth",
        "save_last_name": f"{model_name}_{version}_{reso_size}_last.pth"
        if model_name is not None
        else f"musiq_score_{version}_{reso_size}_last.pth",
    }
    # fix model params
    if mode == "musiq_score":
        model_params["output_scale"] = 1
    elif mode == "musiq_clip":
        model_params["h_dim"] = 384
        model_params["output_scale"] = 2
    # fix dataset params
    if dataset_resume is not None:
        if os.path.isfile(dataset_params["resume"]):
            dataset_params["hdf5_resume"] = True
    return model_params, dataset_params, train_params


def print_dict(data: dict, name: str = None):
    if name is not None:
        print("=" * CONST_STR_KUGIRILINE_LEN)
        print(f"dict {name} data")
        print("-" * CONST_STR_KUGIRILINE_LEN)
    for key, value in data.items():
        print(f"{key}: {value}")
    if name is not None:
        print("=" * CONST_STR_KUGIRILINE_LEN)
        print("")


def create_pos_idx(grid_size, count_w, count_h, scale_id):
    """
    return:
        tensor(1, 1, h, w)
    """
    grid_emb_w = torch.arange(0, grid_size, dtype=torch.float32).view(1, 1, 1, -1)
    grid_emb_w = torch.nn.functional.interpolate(grid_emb_w, size=(1, count_w), mode="nearest")
    grid_emb_w = grid_emb_w.repeat(1, 1, count_h, 1)
    grid_emb_h = torch.arange(0, grid_size, dtype=torch.float32).view(1, 1, -1, 1)
    grid_emb_h = torch.nn.functional.interpolate(grid_emb_h, size=(count_h, 1), mode="nearest")
    grid_emb_h = grid_emb_h.repeat(1, 1, 1, count_w)
    grid_emb = grid_emb_h * grid_size + grid_emb_w
    scale_emb = torch.full_like(grid_emb, scale_id)
    cls_mask = torch.ones_like(grid_emb)
    return torch.concat([grid_emb, scale_emb, cls_mask], dim=1)


def calculate_pad_size(image_size, patch_size, patch_stride):
    num_patches = (image_size - patch_size) // patch_stride + 1
    remainder = image_size - (num_patches - 1) * patch_stride - patch_size
    if image_size == patch_stride:
        return image_size % patch_size
    elif remainder != 0:
        return patch_size - remainder
    else:
        return 0


def extract_patches(image, patch_size, patch_stride, padding="same", output_mode="tf", transform=None):
    """
    Extract patches from an input image using PyTorch.

    Args:
        image (torch.Tensor): Input image (shape: [batch_size, channels, height, width]).
        patch_size (int): Size of the patches (assumed to be square).
        patch_stride (int): Stride for patch extraction.
        padding (str): Padding mode ('same' or 'valid').
        output_mode: 'tf' or 'else' tfの場合tf.image.extract_patchesと同じ出力形式になる(b,patch_count, patch_size*patch_size*3) -> patches.view(b,pc,h,w,c)

    Returns:
        torch.Tensor: Extracted patches (tf shape: [batch_size, num_patches, channels * patch_size * patch_size]), (torch: [batch_size, num_pathes, pathe_size_h, pathe_size_w, channel]), other shape: [bs, channel, x, y, w, h]
        Int: count_w
        Int: count_h
    """
    height, width, channels = image.shape

    if padding == "same":
        pad_w = calculate_pad_size(width, patch_size, patch_stride)
        pad_h = calculate_pad_size(height, patch_size, patch_stride)
    else:
        pad_w = 0
        pad_h = 0

    if transform is not None:
        image = transform(image)
    else:
        image = torch.from_numpy(image)
        image = image.permute(2, 0, 1)

    patches = torch.nn.functional.pad(image.unsqueeze(0), (0, pad_h, 0, pad_w))
    patches = patches.unfold(2, patch_size, patch_stride).unfold(3, patch_size, patch_stride)
    count_h = patches.size(2)
    count_w = patches.size(3)
    if output_mode == "tf":
        patches = patches.permute(0, 2, 3, 5, 4, 1).contiguous()
        patches = patches.view(*patches.size()[:3], -1)
    elif output_mode == "torch":
        patches = patches.permute(0, 2, 3, 4, 5, 1).contiguous()

    return patches, count_w, count_h


def round_to_steps(x, reso_steps):
    x = int(x + 0.5)
    return x - x % reso_steps


def resize_img_resos(image, max_resos, reso_steps) -> list[int, int]:
    height, width, channels = image.shape
    image_resos = height * width
    image_aspec = width / height

    if image_resos > max_resos:
        resize_w = math.sqrt(max_resos * image_aspec)
        resize_h = max_resos / resize_w
        # よりアス比が近いものを選ぶ
        round_ww = round_to_steps(resize_w, reso_steps)
        round_wh = round_to_steps(round_ww / image_aspec, reso_steps)
        w_aspec = round_ww / round_wh

        round_hh = round_to_steps(resize_h, reso_steps)
        round_hw = round_to_steps(round_hh * image_aspec, reso_steps)
        h_aspec = round_hw / round_hh

        if abs(w_aspec - image_aspec) < abs(h_aspec - image_aspec):
            resized_size = (round_ww, int(round_ww / image_aspec + 0.5))
        else:
            resized_size = (int(round_hh * image_aspec + 0.5), round_hh)
    else:
        resized_size = (width, height)
    return resized_size


def resize_image(image, resize):
    return cv2.resize(image, resize, interpolation=cv2.INTER_AREA)  # INTER_AREAでやりたいのでcv2でリサイズ


def load_img(img_path):
    image = Image.open(img_path)
    if not image.mode == "RGB":
        image = image.convert("RGB")
    return np.array(image)


def get_resize_latents(resnet, device, image, resos, division=32):
    transform = get_image_preprocess()
    height, width, channels = image.shape
    image_resos = height * width
    area = resos**2
    resize = resize_img_resos(image, area, division)
    if image_resos > area:
        _img = resize_image(image, resize)
    else:
        _img = image
    _img = Image.fromarray(_img)
    _img = transform(_img)
    _latents = resnet(_img.unsqueeze(0).to(device)).to("cpu")
    _latents = _latents.permute(0, 3, 2, 1).contiguous()
    _, s_cw, s_ch, _ = _latents.size()
    return _latents, s_cw, s_ch


def check_hash(file_path, model="md5"):
    with open(file_path, "rb") as f:
        hash_data = hashlib.md5(f.read()).hexdigest()
    return hash_data


class MUSIQ_Score_Dataset(Dataset):
    def __init__(
        self,
        data_path: str,
        reso_size: int,
        divisible: int,
        patche_size: int,
        patche_stride: int,
        grid_size: int,
        scale_list: list[int],
        max_patches: int = None,
        batch_size: int = 1,
        eval_per: float = 0.0,
        hdf5: bool = False,
        hdf5_resume: bool = True,
        hdf5_add_load: bool = True,
        hdf5_path: str = None,
        resume: list[str] = None,
        save_name: str = None,
        use_cashe: bool = True,
        device: str = "auto",
    ) -> None:
        super().__init__()
        self.reso_size = reso_size
        self.max_area = reso_size * reso_size
        self.divisible = divisible
        self.patche_size = patche_size
        self.patche_stride = patche_stride
        self.grid_size = grid_size
        self.scale_list = scale_list
        self.use_cashe = use_cashe
        self.max_patches = max_patches
        self.resume_list = resume
        self.save_name = save_name
        self.hdf5 = hdf5
        self.hdf5_path = None
        self.hdf5_resume = hdf5_resume
        self.hdf5_add_load = hdf5_add_load
        # HDF5が使えるかチェック
        if self.hdf5:
            try:
                __ = h5py.__version__
                self.hdf5_path = (
                    data_path + f"/dataset_{reso_size}.hdf5" if hdf5_path is None else hdf5_path
                )
            except:
                self.hdf5 = False

        self.batch_size = batch_size
        self.eval_per = eval_per
        self.eval = False

        # dataset management
        self.score_count = {}
        self.eval_score_count = {}
        self.keys = []
        self.key_data_count = {}
        self.total_datalen = 0
        self.train_datalen = 0
        self.return_datalen = 0
        self.eval_keys = []
        self.eval_data_count = {}
        self.eval_datalen = 0
        self.eval_return_len = 0

        self.key_id_list = []
        self.data_id_list = {}
        self.eval_key_id_list = []
        self.eval_id_list = {}
        # transformers
        self.transformer = get_image_preprocess()
        # resnet
        self.device = (
            torch.device("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        )

        self.data_list = {}
        self.eval_list = {}
        # self.load_dataset(resume)

        self.files_path = self.get_data_list(data_path)
        # culc eval len
        if self.eval_per > 0.0:
            self.train_datalen = int(self.total_datalen * (1.0 - self.eval_per))
            self.eval_datalen = int(self.total_datalen - self.train_datalen)
            for _ in range(self.eval_datalen):
                while True:
                    score_id = random.randrange(0, len(self.files_path))
                    if random.random() > (len(self.files_path[score_id]["paths"]) / (self.total_datalen)):
                        continue
                    if len(self.files_path[score_id]["paths"]) <= 0:
                        continue
                    target_id = random.randrange(0, len(self.files_path[score_id]["paths"]))
                    if score_id in self.eval_id_list:
                        if target_id in self.eval_id_list[score_id]:
                            continue
                    else:
                        self.eval_id_list[score_id] = []
                    self.eval_id_list[score_id].append(target_id)
                    break
        else:
            self.train_datalen = self.total_datalen
            self.eval_datalen = 0

    def load_dataset(self, resume):
        if not self.hdf5:
            if resume is not None:
                if os.path.isfile(resume):
                    [self.data_list, self.eval_list] = joblib.load(resume)

    def save_dataset(self, save_name=None):
        if not self.hdf5:
            if save_name is not None:
                joblib.dump([self.data_list, self.eval_list], save_name, compress=3)

    def merge_hdf5(self):
        pass

    def get_data_list(self, base_dir) -> dict[float, list]:
        if base_dir is None:
            files_path = []
        else:
            dir_list = glob.glob(base_dir + "/*")
            files_path = []
            for dir in dir_list:
                if os.path.isdir(dir):
                    files_path.append(
                        {
                            "score": float(os.path.split(dir)[-1]),
                            "paths": glob.glob(dir + "/*.png")
                            + glob.glob(dir + "/*.jpg")
                            + glob.glob(dir + "/*.jpeg")
                            + glob.glob(dir + "/*.webp"),
                        }
                    )
                    self.total_datalen += len(files_path[-1]["paths"])
        return files_path

    def _load_img(self, img_path):
        image = Image.open(img_path)
        if not image.mode == "RGB":
            # print(img_path)
            image = image.convert("RGB")
        return np.array(image)

    def _get_resize(self, image, max_area):
        height, width, channels = image.shape
        image_resos = height * width
        resize = resize_img_resos(image, max_area, self.divisible)
        if image_resos > max_area:
            return resize_image(image, resize)
        return image

    def _to_latents(self, image, resnet):
        # image = [c, h, w] -> [bs, c, h, w]
        latents = resnet(image.unsqueeze(0).to(self.device)).to("cpu")
        # [bs, h, w, bs]
        return latents.permute(0, 3, 2, 1).contiguous()

    def __to_latents(self, patches, resnet):
        # img_pathes = [bs, x, y, h, w, channel]
        bs, x, y, h, w, ch = patches.size()
        patches = patches.view(bs * x * y, h, w, ch).permute(0, 3, 1, 2).contiguous()
        # img_pathes = [bs * x * y, channel, h, w]
        if self.max_patches is None:
            self.max_patches = patches.size(0)
        repeat_count = bs // self.max_patches + (bs % self.max_patches)
        latents = None
        for i in range(repeat_count):
            s_pos = i * self.max_patches
            e_pos = (i + 1) * self.max_patches
            if e_pos > bs:
                e_pos = patches.size(0)
            if latents is None:
                latents = resnet(patches[s_pos:e_pos].to(self.device)).to("cpu")
            else:
                torch.concat([latents, resnet(patches[s_pos:e_pos].to(self.device)).to("cpu")], dim=0)
        return latents.view(bs, x, y, -1).contiguous()

    def _create_resize_img(self, image, area, scale_id, resnet=None):
        _img = self._get_resize(image, area)
        _img = Image.fromarray(_img)
        _img = self.transformer(_img)
        latents = self._to_latents(_img, resnet).squeeze(0)
        s_cw, s_ch, _ = latents.size()
        ppi = create_pos_idx(self.grid_size, s_cw, s_ch, scale_id).permute(0, 2, 3, 1).contiguous()
        return None, ppi, s_cw, s_ch, latents

    def __create_resize_img(self, image, area, scale_id, resnet=None):
        _img = self._get_resize(image, area)
        patches, s_cw, s_ch = extract_patches(
            _img,
            self.patche_size,
            self.patche_stride,
            output_mode="torch",
            transform=get_image_preprocess(),
        )
        if resnet is not None:
            latents = self._to_latents(patches, resnet).squeeze(0)
            patches = None
        else:
            latents = None
        ppi = create_pos_idx(self.grid_size, s_cw, s_ch, scale_id).permute(0, 2, 3, 1).contiguous()
        return patches, ppi, s_cw, s_ch, latents

    def _create_data_id_list(self, target_key=None, eval=False):
        if eval:
            self.eval_id_list[target_key] = [i for i in range(self.eval_data_count[target_key])]
            self._shuffle_data_id_list(target_key, eval)
        else:
            self.data_id_list[target_key] = [i for i in range(self.key_data_count[target_key])]
            self._shuffle_data_id_list(target_key)

    def _shuffle_data_id_list(self, target_key=None, eval=False):
        if eval:
            random.shuffle(self.eval_id_list[target_key])
        else:
            random.shuffle(self.data_id_list[target_key])

    def _create_key_id_list(self, eval=False):
        if eval:
            for i, key in enumerate(self.eval_keys):
                count = self.eval_data_count[key] // self.batch_size + (
                    self.eval_data_count[key] % self.batch_size > 0
                )
                self.eval_key_id_list += [i] * count
            random.shuffle(self.eval_key_id_list)
        else:
            for i, key in enumerate(self.keys):
                count = self.key_data_count[key] // self.batch_size + (
                    self.key_data_count[key] % self.batch_size > 0
                )
                self.key_id_list += [i] * count
            random.shuffle(self.key_id_list)

    def create_datalist(self, resnet=None):
        print("=" * CONST_STR_KUGIRILINE_LEN)
        print("create dataset")
        if resnet is not None:
            resnet.to(self.device)
            resnet.eval()
            resnet.requires_grad_(False)
        if self.hdf5:
            mode = "a" if self.hdf5_resume else "w"
            with h5py.File(self.hdf5_path, mode) as h5:
                if "train" not in h5:
                    h5_train_data = h5.create_group("train")
                    self.hdf5_add_load = True
                else:
                    h5_train_data = h5["train"]
                    for key in h5_train_data.keys():
                        data_list = h5_train_data[key]
                        self.key_data_count[key] = len(data_list)
                if "eval" not in h5:
                    h5_eval_data = h5.create_group("eval")
                    self.hdf5_add_load = True
                else:
                    h5_eval_data = h5["eval"]
                    for key in h5_eval_data.keys():
                        data_list = h5_eval_data[key]
                        self.eval_data_count[key] = len(data_list)
                if "data_info" not in h5:
                    h5_data_info = h5.create_group("data_info")
                    h5_data_info_data = h5_data_info.create_group("train")
                    h5_data_info_data = h5_data_info.create_group("eval")
                    # h5_data_info_hash = h5_data_info.create_group("hash")
                else:
                    h5_data_info = h5["data_info"]
                    h5_data_info_data = h5_data_info["train"]
                    for key in h5_data_info_data.keys():
                        self.score_count[key] = h5_data_info_data[key][0]
                        self.train_datalen += h5_data_info_data[key][0]
                    h5_data_info_data = h5_data_info["eval"]
                    for key in h5_data_info_data.keys():
                        self.eval_score_count[key] = h5_data_info_data[key][0]
                        self.eval_datalen += h5_data_info_data[key][0]
                    # h5_data_info_hash = h5_data_info["hash"]
                # データセット構築
                for target_score, img_path_dic in enumerate(self.files_path):
                    if not self.hdf5_add_load:
                        break
                    score = img_path_dic["score"]
                    for target_id, img_path in enumerate(
                        tqdm.tqdm(img_path_dic["paths"], desc=f"[score: {score}]")
                    ):
                        image = self._load_img(img_path)
                        # scales
                        scale_patches = []
                        scale_pos_idx = []
                        scale_latents = []
                        scale_count = []
                        for i, scale in enumerate(self.scale_list):
                            scale_count.append([0, 0])
                            s_patches, s_pos_idx, scale_count[i][0], scale_count[i][1], latents = (
                                self._create_resize_img(image, scale * scale, i + 1, resnet)
                            )
                            scale_patches.append(s_patches)
                            scale_pos_idx.append(s_pos_idx)
                            scale_latents.append(latents)

                        # img_pathes = [bs, x, y, h, w, channel] if resnet==None else None
                        # latents[bs, x, y, h_dim * w * h] if resnet is not None else None
                        # patche_pos_idx = [bs, x, y, pos_id + scale + cls]
                        img_patches, patche_pos_idx, count_w, count_h, latents = self._create_resize_img(
                            image, self.max_area, 0, resnet
                        )
                        res_str = f"{count_w}_{count_h}"
                        for sc in scale_count:
                            res_str = f"{res_str},{sc[0]}_{sc[1]}"

                        eval_flag = False
                        if target_score in self.eval_id_list:
                            if target_id in self.eval_id_list[target_score]:
                                eval_flag = True

                        if eval_flag:
                            if res_str not in h5_eval_data:
                                self.eval_data_count[res_str] = 0
                                h5_eval_list = h5_eval_data.create_group(res_str)
                                eval_h5_data_list = h5_eval_list.create_group(
                                    str(self.eval_data_count[res_str])
                                )
                            else:
                                h5_eval_list = h5_eval_data[res_str]
                                eval_h5_data_list = h5_eval_list.create_group(
                                    str(self.eval_data_count[res_str])
                                )

                            eval_h5_data = eval_h5_data_list.create_dataset("score", data=[score])
                            eval_h5_latents = eval_h5_data_list.create_dataset(
                                "latents", data=latents.numpy(), shape=latents.size(), compression="gzip"
                            )
                            eval_h5_scale_1_latents = eval_h5_data_list.create_dataset(
                                "scale_1",
                                data=scale_latents[0].numpy(),
                                shape=scale_latents[0].size(),
                                compression="gzip",
                            )
                            eval_h5_scale_2_latents = eval_h5_data_list.create_dataset(
                                "scale_2",
                                data=scale_latents[1].numpy(),
                                shape=scale_latents[1].size(),
                                compression="gzip",
                            )
                            self.eval_data_count[res_str] += 1
                            if str(score) in self.eval_score_count:
                                self.eval_score_count[str(score)] += 1
                            else:
                                self.eval_score_count[str(score)] = 1
                        else:
                            if res_str not in h5_train_data:
                                self.key_data_count[res_str] = 0
                                data_list = h5_train_data.create_group(res_str)
                                h5_data_list = data_list.create_group(str(self.key_data_count[res_str]))
                            else:
                                data_list = h5_train_data[res_str]
                                h5_data_list = data_list.create_group(str(self.key_data_count[res_str]))

                            h5_data = h5_data_list.create_dataset("score", data=[score])
                            h5_latents = h5_data_list.create_dataset(
                                "latents", data=latents.numpy(), shape=latents.size(), compression="gzip"
                            )
                            h5_scale_1_latents = h5_data_list.create_dataset(
                                "scale_1",
                                data=scale_latents[0].numpy(),
                                shape=scale_latents[0].size(),
                                compression="gzip",
                            )
                            h5_scale_2_latents = h5_data_list.create_dataset(
                                "scale_2",
                                data=scale_latents[1].numpy(),
                                shape=scale_latents[1].size(),
                                compression="gzip",
                            )
                            self.key_data_count[res_str] += 1
                            if str(score) in self.score_count:
                                self.score_count[str(score)] += 1
                            else:
                                self.score_count[str(score)] = 1
                # score count情報書き込み
                if self.hdf5_add_load:
                    h5_data_info_data = h5_data_info["train"]
                    for key, value in self.score_count.items():
                        if key in h5_data_info_data:
                            h5_data_info_data_count = h5_data_info_data[key]
                            h5_data_info_data_count[0] = value
                        else:
                            h5_data_info_data_count = h5_data_info_data.create_dataset(key, data=[value])
                    h5_data_info_data = h5_data_info["eval"]
                    for key, value in self.eval_score_count.items():
                        if key in h5_data_info_data:
                            h5_data_info_data_count = h5_data_info_data[key]
                            h5_data_info_data_count[0] = value
                        else:
                            h5_data_info_data_count = h5_data_info_data.create_dataset(key, data=[value])
        else:
            for target_score, img_path_dic in enumerate(self.files_path):
                score = img_path_dic["score"]
                for target_id, img_path in enumerate(tqdm.tqdm(img_path_dic["paths"])):
                    image = self._load_img(img_path)
                    # scales
                    scale_patches = []
                    scale_pos_idx = []
                    scale_latents = []
                    scale_count = []
                    for i, scale in enumerate(self.scale_list):
                        scale_count.append([0, 0])
                        s_patches, s_pos_idx, scale_count[i][0], scale_count[i][1], latents = (
                            self._create_resize_img(image, scale * scale, i + 1, resnet)
                        )
                        scale_patches.append(s_patches)
                        scale_pos_idx.append(s_pos_idx)
                        scale_latents.append(latents)

                    # img_pathes = [bs, x, y, h, w, channel] if resnet==None else None
                    # latents[bs, x, y, h_dim * w * h] if resnet is not None else None
                    # patche_pos_idx = [bs, x, y, pos_id + scale + cls]
                    img_patches, patche_pos_idx, count_w, count_h, latents = self._create_resize_img(
                        image, self.max_area, 0, resnet
                    )
                    res_str = f"{count_w}_{count_h}"
                    for sc in scale_count:
                        res_str = f"{res_str},{sc[0]}_{sc[1]}"
                    eval_flag = False
                    if target_score in self.eval_id_list:
                        if target_id in self.eval_id_list[target_score]:
                            eval_flag = True

                    if eval_flag:
                        if res_str in self.eval_list:
                            self.eval_data_count[res_str] = 1
                            self.eval_list[res_str].append(
                                {
                                    "score": score,
                                    "patches": img_patches,
                                    "latents": latents,
                                    "scale_patches": scale_patches,
                                    "scale_1_latents": scale_latents[0],
                                    "scale_2_latents": scale_latents[1],
                                }
                            )
                        else:
                            self.eval_data_count[res_str] += 1
                            self.eval_list[res_str] = [
                                {
                                    "score": score,
                                    "patches": img_patches,
                                    "latents": latents,
                                    "scale_patches": scale_patches,
                                    "scale_1_latents": scale_latents[0],
                                    "scale_2_latents": scale_latents[1],
                                }
                            ]
                        if str(score) in self.eval_score_count:
                            self.eval_score_count[str(score)] += 1
                        else:
                            self.eval_score_count[str(score)] = 1
                    else:
                        if res_str in self.data_list:
                            self.key_data_count[res_str] = 1
                            self.data_list[res_str].append(
                                {
                                    "score": score,
                                    "patches": img_patches,
                                    "latents": latents,
                                    "scale_patches": scale_patches,
                                    "scale_1_latents": scale_latents[0],
                                    "scale_2_latents": scale_latents[1],
                                }
                            )
                        else:
                            self.key_data_count[res_str] += 1
                            self.data_list[res_str] = [
                                {
                                    "score": score,
                                    "patches": img_patches,
                                    "latents": latents,
                                    "scale_patches": scale_patches,
                                    "scale_1_latents": scale_latents[0],
                                    "scale_2_latents": scale_latents[1],
                                }
                            ]
                        if str(score) in self.score_count:
                            self.score_count[str(score)] += 1
                        else:
                            self.score_count[str(score)] = 1

        if resnet is not None:
            resnet.to("cpu")

        # counting datalist
        self.keys = list(self.key_data_count.keys())
        self.keys.sort()
        for key in self.keys:
            self._create_data_id_list(key)
        # eval
        self.eval_keys = list(self.eval_data_count.keys())
        self.eval_keys.sort()
        for key in self.eval_keys:
            self._create_data_id_list(key, eval=True)

        # create id list
        self._create_key_id_list()
        self.return_datalen = len(self.key_id_list)
        # eval
        self._create_key_id_list(eval=True)
        self.eval_return_len = len(self.eval_key_id_list)

        # save datalist
        # if (not self.hdf5) and (self.save_name is not None):
        #    self.save_dataset(self.save_name)

    def print_datacount(self):
        print("=" * CONST_STR_KUGIRILINE_LEN)
        print(":::データセット情報(サイズ毎のデータ数):::")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        print(f"data count list / data count: {self.train_datalen}")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        for key in self.keys:
            print(f"{key}: {self.key_data_count[key]}")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        print(f"eval count list / data count: {self.eval_datalen}")
        for key in self.eval_keys:
            print(f"{key}: {self.eval_data_count[key]}")
        print("=" * CONST_STR_KUGIRILINE_LEN)

    def print_datacount_score(self):
        print("=" * CONST_STR_KUGIRILINE_LEN)
        print(":::データセット情報(スコア毎のデータ数):::")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        print(f"data count list / data count: {self.train_datalen}")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        for key, value in self.score_count.items():
            print(f"{key}: {value}({(value / self.train_datalen * 100):02.03f}%)")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        print(f"eval count list / data: {self.eval_datalen}")
        print("-" * CONST_STR_KUGIRILINE_LEN)
        for key, value in self.eval_score_count.items():
            print(f"{key}: {value}({(value / self.eval_datalen * 100):02.03f}%)")
        print("=" * CONST_STR_KUGIRILINE_LEN)

    def __total_datalen__(self):
        return self.total_datalen

    def __len__(self):
        if self.eval:
            return self.eval_return_len
        return self.return_datalen

    def __getitem__(self, index):
        # ターゲットとなるkeyを取り出す
        if self.eval:
            if len(self.eval_key_id_list) <= 0:
                self._create_key_id_list(eval=True)
            target_key = self.eval_keys[self.eval_key_id_list.pop(0)]
            if len(self.eval_id_list[target_key]) <= 0:
                self._create_data_id_list(target_key, eval=True)
        else:
            if len(self.key_id_list) <= 0:
                self._create_key_id_list()
            target_key = self.keys[self.key_id_list.pop(0)]
            if len(self.data_id_list[target_key]) <= 0:
                self._create_data_id_list(target_key)
        # batch size分のデータを取り出す
        scores = []
        latents = []
        scale_1_latents = []
        scale_2_latents = []
        if self.hdf5:
            with h5py.File(self.hdf5_path, "r") as h5:
                if self.eval:
                    h5_target_base = h5["eval"]
                    h5_target_key_base = h5_target_base[target_key]
                    for i in range(self.batch_size):
                        if len(self.eval_id_list[target_key]) <= 0:
                            break
                        target_id = str(self.eval_id_list[target_key].pop(0))
                        h5_target_data = h5_target_key_base[target_id]
                        scores.append(h5_target_data["score"][0])
                        latents.append(torch.from_numpy(h5_target_data["latents"][...]).clone())
                        scale_1_latents.append(torch.from_numpy(h5_target_data["scale_1"][...]).clone())
                        scale_2_latents.append(torch.from_numpy(h5_target_data["scale_2"][...]).clone())
                else:
                    h5_target_base = h5["train"]
                    h5_target_key_base = h5_target_base[target_key]
                    for i in range(self.batch_size):
                        if len(self.data_id_list[target_key]) <= 0:
                            break
                        target_id = str(self.data_id_list[target_key].pop(0))
                        h5_target_data = h5_target_key_base[target_id]
                        scores.append(h5_target_data["score"][0])
                        latents.append(torch.from_numpy(h5_target_data["latents"][...]).clone())
                        scale_1_latents.append(torch.from_numpy(h5_target_data["scale_1"][...]).clone())
                        scale_2_latents.append(torch.from_numpy(h5_target_data["scale_2"][...]).clone())
        else:
            if self.eval:
                for i in range(self.batch_size):
                    if len(self.eval_id_list[target_key]) <= 0:
                        break
                    target_id = self.eval_id_list[target_key].pop(0)
                    scores.append(self.eval_list[target_key][target_id]["score"])
                    latents.append(self.eval_list[target_key][target_id]["latents"])
                    scale_1_latents.append(self.eval_list[target_key][target_id]["scale_1_latents"])
                    scale_2_latents.append(self.eval_list[target_key][target_id]["scale_2_latents"])
            else:
                for i in range(self.batch_size):
                    if len(self.data_id_list[target_key]) <= 0:
                        break
                    target_id = self.data_id_list[target_key].pop(0)
                    scores.append(self.data_list[target_key][target_id]["score"])
                    latents.append(self.data_list[target_key][target_id]["latents"])
                    scale_1_latents.append(self.data_list[target_key][target_id]["scale_1_latents"])
                    scale_2_latents.append(self.data_list[target_key][target_id]["scale_2_latents"])
        scores = torch.Tensor(np.stack(scores)).unsqueeze(1)
        latents = torch.stack(latents)
        scale_1_latents = torch.stack(scale_1_latents)
        scale_2_latents = torch.stack(scale_2_latents)
        data = {
            "score": scores,
            "latent": latents,
            "s1_latent": scale_1_latents,
            "s2_latent": scale_2_latents,
        }
        return data


class Bottleneck(torch.nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None, output_relu=True):
        super(Bottleneck, self).__init__()
        self.conv1 = torch.nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = torch.nn.BatchNorm2d(planes)
        self.conv2 = torch.nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn2 = torch.nn.BatchNorm2d(planes)
        self.conv3 = torch.nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = torch.nn.BatchNorm2d(planes * 4)
        if output_relu:
            self.relu = torch.nn.ReLU(inplace=True)
        else:
            self.relu = torch.nn.SiLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out


class ResNetBackbone(torch.nn.Module):
    def __init__(self, block, layers):
        super(ResNetBackbone, self).__init__()
        self.inplanes = 64
        self.conv1 = torch.nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = torch.nn.BatchNorm2d(64)
        self.relu = torch.nn.ReLU(inplace=True)
        self.maxpool = torch.nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)

        for m in self.modules():
            if isinstance(m, torch.nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2.0 / n))
            elif isinstance(m, torch.nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, stride=1, output_relu=True):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = torch.nn.Sequential(
                torch.nn.Conv2d(
                    self.inplanes, planes * block.expansion, kernel_size=1, stride=stride, bias=False
                ),
                torch.nn.BatchNorm2d(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            if i + 1 == blocks:
                layers.append(block(self.inplanes, planes, output_relu=output_relu))
            else:
                layers.append(block(self.inplanes, planes))

        return torch.nn.Sequential(*layers)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        return x


def resnet50_backbone(score_model_dir=None):
    # Constructs a ResNet-50 model_hyper.
    torch_resnet50_url = "https://download.pytorch.org/models/resnet50-11ad3fa6.pth"
    model = ResNetBackbone(Bottleneck, [3, 4, 6, 3])

    # load pre-trained weights
    import torch.utils.model_zoo as model_zoo

    save_model = model_zoo.load_url(torch_resnet50_url, model_dir=score_model_dir)
    model_dict = model.state_dict()
    state_dict = {k: v for k, v in save_model.items() if k in model_dict.keys()}
    model_dict.update(state_dict)
    model.load_state_dict(model_dict)

    return model


class MultiHeadAttention(torch.nn.Module):
    def __init__(self, h_dim, n_head, d_head, dropout) -> None:
        super().__init__()
        self.n_head = n_head
        self.d_head = d_head
        self.dropout_p = dropout
        self.Q = torch.nn.Linear(h_dim, n_head * d_head)
        self.K = torch.nn.Linear(h_dim, n_head * d_head)
        self.V = torch.nn.Linear(h_dim, n_head * d_head)
        # SDPA
        self.sdpa = torch.nn.functional.scaled_dot_product_attention
        # Leniear
        self.linear = torch.nn.Linear(n_head * d_head, h_dim)
        self.dropout = torch.nn.Dropout(dropout)
        self.set_enable_math = True

    def enable_math(self, enable_math: bool = True):
        self.set_enable_math = enable_math

    def forward(self, Q, K, V, attn_mask=None):
        batch_size = Q.size(0)

        # latents = [bs, x * y + scale1 + scale2 + cls, h_dim] -> [bs, n_head, x*y+s1+s2+cls, d_head]
        q_s = self.Q(Q).view(batch_size, -1, self.n_head, self.d_head).transpose(1, 2)
        k_s = self.K(K).view(batch_size, -1, self.n_head, self.d_head).transpose(1, 2)
        v_s = self.V(V).view(batch_size, -1, self.n_head, self.d_head).transpose(1, 2)

        if attn_mask is not None:
            # (bs, n_head, n_q_seq, n_k_seq)
            attn_mask = attn_mask.unsqueeze(1).repeat(1, self.n_head, 1, 1)

        # [bs, n_head, x*y+s1+s2+cls, d_head]
        with torch.backends.cuda.sdp_kernel(
            enable_flash=True, enable_math=self.set_enable_math, enable_mem_efficient=True
        ):
            context = self.sdpa(q_s, k_s, v_s, dropout_p=self.dropout_p)
        # [bs, x*y+s1+s2+cls, n_head * d_head]
        context = context.transpose(1, 2).contiguous().view(batch_size, -1, self.n_head * self.d_head)
        # [bs, x*y+s1+s2+cls, h_dim]
        output = self.linear(context)
        output = self.dropout(output)
        # [bs, x*y+s1+s2+cls, h_dim]
        return output


class PoswiseFeedForwardNet(torch.nn.Module):
    def __init__(self, h_dim, d_ff, dropout) -> None:
        super().__init__()
        self.lin1 = torch.nn.Linear(h_dim, d_ff)
        self.lin2 = torch.nn.Linear(d_ff, h_dim)
        self.active = torch.nn.functional.gelu
        self.dropout = torch.nn.Dropout(dropout)

    def forward(self, input):
        # [bs, h_dim, x*y+s1+s2+cls]
        h = self.lin1(input)
        h = self.active(h)
        # [bs, d_ff, x*y+s1+s2+cls]
        h = self.lin2(h)
        # [bs, h_dim, x*y+s1+s2+cls]
        return self.dropout(h)


def get_sinusoid_encoding_table(n_seq, d_hidn):
    def cal_angle(position, i_hidn):
        return position / np.power(10000, 2 * (i_hidn // 2) / d_hidn)

    def get_posi_angle_vec(position):
        return [cal_angle(position, i_hidn) for i_hidn in range(d_hidn)]

    sinusoid_table = np.array([get_posi_angle_vec(i_seq) for i_seq in range(n_seq)])
    sinusoid_table[:, 0::2] = np.sin(sinusoid_table[:, 0::2])  # even index sin
    sinusoid_table[:, 1::2] = np.cos(sinusoid_table[:, 1::2])  # odd index cos

    return sinusoid_table


def get_attn_pad_mask(seq_q, seq_k, i_pad):
    batch_size, len_q = seq_q.size()
    batch_size, len_k = seq_k.size()
    pad_attn_mask = seq_k.data.eq(i_pad)
    pad_attn_mask = pad_attn_mask.unsqueeze(1).expand(batch_size, len_q, len_k)
    return pad_attn_mask


class Encoder_Layer(torch.nn.Module):
    def __init__(self, h_dim, n_head, d_head, d_ff, dropout, layer_norm_epsilon) -> None:
        super().__init__()
        self.attn = MultiHeadAttention(h_dim, n_head, d_head, dropout)
        self.ln1 = torch.nn.LayerNorm(h_dim, eps=layer_norm_epsilon)
        self.pos_ffn = PoswiseFeedForwardNet(h_dim, d_ff, dropout)
        self.ln2 = torch.nn.LayerNorm(h_dim, eps=layer_norm_epsilon)

    def enable_math(self, enable_math: bool = True):
        self.attn.enable_math(enable_math)

    def forward(self, input, attn_mask):
        # latents = [bs, x * y + scale1 + scale2 + cls, h_dim]
        att_output = self.attn(input, input, input, attn_mask)
        # [bs, x*y+s1+s2+cls, h_dim]
        att_output = self.ln1(input + att_output)
        # [bs, x*y+s1+s2+cls, h_dim]
        ffn_output = self.pos_ffn(att_output)
        return self.ln2(att_output + ffn_output)


class MUSIQ_Encoder(torch.nn.Module):
    def __init__(
        self, n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon
    ) -> None:
        super().__init__()
        # scale Embedding
        self.sce_org_param = torch.nn.Parameter(torch.randn(1, h_dim, 1, 1))
        self.sce_1_param = torch.nn.Parameter(torch.randn(1, h_dim, 1, 1))
        self.sce_2_param = torch.nn.Parameter(torch.randn(1, h_dim, 1, 1))
        # Hash-based 2D Spatial Embedding
        self.grid_size = grid_size
        self.hse_param = torch.nn.Parameter(torch.randn(1, h_dim, grid_size, grid_size))
        # CLS token
        self.cls_param = torch.nn.Parameter(torch.zeros(1, h_dim, 1))
        self.dropout = torch.nn.Dropout(dropout)

        # Transformer Layer
        self.layers = torch.nn.ModuleList(
            [
                Encoder_Layer(h_dim, n_head, d_head, d_ff, dropout, layer_norm_epsilon)
                for _ in range(n_layer)
            ]
        )

    def enable_math(self, enable_math: bool = True):
        for layer in self.layers:
            layer.enable_math(enable_math)

    def forward(self, org_emb, scale_1_emb, scale_2_emb, mask_input=None):
        # latents = [bs, h_dim, x, y]
        bs, h_dim, x, y = org_emb.size()
        __, __, x1, y1 = scale_1_emb.size()
        __, __, x2, y2 = scale_2_emb.size()

        # scale Embedding
        scale_emb_org = repeat(self.sce_org_param, "() h () () -> b h x y", b=bs, x=x, y=y)
        scale_emb_1 = repeat(self.sce_1_param, "() h () () -> b h x y", b=bs, x=x1, y=y1)
        scale_emb_2 = repeat(self.sce_2_param, "() h () () -> b h x y", b=bs, x=x2, y=y2)
        org_emb += scale_emb_org
        scale_1_emb += scale_emb_1
        scale_2_emb += scale_emb_2

        # pos emb
        spatial_org_embed = torch.zeros(1, h_dim, x, y).to(org_emb.device)
        for i in range(x):
            for j in range(y):
                t_i = int((i / x) * self.grid_size)
                t_j = int((j / y) * self.grid_size)
                spatial_org_embed[:, :, i, j] = self.hse_param[:, :, t_i, t_j]
        spatial_org_embed = repeat(spatial_org_embed, "() h x y -> b h x y", b=bs)

        spatial_1_embed = torch.zeros(1, h_dim, x1, y1).to(org_emb.device)
        for i in range(x1):
            for j in range(y1):
                t_i = int((i / x1) * self.grid_size)
                t_j = int((j / y1) * self.grid_size)
                spatial_1_embed[:, :, i, j] = self.hse_param[:, :, t_i, t_j]
        spatial_1_embed = repeat(spatial_1_embed, "() h x y -> b h x y", b=bs)

        spatial_2_embed = torch.zeros(1, h_dim, x2, y2).to(org_emb.device)
        for i in range(x2):
            for j in range(y2):
                t_i = int((i / x2) * self.grid_size)
                t_j = int((j / y2) * self.grid_size)
                spatial_2_embed[:, :, i, j] = self.hse_param[:, :, t_i, t_j]
        spatial_2_embed = repeat(spatial_2_embed, "() h x y -> b h x y", b=bs)

        org_emb += spatial_org_embed
        scale_1_emb += spatial_1_embed
        scale_2_emb += spatial_2_embed

        # latents = [bs, h_dim, x, y] -> [bs, h_dim, x * y]
        org_emb = org_emb.view(bs, h_dim, -1)
        scale_1_emb = scale_1_emb.view(bs, h_dim, -1)
        scale_2_emb = scale_2_emb.view(bs, h_dim, -1)

        # latents = [bs, h_dim, x, y] -> [bs, h_dim, x * y + scale1 + scale2]
        input_emb = torch.concat([org_emb, scale_1_emb, scale_2_emb], dim=2)

        # latents = [bs, h_dim, x * y + scale1 + scale2] -> [bs, h_dim, x * y + scale1 + scale2 + cls]
        cls_emb = repeat(self.cls_param, "() h l -> b h l", b=bs)
        input_emb = torch.cat((cls_emb, input_emb), dim=2)
        # latents = [bs, h_dim, x * y + scale1 + scale2 + cls] -> [bs, x * y + scale1 + scale2 + cls, h_dim]
        output = self.dropout(input_emb).permute(0, 2, 1).contiguous()

        # (bs, n_enc_seq+1, n_enc_seq+1)
        attn_mask = None  # get_attn_pad_mask(mask_input, mask_input, self.config.i_pad)

        for layer in self.layers:
            output = layer(output, attn_mask)
        return output


class MUSIQ(torch.nn.Module):
    def __init__(
        self, n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon
    ) -> None:
        super().__init__()
        self.pre_encoder_dim = 2048

        self.h_dim = h_dim
        self.in_conv = torch.nn.Conv2d(self.pre_encoder_dim, self.h_dim, kernel_size=1, bias=False)
        self.in_conv_1 = torch.nn.Conv2d(self.pre_encoder_dim, self.h_dim, kernel_size=1, bias=False)
        self.in_conv_2 = torch.nn.Conv2d(self.pre_encoder_dim, self.h_dim, kernel_size=1, bias=False)

        self.mhattn = MUSIQ_Encoder(
            n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon
        )

    def enable_math(self, enable_math: bool = True):
        self.mhattn.enable_math(enable_math)

    def forward(self, latents, scale_1_latents, scale_2_latents):
        # latents[bs, x, y, resnet_dim * w * h]
        # scale_latents = [ latents_scale1,  latents_scale2, ...]
        bs, x, y, __ = latents.size()
        __, s0_x, s0_y, __ = scale_1_latents.size()
        __, s1_x, s1_y, __ = scale_2_latents.size()

        # latents[bs, x, y, resnet_dim] -> [bs, resnet_dim, x, y]
        latents = latents.permute(0, 3, 1, 2).contiguous()
        s0_latents = scale_1_latents.permute(0, 3, 1, 2).contiguous()
        s1_latents = scale_2_latents.permute(0, 3, 1, 2).contiguous()

        # Pre Encode
        # latents[bs, resnet_dim, x, y] -> [bs, h_dim, x, y]
        h_org = self.in_conv(latents)
        h_s0 = self.in_conv_1(s0_latents)
        h_s1 = self.in_conv_2(s1_latents)
        #
        output = self.mhattn(h_org, h_s0, h_s1)
        # latents[bs, x*y + s1x*s1y + s2x*s2y, h_dim, x, y]
        return output


class MLP(pytorch_lightning.LightningModule):
    def __init__(self, input_size=768, h_size=None):
        super().__init__()
        self.input_size = input_size
        self.h_size = h_size if h_size is not None else self.input_size // 2
        self.hidden_size = max(self.h_size, 1024)

        self.model = torch.nn.Sequential(
            torch.nn.Linear(self.input_size, self.hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size, self.hidden_size // 8),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(self.hidden_size // 8, self.hidden_size // 32),
            torch.nn.Linear(self.hidden_size // 32, 1),
        )

    def forward(self, x):
        return self.model(x)


class MUSIQ_SCORE_Model(torch.nn.Module):
    def __init__(
        self, n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon, output_scale=1
    ) -> None:
        super().__init__()
        self.musiq = MUSIQ(n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon)
        self.mlp = MLP(h_dim * output_scale)
        self.output_scale = output_scale

    def enable_math(self, enable_math: bool = True):
        self.musiq.enable_math(enable_math)

    def forward(self, latents, scale_1_latents, scale_2_latents):
        if self.output_scale == 1:
            h = self.musiq(latents, scale_1_latents, scale_2_latents)[:, 0]
        else:
            h = (
                self.musiq(latents, scale_1_latents, scale_2_latents)[:, 0 : self.output_scale]
                .contiguous()
                .view(latents.size(0), -1)
            )
        return self.mlp(h)


# モデル作成用
def Create_MUSIQ_Model(
    n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon, score_model_dir=None
):
    return resnet50_backbone(score_model_dir), MUSIQ(
        n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon
    )


def Create_MUSIQ_SCORE_Model(
    n_layer,
    h_dim,
    n_head,
    d_head,
    d_ff,
    grid_size,
    dropout,
    layer_norm_epsilon,
    score_model_dir=None,
    output_scale=1,
):
    return resnet50_backbone(score_model_dir), MUSIQ_SCORE_Model(
        n_layer, h_dim, n_head, d_head, d_ff, grid_size, dropout, layer_norm_epsilon, output_scale
    )


class Score_Manager:
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
            # args.output = args.output + "_x4"
            self.npy_dot = "_x4.npy"
        elif args.version == 2:
            self.scale_size = 3
            self.image_size = 1 + (self.scale_size * self.scale_size)
            # args.output = args.output + "_x9"
            self.npy_dot = "_x9.npy"

        self.image_preprocess = None
        self.clip_model, self.clip_preprocess = clip.load("ViT-L/14", device="cpu")  # RN50x64
        self.preprocess_size = self.clip_model.visual.input_resolution
        if version >= 1:
            self.image_preprocess = get_image_preprocess(self.preprocess_size, self.scale_size)
        self.tokenizer = clip.tokenize
        self.mlp = None  # MLP(768*self.image_size)
        self.device = device
        if score_max is not None:
            self.score_max = score_max
        else:
            self.score_max = 1.0
        if os.path.splitext(model_path)[-1] != ".pth":
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
            # txt_id = self.tokenizer(prompt, truncate=True).to(self.device)
            # if txt_id.size(1) > 77:
            #    print(f"too long token({txt_id.size()}): {prompt}")
            image = self.clip_preprocess(raw_image).unsqueeze(0).to(self.device)
            image_features = self.clip_model.encode_image(image)
            if self.image_size > 1:
                image = self.image_preprocess(raw_image).unsqueeze(0).to(self.device)
                for i in range(self.scale_size):
                    for j in range(self.scale_size):
                        image_features = torch.concat(
                            [
                                image_features,
                                self.clip_model.encode_image(
                                    image[
                                        :,
                                        :,
                                        i * self.preprocess_size : (i + 1) * self.preprocess_size,
                                        j * self.preprocess_size : (j + 1) * self.preprocess_size,
                                    ]
                                ),
                            ],
                            dim=1,
                        )

            # txt_features = self.clip_model.encode_text(txt_id)

        return self.mlp(image_features).data.cpu()[0][0] / self.score_max


if __name__ == "__main__":
    score_module_dir = "./score_module"
    model_params, dataset_params, train_params = get_property(
        "./test_dataset",
        batch_size=2,
        mode="musiq_clip",
        eval_per=0.1,
        hdf5_resume=False,
        hdf5_add_load=False,
    )
    print_dict(model_params, "model params")
    print_dict(dataset_params, "dataset params")

    test = MUSIQ_Score_Dataset(**dataset_params)
    # musiq_model = MUSIQ(2, 332, 5, 5, 5, 10, 0.1, 1e-9, score_module_dir)
    pre_encoder, musiq_model = Create_MUSIQ_SCORE_Model(**model_params)
    # pre_encoder = resnet50_backbone(score_module_dir)
    test.create_datalist(pre_encoder)
    test.print_datacount()
    test.print_datacount_score()
    test.eval = True
    data = test.__getitem__(0)
    scores = data["score"]
    latents = data["latent"]
    scale_1_latents = data["s1_latent"]
    scale_2_latents = data["s2_latent"]
    print("eval---------")
    print(f"datalen: {len(test)}")
    print(f"score: {scores}{scores.size()}\nlatents: {latents.size()}")
    print(f"s1_latents: {scale_1_latents.size()}")
    print(f"s2_latents: {scale_2_latents.size()}")
    print(scale_2_latents)
    test.eval = False
    data = test.__getitem__(0)
    scores = data["score"]
    latents = data["latent"]
    scale_1_latents = data["s1_latent"]
    scale_2_latents = data["s2_latent"]
    print("train---------")
    print(f"datalen: {len(test)}")
    print(f"score: {scores}{scores.size()}\nlatents: {latents.size()}")
    print(f"s1_latents: {scale_1_latents.size()}")
    print(f"s2_latents: {scale_2_latents.size()}")
    print(scale_2_latents)

    print("to cuda")
    musiq_model.to("cuda")
    print("test run")
    output = musiq_model(latents.to("cuda"), scale_1_latents.to("cuda"), scale_2_latents.to("cuda")).to(
        "cpu"
    )
    print(output.size())
