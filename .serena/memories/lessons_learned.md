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
  - **Serena**: コード/ドキュメントの読解、シンボル検索、要約、差分把握（高速・1秒未満）
  - **OpenClaw LTM**: 長期記憶、設計知識の永続化、過去の判断結果参照（Notion DB経由）
  - **Web検索 + OpenClaw補強**: ライブラリドキュメント取得（WebSearch/web.run → LTM保存時にOpenClawがContext7/Perplexityで補強）
  - **Note**: Context7 MCPは直接使用しない（Claude Code/Codex共通）

- **メモリ管理**:
  - 短期メモリ: `.serena/memories/`（Serenaが管理、プロジェクト固有）
  - 長期メモリ: OpenClaw LTM（Notion DB経由、クロスプロジェクト知識）
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
