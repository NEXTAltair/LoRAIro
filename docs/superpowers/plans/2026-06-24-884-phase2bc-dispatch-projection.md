# Annotate async batch dispatch 射影 + 配線 実装計画 (#884 Phase 2b+2c)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development。Steps は checkbox (`- [ ]`)。

**Goal:** Annotate の選択モデル集合を async Provider Batch dispatch へ射影する Qt-free service (2b) を作り、`start_annotation` の `batch_api` 経路に worker thread 配線 + RunSettingsDialog の dispatch mode 行 enable (2c) を行う。これにより async batch が end-to-end で動く。

**Architecture:** ADR 0076 §2「async batch = 選択モデル集合の dispatch 射影」。Qt-free service `dispatch_projection_service` が discovery ∩ helper で batch 適格を判定し、**非 batch-capable 混在は (a) 拒否**、batch-capable モデル1台 = 1 `DispatchEntry` (= 1 `provider_batch_jobs` 行) へ射影する。GUI 側 (2c) は射影結果を `AsyncBatchDispatchWorker` (QThread, ADR 0044 busy/再入ガード) で `submit_images` ループ呼び出しする。moderation preflight の **自動2段オーケストレーションは ADR 0076 line 54 / ADR 0070 に従い deferral**。interim の fail-closed 整合として、staging に「送信可 (sendable)」でない画像 (保留/未判定) が含まれる場合は async dispatch を**拒否**する (既存 `classify_preflight_counts` を再利用)。

**Tech Stack:** Python (Qt-free service), PySide6 (QObject worker / QDialog), pytest / pytest-qt, Loguru。

## Global Constraints

- ADR 0076 が SSoT。射影は `provider_batch_capability` helper + `list_batch_capable_models()` discovery を再利用し、判定を再実装しない。
- **非 batch-capable 混在は (a) 拒否** (ユーザー確定 2026-06-24)。部分射影しない。
- 1 submit = 1 model 不変条件: `submit_images` をモデルごとにループ呼び出し (service 改変ゼロ)。
- 射影出力契約に **model_id (DB Model.id) / prompt_profile / description / processed 画像パス (image_paths, ADR 0064)** を含める。
- moderation preflight 自動2段は **deferral** (ADR 0076 line 54)。interim は未 sendable 画像があれば dispatch 拒否 (fail-closed, ADR 0070)。
- 同期 (`dispatch_mode == "sync"`) は **behavior 完全不変**。
- 型ヒント必須・modern Python 構文・Google-style docstring・日本語コメント・行長 108・Ruff・`# type: ignore`/`# noqa` 禁止 (`.claude/rules/coding-style.md`)。
- INFO はバッチサマリーのみ・per-item は DEBUG (`.claude/rules/logging.md`)。
- QMessageBox は monkeypatch でモック。worker thread は busy/再入ガード (ADR 0044)。
- worktree `.agents/worktree/issue-884-phase2bc` / branch `feat/issue-884-phase2bc`。検証は CI-equivalent filter + `test_main_window_coverage.py`。

---

## Epic 位置づけ

- Phase 1 (#898 merge), Phase 2a (#899 merge) 完了。本計画 = Phase 2b + 2c。
- 残: Phase 3 (Jobs submit 撤去, 可視バグ構造解消), Phase 4 (wireframe v12), moderation 自動2段 follow-up。

---

## File Structure

- `src/lorairo/services/dispatch_projection_service.py` (新規, Qt-free): `DispatchEntry` / `DispatchProjection` / `DispatchProjectionError` / `project_async_batch_dispatch(...)`。
- `src/lorairo/gui/workers/async_batch_dispatch_worker.py` (新規): `AsyncBatchDispatchWorker(QObject)`。射影 entries を `submit_images` でループ submit。
- `src/lorairo/gui/widgets/run_settings_dialog.py` (改修): dispatch mode 行を enable (`enabled=True`)。
- `src/lorairo/gui/window/main_window.py` (改修): `start_annotation` の `batch_api` 分岐を実配線 (`_dispatch_async_batch`)。`{id: path}` ヘルパー追加。
- tests: `tests/unit/services/test_dispatch_projection_service.py` (新規), `tests/unit/gui/workers/test_async_batch_dispatch_worker.py` (新規), `test_run_settings_dialog.py` / `test_main_window_coverage.py` (改修)。

---

### Task 1 (2b): dispatch_projection_service (Qt-free)

純ロジック。selection → discovery ∩ helper → (a) 拒否 → N entries。詳細は実装参照。
unit test: 正常 N entries / 非 batch 混在拒否 / 未解決拒否 / 空選択・空画像拒否 / prompt_profile・description・image_paths 同伴 / moderation 専用モデルは annotation route 拒否。

### Task 2 (2c): AsyncBatchDispatchWorker

`submit_images` をentry ごとに呼ぶ QObject worker。`succeeded(list[int])` / `failed(object)` / `finished()`。
unit test: fake workflow_service で entry 数だけ submit_images 呼び出し・job_ids emit・例外時 failed emit。

### Task 3 (2c): RunSettingsDialog dispatch mode enable

`enabled=False` → enable。2a の disabled テストを enabled 期待へ更新。

### Task 4 (2c): start_annotation batch_api 配線

`batch_api` 分岐で: service_container から workflow_service / model_source / model_repo 取得 → staged {id:path} + image_ids → fail-closed gate (classify_preflight_counts、未 sendable があれば拒否) → `project_async_batch_dispatch` (DispatchProjectionError は QMessageBox.warning) → busy/再入ガード → `AsyncBatchDispatchWorker` を QThread 起動 → 成功で Jobs ledger refresh + サマリー。
unit test: batch_api + 全 sendable → projection+worker 起動 / 未 sendable 混在 → 拒否 / 非 batch model → 拒否 / sync は不変。
