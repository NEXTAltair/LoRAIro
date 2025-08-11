# ModelSelectionWidget設計改善計画（UI優先・段階的アプローチ）

## 📋 計画概要

**作成日**: 2025-08-11
**ブランチ**: `feature/model-selection-widget-ui-layout-refactor`
**アプローチ**: UI開発ベストプラクティスに従った段階的リファクタリング

## 🎯 背景と問題定義

### 現在の設計問題
1. **責任分担の矛盾**: UI表示ロジックがWidget/Service両方に重複実装
2. **設計不整合**: FilterSearchPanelとの設計パターン不統一  
3. **複雑なエラー処理**: Widget層でのビジネスロジックフォールバック
4. **重複実装**: DRY原則違反（tooltip、display name作成）
5. **コメント・実装不整合**: 設計意図と実装の矛盾

### 発見されたTODOコメント
```python
# TODO: レイアウト定義は QtDesigner へ移動 全選択、全解除、推奨選択ボタンは不要
# TODO: プレースホルダーラベルは不要  
# TODO: レイアウト定義は QtDesigner へ移動
```

## 🏗️ 修正された実装アプローチ

### UI優先・段階的開発フロー
1. **レイアウト定義** → 2. **レイアウト確認** → 3. **ウィジェット単体表示確認** → 4. **設計課題対応**

この順序により以下を実現：
- 視覚的検証の優先
- 段階的リスク管理  
- 開発効率の向上
- 手戻り最小化

## 📅 実装計画詳細

### Phase 1: QtDesignerによるレイアウト定義 (1日)

#### 1.1 .uiファイル作成
- **作成先**: `src/lorairo/gui/designer/model_selection_widget.ui`
- **設計方針**: 現在のTODO要件を満たすシンプル化設計
- **削除対象**: 不要な制御ボタン、プレースホルダーラベル

#### 1.2 UIコンポーネント構造
```
ModelSelectionWidget
├── ModelDisplayScrollArea (メイン)
│   └── ScrollContent (vertical layout)
│       └── DynamicModelCheckboxes
└── StatusLabel (選択状況表示)
```

#### 1.3 .uiファイルコンパイル
```bash
uv run pyside6-uic model_selection_widget.ui -o ui_model_selection_widget.py
```

### Phase 2: レイアウト確認・視覚的検証 (0.5日)

#### 2.1 レイアウト専用テスト
- **テストファイル**: `tests/gui/test_model_selection_layout.py`
- **確認項目**: 構造、レスポンシブ、スタイル適用

#### 2.2 ビジュアル確認
- **デモアプリ**: `demo/model_selection_layout_demo.py`
- **目的**: レイアウトのみの視覚確認

### Phase 3: ウィジェット単体での表示確認 (1日)

#### 3.1 基本実装
```python
class ModelSelectionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_ModelSelectionWidget()
        self.ui.setupUi(self)
        self._setup_connections()
```

#### 3.2 単体表示テスト
- **テストファイル**: `tests/gui/test_model_selection_widget_standalone.py`
- **テスト内容**: Widget初期化、基本表示、インタラクション

### Phase 4: 設計課題への対応 (1.5日)

#### 4.1 共有ヘルパーレイヤー実装
```python
# src/lorairo/gui/helpers/model_ui_helper.py
class ModelUIHelper:
    @staticmethod
    def create_display_name(model: ModelInfo) -> str:
        """統一された表示名生成"""
        
    @staticmethod  
    def create_tooltip(model: ModelInfo) -> str:
        """統一されたツールチップ生成"""
```

#### 4.2 重複実装の解消
- Widget側: `_create_model_tooltip()` 削除
- Service側: `create_model_tooltip()`, `create_model_display_name()` 削除
- ModelUIHelperへの統一

### Phase 5: 統合テスト・品質確認 (1日)

#### 5.1 テスト実行
```bash
# 段階別テスト実行
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/gui/test_model_selection_layout.py -v
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/gui/test_model_selection_widget_standalone.py -v  
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/integration/gui/test_model_selection_integration.py -v
```

#### 5.2 品質指標
- ✅ テストカバレッジ75%以上維持
- ✅ 既存API互換性100%維持
- ✅ UI応答性基準値維持
- ✅ メモリリークなし

## 🎯 推奨設計ソリューション

### アプローチ2: 共有ヘルパーレイヤー採用

**選択理由**:
1. **実用性重視**: 過度な抽象化を避け、開発効率を優先
2. **段階的改善**: 既存コードへの影響最小化
3. **重複排除**: DRY原則違反の効果的解決
4. **拡張性確保**: 将来のUI機能追加への対応力

### 新しい責任分担
```
ModelSelectionWidget (UI層)
├── ユーザーインタラクション処理
├── レイアウト・表示制御
├── シグナル発信
└── ModelUIHelper利用

ModelSelectionService (ビジネスロジック層)  
├── データ取得・変換
├── フィルタリング・推奨判定
├── キャッシュ管理
└── エラーハンドリング

ModelUIHelper (表示ヘルパー層)
├── 表示名生成
├── ツールチップ生成
└── アイコン選択
```

## ⚠️ リスク管理

### 段階的リスク緩和
- **Phase 2**: UIレイアウト問題の早期発見
- **Phase 3**: 単体機能の確実な動作確認
- **Phase 5**: 包括的な統合検証

### 予防策
- QtDesignerの段階的学習
- 自動生成コードの適切な管理
- .gitignoreとビルドプロセス整備

## 📊 期待される成果

### 設計品質向上
- ✅ 責任分離の明確化
- ✅ コードの重複排除
- ✅ 設計一貫性の改善
- ✅ 保守性の向上

### 開発効率改善
- ✅ 手戻り最小化
- ✅ 段階的問題解決
- ✅ 並行作業可能性
- ✅ テスト充実による品質担保

## 🚀 次ステップ

1. **Phase 1開始**: QtDesignerでのレイアウト定義
2. **環境整備**: PySide6-uic、QtDesigner確認
3. **段階的実装**: 各Phaseの成功指標達成

**総工数見積もり**: 5日間

---

この計画により、ModelSelectionWidgetの設計課題を解決しつつ、UI開発のベストプラクティスに従った効率的なリファクタリングを実現します。