# System Patterns *Optional*

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-04-14 03:00:12 - Log of updates made.

*

## Coding Patterns

*   [2025-04-14 10:54:55] - **可読性重視:** 常に読みやすく、理解しやすいコードを記述する。
*   [2025-04-14 10:54:55] - **YAGNI原則:** 必要最小限の機能のみを実装する。
*   [2025-04-14 10:54:55] - **半角文字:** コード、コメント、ドキュメント内では半角英数字・記号を使用する。
*   [2025-04-14 10:54:55] - **PEP 8準拠:** PEP 8 ガイドラインに従う。
*   [2025-04-14 10:54:55] - **命名規則:**
    *   変数/関数/メソッド: `snake_case` (具体的)
    *   クラス: `CamelCase` (具体的、`er`命名回避)
*   [2025-04-14 10:54:55] - **パス処理:** `pathlib` を使用する (`os` は非推奨)。
*   [2025-04-14 10:54:55] - **リスト内包表記:** `if`/`for` は各1つまでに制限する。
*   [2025-04-14 10:54:55] - **型ヒント:**
    *   引数/戻り値に具体的型ヒントを付与する。
    *   モダンな型 (`list`, `dict`, `collections.abc`) を使用する (`typing.List/Dict`, `Optional` は非推奨)。
    *   複雑な辞書には `TypedDict` を活用する。
    *   メソッドチェーンには `Self` を使用する。
    *   `Any` の使用は最小限にする。
*   [2025-04-14 10:54:55] - **静的解析:** Mypy/Ruffのエラー/警告は抑制せず修正する (`# type: ignore`, `# noqa`, `try...except ImportError` 等の回避策禁止)。
*   [2025-04-14 10:54:55] - **エラーハンドリング:** 特定のエラーのみ具体的に捕捉し、過剰/無意味なハンドリングは避ける。明確なエラーメッセージを含める。`OutOfMemoryError` は情報含めて再送出する。
*   [2025-04-14 10:54:55] - **設計原則:** 単一責任の原則 (SRP)、責任分離を意識する。
*   [2025-04-14 11:01:40] - **カプセル化:**
    *   他クラス内部変数 (`_`始まり) への直接アクセス禁止。
    *   Tell, Don't Ask 原則。
    *   内部状態は原則非公開 (@property で読み取り専用公開可、ミュータブル参照直接返却禁止)。
    *   単純なゲッター/セッター禁止。
    *   公開インターフェース最小化 (YAGNI)。
    *   内部変数は `_` プレフィックス。
*   [2025-04-14 11:01:40] - **ドキュメンテーション:**
    *   全角英数字禁止。
    *   Google スタイル docstring (Args, Returns, Raises)。
    *   モジュールコメント (目的、主要クラス/関数、依存関係)。
    *   実装コメント (日本語、簡潔明確)。
    *   コードアノテーション (`TODO`, `FIXME` 等) を活用。
    *   コード変更時は関連ドキュメントも更新。
    *   明確なコミットメッセージ。

## Architectural Patterns

*   [2025-04-14 10:54:55] - src layout を採用 (decisionLog.md より)

## Testing Patterns

*   [2025-04-14 10:54:55] - pytest を使用予定 (pyproject.toml より)。
*   [2025-04-14 11:01:40] - **BDD (pytest-bdd):**
    *   **Feature ファイル:**
        *   `tests/features` に配置。
        *   ユーザー視点の Feature 説明、Background、Scenario (単一責任、独立性)。
        *   Given/When/Then (平易な言葉、実装詳細回避)。
        *   Scenario Outline + Examples (パラメータは半角英数字/スネークケース)。
    *   **ステップ定義:**
        *   `tests/step_defs` or `tests/integration` に配置。
        *   Feature との関連付け (`scenarios` 関数)。
        *   パラメータ化 (パーサー活用)。
        *   関数名プレフィックス (`given_`, `when_`, `then_`)。
        *   値渡しはフィクスチャ (`target_fixture`)。
        *   セットアップ/クリーンアップは pytest フィクスチャ活用 (`conftest.py` や専用モジュール)。
        *   ファイルは機能/ドメインで分割。
        *   単一アクション/検証の粒度。
        *   状態共有はフィクスチャ経由。
        *   `Then` にアサーション。
    *   **テスト方針:**
        *   十分なカバレッジ確保。
        *   異常系テストも考慮。
        *   `uv pytest` で実行、カバレッジは XML 出力。