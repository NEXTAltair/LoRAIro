# GUI Wireframes v11 — Phase 1 ナビ骨格 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Design ハンドオフバンドル「Wireframes v11」のナビゲーション構造への第一歩として、MainWindow を 6 タブ構成（検索 / マップ / アノテーション / ジョブ / 結果 / エラー）に再構築する。

**Architecture:** 既存の `tabWidgetMainMode`（ワークスペース / バッチタグ / バッチAPI の 3 タブ）を Wireframes v11 のナビ語彙に揃え、Map / Results のスタブページと Errors タブ（既存 `ErrorLogViewerWidget` の埋め込み）を追加する。タブ index のマジックナンバーを widget 同一性ベースに置換し、後続フェーズでのタブ増減に耐える構造にする。既存 widget の中身（FilterSearchPanel / BatchTagAddWidget / ProviderBatchJobWidget）は一切変更しない。

**Tech Stack:** PySide6 / Qt Designer (.ui + `scripts/generate_ui.py`) / pytest-qt

---

## 背景: デザインバンドルとロードマップ

### 出典

- Claude Design ハンドオフ: `https://api.anthropic.com/v1/design/h/lLO11YeFNJwtj0F1a0msIA`
- リポジトリ内コピー（本計画と同時に取り込み済み）:
  - `docs/design/wireframes-v11/wireframes-v11.html` — ワイヤーフレーム本体（8 フレーム）
  - `docs/design/wireframes-v11/HANDOFF.md` — デザインセッションの引き継ぎメモ
  - `docs/design/wireframes-v11/decisions-impact-on-wireframe.md` — ADR 0019–0055 の影響分析

### 設計の中心仮説（v11 設計メモより）

「アノテーション結果は人間が 1 枚ずつレビューするのではなく、**機械にトリアージさせて要レビューだけ人が触る**」。各画面は「次にとる 1 アクション」を 1 つに絞る。フロー: Search → stage → Annotate → (preflight) → Jobs → ✓done ⇢auto Results → Export。

### v11 フレーム ↔ 現行実装の対応とフェーズ分割

| Phase | v11 フレーム | 現状 | 内容 | 依存 / 未決事項 |
|---|---|---|---|---|
| **1 (本計画)** | ナビ全体 | 3 タブ | 6 タブ化 + スタブ + index マジックナンバー排除 | なし |
| 2 | Frame 5 Results | **未実装** | 品質トリアージ画面（品質ティア分布サマリ・issue カード集約・per-image 行 + accept/edit/reject・bulk 承認）。500 枚で仮想スクロール、9k 枚で per-row 非表示 | ADR 0029/0027/0028/0031。OPEN: 閾値スコープ (batch/project/global)、auto-accept 可否 |
| 3 | Frame 4 Errors | フラットなログビューア | トリアージ UI 化（同一原因グルーピング・status×operation×model クロスフィルタ・日本語タイトル + mono 技術詳細の 2 段組・retry/resolve/ignore + bulk・ADR 0034 worker lifecycle 語彙）。`ErrorLogViewerDialog` の廃止クリーンアップもここで | errors CLI 作業 (`2026-06-11-errors-cli-and-cancellation-fix.md`) と整合させる |
| 4 | Frame 1 Search | FilterSearchPanel あり | 品質ティア facet / AI・手動 2 軸 rating filter + 不一致クイック / scorer 合意状態・ペア比較 facet / DATE ヒストグラム。**画像サイズ・拡張子・has_alpha filter は追加しない**（設計で削除済み） | ADR 0029/0031/0015。OPEN: save query = live view / snapshot |
| 5 | Frame 7 Export | `DatasetExportWidget` (QDialog) | QWidget 化してエクスポートタブ常設。対象 = ステージング集合（ADR 0055/0019）、exact-set bypass の可視化 | OPEN: discontinued モデルの過去結果の扱い |
| 6 | Frame 2/2B Annotate | tabBatchTag あり | ステージ中心パイプライン（TAGS/CAPTION/SCORE/RATING、UPSCALE は別ジョブで含めない）、multimodal の ↝ shadow chip と「N 推論 × M 枚」表示、rating preflight ゲート表示（ADR 0031/0042）、環境ファースト二段モデルピッカー（ADR 0030） | OPEN: multimodal 派生出力の表示方法 |
| 7 | Frame 3 Jobs | 実行 = ポップアップ、Provider Batch = タブ | 同期実行と Provider Batch の統合 Jobs ビュー | **未決: ポップアップ維持 (実装追従 A) vs 独立タブ化 (提案 B)** — デザインセッションでも未回答。着手前にユーザー決定 + ADR 必須 |
| 8 | Frame Map | **未実装** | embedding 散布図 + クラスタ俯瞰（HDBSCAN 等）。バックエンド新規 | 要 ADR（embedding 計算・キャッシュ戦略）。HANDOFF でも優先度最低 |
| — | Frame 8 CLI | **実装済み** | ワイヤーが実装 (ADR 0057–0060) から逆起こししたもの。GUI 作業なし | — |

各フェーズは着手時に個別の実装計画を作成する（本ドキュメントは Phase 1 のみ詳細化）。

### Phase 1 のスコープ判断

- v11 ナビは 8 画面（⌘1–⌘8）だが、Phase 1 のタブは **6 枚**:
  - **CLI タブは作らない** — CLI は GUI とは別の操作面であり、ワイヤーの Frame 8 は契約の図解。Qt タブにする意味がない。
  - **エクスポートタブは Phase 5 に先送り** — `DatasetExportWidget` が QDialog 実装のため、タブ埋め込みは QWidget 化リファクタリングが必要。骨格フェーズでは既存のダイアログ起動（`btnExportData` / `actionExport`）を維持する。
- タブ名は v11 ナビの日本語語彙（検索 / マップ / アノテーション / ジョブ / 結果 / エラー）に揃える。objectName（`tabWorkspace` / `tabBatchTag`）は参照箇所が多いため**変更しない**（タイトル文字列のみ変更）。
- 過去の教訓（lessons-learned「UIファイル生成を忘れると連鎖エラー」）: `.ui` 変更後は必ず `uv run python scripts/generate_ui.py` を実行する。

---

## File Structure

| ファイル | 変更内容 |
|---|---|
| `src/lorairo/gui/designer/MainWindow.ui` | Modify: タブタイトル変更（検索 / アノテーション）、windowTitle 変更、`tabMap` / `tabResults` / `tabErrors` ページ追加 |
| `src/lorairo/gui/designer/MainWindow_ui.py` | Regenerate: `scripts/generate_ui.py` で再生成（手編集禁止） |
| `src/lorairo/gui/window/main_window.py` | Modify: ジョブタブ挿入位置 / index マジックナンバー排除 / Errors タブ埋め込み / 通知導線 / Ctrl+1–6 ショートカット / `SETTINGS_VERSION` bump |
| `src/lorairo/gui/services/tab_reorganization_service.py` | Modify: `REQUIRED_WIDGETS` に新タブ 3 件追加 |
| `tests/integration/test_main_window_tab_integration.py` | Modify: 6 タブ構成への期待値更新 + 新規テスト |
| `tests/unit/gui/services/test_tab_reorganization_service.py` | Modify: 定数テスト更新 |
| `docs/design/wireframes-v11/*` | Add: デザイン資産 3 ファイル（取り込み済み・要 git add） |

---

### Task 1: Worktree 準備

実装作業は共有 checkout でなく専用 worktree で行う（`rules/git-workflow.md`）。共有 checkout には errors CLI の未コミット作業が進行中のため、触らないこと。

- [ ] **Step 1: worktree 作成**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/gui-v11-phase1 -b feat/gui-v11-phase1-nav-skeleton origin/main
cd /workspaces/LoRAIro/.agents/worktree/gui-v11-phase1
```

- [ ] **Step 2: 共有 venv で動作確認**

worktree 内の `uv run` は `.claude/settings.json` の `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` 常設で共有 venv を使う。worktree 内に `.venv` を作らない。

```bash
uv run --no-sync python -c "import lorairo; print('ok')"
```

Expected: `ok`

> **注意（lessons-learned: worktree 検証は main checkout を見る）**: editable install のため worktree からの pytest/mypy は main checkout 側のコードを解決することがある。本計画のタスクごとの pytest はテストファイル自体を worktree パスで指定し、最終検証は push 後の CI を SSoT とする。確実にしたい場合は `PYTHONPATH=$(pwd)/src uv run --no-sync pytest ...` を使う。

### Task 2: デザイン資産の取り込みコミット

資産は共有 checkout の `docs/design/wireframes-v11/` に展開済み（本計画作成時にバンドルからコピー）。worktree へコピーしてコミットする。

- [ ] **Step 1: 資産を worktree へコピー**

```bash
mkdir -p docs/design/wireframes-v11
cp /workspaces/LoRAIro/docs/design/wireframes-v11/wireframes-v11.html docs/design/wireframes-v11/
cp /workspaces/LoRAIro/docs/design/wireframes-v11/HANDOFF.md docs/design/wireframes-v11/
cp /workspaces/LoRAIro/docs/design/wireframes-v11/decisions-impact-on-wireframe.md docs/design/wireframes-v11/
```

（共有 checkout 側に無い場合のフォールバック: ハンドオフ URL `https://api.anthropic.com/v1/design/h/lLO11YeFNJwtj0F1a0msIA` は gzip tar バンドル。`lorairo-01/project/Wireframes v11.html` 等を展開して取得する）

- [ ] **Step 2: 計画ドキュメントもコピーしてコミット**

```bash
cp /workspaces/LoRAIro/docs/superpowers/plans/2026-06-11-gui-wireframes-v11-phase1-nav-skeleton.md docs/superpowers/plans/
git add docs/design/wireframes-v11/ docs/superpowers/plans/2026-06-11-gui-wireframes-v11-phase1-nav-skeleton.md
git commit -m "docs: Wireframes v11 デザイン資産と Phase 1 実装計画を追加"
```

### Task 3: メインタブ 6 枚構成への再編

**Files:**
- Modify: `tests/integration/test_main_window_tab_integration.py`
- Modify: `src/lorairo/gui/designer/MainWindow.ui`
- Regenerate: `src/lorairo/gui/designer/MainWindow_ui.py`
- Modify: `src/lorairo/gui/window/main_window.py`

- [ ] **Step 1: 統合テストを 6 タブ期待値に更新（red）**

`tests/integration/test_main_window_tab_integration.py` を以下のように変更する。

`test_three_tabs_created` を置換:

```python
    def test_six_tabs_created(self, main_window_with_tabs):
        """6つのタブ（検索/マップ/アノテーション/ジョブ/結果/エラー）が作成される"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.count() == 6
        assert [tab_widget.tabText(i) for i in range(tab_widget.count())] == [
            "検索",
            "マップ",
            "アノテーション",
            "ジョブ",
            "結果",
            "エラー",
        ]
```

新規テストを `TestMainWindowTabInitialization` に追加:

```python
    def test_stub_pages_exist(self, main_window_with_tabs):
        """マップ/結果タブはスタブページとして存在する"""
        tab_widget = main_window_with_tabs.tabWidgetMainMode
        assert tab_widget.widget(1).objectName() == "tabMap"
        assert tab_widget.widget(4).objectName() == "tabResults"

    def test_tab_order_matches_wireframe_nav(self, main_window_with_tabs):
        """タブ順序が Wireframes v11 のナビ順 (Search/Map/Annotate/Jobs/Results/Errors) に一致する"""
        window = main_window_with_tabs
        tab_widget = window.tabWidgetMainMode
        assert tab_widget.widget(0) is window.tabWorkspace
        assert tab_widget.widget(2) is window.tabBatchTag
        assert tab_widget.widget(3) is window.provider_batch_job_widget
        assert tab_widget.widget(5).objectName() == "tabErrors"
```

index 直書き箇所を widget 同一性ベースに更新:

- `test_batch_tag_tab_structure` / `test_batchtagaddwidget_in_batch_tag_tab` / `test_batchtagaddwidget_placeholder_replaced` / `test_annotation_display_in_batch_tag_tab` の `tab_widget.widget(1)` →
  `main_window_with_tabs.tabBatchTag`（`tabWidgetMainMode.widget(...)` 経由をやめ、直接属性を使う）
- `test_provider_batch_tab_structure` の `widget(2)` → `widget(3)`
- `test_can_switch_to_batch_tag_tab` / `test_can_switch_back_to_workspace` / `test_dataset_state_manager_preserved_across_tabs` の `setCurrentIndex(1)` →

```python
        tab_widget.setCurrentIndex(tab_widget.indexOf(main_window_with_tabs.tabBatchTag))
```

  （`assert tab_widget.currentIndex() == 1` も `assert tab_widget.currentWidget() is main_window_with_tabs.tabBatchTag` に変更）
- `test_can_switch_to_provider_batch_tab` の `setCurrentIndex(2)` / `== 2` →

```python
        tab_widget.setCurrentIndex(tab_widget.indexOf(main_window_with_tabs.provider_batch_job_widget))
        qtbot.wait(10)
        assert tab_widget.currentWidget() is main_window_with_tabs.provider_batch_job_widget
```

- `test_stage_toolbar_button_treats_clicked_bool_as_selection_request` の
  `assert main_window_with_tabs.tabWidgetMainMode.currentIndex() == 1` →

```python
        assert (
            main_window_with_tabs.tabWidgetMainMode.currentWidget()
            is main_window_with_tabs.tabBatchTag
        )
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

Expected: FAIL（`tab_widget.count() == 6` が 3 で失敗、ほか）

- [ ] **Step 3: MainWindow.ui を編集**

`src/lorairo/gui/designer/MainWindow.ui`:

1. windowTitle 変更:

```xml
  <property name="windowTitle">
   <string>LoRAIro</string>
  </property>
```

2. `tabWorkspace` の title `ワークスペース` → `検索`:

```xml
      <widget class="QWidget" name="tabWorkspace">
       <attribute name="title">
        <string>検索</string>
       </attribute>
```

3. `tabWorkspace` の閉じタグ（`</widget>` — `tabBatchTag` 定義の直前）の直後に `tabMap` ページを挿入:

```xml
      <widget class="QWidget" name="tabMap">
       <attribute name="title">
        <string>マップ</string>
       </attribute>
       <layout class="QVBoxLayout" name="verticalLayout_map">
        <item>
         <widget class="QLabel" name="labelMapStub">
          <property name="text">
           <string>マップビューは未実装です。
embedding 散布図によるデータセット俯瞰を予定（Wireframes v11 · Map / 実装ロードマップ Phase 8）。</string>
          </property>
          <property name="alignment">
           <set>Qt::AlignmentFlag::AlignCenter</set>
          </property>
         </widget>
        </item>
       </layout>
      </widget>
```

4. `tabBatchTag` の title `バッチタグ` → `アノテーション`:

```xml
      <widget class="QWidget" name="tabBatchTag">
       <attribute name="title">
        <string>アノテーション</string>
       </attribute>
```

5. `tabBatchTag` の閉じタグの直後（`tabWidgetMainMode` の閉じタグの前）に `tabResults` と `tabErrors` を挿入:

```xml
      <widget class="QWidget" name="tabResults">
       <attribute name="title">
        <string>結果</string>
       </attribute>
       <layout class="QVBoxLayout" name="verticalLayout_results">
        <item>
         <widget class="QLabel" name="labelResultsStub">
          <property name="text">
           <string>結果ビューは未実装です。
アノテーション品質トリアージ（issue 集約 + accept/edit/reject）を予定（Wireframes v11 · Frame 5 / 実装ロードマップ Phase 2）。</string>
          </property>
          <property name="alignment">
           <set>Qt::AlignmentFlag::AlignCenter</set>
          </property>
         </widget>
        </item>
       </layout>
      </widget>
      <widget class="QWidget" name="tabErrors">
       <attribute name="title">
        <string>エラー</string>
       </attribute>
       <layout class="QVBoxLayout" name="verticalLayout_errors"/>
      </widget>
```

- [ ] **Step 4: UI コード再生成**

```bash
uv run python scripts/generate_ui.py
```

Expected: `MainWindow_ui.py` が再生成され、`tabMap` / `tabResults` / `tabErrors` / `labelMapStub` / `labelResultsStub` が含まれる

```bash
grep -c "tabMap\|tabResults\|tabErrors" src/lorairo/gui/designer/MainWindow_ui.py
```

Expected: 1 以上の数値

- [ ] **Step 5: main_window.py — ジョブタブ挿入位置と index マジックナンバー排除**

`src/lorairo/gui/window/main_window.py` を変更:

(a) `_setup_provider_batch_tab` の `addTab` を `insertTab` に変更（結果タブの直前 = ジョブの位置に挿入）:

```python
            self.provider_batch_job_widget = widget
            insert_index = self.tabWidgetMainMode.indexOf(self.tabResults)
            self.tabWidgetMainMode.insertTab(insert_index, widget, "ジョブ")
            logger.info("✅ ジョブタブ (Provider Batch) initialized")
```

(b) `_on_main_tab_changed` を index 比較から widget 同一性比較に書き換え:

```python
    def _on_main_tab_changed(self, index: int) -> None:
        """メインタブ切り替えハンドラ

        Args:
            index: 切り替え先のタブインデックス
        """
        current = self.tabWidgetMainMode.widget(index)
        if current is getattr(self, "tabBatchTag", None):
            logger.info("Switched to Annotate tab")
            self._refresh_batch_tag_staging()
        elif self.provider_batch_job_widget is not None and current is self.provider_batch_job_widget:
            logger.info("Switched to Jobs tab")
            self.provider_batch_job_widget.refresh_jobs()
```

（`else: logger.warning(f"Unknown tab index: {index}")` は削除する — スタブタブ切替が警告になるため）

(c) アノテーション実行時のタブ判定（旧 line 1513 付近）:

```python
        # アノテーションタブの場合はステージング画像を使用
        override_image_paths: list[str] | None = None
        if self.tabWidgetMainMode.currentWidget() is self.tabBatchTag:
```

(d) ステージ遷移（旧 line 1689 付近）:

```python
        # アノテーションタブへ移動してステージングタブを表示
        if hasattr(self, "tabWidgetMainMode") and self.tabWidgetMainMode:
            self.tabWidgetMainMode.setCurrentIndex(self.tabWidgetMainMode.indexOf(self.tabBatchTag))
```

(e) UI 構造変更のため `SETTINGS_VERSION` を bump:

```python
    SETTINGS_VERSION = 2
```

- [ ] **Step 6: テスト実行（green）**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

Expected: PASS（Errors 埋め込みテストは Task 4 で追加するためまだ無い）

- [ ] **Step 7: コミット**

```bash
git add src/lorairo/gui/designer/MainWindow.ui src/lorairo/gui/designer/MainWindow_ui.py \
        src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): メインタブを Wireframes v11 ナビ構成 (6タブ) に再編"
```

### Task 4: エラータブ — ErrorLogViewerWidget 埋め込みと通知導線

現状エラーログは StatusBar 通知クリック → `ErrorLogViewerDialog`（ポップアップ）。これをエラータブ常設に変え、通知クリックはタブ遷移にする。`ErrorLogViewerDialog` クラス自体は削除しない（Phase 3 Errors トリアージで widget ごと刷新する際にクリーンアップ）。MainWindow からの参照のみ除去する。

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

- [ ] **Step 1: テスト追加（red）**

`tests/integration/test_main_window_tab_integration.py` の import に追加:

```python
from lorairo.gui.widgets.error_log_viewer_widget import ErrorLogViewerWidget
```

`TestMainWindowTabInitialization` にテスト追加:

```python
    def test_errors_tab_embeds_error_log_viewer(self, main_window_with_tabs):
        """エラータブに ErrorLogViewerWidget が常設される"""
        errors_tab = main_window_with_tabs.tabWidgetMainMode.widget(5)
        assert errors_tab.objectName() == "tabErrors"
        viewer = errors_tab.findChild(ErrorLogViewerWidget)
        assert viewer is not None
        assert main_window_with_tabs.error_log_viewer_widget is viewer

    def test_error_notification_click_navigates_to_errors_tab(self, main_window_with_tabs):
        """エラー通知クリックでエラータブへ遷移する"""
        window = main_window_with_tabs
        window._on_error_notification_clicked()
        assert window.tabWidgetMainMode.currentWidget() is window.tabErrors
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v -k "errors_tab or error_notification"
```

Expected: FAIL（`error_log_viewer_widget` 属性なし / `_on_error_notification_clicked` なし）

- [ ] **Step 3: 実装**

`src/lorairo/gui/window/main_window.py`:

(a) import 変更 — `ErrorLogViewerDialog` を外し `ErrorLogViewerWidget` を入れる:

```python
from ..widgets.error_log_viewer_widget import ErrorLogViewerWidget
```

(b) クラス属性アノテーション変更 — `error_log_dialog: ErrorLogViewerDialog | None` を削除し:

```python
    error_log_viewer_widget: ErrorLogViewerWidget | None
```

(c) `_setup_error_notification` 内の変更:

```python
            # クリックでエラータブへ遷移
            self.error_notification_widget.clicked.connect(self._on_error_notification_clicked)

            # Dialog初期化（遅延生成）
            self.tag_management_dialog = None
```

（`self.error_log_dialog = None` の行は削除）

(d) `_show_error_log_dialog` メソッドを丸ごと削除し、代わりに以下を追加:

```python
    def _on_error_notification_clicked(self) -> None:
        """エラー通知クリックでエラータブへ遷移する。"""
        self.tabWidgetMainMode.setCurrentIndex(self.tabWidgetMainMode.indexOf(self.tabErrors))
```

(e) エラータブ埋め込みメソッドを追加し、`_setup_provider_batch_tab()` 呼び出しの直後で呼ぶ:

```python
        self._setup_tab_widget()
        self._setup_provider_batch_tab()
        self._setup_errors_tab()
```

```python
    def _setup_errors_tab(self) -> None:
        """エラータブに ErrorLogViewerWidget を埋め込む。"""
        container = getattr(self, "tabErrors", None)
        if container is None:
            logger.warning("tabErrors not found - errors tab skipped")
            self.error_log_viewer_widget = None
            return

        widget = ErrorLogViewerWidget(parent=container)
        if self.db_manager:
            widget.set_db_manager(self.db_manager)
        widget.error_resolved.connect(self._on_error_resolved)
        container.layout().addWidget(widget)
        self.error_log_viewer_widget = widget
        logger.info("✅ エラータブ (ErrorLogViewerWidget) initialized")
```

(f) `_on_main_tab_changed` にエラータブ分岐を追加（タブ表示のたびに最新化）:

```python
        elif current is getattr(self, "tabErrors", None):
            logger.info("Switched to Errors tab")
            if self.error_log_viewer_widget is not None and self.db_manager:
                self.error_log_viewer_widget.load_error_records()
```

- [ ] **Step 4: テスト実行（green）**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

Expected: 全 PASS

- [ ] **Step 5: ErrorLogViewerDialog の残参照がないことを確認**

```bash
grep -rn "ErrorLogViewerDialog\|error_log_dialog" src/lorairo/gui/window/main_window.py
```

Expected: ヒットなし。`grep -rn "error_log_dialog" tests/` でヒットした既存テスト（あれば）は `error_log_viewer_widget` ベースの検証に書き換えるか、ダイアログ単体テスト（`ErrorLogViewerDialog` を直接 import するもの）なら据え置く。

- [ ] **Step 6: コミット**

```bash
git add src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): エラータブに ErrorLogViewerWidget を常設し通知クリックをタブ遷移化"
```

### Task 5: Ctrl+1〜6 タブ切替ショートカット

v11 ナビの ⌘1–⌘8 に対応する Qt 実装。

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

- [ ] **Step 1: テスト追加（red）**

`TestTabSwitching` に追加:

```python
    def test_ctrl_number_shortcut_switches_tab(self, main_window_with_tabs, qtbot):
        """Ctrl+数字キーでメインタブが切り替わる"""
        window = main_window_with_tabs
        window.show()
        qtbot.waitExposed(window)

        qtbot.keyClick(window, Qt.Key.Key_4, Qt.KeyboardModifier.ControlModifier)
        assert window.tabWidgetMainMode.currentIndex() == 3

        qtbot.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        assert window.tabWidgetMainMode.currentIndex() == 0
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v -k shortcut
```

Expected: FAIL（currentIndex が変化しない）

- [ ] **Step 3: 実装**

`src/lorairo/gui/window/main_window.py`:

(a) import 追加（既存の `PySide6.QtGui` import 行に統合、`functools.partial` は標準ライブラリブロックへ）:

```python
from functools import partial
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
```

（既存の QtGui import 内容は維持して追記する）

(b) メソッド追加。`_setup_errors_tab()` 呼び出しの直後に `self._setup_tab_shortcuts()` を追加:

```python
    def _setup_tab_shortcuts(self) -> None:
        """Ctrl+1〜N でメインタブを切り替えるショートカットを登録する。

        Wireframes v11 のナビショートカット (⌘1–⌘8) に対応する。
        """
        for i in range(self.tabWidgetMainMode.count()):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(partial(self.tabWidgetMainMode.setCurrentIndex, i))
        logger.debug(f"Tab shortcuts registered: Ctrl+1..Ctrl+{self.tabWidgetMainMode.count()}")
```

（`Qt` は `PySide6.QtCore` から import 済みであることを確認、なければ追加）

- [ ] **Step 4: テスト実行（green）**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

Expected: 全 PASS

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): Ctrl+1-6 のメインタブ切替ショートカットを追加"
```

### Task 6: TabReorganizationService の必須ウィジェット更新

**Files:**
- Modify: `src/lorairo/gui/services/tab_reorganization_service.py`
- Modify: `tests/unit/gui/services/test_tab_reorganization_service.py`

- [ ] **Step 1: テスト更新（red）**

`tests/unit/gui/services/test_tab_reorganization_service.py` の `test_required_widgets_contains_tab_structure` に追記:

```python
        assert "tabMap" in required
        assert "tabResults" in required
        assert "tabErrors" in required
```

- [ ] **Step 2: テスト実行で失敗を確認**

```bash
uv run pytest tests/unit/gui/services/test_tab_reorganization_service.py -v
```

Expected: FAIL（`tabMap` が `REQUIRED_WIDGETS` にない）

- [ ] **Step 3: 実装**

`src/lorairo/gui/services/tab_reorganization_service.py` の `REQUIRED_WIDGETS` を更新:

```python
    REQUIRED_WIDGETS: ClassVar[list[str]] = [
        "tabWidgetMainMode",
        "tabWorkspace",
        "tabMap",
        "tabBatchTag",
        "tabResults",
        "tabErrors",
        "splitterBatchTagMain",
        "groupBoxBatchOperations",
        "groupBoxAnnotation",
    ]
```

- [ ] **Step 4: テスト実行（green）**

```bash
uv run pytest tests/unit/gui/services/test_tab_reorganization_service.py -v
```

Expected: 全 PASS（`test_validate_with_complete_widget_hierarchy` が新必須 widget の不足で落ちる場合は、そのテストの階層構築部に以下を追加する）

```python
        map_tab = QWidget()
        map_tab.setObjectName("tabMap")
        tab_widget.addTab(map_tab, "マップ")

        results_tab = QWidget()
        results_tab.setObjectName("tabResults")
        tab_widget.addTab(results_tab, "結果")

        errors_tab = QWidget()
        errors_tab.setObjectName("tabErrors")
        tab_widget.addTab(errors_tab, "エラー")
```

- [ ] **Step 5: コミット**

```bash
git add src/lorairo/gui/services/tab_reorganization_service.py tests/unit/gui/services/test_tab_reorganization_service.py
git commit -m "test(gui): TabReorganizationService の必須ウィジェットに新タブを追加"
```

### Task 7: 全体検証（CI-equivalent filter）

- [ ] **Step 1: フォーマット + 型チェック**

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
```

Expected: ruff エラーなし、mypy 既存エラー以外の新規エラーなし

- [ ] **Step 2: CI-equivalent filter で全テスト**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```

Expected: 全 PASS。タブ index に依存していた他テストが落ちた場合は、widget 同一性ベース（`currentWidget() is window.tabBatchTag` 等）に修正して再実行する。

- [ ] **Step 3: 修正があればコミット**

```bash
git add -A
git commit -m "test: タブ index 依存箇所を widget 同一性ベースに修正"
```

（修正がなければスキップ）

### Task 8: PR 起票と保守

- [ ] **Step 1: push + PR 作成**

```bash
git push -u origin feat/gui-v11-phase1-nav-skeleton
gh pr create --title "feat(gui): Wireframes v11 Phase 1 — メインナビ 6 タブ骨格" --body "$(cat <<'EOF'
## Summary
- Claude Design「Wireframes v11」ハンドオフのナビ構造への第一歩として、メインタブを 6 枚構成（検索 / マップ / アノテーション / ジョブ / 結果 / エラー）に再編
- マップ / 結果タブはスタブ（それぞれ Phase 8 / Phase 2 で実装予定）
- エラータブに ErrorLogViewerWidget を常設し、StatusBar 通知クリックをダイアログ表示からタブ遷移に変更
- Ctrl+1–6 タブ切替ショートカット追加
- タブ index のマジックナンバーを widget 同一性ベースに置換、SETTINGS_VERSION を 2 に bump
- デザイン資産 (`docs/design/wireframes-v11/`) とロードマップ付き実装計画を同梱

## Test plan
- [ ] `tests/integration/test_main_window_tab_integration.py` 全 PASS
- [ ] CI-equivalent filter 全 PASS

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: PR 保守自走**

`agent-pr-autoloop` skill で CI / bot レビューを監視し、safe なら squash merge。merge 後:

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/gui-v11-phase1
```

---

## リスクと注意事項

- **QSettings 互換**: `restoreState` はタブ構成変更の影響を受けないが、保存済みタブ index の意味が変わるため `SETTINGS_VERSION` を 2 に bump する（Task 3 Step 5e）。
- **タブ index 依存の他テスト**: Task 7 Step 2 で網羅的に検出する。`tabWidgetMainMode` への index 直書きは本計画ですべて widget 同一性参照に置換するのが原則。
- **submodule 変更なし**: 本 PR は `local_packages/*` に触れないため、pre-PR submodule hook の対象外。
- **ErrorLogViewerDialog**: クラスは残存（未使用）。Phase 3（Errors トリアージ）で widget 刷新時に削除する。
- **Export タブなし**: v11 ナビとの差分として PR 説明に明記済み。Phase 5 で対応。

## 後続フェーズ着手時のチェックリスト

1. `docs/design/wireframes-v11/wireframes-v11.html` の該当フレーム（`data-screen-label` で検索）を精読する
2. `docs/design/wireframes-v11/decisions-impact-on-wireframe.md` と関連 ADR を確認する
3. 表「v11 フレーム ↔ 現行実装の対応」の未決事項（Phase 7 の A/B、Phase 8 の ADR）はユーザー決定を取ってから着手する
4. フェーズごとに `docs/superpowers/plans/` に個別計画を作成する
