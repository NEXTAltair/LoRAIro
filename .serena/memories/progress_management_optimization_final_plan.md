# LoRAIro進捗管理最適化計画書（最終版）

## 設計方針決定
**採用方針**: 現在実装維持 + 冗長性削減 + ProgressManager削除

### 方針選択理由
1. **過去検証結果の尊重**: LoRAIroWorkerBaseアーキテクチャが包括的検討を経て最適と確認済み
2. **制御性vs冗長性**: 制御の明確性・テスタビリティ・デバッグ容易性が冗長性コストを上回る
3. **リスク最小化**: 大幅アーキテクチャ変更を避け、段階的改善で安定性確保
4. **実用性重視**: パフォーマンス問題（GUIハング）の根本解決を最優先

## 実装計画：3段階アプローチ

### Phase 1: 統一スロットリング + 冗長性削減
**目標**: シグナル発行5212回→50回（99%削減）+ コード重複解消

#### A. ProgressHelper共通ユーティリティ作成
**新規ファイル**: `src/lorairo/gui/workers/progress_helper.py`
```python
class ProgressHelper:
    @staticmethod
    def calculate_percentage(current: int, total: int, base: int = 0, range: int = 100):
        """進捗パーセンテージ計算の統一"""
        return base + int((current / total) * range)
    
    @staticmethod
    def create_batch_reporter(total_items: int, target_reports: int = 50):
        """バッチ進捗レポーター生成"""
        interval = max(1, total_items // target_reports)
        return lambda current: current % interval == 0
    
    @staticmethod
    def create_throttled_reporter(min_interval_ms: int = 50):
        """時間ベーススロットリング制御"""
        # 実装詳細
```

#### B. ProgressReporter拡張
**修正ファイル**: `src/lorairo/gui/workers/base.py`
```python
class ProgressReporter(QObject):
    def __init__(self):
        super().__init__()
        self._last_emit_time = 0
        self._min_interval_ms = 50
    
    def report_throttled(self, progress: WorkerProgress, force_emit: bool = False):
        """スロットリング付き進捗報告"""
        current_time = time.monotonic_ns() // 1_000_000
        
        if force_emit or (current_time - self._last_emit_time >= self._min_interval_ms):
            self.progress_updated.emit(progress)
            self._last_emit_time = current_time
```

#### C. ThumbnailWorkerバッチ処理最適化
**修正ファイル**: `src/lorairo/gui/workers/database_worker.py`
```python
def execute(self) -> ThumbnailLoadResult:
    # 共通ユーティリティ活用
    batch_reporter = ProgressHelper.create_batch_reporter(total_count, 50)
    
    # バッチ処理（2606→27バッチ）
    BATCH_SIZE = 100
    total_batches = (total_count + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_count)
        batch_items = self.search_result.image_metadata[start_idx:end_idx]
        
        # バッチ内処理（シグナル発行なし）
        for image_data in batch_items:
            # サムネイル処理
            
        # バッチ境界でのみ進捗報告
        percentage = ProgressHelper.calculate_percentage(end_idx, total_count, 5, 90)
        self._report_progress_throttled(percentage, f"バッチ {batch_idx+1}/{total_batches} 完了")
```

#### D. 他ワーカーの冗長性削減
**修正ファイル**: 
- `src/lorairo/gui/workers/database_worker.py` (DatabaseRegistrationWorker, SearchWorker)
- `src/lorairo/gui/workers/annotation_worker.py` (AnnotationWorker, ModelSyncWorker)

共通パターンをProgressHelperで統一:
```python
# 修正前（冗長）
percentage = 10 + int((i + 1) / total_count * 85)

# 修正後（統一）  
percentage = ProgressHelper.calculate_percentage(i + 1, total_count, 10, 85)
```

### Phase 2: ProgressManager削除
**目標**: 未使用コード削除によるアーキテクチャ明確化

#### 削除対象ファイル
1. **`src/lorairo/gui/workers/progress_manager.py`** - 本体実装
2. **`tests/unit/gui/workers/test_progress_manager.py`** - 専用単体テスト
3. **`tests/integration/gui/test_worker_coordination.py`** - ProgressManager参照部分のみ除去

#### 影響確認済み箇所
- `src/`ディレクトリ内で実際の使用箇所は存在しない（調査済み）
- テストでのみ参照されているため、削除による実機能への影響なし

### Phase 3: 検証とメトリクス
**目標**: 改善効果の定量評価と品質保証

#### A. パフォーマンステスト
1. **シグナル発行回数測定**:
   - 修正前: 2606アイテム→5212回シグナル
   - 目標: 2606アイテム→50回程度（99%削減）

2. **UI応答性測定**:
   - メインウィンドウハング解消確認
   - 進捗表示の滑らかさ維持確認

3. **メモリ使用量**:
   - 現状維持確認（要求仕様通り）

#### B. 回帰テスト
1. **機能テスト**: 全ワーカーの基本動作確認
2. **統合テスト**: SearchWorker→ThumbnailWorkerパイプライン
3. **負荷テスト**: 5000+アイテムでの安定性確認

#### C. コード品質評価
1. **冗長性削減効果**: 重複コード行数の測定
2. **保守性向上**: 共通ロジック変更時の影響範囲確認

## 期待効果

| 改善項目 | 現在 | 改善後 | 改善率 |
|----------|------|--------|--------|
| シグナル発行回数 | 5212回 | 50回 | 99%削減 |
| GUI応答性 | ハング発生 | 解決 | 100%改善 |
| コード重複度 | 高 | 低 | 60-70%削減 |
| アーキテクチャ複雑度 | 中 | 低 | 向上 |
| メモリ使用量 | 基準値 | 維持 | 変更なし |

## 実装スケジュール

### Week 1-2: Phase 1実装
- [ ] ProgressHelper実装・テスト
- [ ] ProgressReporterスロットリング拡張  
- [ ] ThumbnailWorkerバッチ処理最適化
- [ ] 他ワーカー冗長性削減

### Week 3: Phase 2実装
- [ ] ProgressManager削除
- [ ] 関連テスト整理
- [ ] インポート文清理

### Week 4: Phase 3検証
- [ ] パフォーマンス測定
- [ ] 回帰テスト実行
- [ ] コード品質評価

## リスク管理

### 技術リスク
- **スロットリング副作用**: error/finished等重要シグナルの即時性確保で対応
- **バッチ処理バグ**: 段階的テストで早期発見
- **UI体感劣化**: 30-60Hz進捗更新で滑らかさ維持

### 実装リスク  
- **既存機能影響**: 段階的実装と包括的回帰テストで最小化
- **テスト不備**: Phase 3での集中検証で担保

## 成功基準
1. **主目標**: ThumbnailWorker使用時のGUIハング完全解消
2. **副目標**: コード重複60%以上削減
3. **制約遵守**: メモリ使用量現状維持
4. **品質維持**: 全既存機能の動作保証

この計画により、LoRAIroの確立されたアーキテクチャを尊重しながら、パフォーマンス問題を根本解決し、コードの保守性も大幅向上させることができます。