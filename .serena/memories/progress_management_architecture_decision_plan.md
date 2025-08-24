# LoRAIro進捗管理アーキテクチャ最適化計画

## 設計決定サマリー
**結論**: 現在の実装（各ワーカー直接シグナル発行）を基盤とした段階的改善が最適

**理由**:
- 過去の包括的検証でLoRAIroWorkerBaseアーキテクチャが最適と確認済み
- ProgressManagerはmoveToThreadパターンで制約に抵触
- 現在のWorkerpService統合が安定稼働中
- パフォーマンス問題は基盤変更なしで解決可能

## 実装計画：3段階アプローチ

### Phase 1: 統一スロットリング機構（優先実装）
**目標**: ThumbnailWorkerシグナル発行 5212回→50回程度（99%削減）

**修正ファイル**:
- `src/lorairo/gui/workers/base.py` - ProgressReporter拡張
- `src/lorairo/gui/workers/database_worker.py` - ThumbnailWorkerバッチ処理
- テスト追加

**技術仕様**:
- 時間ベース(50ms間隔) + ステップベース制御
- error/finishedシグナルの即時発行保証
- バッチサイズ100でのThumbnailWorker処理

### Phase 2: ProgressManager削除
**作業内容**:
- `src/lorairo/gui/workers/progress_manager.py` - ファイル削除
- `tests/unit/gui/workers/test_progress_manager.py` - テスト削除  
- `tests/integration/gui/test_worker_coordination.py` - 参照除去

**効果**: アーキテクチャ明確化、メンテナンス負荷軽減

### Phase 3: 検証とメトリクス
- 2606アイテム回帰テスト
- 5000+アイテム負荷テスト
- SearchWorker→ThumbnailWorkerパイプライン統合テスト

## 期待効果
- **パフォーマンス**: GUIハング完全解決
- **アーキテクチャ**: 直接シグナル方式への統一
- **保守性**: 未使用コード除去による向上