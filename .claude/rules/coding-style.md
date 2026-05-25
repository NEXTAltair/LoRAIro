# Coding Style Rules

LoRAIroプロジェクトのコーディング規約。一貫性のある保守しやすいコードベースを維持するためのルール。

## 型ヒント

### 必須
- 全関数/メソッドに型ヒントを付ける
- 引数と戻り値の両方を指定

### モダンPython構文
```python
# 正しい: Python 3.10+ 構文
def process_items(items: list[str]) -> dict[str, int]:
    ...

def get_value(key: str) -> str | None:
    ...

# 禁止: typing モジュールの旧構文
from typing import List, Dict, Optional
def process_items(items: List[str]) -> Dict[str, int]:  # 使わない
    ...
```

### Any型の回避
```python
# 禁止
def process(data: Any) -> Any:
    ...

# 正しい: 具体的な型を使用
def process(data: ImageMetadata) -> ProcessResult:
    ...

# やむを得ない場合はコメントで理由を説明
def dynamic_load(config: Any) -> None:  # Any使用: 外部JSONスキーマが不定
    ...
```

## docstring

### Google-style必須
```python
def calculate_score(image: Image, model: str) -> float:
    """画像の品質スコアを計算する。

    指定されたモデルを使用して画像の品質を評価し、
    0.0から1.0の範囲でスコアを返す。

    Args:
        image: 評価対象の画像オブジェクト。
        model: 使用する評価モデルの名前。
            "aesthetic": 美的評価
            "technical": 技術的品質評価

    Returns:
        0.0から1.0の範囲の品質スコア。

    Raises:
        ValueError: 未知のモデル名が指定された場合。
        ImageProcessingError: 画像の読み込みに失敗した場合。
    """
    ...
```

## import

### 順序
1. 標準ライブラリ
2. サードパーティ
3. ローカルアプリケーション

```python
# 標準ライブラリ
import os
from pathlib import Path

# サードパーティ
from PySide6.QtWidgets import QWidget
from sqlalchemy.orm import Session

# ローカル
from lorairo.services import ImageService
from lorairo.database import Repository
```

### pathlib使用
```python
# 正しい
from pathlib import Path
path = Path("data") / "images" / "sample.png"

# 禁止
import os
path = os.path.join("data", "images", "sample.png")
```

## エラーハンドリング

### 具体的な例外
```python
# 正しい: 具体的な例外をキャッチ
try:
    with open(path) as f:
        data = f.read()
except FileNotFoundError:
    logger.warning(f"File not found: {path}")
    return None
except PermissionError:
    raise ConfigurationError(f"Cannot read file: {path}")

# 禁止: 広範なExceptionキャッチ
try:
    ...
except Exception:  # 避ける
    pass
```

### Manager 層のエラーハンドリング方針

`ImageDatabaseManager` 等の Manager 層では以下のルールに従う:

**許可: 期待される「見つからない」ケースに `return None/[]/0`**
```python
# 正しい: 「存在しない」は正常系扱い
def get_image(self, image_id: int) -> ImageRecord | None:
    try:
        return self.image_repo.get_by_id(image_id)
    except NoResultFound:
        return None
```

**禁止: 予期しない例外を握りつぶす**
```python
# 禁止: DB 接続エラーを None で返すと呼び出し元が気づけない
def get_image(self, image_id: int) -> ImageRecord | None:
    try:
        return self.image_repo.get_by_id(image_id)
    except Exception:  # SQLAlchemyError も OperationalError も一括で隠す
        return None
```

**正しいパターン:**
```python
def get_image(self, image_id: int) -> ImageRecord | None:
    try:
        return self.image_repo.get_by_id(image_id)
    except NoResultFound:
        return None          # 期待される「未登録」ケース
    except SQLAlchemyError:
        logger.error(f"DB error for image_id={image_id}", exc_info=True)
        raise               # 予期しない DB エラーは伝播させる
```

**判断フロー:**
1. この例外は「対象が存在しない」という正常な結果か? → `return None/[]/0`
2. 呼び出し元が例外を知らないと問題になるか? → `raise` または `raise XxxError from e`
3. `except Exception` を書きたくなったら設計を見直す

### 抑制コメント禁止
```python
# 禁止: 根本原因を修正すること
result = some_function()  # type: ignore
result = some_function()  # noqa

# 例外的に必要な場合は理由を詳細に記載
result = external_lib.call()  # type: ignore[no-any-return]  # 外部ライブラリの型定義が不完全
```

## 命名規則

### クラス名
- 具体的な名詞を使用
- 抽象的な名前を避ける

```python
# 正しい
class ImageProcessor:
    ...
class DatabaseRepository:
    ...

# 禁止
class Loader:  # 何をロードするか不明
    ...
class Handler:  # 何を処理するか不明
    ...
```

### 変数名
- スネークケース使用
- 意味のある名前

```python
# 正しい
image_count = 10
selected_tags: list[str] = []

# 禁止
n = 10  # 意味不明
lst = []  # 型情報なし
```

## 文字幅

### 半角文字のみ
- コード中のアルファベット、数字、記号は半角のみ
- 全角英数字・記号は使用禁止

```python
# 正しい
value = 123
message = "Hello"

# 禁止
value = １２３  # 全角数字
message = "Ｈｅｌｌｏ"  # 全角英字
```

## コメント

### 日本語可
- 実装コメントは日本語で記載可能
- ただしdocstringの形式は英語推奨

```python
def process_image(image: Image) -> ProcessedImage:
    """Process the image with enhancement filters."""
    # 画像のリサイズ処理
    resized = resize(image)

    # 色調補正を適用
    corrected = apply_color_correction(resized)

    return corrected
```

### TODO管理
```python
# TODO: Issue #123 - バッチ処理の最適化
# FIXME: Issue #456 参照 - メモリリークの修正
# PENDING: 仕様確定待ち - フィルタ条件の拡張
```

## 行長

- **最大108文字** (Ruff設定に準拠)
- 長い行は適切に改行

```python
# 正しい: 改行で読みやすく
result = some_very_long_function_name(
    first_argument,
    second_argument,
    third_argument,
)

# 禁止: 1行に詰め込む
result = some_very_long_function_name(first_argument, second_argument, third_argument, fourth_argument)
```
