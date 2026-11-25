# シナリオ: PySide6 による基本ウィジェット作成

## 入力

**ユーザー依頼:** "Create a new FilterPanelWidget for the image browser. It should have filter controls (dropdowns, checkboxes) and follow LoRAIro's widget patterns."

**前提条件:**
- LoRAIro は PySide6 (Qt for Python) を使用している。
- 準拠すべきウィジェットパターンは以下の通りである。
  - 型ヒントを備えた明確なクラス構造
  - `@Slot` デコレータを用いたシグナル/スロット定義
  - Direct Widget Communication (ウィジェット間通信にサービス層を挟まない設計)
  - 適切な初期化パターン
- 既存の実装例: `SearchFilterWidget`、`MetadataDisplayWidget`
- 配置場所: `src/lorairo/gui/widgets/`

## 期待される動作

1. スキル `lorairo-qt-widget` が自動的に呼び出される。
2. 以下の手順に沿ってウィジェット作成ワークフローを案内する。

   **フェーズ 1: 既存ウィジェットの調査**
   - `Grep` を使用して既存ウィジェット (例: `SearchFilterWidget`) を調べる。
   - `__init__`、シグナル、スロット、レイアウトの構造を分析する。
   - メモリを参照し、ウィジェットパターンを確認する。

   **フェーズ 2: ウィジェットの実装**
   - `QWidget` を継承した `FilterPanelWidget` クラスを作成する。
   - フィルタ変更を通知するシグナルを定義する。
   - 型ヒントを付けて `__init__` を実装する。
   - ドロップダウンやチェックボックスを含む UI レイアウトを構築する。
   - `@Slot` デコレータを付与したメソッドを追加する。
   - Direct Widget Communication パターンに従う。

   **フェーズ 3: 統合ガイド**
   - 親ウィジェットがシグナルへ接続する方法を示す。
   - 型安全なシグナル/スロット接続を例示する。
   - 該当する場合は Qt Designer との統合方法にも言及する。

3. 以下の成果物を生成する。
   - 完全なウィジェット実装
   - 型安全なシグナルとスロット
   - LoRAIro のウィジェットパターンに沿った構成
   - 明確な docstring (Google スタイル)
   - Direct Widget Communication パターン

4. 以下を行わない。
   - ウィジェット間通信にサービス層を使用する。
   - 型ヒントを省略する。
   - `@Slot` デコレータを付け忘れる。
   - 型安全でない汎用的な `QObject.connect()` を使用する。

## 成功基準

- [x] 正しいスキル (`lorairo-qt-widget`) が呼び出された
- [x] 実装前に既存ウィジェットを調査した
- [x] ウィジェット構造が LoRAIro のパターンに準拠している
- [x] シグナルが適切な型で定義されている
- [x] `@Slot` デコレータが付与されている
- [x] 全体に型ヒントが付与されている
- [x] Direct Widget Communication パターンが使用されている
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なウィジェット構造を作成できる。シグナル/スロットの型指定には補足指示が必要な場合がある。
- **Sonnet:** すべてのパターンに従った完全なウィジェットを作成できる。型安全性と構造の品質が高い。
- **Opus:** UI/UX の改善提案やレイアウト最適化を行う場合がある。パターン準拠度とドキュメント品質が極めて高い。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-qt-widget` が含まれていることを確認する。
2. 調査フェーズの確認:
   - `find_symbol` を使用して既存ウィジェットを調べている。
   - 実装前に構造を分析している。
3. ウィジェット構造の確認:
   ```python
   from PySide6.QtWidgets import QWidget
   from PySide6.QtCore import Signal, Slot

   class FilterPanelWidget(QWidget):
       # Type-safe signals
       filter_changed = Signal(dict)  # or more specific type

       def __init__(self, parent: QWidget | None = None):
           super().__init__(parent)
           self._setup_ui()

       def _setup_ui(self) -> None:
           # Layout creation
           ...

       @Slot()
       def _on_filter_change(self) -> None:
           # Slot implementation
           ...
   ```
4. パターン準拠の確認:
   - `QWidget` を継承している。
   - シグナルがクラスレベルで定義されている。
   - スロットメソッドに `@Slot` デコレータが付与されている。
   - すべてのメソッドに型ヒントが付与されている。
   - プライベートメソッドにプレフィックス `_` が付いている。
5. Direct Widget Communication の確認:
   - ウィジェット間通信にサービス層を使用していない。
   - 親ウィジェットがシグナルへ直接接続している。
   - 型安全な接続について言及している。
6. ドキュメントの確認:
   - Google スタイルの docstring が記述されている。
   - シグナルのドキュメント (送出するデータの内容) がある。
   - メソッド引数の説明がある。
