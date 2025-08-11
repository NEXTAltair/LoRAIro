# C案（DB中心アーキテクチャ）完了実装計画

## 現状分析結果

### 実装進捗: 70%完了
- **完了済み部分**:
  - DB Schema Modelにis_recommended, available, capabilitiesプロパティ実装済み
  - ModelSelectionWidgetがDB Model直接使用に移行済み
  - ServiceContainer DI基盤確立済み
  - SQLAlchemyセッション管理完全実装済み

### 残存課題 (30%)
1. **ModelInfo重複定義問題**: 4箇所で異なる定義が併存
   - `src/lorairo/services/model_info_manager.py` (TypedDict版)
   - `src/lorairo/services/model_registry_protocol.py` (dataclass版)  
   - `src/lorairo/gui/services/model_selection_service.py` (削除コメント有)
   - `src/lorairo/gui/widgets/model_selection_widget.py` (削除コメント有)

2. **Mockブリッジ依存**: ModelSelectionServiceがMock(spec=Model)で変換実装
   - _convert_model_infos_to_models()メソッドでMock使用
   - _convert_db_dicts_to_models()メソッドでMock使用

3. **Widget依存注入破綻**: create(...None...)問題
   - ModelSelectionWidget._create_model_selection_service()でNone渡し

## 推奨戦略: ハイブリッド移行アプローチ

### 実装計画 (2日間で90%完成)

#### Day 1: ModelInfo統一 (最優先)
- model_registry_protocol.pyのModelInfoを正式版として採用
- TypedDict版削除
- 重複定義削除
- 統一import実施

#### Day 1.5: Mockブリッジ削除 (真のDB統合)  
- ModelSelectionServiceのMock変換削除
- DB Repository経由の真のModel取得実装
- Widget層での適切な依存注入修正

#### Day 2: 高頻度Widget DB直接化
- ModelSelectionWidgetでDB Model直接利用
- ServiceContainer経由の依存解決実装
- 統合テスト実施

### 期待成果
- ModelInfo重複: 4箇所 → 1箇所 (75%削減)
- Mockブリッジ: 完全削除
- 実装進捗: 70% → 90%
- 型安全性とデータ整合性の完全確立

## 技術的詳細

### 採用技術スタック
- SQLAlchemy ORM (DB Model直接利用)
- ServiceContainer DIパターン
- PySide6 GUIフレームワーク
- mypy型チェック完全対応

### アーキテクチャ原則
- Single Source of Truth (DB Model)
- 中間変換レイヤー最小化
- Protocol-based依存注入
- 段階的リスク管理

## 品質保証計画
- mypy型チェック完全通過
- ruffコード品質チェック  
- 単体・統合・GUIテスト全通過
- SQLAlchemyセッション管理適切性確認

## 記録日時
作成: 2025-01-11  
対象: ModelInfo重複問題解決とC案完了
実装予定: ハイブリッド移行アプローチ (2日間)