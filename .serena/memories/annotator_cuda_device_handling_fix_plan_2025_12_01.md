# CUDA デバイスハンドリングとログレベル修正計画

**作成日**: 2025-12-01  
**対象**: image-annotator-lib  
**問題**: アノテーション実行時にスコアがGUIに表示されない

## 問題の概要

### 症状
- アノテーション実行後、GUIにスコアが表示されない
- ログに "Torch not compiled with CUDA enabled" のWARNINGが出力される
- 処理自体は停止せず、完了したように見える

### 根本原因（3つの問題）

1. **デバイス設定の不整合**
   - `BaseAnnotator.__init__`: `self.device = "cuda"` (config default、検証なし)
   - `ModelLoad.Loader.__init__`: `determine_effective_device()` で CPU にフォールバック
   - `__enter__`: 検証されていない `self.device` ("cuda") を `restore_model_to_cuda()` に渡す
   - 結果: CPU でロードされたモデルを CUDA に移動しようとして失敗

2. **ログレベルの不適切さ**
   - `_move_components_to_device()` (line 470) でデバイス移動失敗が WARNING としてログされる
   - 本来は ERROR とすべき重要な問題

3. **エラー伝播の欠如**
   - `restore_model_to_cuda()` が None を返しても例外を投げない
   - Pipeline/Transformers の `__enter__` で None チェックがない
   - 結果: 後続の推論で AttributeError、GUI には不明瞭なエラー

### 問題フロー

```
1. BaseAnnotator.__init__
   self.device = "cuda" (config、検証なし)
   ↓
2. load_transformers_pipeline_components
   Loader.__init__ で determine_effective_device() → "cpu"
   モデルを CPU でロード
   ↓
3. __enter__
   restore_model_to_cuda(self.device="cuda") を呼び出し
   ↓
4. restore_model_to_cuda
   CPU のモデルを CUDA へ移動を試みる
   ↓
5. _move_components_to_device
   CUDA 移動失敗、WARNING ログ
   ↓
6. 結果
   - ログに混乱（"復元完了" だが実際は失敗）
   - components の状態が不明瞭
   - GUI にスコアが表示されない
```

## 推奨ソリューション: 早期デバイス検証

**アプローチ**: BaseAnnotator.__init__ でデバイス検証を行い、全ライフサイクルで一貫性を保証

### 選択理由

1. **単一の真実の源**: デバイス設定を一度だけ検証、以降は信頼できる値を使用
2. **一貫性保証**: BaseAnnotator と Loader でデバイス値が一致
3. **最小限の変更**: 既存コードへの影響が小さい（BaseAnnotator のみ変更）
4. **パフォーマンス**: 検証は初期化時のみ（<1ms、ほぼ無影響）
5. **Fail Fast 原則**: 問題を早期に検出、明確なエラー表示

### 代替案（却下理由）

- **Option B**: Lazy 検証（__enter__ で検証）→ 複数回検証、一貫性窓が存在
- **Option C**: Loader から Annotator へ同期 → 関心の分離違反、複雑

## 実装計画（4フェーズ）

### Phase 1: デバイス検証の追加（低リスク）

**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/annotator.py`

**変更内容**:

1. `__init__` メソッド（line 43）でデバイス検証を追加:
```python
# 修正前
self.device = self._config.device

# 修正後
self.device = self._validate_device(self._config.device)
```

2. デバイス検証メソッドを追加（line 44 の後）:
```python
def _validate_device(self, requested_device: str) -> str:
    """要求されたデバイスを検証し、CUDA 利用不可の場合は CPU にフォールバック。
    
    Args:
        requested_device: 設定ファイルからのデバイス文字列 ("cuda", "cpu" など)
    
    Returns:
        検証されたデバイス文字列（CUDA 利用不可の場合は "cpu"）
    
    Note:
        一貫した検証ロジックのため determine_effective_device() を使用。
    """
    from ..utils import determine_effective_device
    return determine_effective_device(requested_device, self.model_name)
```

**影響**:
- 全アノテータータイプ（Pipeline, Transformers, ONNX, WebAPI, CLIP など）が自動的に検証を継承
- サブクラスでの変更不要
- BaseAnnotator と Loader 間でデバイスの一貫性が保証される

**テスト**:
- 新規: `tests/unit/core/test_device_validation.py`
  - CUDA 利用可能時のテスト
  - CUDA 利用不可時の CPU フォールバックテスト
  - CPU 明示指定時のテスト

### Phase 2: ログレベルの変更（低リスク）

**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory.py`

**変更内容**: `_move_components_to_device` メソッド（line 470-473）

```python
# 修正前
logger.warning(
    f"コンポーネント '{component_name}' デバイス移動中にエラー ({target_device}): {e}",
    exc_info=False,
)

# 修正後
logger.error(
    f"コンポーネント '{component_name}' デバイス移動中にエラー ({target_device}): {e}",
    exc_info=True,  # デバッグ用のスタックトレースを含める
)
```

**理由**: デバイス移動失敗は調査が必要な実際の問題であり、警告レベルではない

**テスト**:
- 更新: `tests/unit/core/test_model_factory.py`
  - デバイス移動失敗時に ERROR レベルでログされることを確認
  - スタックトレース（exc_info=True）が含まれることを確認

### Phase 3: エラーハンドリングの改善（中リスク）

**ファイル1**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/pipeline.py`

**変更内容**: `__enter__` メソッド（lines 47-50）

```python
# 修正前
restored_components = ModelLoad.restore_model_to_cuda(
    self.model_name, cast(dict[str, Any], self.components), self.device
)
self.components = cast(TransformersPipelineComponents, restored_components)

# 修正後
restored_components = ModelLoad.restore_model_to_cuda(
    self.model_name, cast(dict[str, Any], self.components), self.device
)
if restored_components is None:
    error_msg = f"Failed to restore model '{self.model_name}' to device '{self.device}'"
    logger.error(error_msg)
    raise ModelLoadError(error_msg, model_name=self.model_name)
self.components = cast(TransformersPipelineComponents, restored_components)
```

**ファイル2**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/transformers.py`

**変更内容**: `__enter__` メソッド（lines 61-68）

```python
# 修正前
restored_components = ModelLoad.restore_model_to_cuda(
    self.model_name,
    dict(self.components),
    str(self.device),
)
if not isinstance(restored_components, dict):
    raise TypeError("restored_componentsはdict型である必要があります。")

# 修正後
restored_components = ModelLoad.restore_model_to_cuda(
    self.model_name,
    dict(self.components),
    str(self.device),
)
if restored_components is None:
    error_msg = f"Failed to restore model '{self.model_name}' to device '{self.device}'"
    logger.error(error_msg)
    raise ModelLoadError(error_msg, model_name=self.model_name)
if not isinstance(restored_components, dict):
    raise TypeError("restored_componentsはdict型である必要があります。")
```

**影響**:
- restore 失敗時に明示的なエラー（ModelLoadError）を発生
- 後続の推論時の AttributeError を防止
- GUI レイヤーへ明確なエラーメッセージが伝播
- 既存の ModelLoadError 例外タイプを使用（新規例外型は不要）

**テスト**:
- ユニット: restore_model_to_cuda が None を返す場合の例外テスト
- 統合: `tests/integration/test_cuda_unavailable_scenarios.py`
  - CPU のみのシステムでの完全なアノテーションフロー
  - CUDA エラーが結果に含まれないことを確認

### Phase 4: ONNX アノテーターの確認

**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/onnx.py`

**分析結果**:
- ONNX アノテーターは `restore_model_to_cuda()` を呼び出さない
- Loader のデバイス検証のみに依存
- Phase 1 の変更により、BaseAnnotator でデバイス検証が行われるため一貫性が保証される
- **結論**: 変更不要

**テスト**: 統合テストで ONNX アノテーターの動作を確認

## 実装順序とリスク管理

### Iteration 1: デバイス検証（低リスク）
1. BaseAnnotator に `_validate_device()` 実装
2. デバイス検証のユニットテスト追加
3. 既存テストスイート実行（リグレッション確認）
4. **検証**: 全アノテータータイプでデバイスが正しく設定されることを確認

### Iteration 2: ログレベル修正（低リスク）
1. `_move_components_to_device()` で WARNING → ERROR 変更
2. `exc_info=True` でスタックトレースを含める
3. ログレベルのテスト期待値を更新
4. **検証**: ERROR ログが正しく出力されることを確認

### Iteration 3: エラーハンドリング（中リスク）
1. Pipeline.__enter__ に None チェック追加
2. Transformers.__enter__ に None チェック追加
3. エラー伝播のユニットテスト追加
4. CUDA 利用不可シナリオの統合テスト追加
5. **検証**: 例外が GUI レイヤーまで正しく伝播することを確認

### Iteration 4: GUI 検証（統合テスト）
1. LoRAIro GUI での完全なアノテーションフローをテスト
2. エラーメッセージが正しく表示されることを確認
3. 修正後にスコアが正しく表示されることを確認
4. **検証**: ユーザー体験が改善されていることを確認

## リスク評価と軽減策

### 高リスク: 既存機能の破壊
**リスク**: デバイス検証により動作が変わり、既存コードが壊れる

**軽減策**:
- 変更前に広範なユニットテストカバレッジを確保
- 全アノテータータイプでの統合テスト実施
- 段階的ロールアウト（テスト環境で最初に検証）
- ロールバック計画: BaseAnnotator 変更を戻し、ログ修正のみ維持

### 中リスク: パフォーマンス影響
**リスク**: 追加のデバイス検証がオーバーヘッドを増やす

**軽減策**:
- 検証は __init__ で一度だけ実行（コストは無視できる）
- `determine_effective_device()` は軽量（torch.cuda.is_available() の呼び出しのみ）
- 実際の影響をベンチマークで測定
- 予想される影響: アノテーター初期化あたり <1ms

### 低リスク: 例外タイプの非互換性
**リスク**: 新しい例外が GUI レイヤーのエラーハンドリングを壊す

**軽減策**:
- 既存の ModelLoadError 例外タイプを使用（新規型なし）
- GUI は既に一般的な例外を処理している
- エラー伝播の特定のテストを追加
- 新しい例外シナリオをドキュメント化

## 検証基準（成功条件）

### 機能要件
1. **デバイスの一貫性**: BaseAnnotator.device が Loader で使用される実際のデバイスと一致
2. **エラーの可視性**: デバイス失敗がスタックトレース付きで ERROR としてログされる
3. **明示的な失敗**: restore_model_to_cuda が None を返した場合に ModelLoadError を発生
4. **GUI 表示**: アノテーションエラーが GUI に明確に表示される

### 非機能要件
1. **パフォーマンス**: 有意なオーバーヘッドなし（<1% アノテーション時間増加）
2. **後方互換性**: 既存テストが最小限の変更（<5%）で合格
3. **コード品質**: 型ヒント維持、新しい type ignore コメントなし

### 期待される結果
1. CPU のみのシステムでデバイス移動試行ゼロ（ログ監視）
2. CUDA 失敗時の明確なエラーメッセージ（ユーザーフィードバック）
3. GUI でアノテーションスコアが正しく表示される（リグレッションテスト）
4. テストカバレッジ >75% 維持（pytest coverage レポート）
5. パフォーマンス劣化なし（<1% 遅延は許容）

## ロールバック計画

### Phase 1 で問題が発生した場合
1. BaseAnnotator._validate_device() 変更を戻す
2. ログレベル修正（Phase 2）は維持（低リスクのため）
3. デバイス不整合を既知の制限としてドキュメント化

### Phase 3 で問題が発生した場合
1. __enter__ メソッドのエラーハンドリング変更を戻す
2. 検証（Phase 1）とログ修正（Phase 2）は維持
3. None 戻り値を例外の代わりに WARNING としてログ

### 完全ロールバック
1. 全コミットを逆順で戻す
2. ログレベル変更のみ再適用（安全な場合）
3. GitHub Issue を作成し、将来の調査のため問題をドキュメント化

## 関連ファイル

### 変更対象
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/annotator.py` - デバイス検証追加
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory.py` - ログレベル変更
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/pipeline.py` - None チェック追加
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/transformers.py` - None チェック追加

### 参照（変更不要）
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/utils.py` - determine_effective_device()
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/onnx.py` - 確認のみ
- `local_packages/image-annotator-lib/src/image_annotator_lib/exceptions/errors.py` - ModelLoadError

### 新規作成
- `local_packages/image-annotator-lib/tests/unit/core/test_device_validation.py` - デバイス検証テスト
- `local_packages/image-annotator-lib/tests/integration/test_cuda_unavailable_scenarios.py` - CUDA 利用不可統合テスト

## 実装後の確認事項

1. **ログ出力の確認**: CPU のみの環境で WARNING ではなく適切な INFO ログが出力される
2. **エラー伝播**: GUI でエラーメッセージが明確に表示される
3. **スコア表示**: アノテーション実行後、GUI にスコアが正しく表示される
4. **パフォーマンス**: ベンチマークで性能劣化がないことを確認
5. **テストカバレッジ**: 75% 以上を維持していることを確認

## 参考情報

- **関連 Issue**: なし（この計画から Issue を作成可能）
- **関連 Memory**: 
  - `annotator_lib_lessons_learned` - 過去の教訓
  - `development_guidelines` - 開発ガイドライン
- **参考ドキュメント**: 
  - image-annotator-lib CLAUDE.md - プロジェクト固有のガイドライン
  - PyTorch CUDA ドキュメント - デバイス管理
