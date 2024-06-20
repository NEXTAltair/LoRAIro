"""
sqlite3を使って、タグのクリーンナップを行う
非推奨タグを推奨のタグ名に置き換える
"""
import sqlite3

def cleanup_tag_sql(db_path, tags):
    # SQLite DBに接続する
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 結果を格納するリスト
    cleaned_tags = []
    # クリーンナップ前のタグを対応する正規のタグ名に置き換えるクエリ
    query = """
    SELECT name
    FROM tags
    WHERE aliases = ?
    """

    for tag_to_cleanup in tags:
        cursor.execute(query, (tag_to_cleanup,))
        results = cursor.fetchall()
        # 結果があれば、正規のタグ名を返す。なければ元のタグを返す
        if results:
            #fetchallはタプルのリストを返すので、リスト内包表記でタプルの要素を取り出す
            names = [result[0] for result in results]
            cleaned_tags.append(','.join(names))
        else:
            cleaned_tags.append(tag_to_cleanup)

    conn.close()
    return cleaned_tags

# 使用例
db_path = 'tags.db'
tag_to_cleanup = 'general, sensitive, looking at viewer, blush, short hair, shirt, blonde hair, multiple girls, holding, 2girls, collarbone, white shirt, upper body, short sleeves, solo focus, indoors, nose blush, embarrassed, wavy mouth, ?, t-shirt, @ @, overalls, spoken question mark, ear blush, general, sensitive, 1girl, solo, blush, short hair, blue eyes, shirt, blonde hair, multiple girls, brown hair, holding, closed mouth, 2girls, collarbone, white shirt, upper body, short sleeves, indoors, embarrassed, wavy mouth, ?, @ @, paper, overalls, spoken question mark, general, sensitive, 1girl, looking at viewer, blush, short hair, shirt, blonde hair, multiple girls, holding, closed mouth, 2girls, collarbone, white shirt, upper body, short sleeves, solo focus, indoors, nose blush, embarrassed, light brown hair, wavy mouth, ?, t-shirt, @ @, paper, full-face blush, overalls, spoken question mark, ear blush, holding paper, female, solo, feral, clothing, clothed, hair, blush, tears, text, crying, anthro, mammal, hi res, ambiguous gender, dagasi, bodily fluids'
#タグを分割
tags = tag_to_cleanup.split(", ")
cleaned_tags = cleanup_tag_sql(db_path, tags)
cleaned_tags_str = ','.join(cleaned_tags)
print(f'Cleaned tag: {cleaned_tags_str}')


