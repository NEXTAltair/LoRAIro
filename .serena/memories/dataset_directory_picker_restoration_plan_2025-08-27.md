# データセットディレクトリ選択→データベース登録機能復旧実装計画

## プランニング完了概要
- **日付**: 2025-08-27
- **対象機能**: データセットディレクトリ選択→自動データベース登録
- **推奨アプローチ**: 最小修正アプローチ（Phase 1）
- **予想実装時間**: 2時間
- **必要変更量**: 15-20行の追加

## Memory-First分析結果

### 過去設計事例確認
- **ThumbnailSelectorWidget リファクタリング事例**: 責任分離・シグナル統合パターンの参考
- **レガシー負債完全排除**: 実証済みアプローチの適用可能性確認

### プロジェクト固有設計状況
- **WorkerService**: production-ready実装完了
- **DatabaseRegistrationWorker**: スレッドセーフ・バッチ処理対応完了
- **MainWindow統合**: わずか2箇所の追加で復旧可能

## 現状分析結果

### 完全実装済みコンポーネント ✅
1. **WorkerService.start_batch_registration**: UUID-based worker管理、進捗シグナル完備
2. **DatabaseRegistrationWorker**: QImage-basedスレッドセーフ実装、バッチ処理対応
3. **DirectoryPickerWidget**: validDirectorySelectedシグナル、履歴・検証機能付き
4. **テスト基盤**: QFileDialogモック化パターン実装済み

### 実装不足箇所 ❌
1. **MainWindow.select_dataset_directory**: QFileDialog表示のみで後続処理なし
2. **MainWindow.register_images_to_db**: 空実装（ログ出力のみ）
3. **バッチ登録シグナル接続**: 完了・エラーハンドリング未接続

## 推奨ソリューション：最小修正アプローチ

### 選択理由
1. **基盤システム完全性**: WorkerService + DatabaseRegistrationWorker は production-ready
2. **リスク最小化**: わずか15-20行の追加で既存機能への影響ゼロ
3. **即効性**: 最短時間での機能復旧
4. **実証済みパターン**: 既存アーキテクチャと完全一致

### 他アプローチとの比較
- **統合フローアプローチ**: より堅牢だが実装複雑度高（Phase 2候補）
- **DirectoryPickerWidget統合**: 高機能だがUI変更リスク（将来実装候補）
- **段階的実装**: 過剰設計で現要件に不適切

## 詳細実装計画

### Phase 1: select_dataset_directory メソッド拡張
**対象**: `src/lorairo/gui/window/main_window.py:495-513`
- QFileDialog後に `WorkerService.start_batch_registration` 呼び出し追加
- エラーハンドリング（WorkerService未初期化対策）
- 進捗表示連携（既存プログレスバー活用）

### Phase 2: バッチ登録シグナル接続
**対象**: `src/lorairo/gui/window/main_window.py` の `_initialize_services`
- `batch_registration_finished` シグナル接続
- `batch_registration_error` シグナル接続
- 完了・エラー処理メソッド実装

### Phase 3: register_images_to_db 実装
**対象**: `src/lorairo/gui/window/main_window.py:515-517`
- `select_dataset_directory` への転送で対応

### Phase 4: テスト拡張
**対象**: `tests/gui/test_main_window_qt.py`
- 既存QFileDialogモック化テストの拡張
- バッチ登録統合テストの追加

## テスト戦略

### 3階層テスト設計
1. **単体テスト**: MainWindow個別メソッドのテスト
2. **統合テスト**: WorkerService + DatabaseRegistrationWorker連携テスト
3. **GUIテスト**: ユーザーインタラクション全体のテスト

### 特別考慮事項
- **パフォーマンステスト**: 大量データセット処理（1000件）
- **エラーシナリオテスト**: WorkerService未初期化、無効ディレクトリ等
- **既存テスト互換性**: 回帰防止

## 実装タイムライン

| Phase | 作業内容 | 時間 | 成果物 |
|-------|---------|------|--------|
| 1 | select_dataset_directory拡張 | 30分 | ディレクトリ選択→登録開始 |
| 2 | シグナル接続・完了処理 | 45分 | エラーハンドリング・進捗表示 |
| 3 | register_images_to_db実装 | 15分 | ボタン統合完了 |
| 4 | テスト追加・検証 | 30分 | 品質確保・回帰防止 |
| **合計** | | **2時間** | **完全機能復旧** |

## リスク分析

### 低リスク要因
- 既存パターン踏襲（WorkerService統合は実証済み）
- 最小変更（15-20行追加で既存機能影響ゼロ）
- 完全なバックエンド（DatabaseRegistrationWorkerは production-ready）

### 潜在リスク・対策
- **WorkerService未初期化**: エラーハンドリング実装済み
- **メモリリーク**: Qtシグナル接続適切管理
- **UI応答性**: ワーカーパターンでUIスレッドブロック回避

## 将来拡張計画

### Phase 2: 品質向上（オプション）
- 統合フローアプローチの検証・進捗表示強化
- バッチ処理パイプライン基盤構築

### Phase 3: 高機能化（将来）
- DirectoryPickerWidget統合による履歴・自動完了機能
- UI全体モダナイゼーションと合わせた実施

## 次ステップ
本計画承認後、`/implement` コマンドで段階的実装を開始。最小修正アプローチにより、確実かつ迅速な機能復旧を実現します。