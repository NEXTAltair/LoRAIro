# LoRA用画像をいろいろするスクリプト

## 概要

「Lorayougazouwoiroirosurusukuriputo」は、LoRA学習用画像データセットの自動処理を行うPythonスクリプト集｡画像のリサイズ、タグ付け、キャプション生成を自動化して、データセット作成を楽にする。

### 特徴

- **画像の一括リサイズ**:  大量の画像を指定したサイズ（例：512x512、1024x1024）に一括でリサイズして、webp形式に変換する。LoRA学習に最適な画像形式とサイズに統一できる。
- **タグとキャプションの自動生成**: 画像の内容をGPT-4などの画像認識モデルで解析して、適切なタグとキャプションを自動生成する。手動タグ付けの手間を大幅に削減。
- **タグのクリーンアップ**:  自動生成されたタグや既存のタグリストから、ノイズとなるタグや重複するタグを削除・統合する。また、別名タグを統一することで、データセットの品質を向上させる。

### スクリプト

- **ImageEditor.py**: 複数の画像を一括で指定されたサイズのwebpにリサイズする。
    - cv2を使用して画像の枠を自動識別＆除去
    - 色域をsRGBないしRGBに変換
    - 長編が指定解像度未満の画像を移動
    - 長編が指定解像度以下かつアスペクト比を維持したまま両辺が32の倍数になるように縮小
    - 画像と付随する .txt と .caption  を親フォルダ+連番にリネーム
- **caption_tags.py**: 画像の内容をGPT-4が解析し、タグとキャプションを自動生成する。
    - 既存の画像情報をインスタンス変数に保存
    - 画像の親フォルダに "nsfw" が含めれてる場合APIに処理させないように弾く
    - 画像情報から kohya/sd-scripts 用 'meta_clean.json' を作成
    - 画像情報から画像ファイルの場所にタグ(.txt)とキャプション(.caption)を作成
    - 既存のタグとキャプションがある場合は結合する｡しない場合は上書き
    - API エラーや キャプション生成の拒絶の場合そのファイルの移動
- **api_utils.py**
    - バッチ用payloadをまとめてjsonlに書き出す
    - バッチ用jsonlが長すぎる場合分割
    - バッチ用jsonlをAPIに投げてアップロードと実行
- **cleanup_txt.py**: テキストファイルを整形し、タグリストをクリーンアップする。
    - アンダースコアの削除
    - 改行の削除､()のエスケープなどの文字列の整形
    - 重複したカンマの削除
    - 複数人の映った画像の場合、髪色、目色の色要素を削除
    - white shirtとshirtのように色についてより説明が詳細なタグがある場合、括りの大きなタグの削除
    - tags.dbを使用して非推奨タグを推奨タグへ置換
- **tags.db**:  SQLite3で作成したタグデータベース(作りかけ)
    - name タグ
    - type タグの種類
    - postCount タグが付いている画像の数
    - alias タグの別名

### 必要条件

- Python 3.6以上 (開発環境はPython 3.11.9)
- Pillow
- requests
- base64
- json
- pathlib
- SQLite3
- opencv-python

### インストール方法

1. GitHubからリポジトリをクローンする。

```bash
git clone https://github.com/NEXTAltair/Lorayougazouwoiroirosurusukuriputo.git
```

2. 必要なPythonライブラリをインストールする。

requirements.txt は無いから手動でインストール

色々建て増しで増やしてるからエクスポートしてもすげえ汚いからやめた

### 使用方法

1. 各スクリプトの使い方は、スクリプトファイル内のコメン
2. `python script_name.py`のように、実行したいスクリプトを直に実行

コマンドライン引数など現時点では使用してない

### ライセンス

MIT

### 参考

- [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) タグのクリーンナップ
- [DominikDoom/a1111-sd-webui-tagcomplete](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete) tags.dbの基になったCSV tag data
- [applemango](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete/discussions/265) CSV tag data の日本語翻訳
- としあき製 CSV tag data の日本語翻訳
- [AngelBottomless/danbooru-2023-sqlite-fixed-7110548](https://huggingface.co/datasets/KBlueLeaf/danbooru2023-sqlite) danbooru タグのデータベース
- [hearmeneigh/e621-rising-v3-preliminary-data](https://huggingface.co/datasets/hearmeneigh/e621-rising-v3-preliminary-data) e621 rule34 タグのデータベース

## 今後

- タグデータベース(tags.db)の機能拡充
- GUIによる操作性の向上
- google AI studio APIへの対応
  