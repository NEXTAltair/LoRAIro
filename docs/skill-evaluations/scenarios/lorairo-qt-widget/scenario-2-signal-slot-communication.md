# シナリオ: ウィジェット間のシグナル/スロット通信

## 入力

**ユーザー依頼:** "I have an ImageListWidget and a MetadataDisplayWidget. When a user selects an image in the list, the metadata widget should update. Show me the correct signal/slot pattern."

**前提条件:**
- 通信が必要な 2 つのウィジェットがある。
  - `ImageListWidget` (送信側): 画像選択シグナルを送出する。
  - `MetadataDisplayWidget` (受信側): 表示内容を更新する。
- 親ウィジェット (`MainWindow`) が両者の通信を調整する。
- LoRAIro 標準の Direct Widget Communication パターンを使用する。
- 型安全なシグナル/スロット接続が必要である。

## 期待される動作

1. スキル `lorairo-qt-widget` が自動的に呼び出される。
2. 以下の手順に沿ってシグナル/スロットパターンを提示する。

   **フェーズ 1: パターン調査**
   - 既存のウィジェット間通信の実装例を確認する。
   - メモリからシグナル/スロットパターンを検索する。
   - Direct Widget Communication の原則を確認する。

   **フェーズ 2: 実装**
   - `ImageListWidget` のシグナル定義を示す。
     ```python
     class ImageListWidget(QWidget):
         image_selected = Signal(int)  # Emits image_id

         def _on_item_clicked(self, item: QListWidgetItem) -> None:
             image_id = item.data(Qt.ItemDataRole.UserRole)
             self.image_selected.emit(image_id)
     ```

   - `MetadataDisplayWidget` のスロットを示す。
     ```python
     class MetadataDisplayWidget(QWidget):
         @Slot(int)
         def update_metadata(self, image_id: int) -> None:
             # Fetch and display metadata
             ...
     ```

   - `MainWindow` での接続を示す。
     ```python
     class MainWindow(QMainWindow):
         def _setup_connections(self) -> None:
             self.image_list_widget.image_selected.connect(
                 self.metadata_widget.update_metadata
             )
     ```

   **フェーズ 3: ベストプラクティス**
   - 型安全性: シグナルとスロットの型を一致させる。
   - 疎結合: ウィジェット同士は互いを知らない構造にする。
   - 親による調整: `MainWindow` が接続を所有する。
   - エラー処理: スロットは無効な ID を適切に処理する。

3. 以下の成果物を生成する。
   - 完全なシグナル/スロットの実装例
   - 型安全な接続
   - Direct Widget Communication パターン
   - ベストプラクティスの解説

4. 以下を行わない。
   - ウィジェット間通信にサービス層を使用する。
   - ウィジェット同士が互いを参照する密結合を作る。
   - 型の一致確認を省略する。
   - スロット内のエラー処理を忘れる。

## 成功基準

- [x] 正しいスキル (`lorairo-qt-widget`) が呼び出された
- [x] パターン調査 (既存実装例やメモリ参照) を行った
- [x] シグナルとスロットの型が一致している
- [x] Direct Widget Communication パターンが使用されている
- [x] ウィジェット同士が疎結合であり、親が接続を調整している
- [x] 型ヒント付きの `@Slot` デコレータが使用されている
- [x] スロット内にエラー処理がある
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なシグナル/スロット接続を示せる。型の一致については補足指示が必要な場合がある。
- **Sonnet:** 型安全性を備えた完全なパターンを提示できる。疎結合の説明も的確である。
- **Opus:** シグナル連鎖やシグナル変換などの応用パターンを提案する場合がある。エラー処理戦略も深く解説できる。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-qt-widget` が含まれていることを確認する。
2. シグナル定義の確認:
   - クラスレベルで `image_selected = Signal(int)` として定義されている。
   - 送出するデータと型が一致している。
   - 適切なメソッド内で送出されている。
3. スロット定義の確認:
   - `@Slot(int)` デコレータが付与されている。
   - `def update_metadata(self, image_id: int)` のようにシグナルと一致する型ヒントがある。
   - 無効な ID を安全に処理している。
4. 接続の確認:
   - 親ウィジェット (`MainWindow`) 内で接続されている。
   - `image_selected.connect(update_metadata)` のように型安全に接続されている。
   - ウィジェット同士が直接参照し合っていない。
5. Direct Widget Communication の検証:
   - サービス層が介在していない。
   - 親ウィジェットが通信を調整している。
   - ウィジェットの疎結合が維持されている。
6. エラー処理の確認:
   - スロットが `None` や無効な `image_id` を処理できる。
   - エッジケースでクラッシュしない。

## 検証すべきエッジケース

- 画像リストが空の場合 (選択項目がない状態)
- 無効な `image_id` が送出された場合 (安全に処理できること)
- 同一シグナルに複数のウィジェットが接続されている場合
- ウィジェット破棄時の接続解除
