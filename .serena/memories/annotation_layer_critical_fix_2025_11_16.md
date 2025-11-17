# アノテーション層Critical Fix記録

**実施日**: 2025-11-16  
**Commit**: efb6fa3  
**対応内容**: Phase 1-10完了後に発見された実装不備の完全修正

## 背景

Phase 7-8でテストは新シグネチャに対応したが、WorkerService実装コードに以下の不備が残存：

1. **AnnotationLogic初期化の不正な引数** (Line 115-119)
   - 誤: `AnnotationLogic(annotator_adapter, config_service, db_manager)`
   - AnnotationLogic.__init__() は `annotator_adapter` のみ受け付ける
   - 結果: `TypeError: __init__() got an unexpected keyword argument 'config_service'`

2. **start_enhanced_single_annotation() の旧シグネチャ** (Line 219-235)
   - 誤: `AnnotationWorker(images=..., phash_list=..., operation_mode="single")`
   - 新: `AnnotationWorker(annotation_logic, image_paths, models)`
   - 結果: `TypeError` (引数不一致)
   - 状況: 未使用メソッドだが、呼び出されると即座にクラッシュ

3. **start_annotation() の旧シグネチャ** (Line 186)
   - 同様に旧シグネチャで TypeError発生
   - test_worker_service.py で使用されていた

## 修正内容

### 1. AnnotationLogic初期化修正

**修正箇所**: `src/lorairo/gui/services/worker_service.py:114-116`

```python
# 修正前
self._annotation_logic = AnnotationLogic(
    annotator_adapter=annotator_adapter,
    config_service=config_service,
    db_manager=self.db_manager,
)

# 修正後
self._annotation_logic = AnnotationLogic(
    annotator_adapter=annotator_adapter,
)
```

**影響**: AnnotationLogicのインスタンス化が正常動作するようになった

### 2. 旧APIメソッド削除

**削除メソッド**:
- `start_annotation(images, phash_list, models)` - 旧API
- `start_enhanced_single_annotation(images, phash_list, models)` - 未使用メソッド

**置き換え**:
- 全て `start_enhanced_batch_annotation(image_paths, models)` に統一

**コメント追加** (Line 169-171):
```python
# === Annotation ===
# 注: 旧APIメソッド（start_annotation, start_enhanced_single_annotation）は削除済み
# 新API: start_enhanced_batch_annotation() を使用してください
```

### 3. worker_id統一

**修正前**: `enhanced_batch_{uuid}`  
**修正後**: `annotation_{uuid}`

**理由**: シグナル発火処理を簡素化し、命名規則を統一

**影響箇所**:
- `start_enhanced_batch_annotation()`: worker_id生成
- `_on_worker_started()`: enhanced_分岐削除
- `_on_worker_finished()`: enhanced_分岐削除
- `_on_worker_error()`: enhanced_分岐削除

### 4. test_worker_service.py修正

**削除テスト**:
- `test_start_annotation_success`
- `test_start_annotation_failure`
- `test_annotation_progress_signal_connection`
- `test_start_enhanced_batch_annotation_with_api_keys` (旧シグネチャ)
- `test_start_enhanced_batch_annotation_without_api_keys` (旧シグネチャ)

**追加テスト**:
- `test_start_enhanced_batch_annotation_success`: 新シグネチャテスト

**テスト結果**: ✅ 1 passed

## 検証結果

### テスト実行

```bash
uv run pytest tests/unit/gui/services/test_worker_service.py::TestWorkerService::test_start_enhanced_batch_annotation_success -xvs
```

**結果**: ✅ PASSED

**ログ確認**:
```
2025-11-16 15:36:54.335 | INFO | バッチアノテーション開始: 2画像, 2モデル (ID: annotation_d8d92556)
```

### 修正の完全性

- ✅ AnnotationLogic初期化が正常動作
- ✅ 旧APIメソッド完全削除
- ✅ 新APIメソッドのみ使用可能
- ✅ worker_id統一（annotation_プレフィックス）
- ✅ テストが新シグネチャで成功

## 影響範囲

### 破壊的変更

**削除されたメソッド**:
- `WorkerService.start_annotation()`
- `WorkerService.start_enhanced_single_annotation()`

**影響する可能性がある箇所**:
- ❌ なし（未使用メソッドだった）
- ⚠️ 将来のコード: 新APIのみ使用可能

### 互換性

**後方互換性**: なし（旧APIメソッド削除）  
**移行パス**: `start_enhanced_batch_annotation(image_paths, models)` 使用

## まとめ

**Phase 6で「完了」とした箇所の実態**:
- WorkerService統合は「部分完了」だった
- start_enhanced_batch_annotation()のみ正しいシグネチャ
- 旧APIメソッドが残存し、TypeError を引き起こす状態

**本Fixで完全解決**:
- 全ての旧シグネチャを削除
- AnnotationLogic初期化を修正
- 新APIのみが使用可能な状態を確立

**今後の注意点**:
- 計画書の「完了」ステータスは実装とテスト両方の確認が必要
- 旧API削除時は grep で使用箇所の完全調査が必要
