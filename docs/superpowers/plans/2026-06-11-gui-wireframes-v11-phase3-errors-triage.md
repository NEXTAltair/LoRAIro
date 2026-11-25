# GUI Wireframes v11 — Phase 3 Errors トリアージ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wireframes v11 Frame 4「Errors」を、同一原因グルーピング、クロスフィルタ、resolve アクションを備えたトリアージ画面として実装する。あわせて、Phase 1 で埋め込んだフラットな `ErrorLogViewerWidget` を置換し、`ErrorLogViewerDialog` も含めて廃止クリーンアップする。

**Architecture:** Qt 非依存の `ErrorTriageService`(グルーピング、サマリ、フィルタの純粋ロジック)と Qt の `ErrorsTriageWidget`(表示、フィルタ UI、resolve 操作)を分離する。`MainWindow` が `ErrorRecord` から `ErrorRow` への変換と DB 書き込みを仲介する MVC 構成とする(Phase 2 と同型)。

**Tech Stack:** PySide6、pytest-qt、既存の `db_manager` エラー API(`get_error_records`、`count_error_records`、`mark_error_resolved`、`mark_errors_resolved_batch`)

---

## 確定スコープ(ユーザー承認済 2026-06-11)

- **アクションは resolve と一括 resolve のみとする:** retry や再インポートは **ADR 0033(自動 retry 廃止)** と整合しない。また、再実行には Jobs 統合(Phase 7)が必要になるため今回は見送る。
- **ignore と resolve は区別しない:** `resolved_at` のみで状態を管理し、スキーマ変更は行わない。
- **グルーピング軸:** `(operation_type, error_type, model_name)` を同一原因とみなす。デフォルトはグループ表示とし、個別行モードへ切り替え可能にする。
- **クロスフィルタ:** `status`(all / unresolved / resolved)× `operation_type` × `error_type` × `model_name` で絞り込む。時間フィルタのファセットは持たず、`created_at` は「過去 24h」サマリの算出にのみ使用する。
- **廃止クリーンアップ:** `ErrorLogViewerWidget`、`ErrorLogViewerDialog`、および関連する `.ui`、`_ui.py`、テストを削除し、`ErrorsTriageWidget` へ置換する。

## 既存資産(検証済)

- `ErrorRecord` スキーマ: `id`、`image_id`、`operation_type`、`error_type`、`error_message`、`stack_trace`、`file_path`、`model_name`、`resolved_at`、`created_at`。なお、**`retry_count` は ADR 0033 で削除済み**である。
- `db_manager.get_error_records(operation_type, error_type, message_contains, resolved, limit, offset) -> list[ErrorRecord]`
- `db_manager.mark_errors_resolved_batch(error_ids) -> tuple[bool, int]`、および `error_record repo.mark_error_resolved(error_id)`
- Phase 1 の実装: `_setup_errors_tab()` が `ErrorLogViewerWidget` を `tabErrors` に埋め込み、`_on_main_tab_changed` の Errors 分岐で `load_error_records()` を呼び出している。

---

## ファイル構成

| ファイル | 担当 | 内容 |
|---|---|---|
| `src/lorairo/services/error_triage_service.py` | Lead(契約)+ A | 契約 dataclass とグルーピング・サマリ・フィルタの実装 |
| `tests/unit/services/test_error_triage_service.py` | A | サービスのユニットテスト |
| `src/lorairo/gui/widgets/errors_triage_widget.py` | Lead(契約)+ B | `ErrorsTriageWidget`(表示、フィルタ、resolve) |
| `tests/unit/gui/widgets/test_errors_triage_widget.py` | B | ウィジェットテスト |
| `src/lorairo/gui/window/main_window.py` | Lead(C) | 埋め込み置換、`ErrorRecord` から `ErrorRow` への変換、resolve の結線 |
| `tests/integration/test_main_window_tab_integration.py` | Lead(C) | Errors 埋め込み統合テストの更新 |
| 削除対象: `error_log_viewer_widget.py`、`error_log_viewer_dialog.py`、`ErrorLogViewerWidget.ui`、`ErrorLogViewerWidget_ui.py`、およびそれらのテスト | Lead(C) | 廃止クリーンアップ |

Track A(サービス)と Track B(ウィジェット)はファイルが完全に分離されている。両者とも契約 dataclass をインポートするのみである。

---

## 共有契約(Lead が Task 1 で先行コミット)

`src/lorairo/services/error_triage_service.py` に以下を定義する。

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
    """1 エラーレコード(ORM 非依存の表示用 dataclass)。"""

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
    image_ids: list[int]  # 影響画像(重複排除・None 除外)
    error_ids: list[int]  # bulk resolve 用(全件)
    unresolved_error_ids: list[int]  # bulk resolve 用(未解決のみ)


@dataclass(frozen=True)
class ErrorTriageSummary:
    """エラー全体のサマリ。"""

    total: int
    unresolved: int
    resolved: int
    last_24h: int
    by_error_type: dict[str, int]  # error_type ごとの件数(未解決基準)


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
        """全行(フィルタ前)からサマリを算出する。last_24h は created_at 基準。"""
        raise NotImplementedError
```

`ErrorsTriageWidget` の公開 API(Track B が実装し、Track C が呼び出す)は以下のとおりである。

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
        """フィルタ combo の選択肢を設定する(controller が DB の distinct 値で更新)。"""
```

---

### Task 1: 共有契約の先行コミット(Lead)

- [ ] `src/lorairo/services/error_triage_service.py` を作成する(上記契約。メソッドは `NotImplementedError`)
- [ ] `src/lorairo/gui/widgets/errors_triage_widget.py` を作成する(`display`、`get_filter`、`is_grouped`、`set_filter_options` は最小スタブとし、`objectName` の設定と契約のインポートを行う)
- [ ] インポートが通ることを確認する(ワークツリーでは `PYTHONPATH=<wt>/src` を付与する)
- [ ] コミットする: `feat(errors): Phase 3 共有契約 (dataclass + service/widget skeleton) を追加`

### Task A: `ErrorTriageService` 実装(Track A・並列)

**Files:** サービスを変更し、`tests/unit/services/test_error_triage_service.py` を新規作成する。

**ルール:**
- `apply_filter`: `status`(`ALL` は全件、`UNRESOLVED` は `resolved` が `False`、`RESOLVED` は `resolved` が `True`)と、`operation_type`、`error_type`、`model_name`(`None` はスキップ)の AND 条件で絞り込む。
- `group_errors`: キーを `(operation_type, error_type, model_name)` とする。各グループの項目は以下のとおりとする。
  - `count`: 件数、`unresolved_count`: `resolved` が `False` の件数
  - `sample_message`: グループ先頭行の `error_message`
  - `image_ids`: `None` を除外して重複排除(出現順を保持)
  - `error_ids`: 全 `error_id`、`unresolved_error_ids`: 未解決の `error_id`
  - 並び順: `unresolved_count` の降順、同数なら `count` の降順
- `summarize`: `total`、`unresolved`、`resolved`、`last_24h`(`created_at >= now(UTC)-24h`、`created_at` が `None` の行は除外)、`by_error_type`(未解決行の `error_type` ごとの件数)を算出する。

- [ ] **Step 1: 失敗するテストを書く**(各フィルタ、グルーピング集約、並び順、サマリ、`last_24h` の境界、空入力を網羅し最低 8 ケース)
- [ ] **Step 2: 失敗を確認し、実装してテストを通す**
- [ ] **Step 3: mypy と ruff format を実行する**
- [ ] **Step 4: コミットする** `feat(errors): エラートリアージ集約サービスを実装 (Refs #725)`

### Task B: `ErrorsTriageWidget` 実装(Track B・並列)

**Files:** ウィジェットを変更し、`tests/unit/gui/widgets/test_errors_triage_widget.py` を新規作成する。

**表示構成(Frame 4 準拠、純コード QWidget):**
- **サマリ帯:** `total`、`unresolved`、`resolved`、`last_24h`、`by_error_type` を表示する。
- **フィルタバー:** `status` セグメント(all / unresolved / resolved)、`operation_type` コンボ、`error_type` コンボ、`model_name` コンボ、グループ/個別行トグルを配置する。変更時に `filter_changed` を発行する。
- **グループ表示(デフォルト):** 各 `ErrorGroup` をカードとして表示する。カードには `{operation_type} · {error_type} · {model_name}` のヘッダ、count/unresolved バッジ、`sample_message`、影響画像リンク(`image_ids`)、および「このグループを resolve」ボタン(`resolve_group_requested.emit(unresolved_error_ids)`)を含める。
- **個別行表示:** 各 `ErrorRow` を行として表示する。`error_id`、`operation`、`error_type`、`message`、`model`、`resolved` 状態を表示し、未解決行のみ単一 resolve ボタン(`resolve_requested.emit(error_id)`)を出す。
- **下部一括操作:** 「未解決をすべて resolve」ボタンを配置し、表示中グループの全 `unresolved_error_ids` を集約して `resolve_group_requested.emit(...)` を発行する。

**必須 `objectName`:**
- グループカード: `errorGroup_{operation_type}_{error_type}_{model_name}`(`model_name` が `None` の場合は `none`、記号は `_` に正規化する)。テストでは `findChild(QFrame, ...)` ではなく、ウィジェットが提供する内部アクセサ `_group_keys() -> list[tuple]` で検証する。
- グループ resolve ボタン: 各カード内に `errorGroupResolveButton` を配置する(複数存在するため、テストではシグナルで検証する)。
- 個別行 resolve ボタン: `errorRowResolveButton_{error_id}`
- 一括 resolve ボタン: `errorsBulkResolveButton`
- 空状態: `errorsEmptyState`

- [ ] **Step 1: 失敗するテストを書く**(手組み dataclass 入力を用いる。グループ表示でのグループ数描画、グループ resolve シグナル、個別行モードでの行描画と単一 resolve シグナル、一括 resolve シグナル、`filter_changed` 発行、空状態を網羅し最低 6 ケース)
- [ ] **Step 2: 失敗を確認し、実装してテストを通す**(ヘッドレス実行: `QT_QPA_PLATFORM=offscreen`)
- [ ] **Step 3: mypy と ruff format を実行する**
- [ ] **Step 4: コミットする** `feat(errors): ErrorsTriageWidget グルーピング表示を実装 (Refs #725)`

### Task C: `MainWindow` 結線と廃止クリーンアップ(Lead・A/B マージ後)

- [ ] **Step 1: 統合テストを更新する(red)**
  - `tabErrors` に `ErrorsTriageWidget` が埋め込まれ、`errors_triage_widget` 属性で参照でき、旧 `ErrorLogViewerWidget` が埋め込まれていないことを検証する。
  - resolve シグナルで `db_manager.mark_errors_resolved_batch` が呼ばれることを検証する。
- [ ] **Step 2: 実装する**
  - インポートを `ErrorsTriageWidget` へ変更し、`error_log_viewer_widget` を `errors_triage_widget` にリネームする。
  - `_setup_errors_tab()` で `ErrorsTriageWidget` を埋め込み、`resolve_requested`、`resolve_group_requested`、`filter_changed` を結線する。
  - `_refresh_errors_tab()` を実装する。`db_manager.get_error_records(...)` で取得し(`widget.get_filter()` を反映。ただし status / operation / error_type は DB クエリ、model はインメモリで絞る)、`ErrorRecord` を `ErrorRow` へ変換して `service.summarize`、`apply_filter`、`group_errors` を呼び出し、`widget.display` へ渡す。あわせて DB の distinct な operation / error_type / model を `set_filter_options` に渡す。
  - `_on_main_tab_changed` の Errors 分岐を `_refresh_errors_tab()` の呼び出しへ変更する。
  - resolve ハンドラでは `mark_errors_resolved_batch` を実行して再描画する。
  - `ErrorTriageService` を `self.error_triage_service` として生成する。
- [ ] **Step 3: 廃止クリーンアップを行う**
  - 削除対象: `src/lorairo/gui/widgets/error_log_viewer_widget.py`、`error_log_viewer_dialog.py`、`src/lorairo/gui/designer/ErrorLogViewerWidget.ui`、`ErrorLogViewerWidget_ui.py`、`tests/unit/gui/widgets/test_error_log_viewer_widget.py`、`test_error_log_viewer_dialog.py`。
  - `ErrorLogViewerWidget` と `ErrorLogViewerDialog` の残参照を grep で確認し、ゼロにする。
- [ ] **Step 4: GUI スコープの CI 相当フィルタで検証する**
- [ ] **Step 5: コミットする**

### Task D: 全体検証と PR(Lead)

- [ ] CI 相当フィルタで全体を検証する(ワークツリー環境特有の失敗は CI を信頼源とする)
- [ ] プッシュし、`gh pr create --base epic/gui-wireframes-v11` で PR を作成する
- [ ] CI を監視し、すべて通れば epic ブランチへスカッシュマージして #725 にコメントする

---

## Agent Teams 実行構成

- **Lead:** Task 1(契約)を実行した後、Track A と B のワークツリーを作成して並列ディスパッチする。両者の完了後にマージし、Task C と D を進める。
- **Track A ワークツリー:** `.agents/worktree/gui-v11-p3-service`(ブランチ `feat/gui-v11-p3-service`)
- **Track B ワークツリー:** `.agents/worktree/gui-v11-p3-widget`(ブランチ `feat/gui-v11-p3-widget`)
- ファイルが完全に分離されているため、マージ競合は発生しない。

## リスクと注意

- **ワークツリーでの pytest 解決差:** 新規ファイルはメインチェックアウトに存在しないため、`PYTHONPATH=<wt>/src` を付与する。最終的な正否はプッシュ後の CI を信頼源とする。
- **`ErrorRecord` ORM のセッション境界:** `MainWindow` で `ErrorRecord` を `ErrorRow` へ変換する際、デタッチ後の遅延読み込みを避けるため、属性アクセスはフェッチ直後に行う。
- **クリーンアップの残参照:** `actionErrorLog` メニューの結線(Phase 1 で `_on_error_notification_clicked` へ変更済み)は維持する。削除対象はウィジェットとダイアログのクラスのみとする。
