# LoRA用画像をいろいろするスクリプト

## 概要

「Lorayougazouwoiroirosurusukuriputo」は、画像の自動処理を行うPythonスクリプト集である。
このプロジェクトは主に画像のリサイズ、タグ付け、キャプション生成を自動化することを目的としている。

## スクリプト

- **ImageEditor.py**: 複数の画像を一括で指定されたサイズにリサイズする。
- **caption_tags.py**: 画像の内容をGPT4が解析し、タグとキャプション自動生成する。
- **cleanup_txt.py**: テキストファイルを整形するモジュール

## 必要条件

このスクリプトを使用するには、Python 3.6以上が必要であり、以下のPythonライブラリが必要となる:

- Pillow
- requests
- base64
- json
- pathlib

これらのライブラリは次のコマンドでインストール可能:

```bash
pip install Pillow requests base64 json pathlib
```

## インストール方法

GitHubからこのリポジトリをクローン:

```bash
git clone https://github.com/NEXTAltair/Lorayougazouwoiroirosurusukuriputo.git
```

## 使用方法

リポジトリのルートディレクトリから、以下のコマンドを実行:

```python
python script_name.py
```

`script_name.py` を使用したいスクリプトのファイル名に置き換える。

## ライセンス

MIT
