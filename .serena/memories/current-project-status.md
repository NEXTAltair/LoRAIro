# image-annotator-lib Project Status

**最終更新**: 2025-11-21

## 現在の状態

### DevContainer環境 Test Explorer修正完了（2025-11-21）

- **問題**: ローカルパッケージ内の独立.venvがVSCode Test Explorerを妨害
- **原因**: `local_packages/image-annotator-lib/.venv/` の存在がCLAUDE.md「Virtual Environment Rules」に違反
- **修正内容**:
  - ローカルパッケージ.venv削除
  - lorairo.code-workspace: マルチフォルダー → 単一フォルダー構成
  - devcontainer.json: postCreateCommandに自動クリーンアップ追加
- **検証結果**: pytest 1472個のテスト収集成功、coverage正常動作
- **詳細**: `vscode_test_explorer_fix_20251020` メモリ更新済み

### MainWindow Phase 3 完了（2025-11-19）

- MainWindow行数: 1,645行 → 688行（**58.2%削減**）
- Phase 3削減: 802行 → 688行（114行削減、目標100行超過達成）
- 完了内容: イベントハンドラー統合 + 初期化ロジック簡素化 + HybridAnnotationController削除
- テスト: 15/15成功（MainWindow関連統合テスト）
- 詳細: `mainwindow_phase3_completion_2025_11_19`

### MainWindow Phase 2 完了（2025-11-15）

- MainWindow行数: 1,645行 → 887行（46.1%削減）
- 抽出済みコンポーネント: Controller 5件 + Service 6件（詳細: `mainwindow_refactoring_phase2_completion_2025_11_15`）
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
- `mainwindow_phase3_completion_2025_11_19`：Phase 3（118行削減、目標達成）完了記録
- `mainwindow_phase3_analysis_2025_11_19`：Phase 3 分析記録
- `mainwindow_refactoring_phase2_completion_2025_11_15`：Phase 2（サービス/コントローラー分離）まとめ
- `mainwindow_customwidgets_investigation_2025`：カスタムウィジェット初期化エラー調査
- `mainwindow_initialization_issue_2025_11_17`：初期化問題の診断と修正記録

### テスト戦略 / 個別タスク
- `test_pydantic_ai_factory_integration_completion_2025_11_07`：PydanticAIファクトリ統合テスト
- `test_strategy_policy_change_2025_11_06` / `test_fixes_and_improvements_2025` など：テスト方針・修正履歴

## 次のタスク

### MainWindow Phase 4: テスト・ドキュメント強化（推奨）

1. MainWindow初期化パスの包括的テスト追加
2. Service委譲パターンのカバレッジ向上（目標75%維持）
3. 5段階初期化パターンの文書化
4. Service/Controller層の責任分離ガイドライン作成

### テスト継続

1. `test_pydantic_ai_factory_integration.py` の最終仕上げ（キャッシュ戦略を含む）
2. `test_cross_provider_integration.py` でマルチプロバイダーフロー検証
3. 既存25件のTensorFlow/GUI失敗ケースの恒久対策

## アーキテクチャ状態

- **MainWindow**: 688行（Phase 3完了、58.2%削減）
- **Controller/Service層**: MainWindowから分離され、依存性注入で疎結合化
- **イベント委譲**: Service別ヘルパーメソッド（3つ）で統一的に管理
- **PipelineControlService + ProgressStateService**: 非同期ワークフローと進捗表示を横断管理
- **ProviderManager + PydanticAI層**: 安定稼働。agentキャッシュとリソース共有ポリシーは `phase5_integration_tests_completion_2025_11_09` を参照

## 開発方針

- **Memory-First Development**: すべての決定・手順は `.serena/memories/`（短期）と Cipher（長期）に記録。tasks/やad-hocドキュメントには戻さない
- **Command-Based Workflow**: `/check-existing` → `/plan` → `/implement` → `/test` を維持し、Serenaは整理・記録、Cipherは実装/検証に専念
- **YAGNI原則**: 過剰な抽象化を避け、必要最小限の実装を維持
