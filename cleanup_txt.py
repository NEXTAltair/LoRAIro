#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/clean_captions_and_tags.py
import re
from pathlib import Path

# 正規表現パターンの定義
PATTERN_HAIR_LENGTH = re.compile(r'(long|short|medium) hair')
PATTERN_HAIR_CUT = re.compile(r'(bob|hime) cut')
PATTERN_HAIR = re.compile(r'([\w\-]+) hair')
PATTERN_WORD = re.compile(r'([\w\-]+|hair ornament)')

# 複数人がいるとき、複数の髪色や目の色が定義されていれば削除する
PATTERNS_REMOVE_IN_MULTI = [
    PATTERN_HAIR_LENGTH,
    PATTERN_HAIR_CUT,
    PATTERN_HAIR,
    re.compile(r'[\w\-]+ eyes'),
    re.compile(r'([\w\-]+ sleeves|sleeveless)'),
    # 複数の髪型定義がある場合は削除する
    re.compile(r'(ponytail|braid|ahoge|twintails|[\w\-]+ bun|single hair bun|single side bun|two side up|two tails|[\w\-]+ braid|sidelocks)'),
]

def clean_format(text):
    """
    テキストから無駄な記号と改行を削除
    ()をエスケープする
    Args:
        text (str): クリーニングするテキスト。
    Returns:
        str: クリーニング後のテキスト。
    """
    text = re.sub(r'\"', '\"', text) # ダブルクォートをエスケープ
    text = re.sub(r'\*\*', '', text) # GPT4 visionがたまに付けるマークダウンの強調を削除
    text = re.sub(r'\.\s*$', ', ', text) # ピリオドをカンマに変換
    text = re.sub(r'\.\s*(?=\S)', ', ', text)  # ピリオド後にスペースがあればカンマとスペースに置換し、新しい単語が続く場合はその前にスペースを追加
    text = re.sub(r'\.\n', ', ', text)  # 改行直前のピリオドをカンマに変換
    text = re.sub(r'\\n+', ', ', text) # 改行をカンマに変換
    text = re.sub(r'\\u2014', ' ', text) # エムダッシュをスペースに変換
    text = re.sub(r'\(', r"\(", text)  # '(' を '\(' にエスケープ
    text = re.sub(r'\)', r"\)", text)  # ')' を '\)' にエスケープ
    return text


def clean_repetition(text):
    #重複した\を消す
    text = re.sub(r'\\+', r"\\", text)
    #重複した,を消す
    text = re.sub(r',+', r",", text)
    #重複したスペースを消す
    text = re.sub(r'\s+', r" ", text)
    return text

def clean_underscore(tags):
    """アンダーバーをスペースに置き換える"""
    # '^_^' をプレースホルダーに置き換える
    tags = tags.replace('^_^', '^@@@^')
    # アンダーバーを消す
    tags = tags.replace('_', ' ')
    # プレースホルダーを元の '^_^' に戻す
    tags = tags.replace('^@@@^', '^_^')
    return tags

def clean_individual_tags(tags_dict):
    """髪の長さを残して色の特徴とかいろいろを含むタグを削除する"""
    # 置き換え用のプレースホルダー
    placeholder = "@@@"
    # 保存されたオリジナルの長さタグ
    original_lengths = {}

    # 長さに関するタグを一時的に保護
    for key, tag in tags_dict.items():
        match = PATTERN_HAIR_LENGTH.search(tag)
        if match:
            original_lengths[key] = match.group()  # オリジナルのタグを保存
            tags_dict[key] = tag.replace(match.group(), placeholder)

    # 不要なタグの削除
    for key, tag in tags_dict.items():
        modified_tag = tag  # 変更を加えるためのローカル変数
        for pattern in PATTERNS_REMOVE_IN_MULTI:
            modified_tag = pattern.sub("", modified_tag)
            tags_dict[key] = modified_tag  # 最終的な変更を反映

    # 髪の長さタグを復元
    for key, tag in tags_dict.items():
        if placeholder in tag:
            # placeholderをオリジナルのタグに置き換え
            tags_dict[key] = tag.replace(placeholder, original_lengths.get(key, ""))

    return tags_dict

def clean_color_Object(tags_dict):
    """white shirtとshirtみたいな重複タグの削除"""
    # 単語の出現を記録する辞書
    word_tags = {}

    # タグから単語を抽出し、単語が含まれるタグを記録
    for key, tag in tags_dict.items():
        words = PATTERN_WORD.findall(tag)
        for word in words:
            if word in word_tags:
                word_tags[word].add(tag)
            else:
                word_tags[word] = {tag}

    # 単語が含まれるタグが他のタグに完全に含まれているかを確認し、そのようなタグを削除
    for word, tags in word_tags.items():
        for tag in list(tags):
            if any(tag != other_tag and tag in other_tag for other_tag in tags):
                # その単語を含むタグを全ての辞書から削除
                tags_dict = {k: v for k, v in tags_dict.items() if v != tag}

    return tags_dict

def tags_to_dict(tags):
    """タグを辞書に変換する"""
    # タグをカンマで分割し、不要な空白を取り除く
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    # 重複を避けるためのセット
    seen_tags = set()
    tags_dict = {}
    for i, tag in enumerate(tag_list):
        if tag not in seen_tags:
            seen_tags.add(tag)
            tags_dict[i] = tag
    return tags_dict

def clean_tags(tags):
    delete_underscore_tags = clean_underscore(tags)

    tags_dict = tags_to_dict(delete_underscore_tags)

    # 複数の人物がいる場合は髪色等のタグを削除する
    if 'girls' in tags or 'boys' in tags:
        tags_dict = clean_individual_tags(tags_dict)

    tags_dict = clean_color_Object(tags_dict)

    # クリーニングされたタグをカンマで再結合
    final_tags = ", ".join(tag for _, tag in tags_dict.items() if tag and tag != "***")
    return final_tags


CAPTION_REPLACEMENTS = [
    ('anime anime', 'anime'),
    ('young ', ''),
    ('anime girl', 'girl'),
    ('cartoon female', 'girl'),
    ('cartoon lady', 'girl'),
    ('cartoon character', 'girl'),      # a or ~s
    ('cartoon woman', 'girl'),
    ('cartoon women', 'girls'),
    ('cartoon girl', 'girl'),
    ('anime female', 'girl'),
    ('anime lady', 'girl'),
    ('anime character', 'girl'),      # a or ~s
    ('anime woman', 'girl'),
    ('anime women', 'girls'),
    ('lady', 'girl'),
    ('female', 'girl'),
    ('woman', 'girl'),
    ('women', 'girls'),
    ('people', 'girls'),
    ('person', 'girl'),
    ('a cartoon figure', 'a figure'),
    ('a cartoon image', 'an image'),
    ('a cartoon picture', 'a picture'),
    ('an anime cartoon image', 'an image'),
    ('a cartoon anime drawing', 'a drawing'),
    ('a cartoon drawing', 'a drawing'),
    ('girl girl', 'girl'),
]

def clean_caption(caption):
    """キャプションをクリーニングする
    Args:
        caption (str): クリーニングするキャプション
    """
    for rf, rt in CAPTION_REPLACEMENTS:
        replaced = True
        while replaced:
            bef = caption
            caption = caption.replace(rf, rt)
            replaced = bef != caption
    return caption

if __name__ == '__main__':
    img_folder = Path(r'H:\lora\asscutout-XL\img_Processed')
    for text_path in img_folder.rglob('*.txt'):
        with open(text_path, 'r', encoding='utf-8') as f:
            tags = f.read()
        tags = clean_format(tags)
        tags = clean_tags(tags)
        tags = clean_repetition(tags)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(tags)
        print(f'Cleaned: {text_path.name}')