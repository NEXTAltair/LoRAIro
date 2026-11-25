# Annotate async batch dispatch 射影と配線 実装計画(#884 Phase 2b+2c)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development。ステップはチェックボックス(`- [ ]`)で追跡する。

**Goal:** Annotate の選択モデル集合を async Provider Batch dispatch へ射影する Qt 非依存サービス(Phase 2b)を作成する。あわせて、`start_annotation` の `batch_api` 経路にワーカースレッドを配線し、`RunSettingsDialog` の dispatch mode 行を有効化する(Phase 2c)。これにより async batch がエンドツーエンドで動作する状態を実現する。

**Architecture:** ADR 0076 §2「async batch = 選択モデル集合の dispatch 射影」を実装する。Qt 非依存の `dispatch_projection_service` が discovery とヘルパーの積集合で batch 適格性を判定し、**非 batch-capable 混在時は (a) 拒否**とする。batch-capable モデル 1 台を 1 `DispatchEntry`(1 `provider_batch_jobs` 行に相当)へ射影する。GUI 側(Phase 2c)は射影結果を `AsyncBatchDispatchWorker`(`QThread`、ADR 0044 の busy・再入ガード付き)で受け取り、`submit_images` をループ呼び出しする。moderation preflight の**自動 2 段オーケストレーションは ADR 0076 line 54 および ADR 0070 に従い先送り**する。暫定的な fail-closed 整合として、ステージングに送信可(sendable)でない画像(保留または未判定)が含まれる場合は async dispatch を**拒否**する(既存の `classify_preflight_counts` を再利用)。

**Tech Stack:** Python(Qt 非依存サービス)、PySide6(QObject ワーカー / QDialog)、pytest / pytest-qt、Loguru

## 全体制約

- ADR 0076 を信頼源(SSoT)とする。射影には `provider_batch_capability` ヘルパーと `list_batch_capable_models()` の discovery を再利用し、判定ロジックを再実装しない。
- **非 batch-capable 混在時は (a) 拒否**とし(ユーザー確定 2026-06-24)、部分射影は行わない。
- 「1 submit = 1 model」の不変条件を守るため、サービスを改変せず `submit_images` をモデルごとにループ呼び出しする。
- 射影出力契約には **`model_id`(DB の `Model.id`)、`prompt_profile`、`description`、processed 画像パス(`image_paths`、ADR 0064)** を含める。
- moderation preflight の自動 2 段実行は**先送り**とする(ADR 0076 line 54)。暫定措置として、未 sendable 画像があれば dispatch を拒否する(fail-closed、ADR 0070)。
- 同期実行(`dispatch_mode == "sync"`)は**振る舞いを完全に維持する**。
- 型ヒント、モダンな Python 構文、Google スタイルの docstring、日本語コメント、最大行長 108 文字、Ruff、`# type: ignore` および `# noqa` 禁止を徹底する(`.claude/rules/coding-style.md`)。
- INFO ログはバッチサマリーのみとし、個別項目は DEBUG とする(`.claude/rules/logging.md`)。
- `QMessageBox` は `monkeypatch` でモック化し、ワーカースレッドには busy・再入ガードを設ける(ADR 0044)。
- ワークツリーは `.agents/worktree/issue-884-phase2bc`、ブランチは `feat/issue-884-phase2bc` を使用する。検証には CI 相当フィルタと `test_main_window_coverage.py` を用いる。

---

## Epic における位置づけ

- Phase 1(PR #898 マージ済み)および Phase 2a(PR #899 マージ済み)は完了している。本計画は Phase 2b と 2c を対象とする。
- 残タスクは Phase 3(Jobs submit 撤去による可視バグの構造解消)、Phase 4(wireframe v12 反映)、および moderation 自動 2 段実行のフォローアップである。

---

## ファイル構成

- `src/lorairo/services/dispatch_projection_service.py`(新規、Qt 非依存): `DispatchEntry`、`DispatchProjection`、`DispatchProjectionError`、`project_async_batch_dispatch(...)`。
- `src/lorairo/gui/workers/async_batch_dispatch_worker.py`(新規): `AsyncBatchDispatchWorker(QObject)`。射影エントリを `submit_images` でループ送信する。
- `src/lorairo/gui/widgets/run_settings_dialog.py`(改修): dispatch mode 行を有効化する(`enabled=True`)。
- `src/lorairo/gui/window/main_window.py`(改修): `start_annotation` の `batch_api` 分岐を `_dispatch_async_batch` へ実配線し、`{id: path}` ヘルパーを追加する。
- テスト: `tests/unit/services/test_dispatch_projection_service.py`(新規)、`tests/unit/gui/workers/test_async_batch_dispatch_worker.py`(新規)、`test_run_settings_dialog.py` および `test_main_window_coverage.py`(改修)。

---

### Task 1(2b): `dispatch_projection_service`(Qt 非依存)

選択モデル集合を discovery とヘルパーの積集合で判定し、非 batch-capable 混在時は (a) 拒否、適格なら N 個のエントリへ射影する純ロジックを実装する(詳細は実装を参照)。

ユニットテストでは以下を検証する。
- 正常時の N エントリ生成
- 非 batch-capable モデル混在時の拒否
- 未解決モデル時の拒否
- 空選択および空画像時の拒否
- `prompt_profile`、`description`、`image_paths` の同伴
- moderation 専用モデルに対する annotation route の拒否

### Task 2(2c): `AsyncBatchDispatchWorker`

エントリごとに `submit_images` を呼び出す `QObject` ワーカーを実装し、`succeeded(list[int])`、`failed(object)`、`finished()` シグナルを提供する。

ユニットテストでは、フェイクの `workflow_service` を使ってエントリ数だけ `submit_images` が呼ばれること、`job_ids` が発行されること、例外発生時に `failed` が発行されることを検証する。

### Task 3(2c): `RunSettingsDialog` の dispatch mode 有効化

`enabled=False` を有効状態へ変更し、Phase 2a で追加した disabled 期待のテストを enabled 期待へ更新する。

### Task 4(2c): `start_annotation` の `batch_api` 配線

`batch_api` 分岐で以下の流れを配線する。
1. `service_container` から `workflow_service`、`model_source`、`model_repo` を取得する。
2. ステージング済みの `{id: path}` と `image_ids` を取得する。
3. fail-closed ゲートとして `classify_preflight_counts` を実行し、未 sendable 画像があれば拒否する。
4. `project_async_batch_dispatch` を呼び出す(`DispatchProjectionError` は `QMessageBox.warning` で通知する)。
5. busy・再入ガードを確認した上で、`AsyncBatchDispatchWorker` を `QThread` で起動する。
6. 成功時に Jobs 台帳を更新し、サマリーを表示する。

ユニットテストでは以下を検証する。
- `batch_api` かつ全画像 sendable の場合に射影とワーカーが起動すること
- 未 sendable 画像が混在する場合に拒否されること
- 非 batch モデルを含む場合に拒否されること
- `sync` モードの振る舞いが変わらないこと
