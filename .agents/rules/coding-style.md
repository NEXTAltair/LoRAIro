---
trigger: glob
description: "Python 実装の lint / 型チェック設定と lint 結果の扱い"
globs: "**/*.py, pyproject.toml"
---

# Coding Style Rules

実装コードのスタイルは、散文のルールではなく Ruff / mypy の設定で定義する。型ヒントの構文、
import 順序、行長、命名の形式 (snake_case 等)、全角文字の混入のような機械で検出できる事項は
ここに書かず、設定と lint 結果に委ねる。本ファイルが持つのは次の 3 つだけ:

1. `pyproject.toml` に置く lint / 型チェック設定 (セキュリティ系の `S` rule を含む。判断事項は [security.md](security.md))
2. lint 結果の扱い方 (commit 前に直す、抑制しない)
3. lint では決まらない設計判断 (言語、例外方針、命名の具体性)

> **プロジェクト固有:** `target-version` / `python_version` は導入先の Python 版に、`exclude` と
> `per-file-ignores` は導入先の構成に合わせる。Ruff の rule 選択と format 設定は個人の好みとして
> 育てたもので、プロジェクト依存度は低いのでそのまま使ってよい。

## lint / 型チェック設定

以下を導入先の `pyproject.toml` に置く。

```toml
[tool.ruff]
# check は read-only。自動修正は `ruff check --fix` を明示したときだけ
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
    "E501", # 行長は line-length と formatter で制御
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

## lint 結果の扱い

- commit 前に `uv run ruff check`、`uv run ruff format`、`uv run mypy` を通す。指摘が残った状態で commit しない。
- 指摘は根本原因を直す。`# noqa` / `# type: ignore` で抑制しない。例外的に必要な場合は rule code を
  限定し、理由を同じ行に書く。

```python
# 禁止
result = some_function()  # type: ignore
result = some_function()  # noqa

# 例外: rule code を限定し理由を書く
result = external_lib.call()  # type: ignore[no-any-return]  # 外部ライブラリの型定義が不完全
```

- 設定側を緩めて通すのは、`per-file-ignores` にコメント付きで理由を書ける場合に限る。`select` から
  rule group を外す、`fail_under` を下げる、`strict` を切るといった全体を緩める変更はしない。
- 自動修正 (`ruff check --fix`) を使う場合は、何が変わったかを diff で確認してから commit する。

## 言語

- docstring・コメント・エラーメッセージ・ログは日本語で書く。国際的な公開を前提にしない。
- docstring は Google 形式 (Args / Returns / Raises)。

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

## エラーハンドリング (Manager / Service 層)

Repository を薄くラップする Manager / Service 層では、「見つからない」と「失敗した」を区別する。

- **期待される「見つからない」は正常系**: `NoResultFound` のような「対象が存在しない」例外は
  `return None / [] / 0` に変換してよい。
- **予期しない例外は握りつぶさない**: DB 接続エラーなどを `None` で返すと呼び出し元が気づけない。
  ログを残して `raise`、または `raise XxxError from e` で伝播させる。
- `except Exception` を書きたくなったら設計を見直す。

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

## 命名: 具体的な名詞を使う

対象を問わず何にでも当てはまる総称語は、実体を指していない。「その語だけを見て、指している実体を
他人が特定できるか」を基準にし、特定できなければ総称語を疑う。

- **コード識別子**: `Loader` / `Handler` / `data` / `n` のような語ではなく、`ItemProcessor` /
  `DatabaseRepository` / `selected_tags` / `item_count` のように何を扱うかを言い当てる。
- **ドキュメント・コメント・説明文の用語も同じ原則に従う**: 「台帳」「マネージャー」「データ」の
  ような総称語は、何を記録・管理する何なのかを言い当てる語 (工程表、タスク進捗表、実行履歴レジストリ 等)
  に置き換える。

## TODO 管理

課題管理システムの識別子を残し、後から追跡できるようにする。

```python
# TODO: <issue-id> - バッチ処理の最適化
# FIXME: <issue-id> 参照 - メモリリークの修正
# PENDING: 仕様確定待ち - フィルタ条件の拡張
```
