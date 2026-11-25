# `src/lorairo` ディレクトリ・モジュール改名 — 設計仕様

**日付:** 2026-06-26  
**対象リポジトリ:** LoRAIro  
**ステータス:** Approved  
**関連 Issue:** [#717](https://github.com/NEXTAltair/LoRAIro/issues/717)

---

## 背景と目的

`src/lorairo/` 配下の一部のディレクトリ名が役割を正確に表しておらず、新規コントリビュータの誤解を招いている。特に `api/` は HTTP/REST API と混同されやすいが、実態は CLI、GUI、外部ツール向けの公開インターフェース層である。一部のモジュール名も曖昧であり、`annotation_logic.py` の「logic」はノイズ語、`existing_file_reader.py` は何を読むのかが分かりにくい。

**目的:** ディレクトリ名とモジュール名を実態に即した説明的な名前へ機械的に改名し、可読性とオンボーディング効率を高める。ロジック変更は一切行わない。

---

## 設計概要

### メカニクス: ハードリネーム(deprecation shim なし)

LoRAIro は配布ライブラリではなくアプリケーションであり、`lorairo.api` などをインポートする外部利用者は存在しない。旧パスを再エクスポートで残す deprecation shim は不要な負債になるだけなので採用しない。

- `git mv` でディレクトリ・ファイルを移動し、blame 履歴を温存する。
- インポート行を機械的に一括置換する(`lorairo.<old>` → `lorairo.<new>`)。
- 移行期の二重パスを残さない。

### 分割: 1 ディレクトリ = 1 サブ PR、優先度順に直列

`utils/` と `domain/` は名前が適切であるため対象外とする。改名対象の 4 ディレクトリを優先度順に 1 本ずつ実装・検証・マージする。各サブ PR 完了後に `make mypy` と CI 相当フィルタでリグレッションがないことを確認してマージし、次のサブ PR を `origin/main` へリベースする。

衝突面を実測したところ、対象 2 ディレクトリを跨いでインポートするファイルは約 10 個であった(最大 2 ディレクトリまでで、3 つ以上を跨ぐファイルはない)。`storage` は他と共起しやすいため**最後に回し**、リベースの巻き込みを最小化する。

### 実行モデル: 直列・リード単独

並列実行(Agent Teams)は採用しない。理由は以下の 3 点である。

1. **PR のマージは直列である:** `main` へのマージは CI とレビューを経て 1 本ずつ行うため、並列化で短縮できるのは差分生成という機械作業のみであり、ボトルネックは縮まらない。
2. **共有 venv と editable install によるローカル検証の制約:** ワークツリーから共有 venv で `mypy -p lorairo` や `pytest` を実行するとメインチェックアウト側のコードを参照する場合があり、最終的な正否はプッシュ後の CI を信頼源(SSoT)とする必要がある。
3. **共有 `.venv` 破壊のリスク:** 並列 `uv sync` は共有 `.venv` を破壊する恐れがある(Issue #222)。

以上の理由から、リード(実装者)が 4 本のサブ PR を優先度順に直列処理する。

---

## 改名内容

| 順 | サブ PR | 改名内容 | 影響範囲 |
|---|---|---|---|
| 1 | `api/` → `public_api/` | ディレクトリのみを改名する。内部ファサードモジュール(`images.py`、`tags.py`、`project.py`、`export.py`、`batch_import.py`、`types.py`、`exceptions.py`、`annotations.py`)はリソース指向で十分説明的であるため**据え置く**(網羅レビューで適切と判断) | 35 ファイル |
| 2 | `editor/` → `image_transforms/` | ディレクトリのみを改名する。`autocrop.py`(`AutoCrop`)、`upscaler.py`(`Upscaler`)、`image_processor.py`(`ImageProcessingManager`、`ImageProcessor`)は**据え置く** | 7 ファイル |
| 3 | `annotations/` → `annotation/` | ディレクトリを単数形へ改名し、内部モジュールも改名する(詳細は下表) | 12 ファイル |
| 4 | `storage/` → `filesystem.py` | ディレクトリを廃して単一モジュールへ平坦化する。`from lorairo.filesystem import FileSystemManager` とし、`FileSystemManager` クラス名は維持する | 24 ファイル |

### サブ PR 3 のモジュール改名詳細

| 現行 | 改名後 | 理由 |
|---|---|---|
| `annotation_logic.py` / `AnnotationLogic` | `annotation_runner.py` / `AnnotationRunner` | `execute_annotation` でアノテーション実行を統括するランナーであるため、ノイズ語の「logic」を排除する |
| `existing_file_reader.py` / `ExistingFileReader` | `sidecar_reader.py` / `SidecarAnnotationReader` | `.txt` や `.caption` のサイドカーファイルから既存アノテーションを読み取る責務を明示する |
| `annotator_adapter.py` / `AnnotatorLibraryAdapter` | 据え置き | すでに `image-annotator-lib` のアダプタと明確に読み取れるため |

### 命名判断のメモ

- `annotations/` → **`annotation/`(単数形):** 当初は「AI 処理であることが読み取れない」点が懸念だったが、同ディレクトリにはサイドカー読み取り(非 AI 処理)も含まれるため、`ai_annotation/` は不正確である。`database` や `domain` と整合する単数形が実態に最も合う。
- `storage/` → **`filesystem.py`:** `storage/` 配下は `file_system.py` の 1 ファイルのみであるため、ディレクトリを維持せず単一モジュール `filesystem.py` へ平坦化するのが最も簡潔である。

---

## 各サブ PR の手順

各サブ PR は共通して以下の手順で進める([.claude/rules/git-workflow.md](../../../.claude/rules/git-workflow.md) および [testing.md](../../../.claude/rules/testing.md) 準拠)。

1. `origin/main` からワークツリーを作成する(`git worktree add .agents/worktree/issue-717-<dir> -b refactor/issue-717-<dir> origin/main`)。
2. `git mv` でディレクトリ・モジュールを移動する。
3. `src/`、`tests/`、`docs/` のインポート行を一括置換する。クラス名変更を伴うサブ PR 3 では対象シンボルも置換する。
4. `make mypy` と CI 相当フィルタ(`-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`)でリグレッションがないことを確認する。
5. コミット・プッシュして PR を起票する(`Closes #717` はサブ PR 4 のみとし、1〜3 は `Refs #717` とする)。
6. CI が通り、bot レビューに問題がないことを確認してスカッシュマージする。
7. 次のサブ PR のワークツリーを `origin/main` に合わせる。
8. 全サブ PR のマージ後にワークツリーを削除する。

### 検証スコープ補足

インポートの改名は GUI、services、cli、tests を横断する。そのため、CI 相当フィルタの実行に加え、改名ディレクトリを参照するテストモジュール(特にサブ PR 3 のアノテーション系、サブ PR 4 の `FileSystemManager` 利用テスト)でテスト収集エラーが起きないことを確認する。

---

## 影響範囲チェックリスト

- `src/lorairo/` 配下のすべての `import` 文
- `tests/` 配下の対応パスおよびモックパッチパス(`@patch("lorairo.<old>...")` の文字列も置換対象。実測で `tests/` 配下に 64 箇所ある)
- `docs/services.md` や `docs/integrations.md` などのドキュメント参照
- `pyproject.toml`: 実測の結果、対象ディレクトリ名への実パス参照は存在しない(一致するのは無関係な pytest マーカー名と Qt 設定のみ)ため**更新不要**である。

ロジック変更はゼロであり、差分はインポートパスとファイル位置のみとなる。
