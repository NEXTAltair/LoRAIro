#https://github.com/kohya-ss/sd-scripts/blob/main/finetune/clean_captions_and_tags.py
## original code is distributed in Apache License 2.0.
import re
import sqlite3
from typing import List, Tuple
from pathlib import Path

# 正規表現パターンの定義
PATTERN_HAIR_LENGTH = re.compile(r'(long|short|medium) hair')
PATTERN_HAIR_CUT = re.compile(r'(bob|hime) cut')
PATTERN_HAIR = re.compile(r'([\w\-]+) hair')
PATTERN_WORD = re.compile(r'([\w\-]+|hair ornament)')
PATTERN_STYLES = re.compile(r'anime|cartoon|manga', re.IGNORECASE)

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

def clean_format(text : str) -> str:
    """
    テキストから無駄な記号と改行を削除
    ()をエスケープする
    Args:
        text (str): クリーニングするテキスト。
    Returns:
        str: クリーニング後のテキスト。
    """
    #str型でない場合はそのまま返す
    if not isinstance(text, str):
        return text
    text = text.lower() # 大文字を小文字に変換
    text = clean_underscore(text) # アンダーバーをスペースに置き換える
    text = re.sub(r'#', '', text) # #を削除
    text = re.sub(r'\"', '\"', text) # ダブルクォートをエスケープ
    text = re.sub(r'\*\*', '', text) # GPT4 visionがたまに付けるマークダウンの強調を削除
    text = re.sub(r'\.\s*$', ', ', text) # ピリオドをカンマに変換
    text = re.sub(r'\.\s*(?=\S)', ', ', text)  # ピリオド後にスペースがあればカンマとスペースに置換し、新しい単語が続く場合はその前にスペースを追加
    text = re.sub(r'\.\n', ', ', text)  # 改行直前のピリオドをカンマに変換
    text = re.sub(r'\n', ', ', text) # 改行をカンマに変換
    text = re.sub(r'\u2014', '-', text) # エムダッシュをハイフンに変換
    text = re.sub(r'\(', r"\(", text)  # '(' を '\(' にエスケープ
    text = re.sub(r'\)', r"\)", text)  # ')' を '\)' にエスケープ
    text = clean_repetition(text) # 重複した記号を削除
    return text

def clean_repetition(text : str) -> str:
    text = re.sub(r'\\+', r"\\", text) #重複した\を消す
    text = re.sub(r',+', r",", text) #重複した,を消す
    text = re.sub(r'\s+', r" ", text) #重複したスペースを消す
    return text

def clean_underscore(tags : str) -> str:
    """アンダーバーをスペースに置き換える"""
    if not isinstance(tags, str):
        return tags
    # '^_^' をプレースホルダーに置き換える
    tags = tags.replace('^_^', '^@@@^')
    # アンダーバーを消す
    tags = tags.replace('_', ' ')
    # プレースホルダーを元の '^_^' に戻す
    tags = tags.replace('^@@@^', '^_^')
    return tags

def clean_individual_tags(tags_dict : dict) -> dict:
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

def clean_color_Object(tags_dict : dict) -> dict:
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

def clean_Style(tags_dict : dict) -> dict:
    """anime styleとanime artみたい重複タグをanimeに統一する"""
    # 単語の出現を記録する辞書
    word_tags = {}

    for key, tag in tags_dict.items():
        unified_tag = tag
        match = PATTERN_STYLES.search(tag)
        if match:
            unified_tag = match.group().lower()  # 統一するタグを小文字に変換
        word_tags[key] = unified_tag

    # 重複タグの削除
    seen_tags = set()
    cleaned_tags_dict = {}
    for key, tag in word_tags.items():
        if tag not in seen_tags:
            seen_tags.add(tag)
            cleaned_tags_dict[key] = tag

    return cleaned_tags_dict


def tags_to_dict(tags : str) -> dict:
    """タグを辞書に変換するして重複を避ける
    Args:
        tags (str): タグ
    Returns:
        tags_dict (dict): タグの辞書
    """
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

def clean_tags(tags: str, format_id: int = 2) -> str:
    """タグをクリーニングする
    Args:
        tags (str): クリーニングするタグ
        format_id (int): タグの形式ID デフォルトでe621
    Returns:
        final_tags (str): クリーニング後のタグ
    """
    tags_dict = tags_to_dict(tags) # タグを辞書に変換する

    # 複数の人物がいる場合は髪色等のタグを削除する
    if 'girls' in tags or 'boys' in tags:
        tags_dict = clean_individual_tags(tags_dict)

    tags_dict = clean_color_Object(tags_dict) # red eyesとeyesみたいな重複タグを削除
    tags_dict = clean_Style(tags_dict) # anime styleとanime artみたい重複タグをanimeに統一する

    # クリーニングされたタグをカンマで再結合してstrに戻す
    tags = ", ".join(tag for _, tag in tags_dict.items() if tag and tag != "***")
    project_root = Path(__file__).resolve().parents[2] 
    db_path = project_root / "tsgs_v3.db" # .dbファイルのパス
    final_tags = cleanup_tag_sql(db_path, tags, format_id) # .dbを参照してタグを正規のタグ名に変換する
    return final_tags

def cleanup_tag_sql(db_path : Path, tags: str, format_id: int) -> str:
    """.dbファイルでタグをクリーニングする
    Args:
        db_path (Path): 参照する.dbファイルのパス
        tags (str): クリーニングするタグ
        format_id (int): タグの形式ID
    Returns:
        cleaned_tags (str): クリーニング後のタグ
    """
    tags_list = tags.split(", ")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cleaned_tags_list = []

    query = """
    SELECT 
        CASE 
            WHEN TS.alias = 1 THEN PT.tag
            ELSE T.tag
        END AS cleaned_tag
    FROM TAGS T
    JOIN TAG_STATUS TS ON T.tag_id = TS.tag_id
    LEFT JOIN TAGS PT ON TS.preferred_tag_id = PT.tag_id
    WHERE T.tag = ? AND TS.format_id = ?
    """

    for tag_to_cleanup in tags_list:
        cursor.execute(query, (tag_to_cleanup, format_id))
        result = cursor.fetchone()
        
        if result and result[0] != tag_to_cleanup:
            cleaned_tag = result[0]
            print(f"置換前: {tag_to_cleanup}")
            print(f"置換後: {cleaned_tag}")
            cleaned_tags_list.append(cleaned_tag)
        else:
            print(f"タグ '{tag_to_cleanup}' は変更されませんでした")
            cleaned_tags_list.append(tag_to_cleanup)

    conn.close()
    return ", ".join(cleaned_tags_list)

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
    tag_to_cleanup = "2girls, ponytail, braid, braid, red hair, blue eyes, long hair, ,"
    tags = clean_tags(tag_to_cleanup)
    print(f'Cleaned tag: {tags}')