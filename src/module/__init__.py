import importlib
import sys
from pathlib import Path

# モジュールのパスを取得
module_path = str(Path(__file__).parent / "genai-tag-db-tools")

# パスをシステムのパスに追加
if module_path not in sys.path:
    sys.path.append(module_path)

# モジュールをインポート
tag_search = importlib.import_module("tag_search")
CSVToDatabaseProcessor = importlib.import_module("CSVToDatabaseProcessor")