# Plan: vivid-swinging-reddy

**Created**: 2025-12-31 13:15:34
**Source**: plan_mode
**Original File**: vivid-swinging-reddy.md
**Status**: planning

---

# TagManagementWidget Implementation Plan

## 実装対象
LoRAIro unknown type tag management UI (Phase 3)

## 設計決定: ErrorLogViewerDialog Pattern のみ

### 選択理由
**ハイブリッドパターンは過剰 - シンプルな ErrorLogViewerDialog パターンで十分**

**複雑度の比較**:
- ❌ Hybrid Pattern: 1,250-1,670 lines (過剰設計)
- ✅ ErrorLogViewerDialog Pattern: ~500-600 lines (適切)

**ErrorLogViewerDialog で十分な理由**:
1. **unknown type タグは少数**: 通常10-50個程度、ページネーション不要
2. **更新は単一API呼び出し**: `update_tags_type_batch()` 1回で完結
3. **進捗表示は最小限**: Worker infrastructure 不要、QThread で十分
4. **既存パターンと一貫性**: ErrorLogViewerDialog と同じ構造

**採用するパターン**:
- Dialog/Widget 2層構造（再利用性）
- Singleton パターン（`WA_DeleteOnClose = False`）
- ServiceContainer DI（TagManagementService 注入）
- 最小限の QThread（update_tags_type_batch 呼び出しのみ）

## アーキテクチャ設計

### Layer 1: TagManagementDialog (~80 lines)
**ErrorLogViewerDialog と同一パターン**

```python
class TagManagementDialog(QDialog):
    """unknown type タグ管理ダイアログ（Singleton）"""

    def __init__(self, tag_service: TagManagementService, parent=None):
        super().__init__(parent)

        # ErrorLogViewerDialog パターン準拠
        self.setWindowTitle("タグタイプ管理")
        self.resize(820, 620)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # Singleton

        # Widget 埋め込み
        self.tag_widget = TagManagementWidget(parent=self)
        self.tag_widget.set_tag_service(tag_service)

        # Layout + ボタン（再読み込み、閉じる）
        # Signal forwarding
```

**責務**:
- Singleton ライフサイクル管理
- Widget のラッピング
- ボタン配置（再読み込み、閉じる）

### Layer 2: TagManagementWidget (~200-250 lines)
**ErrorLogViewerWidget を簡略化したパターン**

```python
class TagManagementWidget(QWidget, Ui_TagManagementWidget):
    """unknown type タグ管理 Widget"""

    update_completed = Signal()
    update_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.tag_service: TagManagementService | None = None
        self.unknown_tags: list[TagRecordPublic] = []
        self.available_types: list[str] = []

        self._setup_table()
        self._connect_signals()

    def set_tag_service(self, service: TagManagementService):
        """依存注入"""
        self.tag_service = service

    def load_unknown_tags(self):
        """unknown type タグを読み込み"""
        # ErrorLogViewerWidget.load_error_records() と同様
        self.unknown_tags = self.tag_service.get_unknown_tags()
        self.available_types = self.tag_service.get_all_available_types()
        self._update_table_display()

    def _on_update_clicked(self):
        """一括更新実行 - 最小限の QThread 使用"""
        updates = self._collect_selected_updates()

        # QThread でシンプルに実行（Worker class 不要）
        def run_update():
            try:
                self.tag_service.update_tag_types(updates)
                self.update_completed.emit()
            except Exception as e:
                self.update_failed.emit(str(e))

        thread = threading.Thread(target=run_update, daemon=True)
        thread.start()
```

**UI Components** (Qt Designer):
- `QTableWidget` - unknown type タグ一覧（5列）
  - Column 0: QCheckBox (選択)
  - Column 1: tag (表示名)
  - Column 2: source_tag (元タグ)
  - Column 3: current type_name (現在の型: "unknown")
  - Column 4: QComboBox (新しい型選択)
- `QPushButton` - 更新実行
- `QLabel` - ステータス表示

**特徴**:
- ❌ ページネーション不要（タグ数少数）
- ❌ Worker class 不要（シンプルな QThread で十分）
- ✅ ErrorLogViewerWidget の構造を踏襲
- ✅ TagManagementService 経由で API 呼び出し

## 実装フェーズ（簡略化）

### Phase 1: Widget 実装 (2-3 hours)
1. Qt Designer で UI 作成 (`tag_management_widget.ui`)
   - QTableWidget (5列: Select, Tag, Source, Current Type, New Type)
   - QPushButton (更新実行)
   - QLabel (ステータス表示)
2. `TagManagementWidget` 実装
   - ErrorLogViewerWidget パターン準拠
   - QComboBox for type selection
   - QThread でシンプルな更新処理
3. Widget 単体テスト

**成果物**:
- `src/lorairo/gui/designer/tag_management_widget.ui` (~100 lines)
- `src/lorairo/gui/widgets/tag_management_widget.py` (~200-250 lines)
- `tests/unit/gui/widgets/test_tag_management_widget.py` (~100 lines)

### Phase 2: Dialog 実装 (1 hour)
1. `TagManagementDialog` 実装
   - ErrorLogViewerDialog と同一パターン
   - Widget ラッピング + ボタン配置
2. Dialog テスト

**成果物**:
- `src/lorairo/gui/widgets/tag_management_dialog.py` (~80 lines)
- `tests/unit/gui/widgets/test_tag_management_dialog.py` (~80 lines)

### Phase 3: MainWindow 統合 (1 hour)
1. ServiceContainer 統合
   - `get_tag_management_service()` 追加
2. MainWindow 統合
   - Menu item 追加 (Tools > Tag Management)
   - Lazy initialization
3. 統合テスト

**成果物**:
- `src/lorairo/services/service_container.py` (+5 lines)
- `src/lorairo/gui/window/main_window.py` (+20 lines)
- `tests/integration/test_tag_management_integration.py` (~100 lines)

## 見積もり合計（簡略化後）

### コード量
- Production code: ~400 lines
  - TagManagementWidget: ~200-250 lines
  - TagManagementDialog: ~80 lines
  - ServiceContainer/MainWindow: ~25 lines
  - Qt Designer UI: ~100 lines
- Test code: ~280 lines
  - Widget tests: ~100 lines
  - Dialog tests: ~80 lines
  - Integration tests: ~100 lines
- **Total**: ~680 lines（従来見積もり 1,250-1,670 lines の約半分）

### 工数
- Phase 1: 2-3 hours (Widget 実装)
- Phase 2: 1 hour (Dialog 実装)
- Phase 3: 1 hour (MainWindow 統合)
- **Total**: 4-5 hours（従来見積もり 8-12 hours の約半分）

## リスク分析（簡略化後）

### リスク 1: QComboBox for type selection 実装
**影響**: Low
**対策**: ErrorLogViewerWidget の QTableWidget パターン参考、シンプルな QComboBox 配置

### リスク 2: QThread でのエラーハンドリング
**影響**: Low
**対策**: try-except で Signal 発火、logging 強化

### リスク 3: 大量タグの UI パフォーマンス
**影響**: Very Low (unknown type は通常10-50個程度)
**対策**: 不要（少数のため）

## テスト戦略（簡略化）

### 単体テスト (pytest -m unit)
- `test_tag_management_service.py` ✅ (14/14 passing)
- `test_tag_management_widget.py` (~100 lines)
  - UI 初期化
  - load_unknown_tags() 動作
  - type selection ロジック
  - Signal 発火確認
- `test_tag_management_dialog.py` (~80 lines)
  - Singleton パターン
  - Widget ラッピング
  - ボタン接続

**目標カバレッジ**: 75%+

### 統合テスト (pytest -m integration)
- `test_tag_management_integration.py` (~100 lines)
  - ServiceContainer → TagManagementService 連携
  - genai-tag-db-tools API 呼び出し（get_unknown_tags, update_tags_type_batch）
  - データベース更新検証

**目標カバレッジ**: 75%+

## 依存関係

### 既存実装 (完了)
- ✅ TagManagementService (14/14 tests passing)
- ✅ genai-tag-db-tools Phase 2.5 APIs
- ✅ ServiceContainer infrastructure

### 新規追加必要
- Qt Designer UI file (~100 lines)
- Dialog/Widget classes (~280-330 lines)
- ServiceContainer/MainWindow integration (~25 lines)

## 配置・移行計画（簡略化）

### ファイル構成
```
src/lorairo/
├── gui/
│   ├── designer/
│   │   └── tag_management_widget.ui  # ~100 lines
│   └── widgets/
│       ├── tag_management_dialog.py  # ~80 lines
│       └── tag_management_widget.py  # ~200-250 lines
├── services/
│   ├── service_container.py  # +5 lines
│   └── tag_management_service.py  # ✅ Complete (~127 lines)
└── gui/window/
    └── main_window.py  # +20 lines

tests/
├── unit/
│   ├── gui/widgets/
│   │   ├── test_tag_management_dialog.py  # ~80 lines
│   │   └── test_tag_management_widget.py  # ~100 lines
│   └── services/
│       └── test_tag_management_service.py  # ✅ Complete (14/14 tests)
└── integration/
    └── test_tag_management_integration.py  # ~100 lines
```

**コード量合計**: ~680 lines (production: ~400, tests: ~280)

### 設定変更
不要（既存 ServiceContainer 利用）

### データ移行
不要（既存 genai-tag-db-tools database 利用）

## ロールバック計画
1. Git revert 可能（機能追加のみ、破壊的変更なし）
2. ServiceContainer への影響なし
3. Database schema 変更なし

## 次ステップ（簡略化後）

### Implementation Phase への引き継ぎ
1. **Phase 1**: Widget 実装（2-3 hours）
2. **Phase 2**: Dialog 実装（1 hour）
3. **Phase 3**: MainWindow 統合（1 hour）
4. **Total**: 4-5 hours

### 承認確認項目
- ✅ **ErrorLogViewerDialog Pattern のみ** 採用（ハイブリッドは過剰）
- ✅ **2層構造** (Dialog → Widget)、Worker class 不要
- ✅ **見積もり**: ~680 lines, 4-5 hours（従来の約半分）
- ✅ **テストカバレッジ**: 75%+ 目標
- ✅ **シンプルさ優先**: unknown type タグは少数、QThread で十分

## 参照
- `.serena/memories/genai_tag_db_tools_phase2_tag_registration_completion_2025_12_30.md` - Phase 2.5 完了記録
- `src/lorairo/gui/widgets/error_log_viewer_dialog.py` - Dialog/Widget パターン
- `src/lorairo/gui/widgets/dataset_export_widget.py` - Worker/Thread パターン
- `src/lorairo/services/tag_management_service.py` - Service 実装 ✅
- `tests/unit/services/test_tag_management_service.py` - Service テスト ✅
