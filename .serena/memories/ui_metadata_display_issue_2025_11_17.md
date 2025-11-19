# UIメタデータ非表示問題の診断と修正計画

**作成日**: 2025-11-17
**最終更新**: 2025-11-18
**優先度**: 高
**ステータス**: Phase 1-2完了、Phase 3調査必要

---

## 📌 問題定義

### 症状
- 画像選択時にSelectedImageDetailsWidgetにメタデータが表示されない
- エラーは発生しない（silent failure）
- アプリケーションは正常起動

### 前提条件
**前タスク完了**: Repository層アノテーションデータ修正（コミット0a82966）
- `source`フィールド修正: `tag.existing` → `tag.is_edited_manually`
- N+1クエリ解決: eager loading追加
- データ型統一: `tags: list[dict[str, Any]]`
- テスト13件通過

**現タスク**: UI表示問題の修正（別問題として分離）

---

## 📊 Phase 1-2 完了サマリー

### ✅ 実装完了項目

#### 1. 接続経路の詳細ログ化（Phase 1）
**目的**: 接続処理の各ステップを可視化

**実施内容**:
- `src/lorairo/gui/widgets/selected_image_details_widget.py:229-250`
  - `connect_to_data_signals()`: 開始/完了/インスタンスID記録
  - 接続状況の詳細ログ追加

- `src/lorairo/gui/services/widget_setup_service.py:68-108`
  - `setup_selected_image_details()`: 全ステップのログ記録
  - 属性存在確認、インスタンス確認、DatasetStateManager確認

- `src/lorairo/gui/widgets/selected_image_details_widget.py:286-315`
  - `_on_image_data_received()`: 型統一（`dict[str, Any]` → `dict`）
  - ImagePreviewWidgetと完全に統一

**結果**:
```
2025-11-18 09:20:59.057 | INFO | 🔌 connect_to_data_signals() 呼び出し開始
2025-11-18 09:20:59.057 | INFO | 🔍 selectedImageDetailsWidget インスタンス確認: 2072386565568
2025-11-18 09:20:59.057 | INFO | ✅ current_image_data_changed シグナル接続完了
```

#### 2. テストで接続を保証（Phase 2 - ユーザー指摘事項2対応）
**目的**: リグレッション防止とシグナル接続の検証

**実施内容**:
- `tests/unit/gui/widgets/test_selected_image_details_widget_signal_connection.py`
  - 5つの単体テスト作成
  - シグナル接続確立テスト
  - シグナル受信テスト
  - 空データ処理テスト
  - 表示更新テスト
  - 複数シグナル発行テスト

**結果**: 全テスト成功（5/5 passed）
```
test_signal_connection_established PASSED
test_signal_reception PASSED
test_signal_reception_with_empty_data PASSED
test_display_update_after_signal PASSED
test_multiple_signal_emissions PASSED
```

#### 3. MainWindow初期化フロー確認（ユーザー指摘事項1対応）
**目的**: `setup_selected_image_details()` が確実に呼ばれることの確認

**確認内容**:
- `src/lorairo/gui/window/main_window.py:272-274`
  - `WidgetSetupService.setup_all_widgets()` の呼び出し確認
  - MainWindow初期化フローの検証

**結果**: 接続処理は正常実行されている（ログで確認）

---

## 🔍 診断結果

### 動作確認状況

| 環境 | シグナル発行 | シグナル受信 | 表示更新 | ステータス |
|------|------------|------------|---------|----------|
| 単体テスト | ✅ | ✅ | ✅ | 正常動作 |
| 直接テスト | ✅ | ✅ | ✅ | 正常動作 |
| MainWindow | ✅ | ❌ | ❌ | **問題あり** |
| ImagePreviewWidget | ✅ | ✅ | ✅ | 正常動作 |

### ログ分析結果

**✅ 正常動作している部分**:
1. DatasetStateManager: シグナル発行成功
   ```
   ✅ 画像選択成功: ID 3540 - current_image_data_changed シグナル発行
   ```

2. ImagePreviewWidget: シグナル受信成功
   ```
   📨 ImagePreviewWidget: current_image_data_changed シグナル受信 - データサイズ: 25
   ```

3. SelectedImageDetailsWidget: 接続処理成功
   ```
   🔌 DatasetStateManager 存在確認: 2072386307968
   ✅ current_image_data_changed シグナル接続完了
   ```

**❌ 問題がある部分**:
- SelectedImageDetailsWidget: MainWindow環境では `_on_image_data_received()` は呼ばれているものの、受信した `metadata` 内に `annotations` キーが存在せず、タグ・キャプションが空のまま `AnnotationDataDisplayWidget` に渡されている
  - ログ例: `📨 SelectedImageDetailsWidget ... current_image_data_changed シグナル受信 - image_id=2135`
  - 同一メタデータを受け取る ImagePreviewWidget ではプレビューが成功していることから、シグナル自体は届いている

---

## 🎯 根本原因の仮説（更新版）

### 削除した仮説
~~1. 型不一致~~: `@Slot(dict)` と `dict[str, Any]` はランタイムで同一
~~2. 接続経路の問題~~: ログで接続成功を確認済み
~~3. 初期化タイミング~~: DatasetStateManagerは正常に渡されている

### 現在の有力仮説

#### 仮説A: metadataに`annotations`が含まれていない（最有力）
**可能性**: DatasetStateManagerが保持するメタデータに`annotations`キーが存在せず、従来の`tags`/`caption`のフォールバックも無いため表示が空になっている

**根拠**:
- `_update_details_display()`が呼ばれているにもかかわらず、`annotation_data.tags`の長さが0でログに出ている
- 512pxサムネイルのみを取得した経路では`_format_annotations_for_metadata()`が実行されない可能性が高い
- ImagePreviewWidgetは`stored_image_path`のみを参照するので、`annotations`欠如の影響を受けない

**検証方法**:
- `_build_image_details_from_metadata()`で`metadata.keys()`/`annotations.keys()`をログ出力し、MainWindow環境で`annotations`が存在するか実測
- `DatasetStateManager._all_images`に格納されている辞書を一件ダンプして、`annotations`の有無を確認

**問題点（ユーザー指摘）**:
> ログだけで「接続成功」と断定しているのは危険です。

**検証方法**:
- `connect()`の戻り値を確認
- `receivers()`で実際の接続先を列挙
- 接続失敗時のエラーログ追加

#### 仮説B: DatasetStateManagerのキャッシュ経路が複数存在する
**可能性**: 検索経路では`update_from_search_results()`が呼ばれ`annotations`付きのメタデータを保持するが、別経路（重複検出後の既存メタデータ再利用や512px生成時の戻り値）では`annotations`未付与の辞書が入る

**根拠**:
- `register_original_image()`は`repository.get_image_metadata()`を直接返しており、こちらは`annotations`を含まない
- `DatasetStateManager.get_image_by_id()`は`_all_images`優先で返すため、古いフォーマットが混在するとUI側で空になる

**検証方法**:
- `DatasetStateManager._all_images`をログ出力し、`annotations`が無いエントリが存在するか確認
- `register_original_image`/`get_image_metadata`で`_format_annotations_for_metadata()`を呼んでいるか確認し、必要なら同様の変換を適用

#### 仮説C: 512pxサムネイル経由のメタデータに`annotations`が乗っていない
**可能性**: `ThumbnailWorker`が`DatasetStateManager.update_from_search_results()`に渡す`image_metadata`は`get_images_by_filter`の`resolution=512`経路を通るため、`_fetch_filtered_metadata`の`resolution != 0`分岐で`annotations`が加わらないまま保管されている

**根拠**:
- `metadata["annotations"]`が空になるのは512px経路のみ、という報告あり
- `_fetch_filtered_metadata`の`resolution != 0`ルートでは`proc_metadata.update(annotations_by_image_id...)`するものの、`selected_metadata = self._filter_by_resolution(...)`後に`annotations`が消えている可能性がある

**検証方法**:
- `proc_metadata`から`selected_metadata`を組み立てる際に`annotations`が維持されているかログで確認
- 必要なら`selected_metadata.update(annotations_by_image_id[image_id])`を挿入し、512px経路でも`annotations`を保持する

---

## 🛠️ 次の調査ステップ（Phase 3）

### 最優先: 受信した`metadata`の中身を可視化

#### ステップ1: metadata/annotationsのログ出力
**目的**: MainWindow環境で`annotations`が欠落しているかを実測

**実施内容**:
```python
# src/lorairo/gui\widgets\selected_image_details_widget.py
def _on_image_data_received(...):
    logger.debug(
        f"metadata keys: {list(image_data.keys())}, "
        f"annotations keys: {list(image_data.get('annotations', {}).keys()) if image_data.get('annotations') else 'None'}"
    )
```

#### ステップ2: DatasetStateManagerキャッシュの中身を確認
**実施内容**:
```python
# src/lorairo/gui/state/dataset_state.py
logger.debug(
    f"update_from_search_results: first item keys={list(search_results[0].keys()) if search_results else []}"
)
```

#### ステップ3: フォールバック実装
**目的**: `annotations`が無い場合でも従来の`tags`/`caption`を表示

**実施内容**:
```python
annotations = metadata.get("annotations") or {}
tags_list = annotations.get("tags")
if not tags_list:
    legacy_tags = metadata.get("tags", "")
    tags_list = [{"tag": t.strip()} for t in legacy_tags.split(",") if t.strip()]
caption_text = annotations.get("caption_text") or metadata.get("caption", "")
```

#### ステップ4: `_fetch_filtered_metadata`での512px経路を検証
**目的**: `resolution != 0`のときも`annotations`が付与されることを保証する

**実施内容**:
```python
selected_metadata = self._filter_by_resolution(metadata_list, resolution)
if selected_metadata and image_id in annotations_by_image_id:
    selected_metadata.update(annotations_by_id[image_id])
```

### 補足調査

#### ステップ5: ImagePreviewWidget との詳細比較
**実施内容**:
```bash
# 両Widgetの接続処理を並べて比較
diff -u \
  <(grep -A20 "connect_to_data_signals" src/lorairo/gui/widgets/image_preview.py) \
  <(grep -A20 "connect_to_data_signals" src/lorairo/gui/widgets/selected_image_details_widget.py)

# MainWindowでの初期化順序比較
grep -n "setup_image_preview\|setup_selected_image_details" \
  src/lorairo/gui/services/widget_setup_service.py
```

#### ステップ6: Qt Designer UIファイル検証
**実施内容**:
```bash
# MainWindow_ui.pyでのWidget生成方法確認
grep -B5 -A15 "selectedImageDetailsWidget\|imagePreviewWidget" \
  src/lorairo/gui/designer/MainWindow_ui.py
```

---

## 📝 修正ファイル一覧

### Phase 1-2で修正済み
1. `src/lorairo/gui/widgets/selected_image_details_widget.py`
   - L229-250: `connect_to_data_signals()` 詳細ログ追加
   - L286-315: `_on_image_data_received()` 型統一・ログ向上

2. `src/lorairo/gui/services/widget_setup_service.py`
   - L68-108: `setup_selected_image_details()` 詳細ログ追加

3. `tests/unit/gui/widgets/test_selected_image_details_widget_signal_connection.py`
   - 新規作成: 5つのシグナル接続テスト

4. `test_signal_connection.py`
   - 一時ファイル: 直接動作確認用スクリプト

### Phase 3で修正可能性
- `src/lorairo/gui/window/main_window.py` - 初期化順序
- `src/lorairo/gui/designer/MainWindow_ui.py` - UI生成方法
- `src/lorairo/gui/widgets/selected_image_details_widget.py` - 接続方法

---

## ✅ 完了基準

Phase 1-2完了基準（達成済み）:
- [x] 接続経路の詳細ログ追加
- [x] テストで接続を保証（5テスト成功）
- [x] MainWindow初期化フロー確認

Phase 3-4完了基準（未達成）:
- [ ] 根本原因の特定
- [ ] MainWindow環境でシグナル受信成功
- [ ] 画像選択時にメタデータが正しく表示される
- [ ] タグテーブルに5列データが表示される
- [ ] キャプション、スコアも正常表示される

---

## 🔗 関連情報

### 関連メモリー
- `selected_image_details_widget_plan_2025_11_17.md` - 前タスク完了記録
- `mainwindow_initialization_issue_2025_11_17.md` - 別問題（初期化順序）

### 関連コミット
- `0a82966` - Repository層アノテーションデータ修正（前タスク完了）

### 参照コード
- `src/lorairo/gui/widgets/image_preview.py:124-181` - ImagePreviewWidget（正常動作例）
- `src/lorairo/gui/state/dataset_state.py:31` - `current_image_data_changed`シグナル定義
- `src/lorairo/gui/services/widget_setup_service.py:68-108` - SelectedImageDetailsWidget接続処理

---

**次アクション**: Phase 3調査（Qt Designer UIファイル検証、差異分析、接続状態確認）
**推定残り時間**: 2-3時間
