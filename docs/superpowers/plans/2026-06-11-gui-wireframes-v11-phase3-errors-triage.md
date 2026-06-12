# GUI Wireframes v11 — Phase 3 Errors トリアージ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Wireframes v11 Frame 4「Errors」を、同一原因グルーピング + クロスフィルタ + resolve アクションを持つトリアージ画面として実装し、Phase 1 で埋め込んだフラットな `ErrorLogViewerWidget` を置換する。`ErrorLogViewerDialog` 含め廃止クリーンアップする。

**Architecture:** Qt-free の `ErrorTriageService`（グルーピング・サマリ・フィルタの純粋ロジック）と Qt の `ErrorsTriageWidget`（表示 + フィルタ UI + resolve）を分離し、MainWindow が ErrorRecord → ErrorRow 変換と DB 書き込みを仲介する MVC 構成（Phase 2 と同型）。

**Tech Stack:** PySide6 / pytest-qt / 既存 `db_manager` error API（`get_error_records` / `count_error_records` / `mark_error_resolved` / `mark_errors_resolved_batch`）

---

## 確定スコープ（ユーザー承認済 2026-06-11）

- **アクション = resolve / bulk resolve のみ**。retry / 再インポートは **ADR 0033（自動 retry 廃止）** と整合せず、再実行は Jobs 統合（Phase 7）が必要なため見送る。
- **ignore = resolve**（区別しない。`resolved_at` のみで状態管理、schema 変更なし）。
- **グルーピング軸** = `(operation_type, error_type, model_name)`（= 同一原因）。デフォルトはグループ表示、個別行モードに切替可。
- **クロスフィルタ** = status（all / unresolved / resolved）× operation_type × error_type × model_name。time フィルタ facet は持たず、`created_at` は「過去24h」サマリ算出にのみ使う。
- **廃止クリーンアップ**: `ErrorLogViewerWidget` / `ErrorLogViewerDialog` とその `.ui` / `_ui.py` / テストを削除し、`ErrorsTriageWidget` に置換。

## 既存資産（検証済）

- `ErrorRecord` schema: `id` / `image_id` / `operation_type` / `error_type` / `error_message` / `stack_trace` / `file_path` / `model_name` / `resolved_at` / `created_at`。**`retry_count` は ADR 0033 で drop 済み**。
- `db_manager.get_error_records(operation_type, error_type, message_contains, resolved, limit, offset) -> list[ErrorRecord]`
- `db_manager.mark_errors_resolved_batch(error_ids) -> tuple[bool, int]`、`error_record repo.mark_error_resolved(error_id)`
- Phase 1: `_setup_errors_tab()` が `ErrorLogViewerWidget` を `tabErrors` に embed、`_on_main_tab_changed` の Errors 分岐で `load_error_records()` 呼び出し。

---

## File Structure

| ファイル | 担当 | 内容 |
|---|---|---|
| `src/lorairo/services/error_triage_service.py` | Lead(契約)+A | 契約 dataclass + グルーピング/サマリ/フィルタ実装 |
| `tests/unit/services/test_error_triage_service.py` | A | サービスの unit テスト |
| `src/lorairo/gui/widgets/errors_triage_widget.py` | Lead(契約)+B | ErrorsTriageWidget（表示 + フィルタ + resolve） |
| `tests/unit/gui/widgets/test_errors_triage_widget.py` | B | widget テスト |
| `src/lorairo/gui/window/main_window.py` | Lead(C) | embed 置換 + ErrorRecord→ErrorRow 変換 + resolve 結線 |
| `tests/integration/test_main_window_tab_integration.py` | Lead(C) | Errors 埋め込み統合テスト更新 |
| 削除: `error_log_viewer_widget.py` / `error_log_viewer_dialog.py` / `ErrorLogViewerWidget.ui` / `ErrorLogViewerWidget_ui.py` / それらの test | Lead(C) | 廃止クリーンアップ |

Track A（service）と Track B（widget）はファイル disjoint。両者とも契約 dataclass を import するのみ。

---

## 共有契約（Lead が Task 1 で先行コミット）

`src/lorairo/services/error_triage_service.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum


class ErrorStatusFilter(Enum):
    """status クロスフィルタの 3 値。"""

    ALL = "all"
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class ErrorRow:
    """1 エラーレコード（ORM 非依存の表示用 dataclass）。"""

    error_id: int
    image_id: int | None
    operation_type: str
    error_type: str
    error_message: str
    model_name: str | None
    resolved: bool
    created_at: datetime | None


@dataclass(frozen=True)
class ErrorFilter:
    """クロスフィルタの選択状態。None = 全て。"""

    status: ErrorStatusFilter = ErrorStatusFilter.UNRESOLVED
    operation_type: str | None = None
    error_type: str | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class ErrorGroup:
    """同一原因 (operation_type, error_type, model_name) で集約したグループ。"""

    operation_type: str
    error_type: str
    model_name: str | None
    count: int
    unresolved_count: int
    sample_message: str
    image_ids: list[int]  # 影響画像（重複排除・None 除外）
    error_ids: list[int]  # bulk resolve 用（全件）
    unresolved_error_ids: list[int]  # bulk resolve 用（未解決のみ）


@dataclass(frozen=True)
class ErrorTriageSummary:
    """エラー全体のサマリ。"""

    total: int
    unresolved: int
    resolved: int
    last_24h: int
    by_error_type: dict[str, int]  # error_type ごとの件数（未解決基準）


class ErrorTriageService:
    """エラーレコードを同一原因にグルーピングし triage する (Qt-free)。"""

    def apply_filter(self, rows: list[ErrorRow], error_filter: ErrorFilter) -> list[ErrorRow]:
        """フィルタ条件に一致する行のみ返す。"""
        raise NotImplementedError

    def group_errors(self, rows: list[ErrorRow]) -> list[ErrorGroup]:
        """行を (operation_type, error_type, model_name) で集約する。

        unresolved_count 降順 → count 降順で並べる。
        """
        raise NotImplementedError

    def summarize(self, rows: list[ErrorRow]) -> ErrorTriageSummary:
        """全行（フィルタ前）からサマリを算出する。last_24h は created_at 基準。"""
        raise NotImplementedError
```

`ErrorsTriageWidget` の公開 API（Track B 実装、Track C が呼ぶ）:

```python
class ErrorsTriageWidget(QWidget):
    """Frame 4 · Errors トリアージ表示。objectName = "errorsTriageWidget"。"""

    resolve_requested = Signal(int)          # error_id (単一 resolve)
    resolve_group_requested = Signal(list)   # list[int] error_ids (グループ一括 resolve)
    filter_changed = Signal()                # フィルタ/表示モード変更 → controller が再取得
    image_link_clicked = Signal(int)         # image_id (将来 Search 連携用、本フェーズは未接続可)

    def __init__(self, parent: QWidget | None = None) -> None: ...

    def display(
        self,
        summary: ErrorTriageSummary,
        groups: list[ErrorGroup],
        rows: list[ErrorRow],
    ) -> None:
        """サマリ band + (グループ表示 or 個別行表示) を再描画する。"""

    def get_filter(self) -> ErrorFilter:
        """フィルタ UI の現在の選択状態を返す。"""

    def is_grouped(self) -> bool:
        """グループ表示モードなら True、個別行モードなら False。"""

    def set_filter_options(
        self, operation_types: list[str], error_types: list[str], model_names: list[str]
    ) -> None:
        """フィルタ combo の選択肢を設定する（controller が DB の distinct 値で更新）。"""
```

---

### Task 1: 共有契約の先行コミット（Lead）

- [ ] Create `src/lorairo/services/error_triage_service.py`（上記契約、メソッドは `NotImplementedError`）
- [ ] Create `src/lorairo/gui/widgets/errors_triage_widget.py`（`display`/`get_filter`/`is_grouped`/`set_filter_options` は最小スタブ、objectName 設定、契約 import）
- [ ] import が通ることを確認（worktree では `PYTHONPATH=<wt>/src` を付与）
- [ ] commit: `feat(errors): Phase 3 共有契約 (dataclass + service/widget skeleton) を追加`

### Task A: ErrorTriageService 実装（Track A・並列）

**Files:** Modify service / Create `tests/unit/services/test_error_triage_service.py`

**ルール:**
- `apply_filter`: status（ALL=全件 / UNRESOLVED=resolved False / RESOLVED=resolved True）+ operation_type / error_type / model_name（None はスキップ）の AND。
- `group_errors`: キー `(operation_type, error_type, model_name)`。各グループ:
  - `count` = 件数、`unresolved_count` = resolved False の件数
  - `sample_message` = グループ先頭行の error_message
  - `image_ids` = None 除外・重複排除（出現順）
  - `error_ids` = 全 error_id、`unresolved_error_ids` = 未解決の error_id
  - 並び順: `unresolved_count` 降順 → `count` 降順
- `summarize`: `total` / `unresolved` / `resolved` / `last_24h`（`created_at >= now(UTC)-24h`、created_at None は除外）/ `by_error_type`（未解決行の error_type ごと件数）

- [ ] **Step 1: 失敗するテストを書く**（最低 8 ケース: 各フィルタ・グルーピング集約・並び順・サマリ・last_24h 境界・空入力）
- [ ] **Step 2: 失敗確認 → 実装 → green**
- [ ] **Step 3: mypy + ruff format**
- [ ] **Step 4: commit** `feat(errors): エラートリアージ集約サービスを実装 (Refs #725)`

### Task B: ErrorsTriageWidget 実装（Track B・並列）

**Files:** Modify widget / Create `tests/unit/gui/widgets/test_errors_triage_widget.py`

**表示構成（Frame 4 準拠、純コード QWidget）:**
- **サマリ band**: total / unresolved / resolved / last_24h / by_error_type
- **フィルタ bar**: status セグメント（all/unresolved/resolved）+ operation_type combo + error_type combo + model_name combo + グループ/個別行トグル。変更で `filter_changed` emit。
- **グループ表示（デフォルト）**: 各 `ErrorGroup` をカードで。`{operation_type} · {error_type} · {model_name}` ヘッダ + count/unresolved バッジ + sample_message + 影響画像リンク（image_ids）+ 「このグループを resolve」ボタン（`resolve_group_requested.emit(unresolved_error_ids)`）。
- **個別行表示**: 各 `ErrorRow` を行で。error_id / operation / error_type / message / model / resolved 状態 + 単一 resolve ボタン（`resolve_requested.emit(error_id)`、resolved 済みは出さない）。
- **bottom bulk**: 「未解決をすべて resolve」ボタン（表示中グループの全 `unresolved_error_ids` を集約して `resolve_group_requested.emit(...)`）。

必須 objectName:
- グループカード: `errorGroup_{operation_type}_{error_type}_{model_name}`（model_name None は `none`、記号は `_` 正規化）→ テストは `findChild(QFrame, ...)` ではなく widget が提供する内部アクセサ `_group_keys() -> list[tuple]` で検証
- グループ resolve ボタン: 各カード内に `errorGroupResolveButton`（複数）→ テストは signal で検証
- 個別行 resolve ボタン: `errorRowResolveButton_{error_id}`
- bulk resolve ボタン: `errorsBulkResolveButton`
- 空状態: `errorsEmptyState`

- [ ] **Step 1: 失敗するテストを書く**（hand-built dataclass 入力。グループ表示で group 数描画 / グループ resolve signal / 個別行モードで行描画 + 単一 resolve signal / bulk resolve signal / filter_changed emit / 空状態。最低 6 ケース）
- [ ] **Step 2: 失敗確認 → 実装 → green**（headless: `QT_QPA_PLATFORM=offscreen`）
- [ ] **Step 3: mypy + ruff format**
- [ ] **Step 4: commit** `feat(errors): ErrorsTriageWidget グルーピング表示を実装 (Refs #725)`

### Task C: MainWindow 結線 + 廃止クリーンアップ（Lead・A/B マージ後）

- [ ] **Step 1: 統合テスト更新（red）**
  - `tabErrors` に `ErrorsTriageWidget` が embed される / `errors_triage_widget` 属性 / 旧 `ErrorLogViewerWidget` が embed されていない
  - resolve シグナルで `db_manager.mark_errors_resolved_batch` が呼ばれる
- [ ] **Step 2: 実装**
  - import を `ErrorsTriageWidget` に変更、`error_log_viewer_widget` → `errors_triage_widget` にリネーム
  - `_setup_errors_tab()` で `ErrorsTriageWidget` を embed、`resolve_requested` / `resolve_group_requested` / `filter_changed` を結線
  - `_refresh_errors_tab()`: `db_manager.get_error_records(...)`（widget.get_filter() を反映、ただし status/operation/error_type は DB クエリ、model は in-memory）→ ErrorRecord→ErrorRow 変換 → `service.summarize` / `apply_filter` / `group_errors` → `widget.display`。distinct の operation/error_type/model を `set_filter_options` に渡す
  - `_on_main_tab_changed` の Errors 分岐を `_refresh_errors_tab()` 呼び出しに変更
  - resolve ハンドラ: `mark_errors_resolved_batch` → 再描画
  - `ErrorTriageService` を `self.error_triage_service` として生成
- [ ] **Step 3: 廃止クリーンアップ**
  - 削除: `src/lorairo/gui/widgets/error_log_viewer_widget.py` / `error_log_viewer_dialog.py` / `src/lorairo/gui/designer/ErrorLogViewerWidget.ui` / `ErrorLogViewerWidget_ui.py` / `tests/unit/gui/widgets/test_error_log_viewer_widget.py` / `test_error_log_viewer_dialog.py`
  - 残参照を grep で確認しゼロにする（`ErrorLogViewerWidget` / `ErrorLogViewerDialog`）
- [ ] **Step 4: GUI スコープ CI-equivalent filter で検証**
- [ ] **Step 5: commit**

### Task D: 全体検証 + PR（Lead）

- [ ] CI-equivalent filter（worktree 環境失敗は CI が SSoT）
- [ ] push + `gh pr create --base epic/gui-wireframes-v11`
- [ ] CI 監視 → green なら epic へ squash merge → #725 にコメント

---

## Agent Teams 実行構成

- **Lead**: Task 1（契約）→ Track A/B worktree 作成 + 並列 dispatch → マージ → Task C/D
- **Track A worktree**: `.agents/worktree/gui-v11-p3-service`（`feat/gui-v11-p3-service`）
- **Track B worktree**: `.agents/worktree/gui-v11-p3-widget`（`feat/gui-v11-p3-widget`）
- ファイル disjoint → マージ無衝突。

## リスクと注意

- **worktree pytest の解決差**: 新規ファイルは main checkout に無いため `PYTHONPATH=<wt>/src` を付与。真偽は push 後 CI が SSoT。
- **ErrorRecord ORM のセッション境界**: MainWindow で ErrorRecord → ErrorRow へ変換する際、属性アクセスは fetch 直後に行う（detach 後の lazy load を避ける）。
- **クリーンアップの残参照**: `actionErrorLog` メニュー結線（Phase 1 で `_on_error_notification_clicked` に変更済み）は維持。削除対象は widget/dialog クラスのみ。
