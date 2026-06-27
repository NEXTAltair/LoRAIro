---
type: ADR
title: Model installer の明示ジョブ化 — 暗黙 HuggingFace DL を Jobs lifecycle へ
status: Accepted
timestamp: 2026-06-27
tags: [jobs, annotation, local-ml, iam-lib, worker]
---
# ADR 0078: Model installer の明示ジョブ化 — 暗黙 HuggingFace DL を Jobs lifecycle へ

- **関連 Issue**: #754 (Model installer 明示ジョブ化)
- **前 ADR**: 0066 §5 — `job_type = "model_install"` 予約枠のみ定義、DL の job 化を本 ADR で確定
- **関連 ADR**: 0066 (Unified Jobs Lifecycle View), 0040 (Local ML Model Config Ownership)

## Context

ローカル ML モデル (WD Tagger、aesthetic scorer 等) の初回使用時、image-annotator-lib が推論中に HuggingFace から暗黙にモデルをダウンロードしていた。ユーザーには数分間フリーズしたように見え、進捗もキャンセル手段もなく「推論が遅い」のか「DL 中」なのか区別できなかった。

ADR 0066 §5 は `JOB_TYPE_MODEL_INSTALL = "model_install"` の予約枠のみを定義し、実装を「iam-lib 側バックエンド新規を伴うため別 Phase」に分離していた。本 ADR でその判断を確定する。

## Decision

### 1. install ジョブを推論ジョブの前段に発行する

`WorkerService.start_enhanced_batch_annotation()` は未インストールモデルを検出すると、推論ジョブの前段に `model_install` ジョブを **GPU 直列スロット (ADR 0066 §6) で先行実行**する。後続の推論ジョブは `queued` 状態で待機し、install 完了後に推論を開始する。Jobs lifecycle ビュー上で「install → 推論」の順序が明示される。

### 2. install 失敗 / キャンセル時は後続推論ジョブを取り消す

install ジョブが失敗またはキャンセルされた場合、後続の推論ジョブはすべて取り消す。暗黙 DL によるフリーズへ逆戻りさせない。

### 3. install ワーカー起動失敗時は従来フローに縮退

`ModelInstallWorker` の起動自体が失敗した場合（環境問題等）は、従来の暗黙 DL フロー（iam-lib が推論中に自動 DL）に縮退する。縮退時は WARNING ログを出す。縮退を完全廃止するのは iam-lib 側で暗黙 DL を除去してからとする。

### 4. iam-lib インターフェース

iam-lib が提供するインターフェース:
- `is_model_installed(model_class, config)` — install marker による高速判定
- `install_model(model_class, config, progress_cb, cancel_event)` — DL 実行。進捗は byte 集約で報告
- `ModelInstallProgress` — `(downloaded_bytes, total_bytes)` ペア
- `ModelInstallCancelledError` — キャンセル時の例外

LoRAIro 側の `AnnotatorLibraryAdapter` は byte 単位の進捗を整数 % ペアに正規化して `ModelInstallWorker` へ渡す。

### 5. Jobs 表示

進捗は台帳サマリー列に `<model> をダウンロード中 45% (350.0/780.0 MB)` 形式で反映する。整数 % 変化時のみ通知してテーブル再描画を抑制する。キャンセルは既存の Jobs 行ボタンがそのまま機能する。

### 6. OperationType と job_type の対応

```python
OperationType.MODEL_INSTALL  # = JOB_TYPE_MODEL_INSTALL = "model_install" (ADR 0066 §5 予約枠の実装)
```

## Consequences

- ユーザーは DL 進捗 / キャンセルを Jobs ビューで操作できる
- install ジョブが失敗したとき後続推論ジョブは自動取り消しになり、フリーズへ逆戻りしない
- install ワーカー起動失敗時のみ従来フロー縮退が残る（iam-lib 側の暗黙 DL 除去が前提条件）
- `main_window` への変更はゼロ（JobsTabWidget の既存 cancel ボタンが再利用される）
