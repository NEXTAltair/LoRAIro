---
trigger: glob
description: "Python 実装の lint / 型チェック設定と lint 結果の扱い"
globs: "**/*.py, pyproject.toml"
---

# コーディングスタイル規約

実装コードのスタイルは、散文のルールではなく Ruff と mypy の設定で定義する。型ヒントの構文、インポート順序、行長、命名形式(スネークケースなど)、全角文字の混入といった機械で検出できる事項はここに記載せず、設定と静的解析の結果に委ねる。

本ファイルでは、次の 3 点だけを定める。

1. `pyproject.toml` に置く Lint・型チェック設定(セキュリティ系の `S` ルールを含む。判断事項は [security.md](security.md) を参照)
2. Lint 結果の扱い方(コミット前に修正し、原則として抑制しない)
3. Lint では決められない設計判断(言語、例外方針、命名の具体性)

> **プロジェクト固有:** `target-version` と `python_version` は導入先の Python バージョンに、`exclude` と `per-file-ignores` は導入先の構成に合わせる。Ruff のルール選択とフォーマット設定はプロジェクト依存度が低いため、そのまま利用してよい。

## Lint・型チェック設定

以下の設定を導入先の `pyproject.toml` に配置する。

```toml
[tool.ruff]
# check は読み取り専用。自動修正は `ruff check --fix` を明示したときだけ行う
fix = false
line-length = 108
target-version = "py312"
exclude = [
    "*/gui/designer/*",  # Qt Designer が生成するコード
    "*/__pycache__",
]

[tool.ruff.lint]
fixable = ["ALL"]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "C4",  # flake8-comprehensions
    "C90", # McCabe complexity
    "B",   # flake8-bugbear
    "UP",  # pyupgrade (list[str], X | None 等のモダン構文へ寄せる)
    "RUF", # Ruff 固有 (全角記号の混入検出 RUF001-003 を含む)
    "S",   # flake8-bandit (eval/exec, pickle, shell=True, ハードコード秘密, SQL 連結。security.md 参照)
]
ignore = [
    "E501", # 行長は line-length とフォーマッターで制御
    "B008", # typer.Option/Argument を関数デフォルトに置く typer 標準パターン
]
# 日本語表記として自然な文字だけ confusable 警告から除外する。
# 残る全角記号 (: = + ! ? - 等) は RUF001/002/003 で検出し半角化させる
allowed-confusables = ["ノ", "(", ")", "×"]

[tool.ruff.lint.per-file-ignores]
# テストでは assert (S101) を使う
"tests/**" = ["S101"]
# 例: モックを先に設定してから import する必要がある conftest は E402 を意図的に許可する。
# 導入先で理由をコメント付きで追記する
# "tests/conftest.py" = ["E402"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"

[tool.mypy]
strict = true              # 全関数の型ヒント必須、Any の暗黙利用禁止を含む
python_version = "3.12"
ignore_missing_imports = true
exclude = ['^src/[^/]+/gui/designer/', '^tests/']

[[tool.mypy.overrides]]
module = ["tests.*"]
ignore_errors = true
follow_imports = "skip"
```

## Lint 結果の扱い

- コミット前に `uv run ruff check`、`uv run ruff format`、`uv run mypy` を実行し、すべてのチェックを通す。指摘が残った状態でコミットしてはならない。
- 指摘は根本原因を修正し、`# noqa` や `# type: ignore` で抑制しない。例外的に抑制が必要な場合は、ルールコードを限定したうえで同じ行に理由を明記する。

```python
# 禁止
result = some_function()  # type: ignore
result = some_function()  # noqa

# 例外: ルールコードを限定して理由を書く
result = external_lib.call()  # type: ignore[no-any-return]  # 外部ライブラリの型定義が不完全
```

- 設定側を緩めてチェックを通すのは、`per-file-ignores` にコメント付きで理由を明記できる場合に限る。`select` からルールグループを外す、`fail_under` を下げる、`strict` を無効化するなど、全体基準を緩める変更は行わない。
- 自動修正(`ruff check --fix`)を使った場合は、変更内容を差分で確認してからコミットする。

## 言語と docstring

- docstring、コメント、エラーメッセージ、ログは日本語で記述する。国際的な公開を前提としない。
- docstring は Google 形式(`Args`、`Returns`、`Raises`)で記述する。

```python
def calculate_score(item: Item, model: str) -> float:
    """対象の品質スコアを計算する。

    Args:
        item: 評価対象のオブジェクト。
        model: 使用する評価モデルの名前。

    Returns:
        0.0 から 1.0 の範囲の品質スコア。

    Raises:
        ValueError: 未知のモデル名が指定された場合。
    """
```

## エラーハンドリング(Manager / Service 層)

Repository を薄くラップする Manager 層や Service 層では、「対象が見つからない」と「処理が失敗した」を明確に区別する。

- **期待される「見つからない」は正常系として扱う**: `NoResultFound` のように「対象が存在しない」ことを示す例外は、`None`、`[]`、`0` などの戻り値へ変換してよい。
- **予期しない例外は握りつぶさない**: データベース接続エラーなどを `None` に変換して返すと、呼び出し元が異常に気づけない。ログを残したうえで `raise`、または `raise XxxError from e` で上位へ伝播させる。
- `except Exception` を書きたくなったときは、例外設計そのものを見直す。

```python
def get_item(self, item_id: int) -> ItemRecord | None:
    try:
        return self.item_repo.get_by_id(item_id)
    except NoResultFound:
        return None          # 期待される「未登録」ケース
    except SQLAlchemyError:
        logger.error(f"DB error for item_id={item_id}", exc_info=True)
        raise               # 予期しない DB エラーは伝播させる
```

## 命名:具体的な名詞を使う

対象を問わず何にでも当てはまる総称語は、実体を指していない。「その語だけを見て、指している実体を他人が特定できるか」を基準とし、特定できなければ総称語を疑う。

- **コード識別子**: `Loader`、`Handler`、`data`、`n` のような曖昧な名前を避ける。代わりに `ItemProcessor`、`DatabaseRepository`、`selected_tags`、`item_count` のように、扱う対象を具体的に表す名前を付ける。
- **ドキュメント・コメント・説明文の用語**: 「台帳」「マネージャー」「データ」といった総称語を避け、何を記録・管理するものかが分かる語(工程表、タスク進捗表、実行履歴レジストリなど)に置き換える。

## TODO 管理

課題管理システムの識別子をコメントに残し、後から追跡できるようにする。

```python
# TODO: <issue-id> - バッチ処理の最適化
# FIXME: <issue-id> 参照 - メモリリークの修正
# PENDING: 仕様確定待ち - フィルタ条件の拡張
```
