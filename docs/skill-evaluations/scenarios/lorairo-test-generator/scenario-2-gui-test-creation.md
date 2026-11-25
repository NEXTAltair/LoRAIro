# シナリオ: pytest-qt による GUI テスト作成

## 入力

**ユーザー依頼:** "Create GUI tests for the FilterPanelWidget. Test signal emissions, user interactions, and widget state. Use pytest-qt for headless execution."

**前提条件:**
- LoRAIro の GUI テスト要件は以下の通りである。
  - pytest-qt フレームワーク
  - ヘッドレス実行 (`QT_QPA_PLATFORM=offscreen`)
  - AAA パターン
  - シグナル/スロットのテスト
  - ユーザー操作シミュレーション (クリック、入力)
- 対象ウィジェット: `src/lorairo/gui/widgets/filter_panel_widget.py` の `FilterPanelWidget`
- テスト配置場所: `tests/integration/gui/widgets/`
- pytest マーカー: `@pytest.mark.gui`

## 期待される動作

1. スキル `lorairo-test-generator` が自動的に呼び出される。
2. 以下の手順に沿って GUI テスト作成を案内する。

   **フェーズ 1: パターン調査**
   - 既存の GUI テストを調べる。
   - メモリから pytest-qt のパターンを確認する。
   - `FilterPanelWidget` のシグナルとメソッドを確認する。

   **フェーズ 2: フィクスチャの作成**
   - `qtbot` フィクスチャ (pytest-qt 提供) を利用する。
   - ウィジェットインスタンス用のフィクスチャを作成する。

   **フェーズ 3: テスト実装**
   - シグナル送出のテスト:
     ```python
     @pytest.mark.gui
     def test_filter_changed_signal_emitted(filter_panel_widget, qtbot):
         # Arrange
         with qtbot.waitSignal(filter_panel_widget.filter_changed, timeout=1000):
             # Act
             filter_panel_widget.tag_combo.setCurrentText("landscape")

         # Assert (signal was emitted, verified by waitSignal)
     ```

   - ユーザー操作のテスト:
     ```python
     @pytest.mark.gui
     def test_apply_button_click(filter_panel_widget, qtbot):
         # Arrange
         filter_panel_widget.tag_combo.setCurrentText("portrait")
         signals = []
         filter_panel_widget.filter_changed.connect(lambda: signals.append(True))

         # Act
         qtbot.mouseClick(filter_panel_widget.apply_button, Qt.MouseButton.LeftButton)

         # Assert
         assert len(signals) == 1
     ```

   - ウィジェット状態のテスト:
     ```python
     @pytest.mark.gui
     def test_reset_button_clears_filters(filter_panel_widget, qtbot):
         # Arrange
         filter_panel_widget.tag_combo.setCurrentText("nature")

         # Act
         qtbot.mouseClick(filter_panel_widget.reset_button, Qt.MouseButton.LeftButton)

         # Assert
         assert filter_panel_widget.tag_combo.currentText() == ""
     ```

   **フェーズ 4: ヘッドレス実行**
   - `QT_QPA_PLATFORM=offscreen` に言及する。
   - `uv run pytest -m gui` での実行を提案する。

3. 以下の成果物を生成する。
   - 完全な GUI テストスイート
   - pytest-qt (`qtbot`) の適切な使用
   - シグナル/スロットのテスト
   - ユーザー操作のシミュレーション
   - ウィジェット状態の検証
   - ヘッドレス環境での実行互換性

4. 以下を行わない。
   - GUI ディスプレイを必須とする (ヘッドレスで実行できなければならない)。
   - シグナルのテストを省略する。
   - `qtbot` フィクスチャを使い忘れる。
   - ユニットテストと GUI テストを混在させる。

## 成功基準

- [x] 正しいスキル (`lorairo-test-generator`) が呼び出された
- [x] パターン調査 (既存 GUI テストの確認) を行った
- [x] `qtbot` フィクスチャが正しく使用されている
- [x] シグナルがテストされている (`waitSignal` または手動接続)
- [x] ユーザー操作がシミュレートされている (`mouseClick`、`keyPress`)
- [x] ウィジェット状態が検証されている
- [x] `@pytest.mark.gui` マーカーが付与されている
- [x] ヘッドレス環境でテストが正常に実行できる
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的な GUI テストを作成できる。pytest-qt の API やシグナルテストには補足指示が必要な場合がある。
- **Sonnet:** 包括的な GUI テストスイートを作成できる。`qtbot` の使い方と操作シミュレーションの品質が高い。
- **Opus:** 非同期シグナルテストや複雑な操作パターンを提案する場合がある。状態検証の戦略にも優れる。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-test-generator` が含まれていることを確認する。
2. pytest-qt の使用確認:
   - すべてのテストで `qtbot` フィクスチャを使用している。
   - シグナル検証に `qtbot.waitSignal()` を使用している。
   - 操作シミュレーションに `qtbot.mouseClick()` / `qtbot.keyPress()` を使用している。
3. シグナルテストの確認:
   - `waitSignal` または手動接続でシグナルをテストしている。
   - タイムアウト (例: 1000ms) を指定している。
   - 該当する場合はシグナルのデータ内容も検証している。
4. ユーザー操作テストの確認:
   - ボタンクリックをシミュレートしている。
   - 入力フィールドの変更をテストしている。
   - コンボボックスの選択をテストしている。
5. ウィジェット状態の確認:
   - 初期状態を確認している。
   - 操作後の状態を検証している。
   - リセット/クリア機能をテストしている。
6. pytest マーカーの確認:
   - すべての GUI テストに `@pytest.mark.gui` が付与されている。
7. ヘッドレスでのテスト実行:
   ```bash
   QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/gui/widgets/test_filter_panel_widget.py -m gui
   ```
8. 実行結果の確認:
   - ディスプレイなしでテストが実行できる。
   - すべてのテストがパスする。
   - GUI ウィンドウが開かない。

## 検証すべきエッジケース

- シグナルが複数回送出された場合 (デバウンス処理)
- ユーザーが素早く連続操作した場合 (ダブルクリック防止)
- ウィジェットが無効化されている状態 (操作が無視されること)
- 不正な入力値の処理 (バリデーション)
