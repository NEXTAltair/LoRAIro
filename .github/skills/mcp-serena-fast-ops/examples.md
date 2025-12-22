# Serena Fast Operations - 使用例

## Example 1: 新しいファイルの調査

### シナリオ
`src/lorairo/gui/widgets/thumbnail_widget.py` の構造を理解したい。

### 手順
```
1. get_symbols_overview で概要取得:
   mcp__serena__get_symbols_overview(
     relative_path="src/lorairo/gui/widgets/thumbnail_widget.py"
   )

   結果: ThumbnailWidget クラスと __init__, handle_click などのメソッド一覧

2. 詳細が必要なシンボルを find_symbol で取得:
   mcp__serena__find_symbol(
     name_path="ThumbnailWidget/handle_click",
     relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
     include_body=True
   )

   結果: handle_click メソッドの完全なコード
```

## Example 2: 実装前のMemory確認

### シナリオ
新機能実装前に、現在のプロジェクト状況と過去の類似実装を確認したい。

### 手順
```
1. 利用可能なメモリ確認:
   mcp__serena__list_memories()

   結果: ["current-project-status", "active-development-tasks",
          "thumbnail_implementation_2025", ...]

2. プロジェクト状況を読み込み:
   mcp__serena__read_memory(
     memory_file_name="current-project-status"
   )

   結果: 現在のブランチ、最新の実装変更、次の優先事項などが分かる

3. 関連実装記録を読み込み:
   mcp__serena__read_memory(
     memory_file_name="thumbnail_implementation_2025"
   )

   結果: サムネイル関連の実装パターンとアーキテクチャ判断が分かる
```

## Example 3: シンボルの参照箇所確認

### シナリオ
`DatasetStateManager.get_image_by_id()` メソッドを削除する前に、どこで使われているか確認したい。

### 手順
```
1. 参照箇所を検索:
   mcp__serena__find_referencing_symbols(
     name_path="DatasetStateManager/get_image_by_id",
     relative_path="src/lorairo/gui/state/dataset_state_manager.py"
   )

   結果: このメソッドを呼び出している全ての場所（ファイル名、行番号、コードスニペット）

2. 各参照箇所を確認して削除の影響を評価
3. 必要に応じて代替実装を計画
```

## Example 4: パターン検索で似たコードを探す

### シナリオ
プロジェクト内で Signal/Slot 接続パターンを使っている箇所を探したい。

### 手順
```
mcp__serena__search_for_pattern(
  substring_pattern="\\.connect\\(",
  relative_path="src/lorairo/gui",
  restrict_search_to_code_files=True,
  paths_include_glob="**/*.py"
)

結果: src/lorairo/gui/ 配下で .connect( を使っている全ての箇所
```

## Example 5: シンボル単位でのコード実装

### シナリオ
`ThumbnailWidget` クラスに新しいメソッド `clear_selection()` を追加したい。

### 手順
```
1. 既存のクラス構造を確認:
   mcp__serena__find_symbol(
     name_path="ThumbnailWidget",
     relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
     depth=1,
     include_body=False
   )

   結果: ThumbnailWidget の全メソッド一覧

2. 最後のメソッドの後に新メソッドを挿入:
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

   結果: clear_selection メソッドが handle_click の後に追加される
```

## Example 6: 実装中の進捗記録

### シナリオ
複雑な実装の途中で、現在の状況と次のステップを記録したい。

### 手順
```
mcp__serena__write_memory(
  memory_name="active-development-tasks",
  content='''
# 現在の実装状況 - 2025-10-20

## 進行中タスク
- ThumbnailWidget の新しい選択ロジック実装

## 完了した作業
✅ clear_selection メソッド追加
✅ handle_click メソッドのリファクタリング

## 次のステップ
1. SelectedImageDetailsWidget との Signal/Slot 接続実装
2. 単体テスト作成
3. 統合テスト実行

## 技術的判断
- Direct Widget Communication パターンを採用
- DatasetStateManager 経由を避けて直接接続
  理由: レスポンス向上、コード簡素化
'''
)

結果: 次回実装時にこのメモリを読み込めば、すぐに続きから作業可能
```

## Example 7: メソッド本体の置換

### シナリオ
`handle_click()` メソッドの実装を大幅に変更したい。

### 手順
```
mcp__serena__replace_symbol_body(
  name_path="ThumbnailWidget/handle_click",
  relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
  body='''
    def handle_click(self, event: QMouseEvent) -> None:
        """Handle mouse click events with improved selection logic."""
        if not self.is_valid_click(event):
            return

        item = self.item_at(event.position().toPoint())
        if item:
            self.select_item(item)
            self.image_selected.emit(item.image_path)
        else:
            self.clear_selection()
'''
)

結果: handle_click メソッド全体が新しい実装に置き換わる
```

## Example 8: import文の追加

### シナリオ
ファイルの先頭に新しいimport文を追加したい。

### 手順
```
1. ファイルの最初のシンボルを確認:
   mcp__serena__get_symbols_overview(
     relative_path="src/lorairo/gui/widgets/thumbnail_widget.py"
   )

   結果: 最初のシンボル（通常はクラス定義）が分かる

2. 最初のシンボルの前に import を挿入:
   mcp__serena__insert_before_symbol(
     name_path="ThumbnailWidget",
     relative_path="src/lorairo/gui/widgets/thumbnail_widget.py",
     body='''
from PySide6.QtGui import QMouseEvent

'''
   )

   結果: ThumbnailWidget クラス定義の前（通常はimportセクション）に追加
```

## ベストプラクティス

### 効率的なワークフロー
1. **概要 → 詳細**: 常に `get_symbols_overview` から始める
2. **段階的取得**: 一度に全てを読まず、必要な部分のみを段階的に取得
3. **Memory-First**: 実装前に必ず関連メモリを確認
4. **継続記録**: 実装中は定期的に `write_memory` で進捗記録

### パフォーマンス最適化
- **Serena優先**: 1-3秒で完了する高速操作を活用
- **Full read回避**: 可能な限りシンボル単位で取得
- **キャッシュ活用**: 一度取得した情報は覚えておく

### LoRAIro固有
- **Repository Pattern**: データベース操作は必ずリポジトリ経由
- **Direct Communication**: GUI間通信は直接Signal/Slot接続
- **Memory命名**: `{feature}_implementation_{date}` 形式で記録
