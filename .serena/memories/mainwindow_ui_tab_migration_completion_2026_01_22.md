# MainWindow.ui タブレイアウト移行完了レポート

**計画作成**: 2026-01-22
**完了日**: 2026-01-22
**ステータス**: ✅ 完了

---

## 概要

MainWindow.ui にタブ構造を宣言的に定義し、プログラム的なレイアウト構築コードを削除するリファクタリング。

### 解決した問題
- TabReorganizationService (354行) がプログラム的にタブ構造を作成していた
- build_batch_tag_tab() が約115行のネストしたレイアウト構築コード
- MainWindow初期化に「Phase 2.5」という追加フェーズが必要だった
- Qt Designerでレイアウトを視覚的に確認できなかった

---

## 実装完了ステータス

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 0 | objectName確認・記録 | ✅ 完了 |
| Phase 1 | MainWindow.ui タブ構造追加 | ✅ 完了 |
| Phase 2 | TabReorganizationService 簡素化 | ✅ 完了 |
| Phase 3 | main_window.py 修正 | ✅ 完了 |
| Phase 4 | テスト更新 | ✅ 完了 |
| Phase 5 | クリーンアップ・Memory作成 | ✅ 完了 |
| 追加 | プレースホルダー形式修正 | ✅ 完了 |
| 追加 | BatchTagAddWidget新規作成ロジック | ✅ 完了 |
| 追加 | スプリッター追加（リサイズ対応） | ✅ 完了 |

---

## 変更内容

### Phase 1: MainWindow.ui 修正
- `tabWidgetMainMode` をトップレベルタブとして追加
- `tabWorkspace` タブ: 既存4フレーム（frameDatasetSelector, frameDbStatus, splitterMainWorkArea, frameActionToolbar）を配置
- `tabBatchTag` タブ: 2カラムレイアウト（groupBoxStagingImages + groupBoxBatchOperations）を新設

### Phase 2: TabReorganizationService 簡素化
- **削減量**: 354行 → 117行（67%削減）
- **削除メソッド**:
  - `create_main_tab_widget()` - UIで定義済み
  - `extract_existing_widgets()` - ウィジェット移動不要
  - `build_workspace_tab()` - UIで定義済み
  - `build_batch_tag_tab()` - UIで定義済み
  - `reorganize_main_window_layout()` - 再構成不要
- **残存機能**:
  - `validate_tab_structure()` - タブ構造検証
  - `get_tab_widget_count()` - タブ数取得
  - `REQUIRED_WIDGETS` / `REQUIRED_PLACEHOLDERS` 定数

### Phase 3: main_window.py 修正
- `_create_main_tab_widget()` → `_setup_main_tab_connections()` に置換
- Phase 2.5 の概念を削除（タブはUIで定義済み）

### Phase 4: テスト更新
- 削除されたメソッドのテストを削除
- 新しい検証APIのテストを追加（10テスト全て成功）

### 追加修正1: プレースホルダー形式修正
| 修正前 | 修正後 |
|--------|--------|
| `labelBatchTagPlaceholder` (QLabel) | `batchTagWidgetPlaceholder` (QWidget) |
| `labelAnnotationPlaceholder` (QLabel) | `annotationDisplayPlaceholder` (QWidget) |

### 追加修正2: BatchTagAddWidget新規作成
- `widget_setup_service.py`を修正
- `batchTagAddWidget`が存在しない場合に新規作成するロジックを追加
- メソッドを3つのヘルパーに分割して複雑度を削減

### 追加修正3: スプリッター追加
バッチタグタブにスプリッターを追加してリサイズ可能に:
- `splitterBatchTag` (水平): 左カラム / 右カラム (60:40)
- `splitterBatchTagOperations` (垂直): タグ追加 / 表示 / アノテーション (3:4:3)

---

## 最終UI構造

```
tabWidgetMainMode (トップレベルタブ)
├── tabWorkspace (ワークスペース)
│   ├── frameDatasetSelector
│   ├── frameDbStatus
│   ├── splitterMainWorkArea
│   └── frameActionToolbar
└── tabBatchTag (バッチタグ)
    └── splitterBatchTag (水平)
        ├── groupBoxStagingImages (ステージング画像)
        └── groupBoxBatchOperations (操作パネル)
            └── splitterBatchTagOperations (垂直)
                ├── BatchTagAddWidget
                ├── AnnotationDataDisplayWidget
                └── groupBoxAnnotation
                    ├── AnnotationFilterWidget
                    ├── ModelSelectionWidget
                    └── btnAnnotationExecute
```

---

## 効果

| 項目 | 変更前 | 変更後 | 削減 |
|------|--------|--------|------|
| TabReorganizationService | 354行 | 117行 | 67% |
| プログラム的レイアウト構築 | 必要 | 不要 | 100% |
| Phase 2.5 初期化段階 | あり | なし | 削除 |

### その他の効果
- Qt Designerでタブ構造をビジュアル編集可能
- MainWindow初期化が5段階 → 4段階に簡素化
- バッチタグタブのウィジェットがリサイズ可能

---

## 関連ファイル

| ファイル | 変更内容 |
|---------|---------|
| [MainWindow.ui](src/lorairo/gui/designer/MainWindow.ui) | タブ構造・スプリッター追加 |
| [tab_reorganization_service.py](src/lorairo/gui/services/tab_reorganization_service.py) | 354行 → 117行 |
| [main_window.py](src/lorairo/gui/window/main_window.py) | Phase 2.5 削除 |
| [widget_setup_service.py](src/lorairo/gui/services/widget_setup_service.py) | BatchTagAddWidget作成・スプリッター初期化 |
| [test_tab_reorganization_service.py](tests/unit/gui/services/test_tab_reorganization_service.py) | テスト更新 |

---

## 検証方法

```bash
# UI生成
make gene-ui

# テスト実行
uv run pytest tests/unit/gui/services/test_tab_reorganization_service.py -v

# アプリケーション起動
uv run lorairo
```

---

## 修正内容サマリー（2026-01-23）

| 指摘事項 | 対応 |
|---------|------|
| tabWidgetMainMode currentIndex=1 | currentIndex=0 に変更（ワークスペースが初期表示） |
| ログ「2 tabs: 画像詳細, バッチタグ追加」 | 「1 tab: 画像詳細」に修正 |
| btnAnnotationExecute 未接続 | start_annotation() スロットに接続追加 |
| _hide_annotation_control_in_workspace() | メソッド削除（不要なコード） |

**変更ファイル:**
- [MainWindow.ui](src/lorairo/gui/designer/MainWindow.ui): currentIndex 修正、btnAnnotationExecute 接続追加
- [main_window.py](src/lorairo/gui/window/main_window.py): ログメッセージ修正、_hide_annotation_control_in_workspace() 削除
