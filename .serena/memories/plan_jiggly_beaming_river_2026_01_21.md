# Plan: jiggly-beaming-river

**Created**: 2026-01-21 15:27:34
**Source**: plan_mode
**Original File**: jiggly-beaming-river.md
**Status**: planning

---

# アノテーションモデル選択レイアウト実装計画

## 概要

`scripts/mock_main_window.py` で決定されたアノテーションモデル選択レイアウトを本番実装する計画。

## 現状分析

### 実装済みコンポーネント
| コンポーネント | パス | 状態 |
|--------------|------|------|
| ModelSelectionWidget | `src/lorairo/gui/widgets/model_selection_widget.py` (334行) | 完成 |
| ModelCheckboxWidget | `src/lorairo/gui/widgets/model_checkbox_widget.py` (291行) | 完成 |
| ModelSelectionService | `src/lorairo/services/model_selection_service.py` (126行) | 完成 |
| ModelSelectionWidget.ui | `src/lorairo/gui/designer/ModelSelectionWidget.ui` | 完成 |

### 未実装コンポーネント (mock_main_window.py で設計済み)
1. **アノテーションフィルターウィジェット**
   - 機能タイプ: Caption生成、Tag生成、品質スコア
   - 実行環境: Web API、ローカルモデル
2. **バッチタグタブへのフィルター+モデル選択統合**

### 既存APIの確認
```python
# ModelSelectionWidget.apply_filters() - フィルター適用メソッド
def apply_filters(self, provider: str | None = None, capabilities: list[str] | None = None) -> None:
    self.current_provider_filter = provider
    self.current_capability_filters = capabilities or []
    self.update_model_display()
```

### 重要な制約
1. **mode="advanced" 必須**: `ModelSelectionWidget(mode="simple")` は推奨モデル固定で `apply_filters()` が無視される。フィルタ反映には `mode="advanced"` で生成が必要
2. **統合先**: 実際のウィジェット再配置は `WidgetSetupService.setup_batch_tag_tab_widgets()` が担当（tab_reorganization_service.py はレイアウト骨格のみ）
3. **capabilities マッピング**: DB の ModelType.name 値 ('caption', 'tag', 'score') と一致させる必要あり

## 推奨アプローチ

**アプローチ1: AnnotationFilterWidget 新規作成 (独立型)**

選択理由:
- 既存パターン (AnnotationStatusFilterWidget) に準拠
- SRP準拠 (フィルタリングUIとモデル選択UIを分離)
- テスト容易性 (各ウィジェットを独立テスト可能)
- 既存 ModelSelectionWidget への変更なし (低リスク)

## 実装計画

### Phase 1: AnnotationFilterWidget UI設計

**ファイル**: `src/lorairo/gui/designer/AnnotationFilterWidget.ui`

```
AnnotationFilterWidget (QWidget)
├── QVBoxLayout (mainLayout)
│   ├── QGroupBox "機能タイプ" (groupBoxFunctionType)
│   │   └── QHBoxLayout
│   │       ├── QCheckBox "Caption生成" (checkBoxCaption)
│   │       ├── QCheckBox "Tag生成" (checkBoxTags)
│   │       ├── QCheckBox "品質スコア" (checkBoxScore)
│   │       └── QSpacerItem (horizontal)
│   │
│   └── QGroupBox "実行環境選択" (groupBoxEnvironment)
│       └── QHBoxLayout
│           ├── QCheckBox "Web API" (checkBoxWebAPI)
│           ├── QCheckBox "ローカルモデル" (checkBoxLocal)
│           └── QSpacerItem (horizontal)
```

### Phase 2: AnnotationFilterWidget 実装

**ファイル**: `src/lorairo/gui/widgets/annotation_filter_widget.py`

```python
class AnnotationFilterWidget(QWidget, Ui_AnnotationFilterWidget):
    """アノテーションフィルターウィジェット"""

    # Signal: フィルター変更時に emit
    filter_changed = Signal(dict)  # {capabilities: list[str], environment: str | None}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self._connect_signals()

    def _connect_signals(self):
        # 各チェックボックスの stateChanged を接続
        self.checkBoxCaption.stateChanged.connect(self._on_filter_changed)
        self.checkBoxTags.stateChanged.connect(self._on_filter_changed)
        self.checkBoxScore.stateChanged.connect(self._on_filter_changed)
        self.checkBoxWebAPI.stateChanged.connect(self._on_filter_changed)
        self.checkBoxLocal.stateChanged.connect(self._on_filter_changed)

    def _on_filter_changed(self):
        self.filter_changed.emit(self.get_current_filters())

    def get_current_filters(self) -> dict:
        """現在のフィルター状態を取得"""
        # ModelType.name 値と一致させる ('caption', 'tag', 'score')
        capabilities = []
        if self.checkBoxCaption.isChecked():
            capabilities.append("caption")
        if self.checkBoxTags.isChecked():
            capabilities.append("tag")
        if self.checkBoxScore.isChecked():
            capabilities.append("score")

        environment = None
        web_api = self.checkBoxWebAPI.isChecked()
        local = self.checkBoxLocal.isChecked()
        if local and not web_api:
            environment = "local"
        elif web_api and not local:
            environment = "api"
        # 両方チェックまたは両方未チェック → None (フィルターなし)

        return {"capabilities": capabilities, "environment": environment}
```

### Phase 3: バッチタグタブへの統合

#### Step 3-1: レイアウト骨格追加
**修正ファイル**: `src/lorairo/gui/services/tab_reorganization_service.py`
- `build_batch_tag_tab()` にアノテーショングループのプレースホルダーを追加

```python
# right_layout に追加
annotation_group = QGroupBox("アノテーション")
annotation_group.setObjectName("groupBoxAnnotation")
annotation_layout = QVBoxLayout(annotation_group)
annotation_layout.addWidget(QLabel("対象: ステージング済み画像"))

# プレースホルダー
filter_placeholder = QWidget()
filter_placeholder.setObjectName("annotationFilterPlaceholder")
annotation_layout.addWidget(filter_placeholder)

model_placeholder = QWidget()
model_placeholder.setObjectName("modelSelectionPlaceholder")
annotation_layout.addWidget(model_placeholder)

btn_placeholder = QPushButton("アノテーション実行")
btn_placeholder.setObjectName("btnAnnotationExecute")
annotation_layout.addWidget(btn_placeholder)

right_layout.addWidget(annotation_group)
```

#### Step 3-2: ウィジェット統合
**修正ファイル**: `src/lorairo/gui/services/widget_setup_service.py`
- `setup_batch_tag_tab_widgets()` に AnnotationFilterWidget と ModelSelectionWidget の統合を追加

```python
# AnnotationFilterWidget 作成・配置
from ..widgets.annotation_filter_widget import AnnotationFilterWidget

filter_placeholder = right_column.findChild(object, "annotationFilterPlaceholder")
if filter_placeholder:
    right_column.layout().removeWidget(filter_placeholder)
    filter_placeholder.deleteLater()

annotation_filter = AnnotationFilterWidget()
annotation_filter.setObjectName("batchAnnotationFilter")
right_column.layout().addWidget(annotation_filter)
main_window.batchAnnotationFilter = annotation_filter

# ModelSelectionWidget 作成・配置 (mode="advanced" 必須)
from ..widgets.model_selection_widget import ModelSelectionWidget

model_placeholder = right_column.findChild(object, "modelSelectionPlaceholder")
if model_placeholder:
    right_column.layout().removeWidget(model_placeholder)
    model_placeholder.deleteLater()

model_selection = ModelSelectionWidget(mode="advanced")  # フィルタ有効化
model_selection.setObjectName("batchModelSelection")
right_column.layout().addWidget(model_selection)
main_window.batchModelSelection = model_selection

# Signal接続
annotation_filter.filter_changed.connect(
    lambda filters: model_selection.apply_filters(
        provider="local" if filters.get("environment") == "local" else None,
        capabilities=filters.get("capabilities", [])
    )
)
```

### Phase 4: テスト実装

**テストファイル**: `tests/unit/gui/widgets/test_annotation_filter_widget.py`

テスト項目:
1. 初期状態の確認 (全チェックボックスが未チェック)
2. チェックボックス操作で filter_changed シグナル発火
3. get_current_filters() の戻り値検証
4. 機能タイプフィルター (Caption/Tags/Score) のマッピング
5. 実行環境フィルター (WebAPI/Local) のマッピング

## 変更対象ファイル

### 新規作成
- `src/lorairo/gui/designer/AnnotationFilterWidget.ui`
- `src/lorairo/gui/widgets/annotation_filter_widget.py`
- `tests/unit/gui/widgets/test_annotation_filter_widget.py`

### 修正
- `src/lorairo/gui/services/tab_reorganization_service.py`
  - `build_batch_tag_tab()` にアノテーショングループのプレースホルダー追加
- `src/lorairo/gui/services/widget_setup_service.py`
  - `setup_batch_tag_tab_widgets()` に AnnotationFilterWidget/ModelSelectionWidget 統合追加

### UI生成
- `uv run python scripts/generate_ui.py` で AnnotationFilterWidget_ui.py 生成

## 検証手順

1. **UI生成確認**
   ```bash
   uv run python scripts/generate_ui.py
   ```
   - AnnotationFilterWidget_ui.py が生成されること

2. **単体テスト実行**
   ```bash
   uv run pytest tests/unit/gui/widgets/test_annotation_filter_widget.py -v
   ```

3. **モックウィンドウで動作確認**
   ```bash
   uv run python scripts/mock_main_window.py
   ```
   - バッチタグタブでフィルター操作
   - フィルター変更時にモデル一覧が更新されること

4. **統合テスト** (必要に応じて)
   ```bash
   uv run pytest tests/integration/gui/ -v -k annotation
   ```

## リスクと対策

| リスク | 対策 |
|-------|------|
| UI生成失敗 | .ui ファイルの XML 構造を既存ファイル参照で作成 |
| Signal接続エラー | 単体テストで先にシグナル発火を確認 |
| ModelSelectionWidget との連携失敗 | apply_filters() の引数形式を事前確認済み |
| フィルタが効かない (mode問題) | `mode="advanced"` でウィジェット生成 |
| 統合先ズレ | widget_setup_service.py で統合（tab_reorganization_service.py は骨格のみ） |
| capabilities マッピング不一致 | ModelType.name 値 ('caption', 'tag', 'score') と一致させる |

## 実装順序

1. AnnotationFilterWidget.ui 作成
2. `scripts/generate_ui.py` 実行
3. annotation_filter_widget.py 実装
4. 単体テスト作成・実行
5. バッチタグタブへの統合
6. 動作確認

---

## Phase 5: バグ修正（ユーザーフィードバック 2026-01-21）

### 問題1: capabilities の値不一致 [高]

**現状:**
- `annotation_filter_widget.py` (line 102): `"tag"`, `"score"` (単数形)
- `model_registry_protocol.py` (line 17): `"tags"`, `"scores"` (複数形)

**分析:**
- DB schema `ModelType.name`: docstring に `'caption', 'tag', 'score'` (単数形)
- `Model.capabilities` プロパティ: `[model_type.name for model_type in self.model_types]`
- ModelSelectionWidget は DB Model を使用するため、**単数形が正解**

**確認事項:**
- 実際のDBデータで ModelType.name が何か確認が必要
- `model_registry_protocol.py` の複数形は ModelInfo 用（別データソース）

**修正案:**
- 単数形維持（DB schema と一致）
- ただし実際の DB データ確認後に最終判断

### 問題2: Web API フィルタが効かない [中]

**現状:**
```python
provider="local" if filters.get("environment") == "local" else None
```
- `environment == "api"` のとき `provider=None` でフィルタなし

**修正案:**
```python
provider = None
if filters.get("environment") == "local":
    provider = "local"
elif filters.get("environment") == "api":
    # Web API プロバイダーリスト（openai, anthropic, google など）
    # ただし単一 provider では絞れないため、別アプローチ必要
```

**課題:**
- Web API は複数プロバイダー（openai, anthropic, google）
- 単一 `provider` フィルタでは表現不可
- `ModelSelectionCriteria` に `exclude_provider` または `is_api_model` フィルタ追加が必要

**採用対応:** local 以外を API とみなす

```python
# widget_setup_service.py 修正
provider = None
env = filters.get("environment")
if env == "local":
    provider = "local"
elif env == "api":
    # local 以外を API とみなす → ModelSelectionCriteria 拡張必要
    # 暫定: exclude_local=True フラグを追加
    pass  # 別途 ModelSelectionCriteria 拡張で対応
```

**必要な追加修正:**
- `ModelSelectionCriteria` に `exclude_local: bool = False` 追加
- `ModelSelectionService.filter_models()` で `exclude_local` 処理追加

### 問題3: Signal 重複接続 [中]

**現状:**
- `setup_batch_tag_tab_widgets()` 複数回呼び出しで `filter_changed.connect()` が重複
- `apply_filters()` が多重実行される

**修正ファイル:** `src/lorairo/gui/services/widget_setup_service.py`

**修正案:**
```python
# Signal接続: フィルター変更 → モデル一覧更新
# 再接続ガード: 既に接続済みなら再接続しない
if (
    hasattr(main_window, "batchAnnotationFilter")
    and hasattr(main_window, "batchModelSelection")
    and main_window.batchAnnotationFilter
    and main_window.batchModelSelection
):
    # 既に接続済みかチェック（フラグ管理）
    if not getattr(main_window, "_annotation_filter_connected", False):
        main_window.batchAnnotationFilter.filter_changed.connect(
            lambda filters: main_window.batchModelSelection.apply_filters(
                provider="local" if filters.get("environment") == "local" else None,
                capabilities=filters.get("capabilities", []),
            )
        )
        main_window._annotation_filter_connected = True
        logger.info("✅ フィルター → モデル選択 Signal接続完了")
    else:
        logger.debug("フィルター Signal 既に接続済み、スキップ")
```

## Phase 5 修正対象ファイル

| ファイル | 修正内容 | 優先度 |
|----------|----------|--------|
| `widget_setup_service.py` | Signal 重複接続ガード追加 | 高 |
| `model_selection_service.py` | `ModelSelectionCriteria` に `exclude_local` 追加 | 中 |
| `widget_setup_service.py` | `exclude_local=True` でAPIフィルタ対応 | 中 |
| （確認後）`annotation_filter_widget.py` | capabilities 値修正（必要な場合） | 高 |

## Phase 5 検証

1. **capabilities 確認**
   ```bash
   uv run python -c "
   from lorairo.services.service_container import get_service_container
   sc = get_service_container()
   models = sc.image_repository.get_model_objects()
   for m in models[:5]:
       print(f'{m.name}: {m.capabilities}')
   "
   ```

2. **Signal 重複テスト**
   - `setup_batch_tag_tab_widgets()` を2回呼び出し
   - フィルター変更時に `apply_filters()` が1回だけ呼ばれることを確認

---

## Phase 5 実装完了 (2026-01-21 15:50)

### DB capabilities 実データ確認結果
```
ユニーク capabilities 値: ['caption', 'multimodal', 'scores', 'tags', 'upscaler']
```
- `'caption'` (単数形)
- `'tags'` (複数形) ← **修正が必要だった**
- `'scores'` (複数形) ← **修正が必要だった**

### 修正内容

| 問題 | ファイル | 修正内容 |
|------|----------|----------|
| capabilities 値不一致 | `annotation_filter_widget.py` | `'tag'`→`'tags'`, `'score'`→`'scores'` |
| capabilities 値不一致 | `test_annotation_filter_widget.py` | テストも同様に修正 |
| Web API フィルタ | `model_selection_service.py` | `ModelSelectionCriteria` に `exclude_local` 追加 |
| Web API フィルタ | `model_selection_widget.py` | `apply_filters(exclude_local=)` パラメータ追加 |
| Signal 重複接続 | `widget_setup_service.py` | `_annotation_filter_connected` フラグでガード |

### 検証結果
```
=== Phase 5 バグ修正 統合テスト ===
1. capabilities 値確認: ['tags', 'scores'] ✅
2. exclude_local フィルタ: local=0, api=15, total=56 ✅
3. Signal連携: 3回発火 ✅
```

### テスト結果
- 単体テスト: 16件全て成功
- 関連GUIテスト: 23/24件成功
