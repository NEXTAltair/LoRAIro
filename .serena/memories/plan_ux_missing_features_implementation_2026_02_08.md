# Plan: ux_missing_features_implementation

**Created**: 2026-02-08 22:40:00
**Source**: manual_sync
**Original File**: n/a
**Status**: planning

---

## 背景
直近のUX監査で、以下6点の不足機能が確認された。
1. 設定画面が実質未提供（フォールバック表示のみ）
2. タグ追加フローの入力エラー/失敗時フィードバック不足
3. 選択解除時の詳細パネル・Rating/Scoreのクリア未実装
4. エラーログエクスポート未実装
5. 検索入力エラー（条件不足・日付不正）のユーザー通知不足
6. プレビュー表示サイズ異常（既知FIXME）

## 実装ゴール
- 主要操作（設定、検索、タグ付け、選択、エラーログ、プレビュー）で「無言失敗」をなくす。
- 既存アーキテクチャ（Controller/Service分離）を崩さずにUX欠落を補完する。
- GUI統合テスト/ユニットテストで回帰防止する。

## 優先順位（実装順）

### P0（即効UX改善）
- タグ追加フィードバック（Batch + Quick）
- 選択解除クリア実装
- 検索入力エラーフィードバック

### P1（主要機能の欠落補完）
- 設定画面（ConfigurationWindow）復旧
- エラーログエクスポート

### P2（視認性・操作品質）
- プレビューサイズ異常修正

---

## Phase 1: P0 UXフィードバック基盤（1-2日）

### 1-1. バッチタグ追加の入力エラー通知
**対象**:
- `src/lorairo/gui/widgets/batch_tag_add_widget.py`
- `src/lorairo/gui/window/main_window.py`

**実装**:
- `TODO: QMessageBox` 部分を具体実装
  - ステージング空: 警告
  - 空入力: 警告
  - 正規化失敗: 警告
- DB書き込み失敗時（MainWindow側）もユーザー通知（warning/critical）を追加

**受け入れ条件**:
- 不正入力時に必ずUI通知が出る
- ログのみで操作が終わるケースがなくなる

### 1-2. クイックタグ追加の失敗通知
**対象**:
- `src/lorairo/gui/widgets/quick_tag_dialog.py`
- `src/lorairo/gui/window/main_window.py`

**実装**:
- 空タグ、正規化失敗時にダイアログ内メッセージ表示
- `_handle_quick_tag_add` 失敗時にメッセージボックス通知

**受け入れ条件**:
- Quick Tagで無言失敗が発生しない

### 1-3. 選択解除時クリア処理
**対象**:
- `src/lorairo/gui/window/main_window.py`
- 必要に応じて `src/lorairo/gui/widgets/selected_image_details_widget.py`

**実装**:
- `_handle_selection_changed_for_rating` の `len(image_ids)==0` にクリア処理追加
- 既存クリアAPIがあればそれを利用（内部状態とUIを一貫リセット）

**受け入れ条件**:
- 画像未選択時、前回選択情報が残らない
- Rating/Score UIが初期状態へ戻る

### 1-4. 検索入力エラーフィードバック
**対象**:
- `src/lorairo/gui/widgets/filter_search_panel.py`

**実装**:
- 条件未指定で検索スキップ時にステータス表示（または非モーダル通知）
- 日付範囲無効時に明示通知
- 既存UI状態遷移（PipelineState）と矛盾しない形で実装

**受け入れ条件**:
- 「何も起きない」挙動を解消

---

## Phase 2: 設定画面復旧（P1, 1-2日）

### 2-1. 設定ウィンドウ本体実装
**対象**:
- 新規: `src/lorairo/gui/window/configuration_window.py`
- `src/lorairo/gui/controllers/settings_controller.py`
- `src/lorairo/gui/window/__init__.py`（必要時）

**実装**:
- `ConfigurationWindow.ui` を使った実ウィンドウクラス実装
- `ConfigurationService` 連携（読込/更新/保存）
- 保存成功/失敗メッセージ
- importパス整合（`..windows` vs `..window` 問題を解消）

**受け入れ条件**:
- `open_settings` から実画面が開く
- 設定の変更・保存がUI経由で完結する
- 「設定画面は開発中」フォールバックに依存しない

### 2-2. 回帰防止テスト
**対象**:
- 新規: `tests/unit/gui/controllers/test_settings_controller.py`
- 必要なら: `tests/integration/gui/test_configuration_window_integration.py`

**観点**:
- ダイアログ起動
- 保存成功/失敗時の通知
- ImportErrorフォールバック分岐（不要化または縮小）

---

## Phase 3: エラーログエクスポート（P1, 0.5-1日）

### 3-1. エクスポート機能実装
**対象**:
- `src/lorairo/gui/widgets/error_log_viewer_widget.py`
- 必要なら `src/lorairo/gui/widgets/error_log_viewer_dialog.py`

**実装**:
- `_on_export_log_clicked` を実装
- `QFileDialog` で保存先選択
- CSV（必須）+ JSON（任意）
- エクスポート成功/失敗通知

**受け入れ条件**:
- 選択中フィルタ条件に基づく一覧をファイル出力できる
- 未実装メッセージが消える

---

## Phase 4: プレビュー表示サイズ修正（P2, 0.5-1日）

### 4-1. fitInView/リサイズ挙動の安定化
**対象**:
- `src/lorairo/gui/widgets/image_preview.py`

**実装**:
- `QGraphicsView` のスケーリング処理を見直し
- `resizeEvent` と初回表示時の重複処理を整理
- 必要であれば `QTimer.singleShot` 依存を最小化

**受け入れ条件**:
- 初回表示で異常に小さくならない
- ウィンドウリサイズ後もアスペクト維持で適切表示

---

## テスト計画

### Unit/Widget tests
- `tests/unit/gui/widgets/test_batch_tag_add_widget.py`
- `tests/unit/gui/widgets/test_filter_search_panel.py`（新規または拡張）
- `tests/unit/gui/widgets/test_error_log_viewer_widget.py`
- `tests/unit/gui/widgets/test_image_preview_widget.py`

### Integration tests
- `tests/integration/gui/test_gui_component_interactions.py`
- `tests/integration/gui/test_filter_search_integration.py`
- 設定画面統合（新規）

### Manual smoke test
1. 設定画面を開き保存
2. Batch Tag/Quick Tagで不正入力確認
3. 選択→解除で詳細パネル確認
4. 検索条件不備時の通知確認
5. エラーログエクスポート
6. 画像プレビューの初回表示/リサイズ

---

## リスクと対策

- **Risk**: 設定画面の依存関係不足（Custom widget初期化）
  - **Mitigation**: 最小機能で起動確認→段階的に項目追加

- **Risk**: 既存UIテストの不安定化（Qt timing）
  - **Mitigation**: `qtbot.waitUntil` とシグナル待ちで安定化

- **Risk**: 既存Service責務との重複
  - **Mitigation**: Controllerは表示制御、永続化はServiceへ委譲を維持

---

## 完了条件（Definition of Done）
- 6つの不足機能が実装済みで、少なくとも主要分岐にテストがある
- 既存テストを壊さない（対象スイートがパス）
- ユーザー操作で「無反応/未実装」体験が残っていない

## 実装メモ（着手時の順序）
1. Phase 1（P0）を先行して即効改善
2. Phase 2設定画面で本命の欠落を埋める
3. Phase 3/4で品質仕上げ

## Implementation Notes
**Progress**:
- [ ] Phase 1: P0 UXフィードバック
- [ ] Phase 2: 設定画面復旧
- [ ] Phase 3: エラーログエクスポート
- [ ] Phase 4: プレビュー表示修正

**Deviations from Plan**:
- なし（初版）

**Challenges Encountered**:
- なし（計画策定段階）

## Outcome
（実装完了後に記入）

**Extract to OpenClaw LTM**:
- [ ] 重要設計判断をLTMへ抽出
- [ ] 再利用可能パターンを記録
- [ ] 学びを記録
