# Security Rules

LoRAIroプロジェクトにおけるセキュリティガイドライン。コミット前に必ず確認すること。

## API Key管理

### 必須事項
- **ハードコード禁止**: API Keyをソースコードに直接記述しない
- **環境変数経由**: すべての機密情報は環境変数から取得
- **.gitignore必須**: `.env`ファイルは必ず`.gitignore`に含める

### 正しいパターン
```python
import os

# 環境変数から取得
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is required")
```

### 禁止パターン
```python
# これらは絶対に行わない
api_key = "sk-..."  # ハードコード
api_key = "your-api-key-here"  # プレースホルダー残存
```

## 入力検証

### ファイルパス
- `Path.resolve()`で正規化してpath traversalを防止
- ユーザー入力のパスは必ず検証

```python
from pathlib import Path

def safe_path(user_input: str, base_dir: Path) -> Path:
    resolved = (base_dir / user_input).resolve()
    if not resolved.is_relative_to(base_dir):
        raise ValueError("Invalid path: outside allowed directory")
    return resolved
```

### ユーザー入力
- すべてのユーザー入力はバリデーション必須
- 型変換前にnullチェック
- 予期しない値は早期にエラー

## SQLセキュリティ

### SQLAlchemy ORM使用
- 生のSQL文字列連結は禁止
- パラメータ化クエリを使用

```python
# 正しい: SQLAlchemy ORM
session.query(Image).filter(Image.id == image_id).first()

# 禁止: 文字列連結
session.execute(f"SELECT * FROM images WHERE id = {image_id}")
```

## 危険な関数の使用禁止

以下の関数は原則使用禁止:
- `eval()` / `exec()` - コードインジェクションリスク
- `pickle.load()` - 任意コード実行リスク
- `os.system()` - コマンドインジェクションリスク
- `subprocess` with `shell=True` - コマンドインジェクションリスク
- `yaml.load()` without `Loader=SafeLoader`

### 例外が必要な場合
- コードレビューで明示的な承認を得る
- 入力が完全に信頼できることを文書化
- コメントで理由を説明

## 例外処理と情報漏洩

### 禁止事項
- ユーザー向けエラーメッセージに内部パス/スタック情報を含めない
- ログに機密情報を出力しない

```python
# 正しい
except FileNotFoundError:
    raise ValueError("File not found")

# 禁止
except FileNotFoundError as e:
    raise ValueError(f"File not found: {e}")  # 内部パス露出
```

## セキュリティ問題発見時

重大なセキュリティ脆弱性を発見した場合:
1. 即座に作業を中断
2. 該当コードを修正
3. コードレビューで確認
4. 必要に応じてセキュリティ監査を実施
