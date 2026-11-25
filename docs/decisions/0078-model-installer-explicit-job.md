---
type: ADR
title: Model installer の明示ジョブ化 — 暗黙 HuggingFace DL を Jobs lifecycle へ
status: Accepted
timestamp: 2026-06-27
tags: [jobs, annotation, local-ml, iam-lib, worker]
---
# ADR 0078: Model installer の明示ジョブ化 — 暗黙 HuggingFace DL を Jobs lifecycle へ

- **関連 Issue**: #754(モデルインストーラの明示ジョブ化)
- **前 ADR**: 0066 §5(`job_type = "model_install"` の予約枠のみ定義。ダウンロードのジョブ化を本 ADR で確定する)
- **関連 ADR**: 0066(Unified Jobs Lifecycle View)、0040(Local ML Model Config Ownership)

## Context

ローカル ML モデル(WD Tagger、aesthetic scorer 等)を初回使用する際、`image-annotator-lib` が推論処理の内部で HuggingFace からモデルを暗黙的にダウンロードしていた。その結果、ユーザーからは数分間アプリがフリーズしたように見え、進捗の確認もキャンセルもできなかった。さらに、「推論が遅いのか」「ダウンロード中なのか」を区別する手段もなかった。

ADR 0066 §5 では `JOB_TYPE_MODEL_INSTALL = "model_install"` の予約枠だけを定義し、実装は `iam-lib` 側の新規バックエンド開発を伴うため別フェーズへ分離していた。本 ADR でその設計と実装方針を確定する。

## Decision

### 1. インストールジョブを推論ジョブの前段に発行する

`WorkerService.start_enhanced_batch_annotation()` は未インストールのモデルを検出すると、推論ジョブの前段に `model_install` ジョブを発行する。このインストールジョブは **GPU 直列スロット(ADR 0066 §6)で先行実行**する。

後続の推論ジョブは `queued` 状態で待機し、インストール完了後に実行を開始する。これにより、Jobs ライフサイクルビュー上で「インストールから推論へ」の実行順序が明示される。

### 2. インストール失敗・キャンセル時は後続の推論ジョブを取り消す

インストールジョブが失敗またはキャンセルされた場合、後続の推論ジョブはすべて取り消す。暗黙ダウンロードによるフリーズ挙動へ逆戻りさせないためである。

### 3. インストールワーカーの起動失敗時は従来フローへ縮退する

環境問題などにより `ModelInstallWorker` の起動自体が失敗した場合は、従来の暗黙ダウンロードフロー(`iam-lib` が推論中に自動ダウンロードする方式)へ縮退する。縮退時は `WARNING` ログを出力する。

この縮退経路の完全廃止は、`iam-lib` 側で暗黙ダウンロードを除去した後に行う。

### 4. iam-lib のインターフェース

`iam-lib` は次のインターフェースを提供する。

- `is_model_installed(model_class, config)`: インストールマーカーを用いた高速な導入済み判定を行う。
- `install_model(model_class, config, progress_cb, cancel_event)`: ダウンロードを実行し、進捗をバイト単位の集約値で報告する。
- `ModelInstallProgress`: `(downloaded_bytes, total_bytes)` のペアを表すデータ型である。
- `ModelInstallCancelledError`: キャンセル時に送出される例外である。

LoRAIro 側の `AnnotatorLibraryAdapter` は、バイト単位の進捗を整数パーセントのペアに正規化して `ModelInstallWorker` へ渡す。

### 5. Jobs 画面での表示と操作

ダウンロード進捗は、台帳のサマリー列に `<model> をダウンロード中 45% (350.0/780.0 MB)` の形式で表示する。テーブルの再描画を抑えるため、整数パーセントが変化したタイミングでのみ更新を通知する。キャンセル操作には、既存の Jobs 行のキャンセルボタンをそのまま利用する。

### 6. OperationType と job_type の対応

```python
OperationType.MODEL_INSTALL  # = JOB_TYPE_MODEL_INSTALL = "model_install" (ADR 0066 §5 予約枠の実装)
```

## Consequences

- ユーザーはモデルのダウンロード進捗の確認とキャンセルを Jobs ビュー上から操作できる。
- インストールジョブが失敗した際に後続の推論ジョブが自動取り消しされるため、フリーズ挙動へ逆戻りしない。
- インストールワーカーの起動失敗時のみ従来フローへの縮退が残る(完全廃止には `iam-lib` 側の暗黙ダウンロード除去が必要である)。
- `main_window` への変更は不要であり、`JobsTabWidget` の既存キャンセルボタンを再利用できる。
