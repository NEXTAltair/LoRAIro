"""CLI実装基盤モジュール。

LoRAIroのCLIツール群。GUI なし環境でのデータセット操作、
バッチ処理自動化、プログラマティックアクセスを提供する。

環境変数 LORAIRO_CLI_MODE を有効化してから CLI を実行する。
"""

import os

# CLI モード有効化: ServiceContainer が NoOpSignalManager を自動選択
os.environ.setdefault("LORAIRO_CLI_MODE", "true")
