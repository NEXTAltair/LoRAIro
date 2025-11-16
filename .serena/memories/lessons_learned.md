# 学習した教訓

このメモリは、プロジェクト開発中に学んだ重要なパターン、設計上の好み、プロジェクト固有の知見を記録するものです。開発が進むにつれて更新される生きたドキュメントです。

## アーキテクチャ関連

- **状態管理**: `DatasetStateManager`を使用して集中的な状態管理を行う。以前の`WorkflowStateManager`は非推奨となり、使用されていない。

## コード構造

- **デッドコード**: `src/lorairo/gui/state/workflow_state.py`はデッドコードとして特定されている。このモジュールの機能は`DatasetStateManager`に吸収されたか、更新されたGUIアーキテクチャでは不要と判断された。このようなデッドコードは削除すべき。
- **段階的リファクタリング**: MainWindowのような巨大UIクラスは「責務ごとにController/Serviceを抽出→MainWindowはイベント配線とDIのみに集中」というフェーズ分割で削減する。Phase 1: サービス層抽出、Phase 2: Controller導入、Phase 3: 仕上げ削減という順番が安全。
- **依存性注入の徹底**: Controller/Serviceを導入する際はServiceContainer経由で依存解決することで、PySide6固有ロジックとドメインロジックを分離しテスタビリティを確保する。

## 開発プラクティス

- **MCPエージェントの役割分担**:
  - **serena**: コード/ドキュメントの読解、要約、差分把握、計画草案作成
  - **cipher**: 実装/編集、コマンド実行、他MCP呼出、ドキュメント/タスク反映

- **メモリ管理**:
  - 機械メモリの原本: `.serena/memories/`（serenaが管理、2025-11以降はここに集約）
  - 長期知識/教訓: Cipher長期記憶（ByteRover playbook等）に即時転記
  - tasks/ ディレクトリやad-hocドキュメントは廃止済み。計画・進行も `.serena/memories/` へ記録する

## エラー処理とロギング

- **ロギングレベル**:
  - INFO: ユーザー操作や主要な処理の開始・終了
  - WARNING/ERROR/CRITICAL: 例外発生時、想定外の分岐、リトライ発生時
  - DEBUG: 開発・デバッグ時のみ、詳細な変数値や分岐の記録

- **例外処理**:
  - 例外をキャッチしたら`logger.error(..., exc_info=True)`でトレースバックを記録
  - 回復不可能な例外は`raise`で再送出し、上位でハンドリング
  - 回復可能な場合はエラー内容と対応をINFO/WARNINGで記録
