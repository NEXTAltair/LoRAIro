# Model Selection Table Widget Separation Plan (2025-08-09)

## 🎯 目的
`AnnotationControlWidget` のTODOコメント（165行目）に基づき、モデル選択テーブル機能を専用ウィジェットに分離: "別ウィジェットにしてQtデザイナーで作成する"

## 📊 現状分析

### 問題点
1. **コード結合**: モデルテーブル管理がアノテーション制御ロジックと密結合（164-206行、420-473行）
2. **UI/ロジック混在**: テーブルスタイリングとビジネスロジックが同一コンポーネント内
3. **カラム不整合**: UIファイルは3列定義だがコードは4列作成（"選択", "モデル名", "プロバイダー", "機能"）
4. **再利用性**: テーブル機能を他のコンテキストで再利用不可

### アーキテクチャパターン確認済み
- **Qt Designer統合**: 全ウィジェットが `QWidget + Ui_Widget` 継承 + `.ui` ファイル使用
- **サービス注入**: 統一された `set_*_service()` パターンでの依存性注入
- **シグナル通信**: Qt シグナルによるクリーンな親子間通信
- **既存参照**: `ModelSelectionWidget` はスクロールエリア + チェックボックス方式（異なるアプローチ）

## 🏗️ ソリューションアーキテクチャ

### 推奨アプローチ: Pure Table Widget

**選択理由:**
- ✅ TODOの Qt Designer 使用要求を直接満たす
- ✅ 関心事のクリーンな分離を維持
- ✅ 確立されたプロジェクトパターンに従う
- ✅ 現在のカラム不整合問題を解決
- ✅ 他のコンテキストでの再利用性を実現

### 実装ステップ

#### Step 1: Qt Designer UI ファイル作成
- **ファイル**: `src/lorairo/gui/designer/ModelSelectionTableWidget.ui`
- **レイアウト**: 適切なヘッダーと設定を持つ4列テーブル
- **プロパティ**: 交互の行色、行選択、ソート有効
- **追加要素**: 選択数表示用ステータスラベル

#### Step 2: UI コード生成
- `pyside6-uic` で `ModelSelectionTableWidget_ui.py` 生成
- designer ディレクトリの既存命名規則に従う

#### Step 3: ウィジェット実装作成
- **ファイル**: `src/lorairo/gui/widgets/model_selection_table_widget.py`
- **クラス**: `ModelSelectionTableWidget(QWidget, Ui_ModelSelectionTableWidget)`
- **依存関係**:
  - サービス注入: `set_search_filter_service(SearchFilterService)`
  - データモデル: `AnnotationSettings` データクラス再利用
  - ロギング: 既存ロガーパターン使用

#### Step 4: 機能の抽出
`AnnotationControlWidget` から以下のメソッドを移行:
- `_setup_model_table()` → `_setup_table_properties()`
- `_update_model_table()` → `update_table_display()`
- `_get_selected_models()` → `get_selected_models()`
- テーブルフィルタリングロジック → `apply_model_filters()`

#### Step 5: シグナルインターフェース定義
```python
class ModelSelectionTableWidget(QWidget):
    # 親との通信用シグナル
    model_selection_changed = Signal(list)  # selected_model_names
    selection_count_changed = Signal(int, int)  # selected, total
    models_loaded = Signal(int)  # total_count
```

#### Step 6: AnnotationControlWidget 更新
- 直接テーブル管理をウィジェット合成に置換
- Qt Designer ファイルを新ウィジェット含むよう更新
- 親子ウィジェット間のシグナル接続
- 抽出されたメソッドとテーブル固有コードを削除
- 後方互換性のため既存パブリックインターフェース維持

#### Step 7: テスト & 統合
- 影響を受けるユニットテスト更新
- サービス注入の正常動作検証
- シグナル通信テスト
- 既存機能の回帰がないことを保証

## 🔧 技術詳細

### ウィジェットアーキテクチャ
```python
class ModelSelectionTableWidget(QWidget, Ui_ModelSelectionTableWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        
        # プロジェクトパターンに従うサービス注入
        self.search_filter_service: SearchFilterService | None = None
        
        # データ管理
        self.all_models: list[dict[str, Any]] = []
        self.filtered_models: list[dict[str, Any]] = []
        
        self._setup_table_properties()
        self._setup_connections()
```

### サービス統合
- 既存ウィジェットと同じパターンに従う
- モデルデータとフィルタリングに `SearchFilterService` 使用
- サービス層を通じた検証維持
- モダンとレガシー両方のモデルローディングアプローチをサポート

### 親ウィジェット統合
```python
class AnnotationControlWidget(QWidget, Ui_AnnotationControlWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setupUi(self)
        
        # テーブルをウィジェットに置換
        self.model_table_widget = self.findChild(ModelSelectionTableWidget, "modelTableWidget")
        self.model_table_widget.model_selection_changed.connect(self._on_model_selection_changed)
```

## ✅ 利点

1. **関心事の分離**: テーブルロジックが制御ロジックから分離
2. **Qt Designer準拠**: 特定のTODO要求を満たす
3. **再利用性**: テーブルウィジェットを他のコンテキストで使用可能
4. **保守性**: より小さく、集中したコンポーネント
5. **一貫性**: 確立されたプロジェクトアーキテクチャパターンに従う
6. **バグ修正**: 現在の3/4列不整合問題を解決

## ⚠️ リスク軽減

1. **インターフェース互換性**: 既存のパブリックメソッドとシグナルをすべて維持
2. **サービス依存関係**: `SearchFilterService` 統合が安定したまま確保
3. **テストカバレッジ**: 回帰防止のための包括的テスト更新
4. **段階的移行**: 移行期間中のフォールバックメカニズム保持
5. **エラーハンドリング**: 既存エラーハンドリングパターンを保持

## 🧪 テスト戦略

1. **ユニットテスト**: 分離されたウィジェット機能
2. **統合テスト**: サービス注入とフィルタリング
3. **GUIテスト**: シグナル通信とユーザーインタラクション
4. **回帰テスト**: `AnnotationControlWidget` の動作が変わらないことを保証
5. **エッジケース**: エラー条件とサービス利用不可時

## 📋 成功基準

- ✅ モデルテーブルがQt Designerで別ウィジェットに抽出済み
- ✅ 既存機能がすべて保持済み
- ✅ クリーンなシグナルベース通信が確立済み
- ✅ サービス注入が正常動作
- ✅ テストが回帰なしで合格
- ✅ TODOコメント要求が満たされた

## 🚀 実装の優先順位

### Phase 1: 基盤構築 (高優先度)
1. Qt Designer UI ファイル作成
2. ウィジェットクラス基本実装
3. シグナルインターフェース定義

### Phase 2: 機能移行 (中優先度) 
4. テーブル管理ロジック抽出
5. サービス統合実装
6. 親ウィジェット更新

### Phase 3: 品質保証 (高優先度)
7. テスト更新と検証
8. 回帰テスト実行
9. ドキュメント更新

この計画は、TODOの要求に対応し、LoRAIroの確立されたパターンとの一貫性を維持しながら、機能回帰なしでクリーンなアーキテクチャソリューションを提供します。