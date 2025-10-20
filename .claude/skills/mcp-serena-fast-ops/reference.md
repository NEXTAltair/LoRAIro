# Serena Fast Operations - APIリファレンス

## シンボル検索ツール

### mcp__serena__get_symbols_overview
ファイル内のトップレベルシンボル（クラス、関数、変数）の概要を取得。

**パラメータ:**
- `relative_path` (string, 必須): 対象ファイルの相対パス
- `max_answer_chars` (integer, オプション): 出力の最大文字数（デフォルト: -1 = 無制限）

**戻り値:**
JSONオブジェクト - トップレベルシンボルの情報（名前、種類、行番号など）

**使用例:**
```python
mcp__serena__get_symbols_overview(
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py"
)
```

---

### mcp__serena__find_symbol
名前パスに基づいてシンボル（クラス、メソッド、関数）を検索。

**パラメータ:**
- `name_path` (string, 必須): シンボルの名前パス（例: "ThumbnailWidget/handle_click"）
- `relative_path` (string, オプション): 検索範囲を絞るファイル/ディレクトリパス
- `include_body` (boolean, オプション): コード本体を含めるか（デフォルト: False）
- `depth` (integer, オプション): 子シンボルを取得する深さ（デフォルト: 0）
- `substring_matching` (boolean, オプション): 部分一致検索（デフォルト: False）
- `include_kinds` (array[integer], オプション): 含めるシンボル種別（LSP symbol kind）
- `exclude_kinds` (array[integer], オプション): 除外するシンボル種別
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**LSP Symbol Kinds:**
- 5 = Class
- 6 = Method
- 12 = Function
- 13 = Variable
- その他の種別は SKILL.md 参照

**戻り値:**
マッチしたシンボルのリスト（位置、コード本体、子シンボルなど）

**使用例:**
```python
# クラス定義を取得（メソッド一覧付き）
mcp__serena__find_symbol(
    name_path="ThumbnailWidget",
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
    include_body=False,
    depth=1  # メソッド一覧も取得
)

# メソッド実装を取得
mcp__serena__find_symbol(
    name_path="ThumbnailWidget/handle_click",
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
    include_body=True
)
```

---

### mcp__serena__search_for_pattern
正規表現パターンに基づいてコードを検索。

**パラメータ:**
- `substring_pattern` (string, 必須): 正規表現パターン
- `relative_path` (string, オプション): 検索範囲（ファイルまたはディレクトリ）
- `restrict_search_to_code_files` (boolean, オプション): コードファイルのみに限定（デフォルト: False）
- `paths_include_glob` (string, オプション): 含めるファイルのglob パターン
- `paths_exclude_glob` (string, オプション): 除外するファイルのglob パターン
- `context_lines_before` (integer, オプション): マッチ前の文脈行数
- `context_lines_after` (integer, オプション): マッチ後の文脈行数
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**戻り値:**
ファイルパスとマッチした行のマッピング

**使用例:**
```python
# Signal/Slot接続パターンを検索
mcp__serena__search_for_pattern(
    substring_pattern="\\.connect\\(",
    relative_path="src/lorairo/gui",
    restrict_search_to_code_files=True,
    paths_include_glob="**/*.py",
    context_lines_before=2,
    context_lines_after=2
)
```

---

### mcp__serena__find_referencing_symbols
指定したシンボルを参照している箇所を検索。

**パラメータ:**
- `name_path` (string, 必須): 対象シンボルの名前パス
- `relative_path` (string, 必須): シンボルが定義されているファイルパス
- `include_kinds` (array[integer], オプション): 含める参照元の種別
- `exclude_kinds` (array[integer], オプション): 除外する参照元の種別
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**戻り値:**
参照しているシンボルのリスト（ファイルパス、行番号、コードスニペット）

**使用例:**
```python
mcp__serena__find_referencing_symbols(
    name_path="DatasetStateManager/get_image_by_id",
    relative_path="src/lorairo/gui/state/dataset_state_manager.py"
)
```

---

## ディレクトリ操作ツール

### mcp__serena__list_dir
ディレクトリ内のファイルとサブディレクトリを一覧表示。

**パラメータ:**
- `relative_path` (string, 必須): 対象ディレクトリの相対パス（"." = プロジェクトルート）
- `recursive` (boolean, 必須): サブディレクトリを再帰的にスキャンするか
- `skip_ignored_files` (boolean, オプション): 無視ファイルをスキップ（デフォルト: False）
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**戻り値:**
ディレクトリとファイルの名前を含むJSONオブジェクト

**使用例:**
```python
# プロジェクトルートの構造を確認
mcp__serena__list_dir(
    relative_path=".",
    recursive=False
)

# src/lorairo/ 配下を再帰的に確認
mcp__serena__list_dir(
    relative_path="src/lorairo",
    recursive=True,
    skip_ignored_files=True
)
```

---

## メモリ操作ツール

### mcp__serena__list_memories
利用可能なメモリファイルの一覧を取得。

**パラメータ:** なし

**戻り値:**
メモリファイル名のリスト

**使用例:**
```python
mcp__serena__list_memories()
```

---

### mcp__serena__read_memory
指定したメモリファイルの内容を読み込む。

**パラメータ:**
- `memory_file_name` (string, 必須): メモリファイル名
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**戻り値:**
メモリファイルの内容（Markdown形式）

**使用例:**
```python
mcp__serena__read_memory(
    memory_file_name="current-project-status"
)
```

---

### mcp__serena__write_memory
メモリファイルに内容を書き込む（新規作成または更新）。

**パラメータ:**
- `memory_name` (string, 必須): メモリファイル名
- `content` (string, 必須): 書き込む内容（Markdown形式推奨）
- `max_answer_chars` (integer, オプション): 出力の最大文字数

**戻り値:**
成功/失敗の結果

**使用例:**
```python
mcp__serena__write_memory(
    memory_name="active-development-tasks",
    content='''
# 現在の開発タスク - 2025-10-20

## 進行中
- ThumbnailWidget リファクタリング

## 完了
✅ DatasetStateManager キャッシュ削除

## 次のステップ
1. 単体テスト作成
2. 統合テスト実行
'''
)
```

---

## コード編集ツール

### mcp__serena__replace_symbol_body
シンボル（関数、メソッド、クラス）の本体を置換。

**パラメータ:**
- `name_path` (string, 必須): 対象シンボルの名前パス
- `relative_path` (string, 必須): ファイルパス
- `body` (string, 必須): 新しいシンボル本体（シグネチャ行を含む）

**重要:** body にはdocstring、import、前後のコメントは含めない。シンボルの定義のみを含める。

**戻り値:**
成功/失敗の結果

**使用例:**
```python
mcp__serena__replace_symbol_body(
    name_path="ThumbnailWidget/handle_click",
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
    body='''
    def handle_click(self, event: QMouseEvent) -> None:
        """Handle mouse click events."""
        item = self.item_at(event.position().toPoint())
        if item:
            self.select_item(item)
'''
)
```

---

### mcp__serena__insert_after_symbol
指定したシンボルの後にコードを挿入。

**パラメータ:**
- `name_path` (string, 必須): 基準シンボルの名前パス
- `relative_path` (string, 必須): ファイルパス
- `body` (string, 必須): 挿入するコード

**用途:** 新しいメソッド、関数、クラスの追加

**戻り値:**
成功/失敗の結果

**使用例:**
```python
mcp__serena__insert_after_symbol(
    name_path="ThumbnailWidget/handle_click",
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
    body='''
    def clear_selection(self) -> None:
        """Clear the current selection."""
        self.selected_item = None
        self.update()
'''
)
```

---

### mcp__serena__insert_before_symbol
指定したシンボルの前にコードを挿入。

**パラメータ:**
- `name_path` (string, 必須): 基準シンボルの名前パス
- `relative_path` (string, 必須): ファイルパス
- `body` (string, 必須): 挿入するコード

**用途:** import文の追加、前置き的なコードの挿入

**戻り値:**
成功/失敗の結果

**使用例:**
```python
# ファイル先頭（最初のシンボルの前）にimport追加
mcp__serena__insert_before_symbol(
    name_path="ThumbnailWidget",
    relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
    body='''
from PySide6.QtGui import QMouseEvent

'''
)
```

---

## パフォーマンス特性

### 実行時間の目安
- **get_symbols_overview**: 0.5-1秒
- **find_symbol**: 1-2秒
- **search_for_pattern**: 1-3秒（検索範囲による）
- **list_dir**: 0.5-1秒
- **read_memory**: 0.3-0.5秒
- **write_memory**: 0.3-0.5秒
- **replace_symbol_body**: 1-2秒
- **insert_after_symbol**: 1-2秒
- **insert_before_symbol**: 1-2秒
- **find_referencing_symbols**: 2-3秒

### 最適化のヒント
1. **Progressive Disclosure**: 概要から詳細へ段階的に取得
2. **Scope Narrowing**: `relative_path` で検索範囲を絞る
3. **Selective Loading**: `include_body=False` で必要な時だけコード本体を取得
4. **Memory Caching**: 頻繁に参照する情報はメモリに記録

---

## エラーハンドリング

### 一般的なエラー
- **FileNotFoundError**: 指定されたファイル/ディレクトリが存在しない
- **SymbolNotFoundError**: 指定されたシンボルが見つからない
- **OutputTooLargeError**: 出力が `max_answer_chars` を超過

### エラー対応
1. **ファイルパス確認**: 相対パスが正しいか確認
2. **シンボル名確認**: `get_symbols_overview` で実際のシンボル名を確認
3. **範囲縮小**: `max_answer_chars` を増やすか、検索範囲を絞る

---

## LoRAIro固有のベストプラクティス

### Memory命名規則
- **current-project-status**: プロジェクト全体状況
- **active-development-tasks**: 現在の開発タスク
- **{feature}_implementation_{YYYY_MM}**: 具体的実装記録
- **archived_{name}**: 完了タスクのアーカイブ

### シンボル検索パターン
- **Repository**: `{RepositoryName}/{method_name}`
- **Service**: `{ServiceName}/{method_name}`
- **Widget**: `{WidgetName}/{method_name}`
- **Test**: `Test{ClassName}/{test_method_name}`

### コード編集ガイドライン
1. **型ヒント必須**: 全ての関数/メソッドに型ヒント
2. **docstring必須**: 全てのpublic関数/メソッドにdocstring
3. **Ruff準拠**: 行長108文字、modern Python types使用
