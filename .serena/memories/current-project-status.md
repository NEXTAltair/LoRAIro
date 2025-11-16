# image-annotator-lib Project Status

**最終更新**: 2025-11-15

## 現在の状態

### MainWindow Phase 2 完了（2025-11-15）

- MainWindow行数: 1,645行 → 887行（46.1%削減）
- 抽出済みコンポーネント: Controller 5件 + Service 6件（詳細: `mainwindow_refactoring_phase2_completion_2025_11_15`）
- Phase 3（追加削減）は任意としてスキップ。残りの責務はサービス初期化とシグナル配線に集中
- 統合テスト: 417 pass / 25 fail（いずれも既存のTensorFlow & GUI課題）

### Phase 5 統合テスト状況（2025-11-09）

- 新規統合テスト 8件追加でGUI/Providerフローの回帰を保護
- Phase 5総括: `phase5_integration_tests_completion_2025_11_09`

### タスク管理の変更（2025-11-06）

- tasks/ ディレクトリ廃止、すべての進行ログは `.serena/memories/` + Cipher長期記憶へ移行
- 詳細: `tasks_directory_removal_2025_11_06`

## フェーズ索引

### Phase 2 – image-annotator-lib 品質改善
- `phase2_completion_comprehensive_record_2025`：Phase 2 全体のまとめ（例外階層 / ErrorHandler / メッセージ標準化 / カバレッジ）
- `phase2_tasks_1_2_completion_2025_10_25`：Task 1-2（失敗テスト修正、API互換性検証）
- `phase2_task2_1_provider_execution_tests_completion_2025_11_06`：プロバイダー実行パステスト追加
- `phase2_task2_2_error_handling_tests_completion_2025_11_06`：エラーハンドリング境界テスト
- `phase2_task2_3_coverage_configuration_fix_2025_11_06` / `phase2_task2_3_torch_environment_issue_2025_11_07` / `phase2_torch_coverage_solution_2025_11_08`：カバレッジ設定修正とtorch課題
- `phase2_cross_provider_tests_extension_2025_11_07`：クロスプロバイダー統合テスト拡張

### Phase 3 – テスト安定化（P1〜P4）
- `phase3_p1_p2_completion_2025_10_31`：モデルファクトリ系ユニットテスト追加とGoogle API修正
- `phase3_p3_1_test_isolation_fixes_2025_10_31`：テスト隔離対応（Memory/Env系）
- `phase3_p3_3_to_p3_5_completion_2025_11_03`：Transformers/WebAPI テスト修復とskip整理
- `phase3_p3_6_completion_2025_11_03`：test_base.py & CLIPテスト修正
- `phase3_p3_6_and_p4_completion_2025_11_03`：P3.6最終まとめ + P4スキップ分析

### Phase 4 – image-annotator-lib 統合
- `phase4_completion_record_2025_11_08`：Phase 4 全体まとめ
- `phase4_task4_5_api_key_management_completion_2025_11_08`：APIキー引数化とテスト

### Phase 5 – GUI/Worker 統合テスト
- `phase5_integration_tests_completion_2025_11_09`：MainWindow/WorkerService の統合テスト計画と結果

### MainWindow リファクタリング
- `mainwindow_refactoring_phase2_completion_2025_11_15`：Phase 2（サービス/コントローラー分離）まとめ
- `mainwindow_customwidgets_investigation_2025`：カスタムウィジェット初期化エラー調査

### テスト戦略 / 個別タスク
- `test_pydantic_ai_factory_integration_completion_2025_11_07`：PydanticAIファクトリ統合テスト
- `test_strategy_policy_change_2025_11_06` / `test_fixes_and_improvements_2025` など：テスト方針・修正履歴

## 次のタスク

### MainWindow後続（任意）

1. Phase 3再開: 初期化ロジック整理と追加のController/Service分離（推定100行削減余地）
2. HybridAnnotationControllerの完全削除（未使用God class）
3. 進捗/状態系Serviceの単体テスト強化（現状75%ラインを維持）

### テスト継続

1. `test_pydantic_ai_factory_integration.py` の最終仕上げ（キャッシュ戦略を含む）
2. `test_cross_provider_integration.py` でマルチプロバイダーフロー検証
3. 既存25件のTensorFlow/GUI失敗ケースの恒久対策

## アーキテクチャ状態

- Controller/Service層がMainWindowから分離され、依存性注入で疎結合化
- PipelineControlService + ProgressStateServiceで非同期ワークフローと進捗表示を横断管理
- ProviderManager + PydanticAI層は安定稼働。agentキャッシュとリソース共有ポリシーは `phase5_integration_tests_completion_2025_11_09` を参照

## 開発方針

- **Memory-First Development**: すべての決定・手順は `.serena/memories/`（短期）と Cipher（長期）に記録。tasks/やad-hocドキュメントには戻さない
- **Command-Based Workflow**: `/check-existing` → `/plan` → `/implement` → `/test` を維持し、Serenaは整理・記録、Cipherは実装/検証に専念
