# Widget Main Block 追加プラン

**作成日**: 2025年8月4日  
**ステータス**: 🚧 実装中  
**重要度**: 中  
**カテゴリ**: 開発効率・デバッグ支援

## 📋 プロジェクト概要

`src/lorairo/gui/widgets/` 内の全ウィジェットに表示確認用の `__main__` ブロックを追加し、個別実行・テスト・デバッグを可能にします。

## 🔍 現状分析

### ✅ 既存実装済み (8個)
- `thumbnail.py` - 完全実装済み（ヘッダーコメント要修正）
- `image_preview.py` - 基本実装済み
- `filter_search_panel.py` - 高度実装済み
- `selected_image_details_widget.py` - 包括実装済み
- `annotation_control_widget.py` - フル実装済み
- `directory_picker.py` - 基本実装済み
- `file_picker.py` - 基本実装済み
- `picker.py` - 基本実装済み

### 🎯 実装対象 (7個)
1. `annotation_coordinator.py` - ワークフロー調整クラス
2. `annotation_data_display_widget.py` - データ表示コンポーネント
3. `annotation_results_widget.py` - 結果表示ウィジェット
4. `annotation_status_filter_widget.py` - ステータスフィルター
5. `model_selection_widget.py` - モデル選択インターフェース
6. `filter.py` - カスタムフィルターコンポーネント群

## 🏗️ 実装戦略

### 3層構造アプローチ

#### **Tier 1: Simple Display (シンプル表示)**
- `model_selection_widget.py`
- `filter.py`

**特徴**: 基本的なウィジェット表示のみ、最小限の依存関係

#### **Tier 2: Data Display (データ表示)**
- `annotation_data_display_widget.py`
- `annotation_results_widget.py`
- `annotation_status_filter_widget.py`

**特徴**: ダミーデータでの機能確認、シグナル接続テスト

#### **Tier 3: Complex Integration (複雑統合)**
- `annotation_coordinator.py`

**特徴**: モック統合での統合確認、高度なシグナル・状態管理

## 📝 実装詳細

### 共通実装パターン

```python
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    from ...utils.log import initialize_logging
    
    # 1. ログ初期化
    logconf = {"level": "DEBUG", "file": None}
    initialize_logging(logconf)
    
    # 2. アプリケーション作成
    app = QApplication(sys.argv)
    
    # 3. ウィジェット作成・設定
    widget = WidgetClass()
    
    # 4. ダミーデータ・シグナル接続（必要に応じて）
    
    # 5. 表示・実行
    widget.show()
    sys.exit(app.exec())
```

### 個別実装方針

#### **Tier 1 実装**

**model_selection_widget.py**:
```python
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    widget = ModelSelectionWidget()
    widget.show()
    sys.exit(app.exec())
```

**filter.py**:
```python
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow
    import sys
    
    app = QApplication(sys.argv)
    main_window = QMainWindow()
    
    # CustomRangeSliderのテスト
    widget = CustomRangeSlider(min_value=0, max_value=1000)
    main_window.setCentralWidget(widget)
    main_window.show()
    sys.exit(app.exec())
```

#### **Tier 2 実装**

**annotation_data_display_widget.py**:
- `AnnotationData` / `ImageDetails` のダミーデータ作成
- リアルなサンプル値での機能確認

**annotation_results_widget.py**:
- 複数プロバイダーの結果データをシミュレート
- 結果表示機能の視覚確認

**annotation_status_filter_widget.py**:
- フィルター変更シグナルの接続テスト
- ステータス変更の動作確認

#### **Tier 3 実装**

**annotation_coordinator.py**:
- モックデータベースマネージャー使用
- ワークフロー状態変更のシグナル確認
- 統合シナリオのテスト

## 🔧 技術的考慮事項

### 依存関係管理
- **外部サービス**: モック使用で依存を最小化
- **相対インポート**: ウィジェット内からの適切なパス
- **オプショナル依存**: 存在しない場合の graceful degradation

### テストデータ設計
- **リアリスティック**: 実際の使用シナリオに近いデータ
- **多様性**: 様々なケースをカバー
- **視覚的確認**: UI表示で問題を発見しやすい構造

### パフォーマンス配慮
- **軽量実装**: 起動時間を最小限に
- **メモリ効率**: 大量データでの動作確認
- **レスポンシブ**: UI操作の応答性確保

## 📈 期待効果

### 開発効率向上
- **単体テスト簡単化**: `uv run python -m lorairo.gui.widgets.{widget_name}`
- **デバッグ効率**: 問題の局所化と修正の容易化
- **UI確認**: レイアウト・見た目の迅速な検証

### 品質向上
- **視覚的確認**: 実際の表示での問題発見
- **機能テスト**: シグナル・イベント処理の動作確認
- **リグレッション防止**: 変更による影響の早期発見

### ドキュメント価値
- **使用例**: 各ウィジェットの具体的な使用方法
- **設定パターン**: 初期化・設定の実装例
- **統合ガイド**: 他システムとの連携方法

## 🗂️ 作業手順

### Phase 1: 準備作業
- [x] ブランチ作成: `feature/add-widget-main-blocks`
- [x] 計画書作成・保存
- [ ] `thumbnail.py` ヘッダーコメント修正

### Phase 2: 実装作業
- [ ] Tier 1: Simple Display (2個)
- [ ] Tier 2: Data Display (3個)
- [ ] Tier 3: Complex Integration (1個)

### Phase 3: 検証・完成
- [ ] 全ウィジェット個別実行テスト
- [ ] 動作確認・問題修正
- [ ] 最終コミット・ブランチマージ

## ✅ 完成基準

### 技術基準
- [ ] 全7個のウィジェットに __main__ ブロック追加完了
- [ ] 各ウィジェットが `uv run python -m lorairo.gui.widgets.{name}` で正常表示
- [ ] エラー・警告なしでの実行
- [ ] 適切なダミーデータでの機能確認

### 品質基準
- [ ] 既存コードスタイルとの整合性
- [ ] ログ出力による動作状況の確認可能性
- [ ] シグナル・イベントの動作確認
- [ ] メモリリーク・パフォーマンス問題なし

## 📊 進捗状況

**全体進捗**: 🟨 10% (1/10 完了)

- [x] ブランチ作成・計画策定
- [ ] thumbnail.py ヘッダー修正
- [ ] model_selection_widget.py 実装
- [ ] filter.py 実装
- [ ] annotation_data_display_widget.py 実装
- [ ] annotation_results_widget.py 実装
- [ ] annotation_status_filter_widget.py 実装
- [ ] annotation_coordinator.py 実装
- [ ] 全体テスト・検証
- [ ] 完成・マージ

---

**注意**: この計画により、全15個のウィジェット（既存8個 + 新規7個）が統一された方法で単体表示確認できるようになり、開発・保守効率が大幅に向上します。