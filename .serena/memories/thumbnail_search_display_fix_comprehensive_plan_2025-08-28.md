# サムネイル検索表示修正・包括的計画（2025-08-28）

## 計画概要
**日付**: 2025-08-28  
**ブランチ**: `fix/thumbnail-search-display`  
**問題**: 日付で絞り込み検索からサムネイル表示がうまくいかない  
**エラー**: `'WorkerService' object has no attribute 'start_thumbnail_loading'`

## Memory-First分析結果

### 過去実装の確認
- **2025-08-21**: Phase 2で Search→Thumbnail Sequential Pipeline 実装完了
- **2025-08-26**: Thumbnail選択→プレビュー表示問題解決済み
- **既存実装**: MainWindow signal wiring, WorkerService統合, ThumbnailSelectorWidget実装済み

### 根本原因特定
- **メソッド名不一致**: `start_thumbnail_loading` → 正しくは `start_thumbnail_load`
- **パラメータ不整合**: `(search_result, default_thumbnail_size)` → 正しくは `(search_result.image_metadata)`
- **修正状況**: 既にfix/thumbnail-search-displayブランチで修正適用済み

## 選択した解決アプローチ

### アプローチ: 段階的診断 + Fallback堅牢化ハイブリッド（推奨★★★）
**選択理由**:
- ✅ 既存のPhase 2 Sequential Pipeline実装活用
- ✅ 低リスクで確実な問題解決
- ✅ ユーザー体験改善とフォールバック機能
- ✅ 実装コストと効果のバランス最適

### 実装計画（3段階・合計2.5-4時間）

#### **Phase A: 診断強化・問題特定（30-60分）**
1. **Pipeline診断ログ強化**: 各段階での詳細ログ出力追加
2. **Signal発火確認**: thumbnail_finished signal発火の確実な確認  
3. **データフロー追跡**: Search→Thumbnail→Display全体の追跡

#### **Phase B: 問題特定・修正（1-2時間）**
1. **Signal接続確認・強化**: MainWindow初期化時の明示的接続確認
2. **型安全性向上**: 適切な型ヒントとvalidation追加
3. **特定問題修正**: ログ分析結果に基づく最小限修正

#### **Phase C: Fallback機能追加（1時間）**  
1. **Manual Thumbnail Reload**: Pipeline失敗時の手動再読み込み機能
2. **Pipeline Status表示**: 進行状況のユーザー可視化
3. **Error Recovery**: 自動処理失敗時のフォールバック確保

## テスト戦略

### 単体テスト計画
- **Pipeline Signal Chain**: 完全なSignal chain動作テスト
- **Error Handling**: エラーハンドリングと手動復旧機能テスト

### 統合テスト計画
- **End-to-End Pipeline**: 検索→サムネイル→表示の全体テスト
- **パフォーマンステスト**: 大量画像でのpipeline性能テスト

### 検証環境
```bash
# Windows実機テスト
uv run python src/lorairo/main.py

# Linux GUIテスト  
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/gui/test_thumbnail_pipeline.py -xvs
```

## リスク対策

### 特定リスク
1. **Signal接続重複**: Connection確認とdisconnect処理の明示的実装
2. **ThumbnailWorker並行処理**: 既存worker_idトラッキング機能活用
3. **メモリリーク**: ThumbnailCache適切な管理とクリーンアップ

### 品質保証
- **コード品質**: Ruff formatting, mypy type checking
- **テストカバレッジ**: 新規実装部分75%+カバレッジ  
- **User Experience**: 直感的なエラー回復機能

## 実装対象ファイル

### 主要修正対象
1. `src/lorairo/gui/window/main_window.py`
   - `_on_search_completed_start_thumbnail()`: 診断ログ強化
   - `_on_thumbnail_completed_update_display()`: エラーハンドリング強化
   - `_setup_worker_service_connections()`: Signal接続の明示的確認

2. `src/lorairo/gui/services/worker_service.py`
   - `_on_worker_finished()`: thumbnail_finished signal診断ログ

3. `src/lorairo/gui/widgets/filter_search_panel.py`  
   - Manual thumbnail reload button追加
   - Pipeline status表示機能追加

### テスト対象
- `tests/gui/test_thumbnail_pipeline.py`: 新規作成
- `tests/gui/test_main_window_qt.py`: Pipeline関連テスト追加

## 期待効果

### 直接効果
- ✅ サムネイル検索表示問題の確実な解決
- ✅ Pipeline diagnostic向上による保守性改善
- ✅ Manual fallback機能によるユーザー体験向上

### 間接効果
- ✅ Phase 2 Sequential Pipeline実装の堅牢化
- ✅ 将来の類似問題の予防・早期発見
- ✅ ThumbnailWorker/ThumbnailSelectorWidget統合の信頼性向上

## Next Steps

### 実装フェーズ（/implement）
1. Phase A: 診断強化実装とログ分析
2. Phase B: 特定問題修正と型安全性向上
3. Phase C: Fallback機能実装と統合テスト

### 完了後  
- 設計知識のCipher memory長期保存
- プロジェクト固有パターンの蓄積
- アーキテクチャ改善提案への基盤確立

## 関連記録
- `search_thumbnail_integration_phase2_implementation_complete_2025-08-21`
- `thumbnail_preview_connection_fix_2025`  
- `current-project-status`