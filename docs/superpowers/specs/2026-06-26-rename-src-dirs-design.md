# src/lorairo ディレクトリ/モジュール改名 — 設計仕様

**日付:** 2026-06-26
**対象リポジトリ:** LoRAIro
**ステータス:** Approved
**関連 Issue:** [#717](https://github.com/NEXTAltair/LoRAIro/issues/717)

---

## 背景と目的

`src/lorairo/` 配下のディレクトリ名の一部が役割を正確に表現しておらず、新規コントリビュータの誤解を招く。特に `api/` は HTTP/REST API と混同されやすい（実態は CLI/GUI/外部ツール向けの公開インターフェース層）。一部モジュール名も曖昧（`annotation_logic.py` の "logic" はノイズ語、`existing_file_reader.py` は何を読むか不明）。

**目的:** ディレクトリ名・モジュール名を実態に即した説明的な名前へ機械的に改名し、リーダビリティとオンボーディング効率を上げる。ロジック変更は伴わない。

---

## 設計概要

### メカニクス: ハードリネーム（deprecation shim なし）

LoRAIro は配布ライブラリではなくアプリケーションで、`lorairo.api` 等を import する外部利用者は存在しない。よって旧パスを re-export で残す deprecation shim は cruft になるだけなので採用しない。

- `git mv` でディレクトリ/ファイルを移動し blame 履歴を温存
- 機械的に import 行を一括置換（`lorairo.<old>` → `lorairo.<new>`）
- 移行期の二重パスを残さない

### 分割: 1 ディレクトリ = 1 サブPR、優先度順に直列

`utils/`・`domain/` は対象外（名前は適切）。改名対象4ディレクトリを優先度順に1本ずつ実装・検証・merge する。各サブPR後に `make mypy` + CI-equivalent filter で regression なしを確認 → merge → 次サブを `origin/main` に rebase。

衝突面の実測: 対象2ディレクトリを跨いで import するファイルは約10個（最大2ディレクトリまで、3つ以上跨ぐファイルは無し）。`storage` が他と共起しやすいため**最後に回して** rebase 巻き込みを最小化する。

### 実行モデル: 直列・リード単独

並列（Agent Teams）は採用しない。理由:

1. **PR は main へ1本ずつしか merge できない**（CI/レビューが直列）ため、並列化で短縮できるのは「diff 生成」という機械作業のみでボトルネックは縮まらない。
2. **editable install + 共有 venv で worktree 内のローカル検証が無効化される**（worktree から `mypy -p lorairo` / `pytest` を共有 venv で走らせると main checkout のコードを検証してしまう。真偽は push 後 CI が SSoT）。
3. **並列 `uv sync` が共有 `.venv` を破壊する**（Issue #222）。

リード（実装者）が4サブPRを優先度順に順次処理する。

---

## 改名内容

| 順 | サブPR | 改名 | 影響 |
|---|---|---|---|
| 1 | `api/` → `public_api/` | ディレクトリのみ。内部 facade モジュール（`images.py`/`tags.py`/`project.py`/`export.py`/`batch_import.py`/`types.py`/`exceptions.py`/`annotations.py`）はリソース指向で既に説明的なので**据え置き**（網羅レビューの結果「適切」と判断） | 35 files |
| 2 | `editor/` → `image_transforms/` | ディレクトリのみ。`autocrop.py`(AutoCrop) / `upscaler.py`(Upscaler) / `image_processor.py`(ImageProcessingManager, ImageProcessor) は**据え置き** | 7 files |
| 3 | `annotations/` → `annotation/` | ディレクトリ単数化 + モジュール改名（下記） | 12 files |
| 4 | `storage/` → `filesystem.py` | ディレクトリを廃して単一モジュールへ平坦化。`from lorairo.filesystem import FileSystemManager`（`FileSystemManager` クラス名は維持） | 24 files |

### サブPR3 のモジュール改名詳細

| 現 | 新 | 理由 |
|---|---|---|
| `annotation_logic.py` / `AnnotationLogic` | `annotation_runner.py` / `AnnotationRunner` | `execute_annotation` でアノテーション実行を統括するランナー。ノイズ語 "logic" を排除 |
| `existing_file_reader.py` / `ExistingFileReader` | `sidecar_reader.py` / `SidecarAnnotationReader` | `.txt`/`.caption` サイドカーファイルからの既存アノテーション読取を明示 |
| `annotator_adapter.py` / `AnnotatorLibraryAdapter` | 据え置き | 既に image-annotator-lib アダプタと読める |

### 命名判断のメモ

- `annotations/` → **`annotation/`**（単数）。当初「AI であることが読めない」が不満点だったが、当ディレクトリはサイドカー読取（非AI処理）も含むアノテーション処理全般であり、`ai_annotation/` は不正確。`database`/`domain` と整合する単数形が実態に合う。
- `storage/` の `file_system.py` は1ファイルのみのため、ディレクトリを維持せず単一モジュール `filesystem.py` へ平坦化するのが最も正直。

---

## 各サブPR の手順

各サブPR共通（[.claude/rules/git-workflow.md](../../../.claude/rules/git-workflow.md) / [testing.md](../../../.claude/rules/testing.md) 準拠）:

1. `origin/main` から worktree を切る（`git worktree add .agents/worktree/issue-717-<dir> -b refactor/issue-717-<dir> origin/main`）
2. `git mv` でディレクトリ/モジュールを移動
3. import 行を一括置換（`src/` + `tests/` + `docs/`）。クラス名変更を伴うサブPR3 は対象シンボルも置換
4. `make mypy` + CI-equivalent filter（`-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`）で regression なし確認
5. commit & push → PR 起票（`Closes #717` はサブPR4 のみ、1〜3 は `Refs #717`）
6. CI green + bot レビュー safe を確認して squash merge
7. 次サブPRの worktree を `origin/main` に rebase
8. 全サブPR merge 後に worktree を削除

### 検証スコープ補足

import 改名は GUI / services / cli / tests 横断に及ぶため、CI-equivalent filter に加えて改名ディレクトリを参照するテストモジュール（特にサブPR3 のアノテーション系、サブPR4 の FileSystemManager 利用テスト）が collection エラーを起こさないことを確認する。

---

## 影響範囲チェックリスト

- `src/lorairo/` 配下の全 `import` 文
- `tests/` の対応パス・mock パッチパス（`@patch("lorairo.<old>...")` の文字列も置換対象。実測で tests 配下に64箇所）
- `docs/services.md` / `docs/integrations.md` 等のドキュメント参照
- `pyproject.toml`: 実測の結果、対象ディレクトリ名への実パス参照は無し（マッチは無関係な pytest マーカー名・qt 設定のみ）。**更新不要**

ロジック変更ゼロ。差分は import パスとファイル位置のみ。
