# GUI Wireframes v11 — Phase 1 ナビ骨格 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Design のハンドオフバンドル「Wireframes v11」のナビゲーション構造へ移行する第一歩として、MainWindow を 6 タブ構成(検索、マップ、アノテーション、ジョブ、結果、エラー)に再構築する。

**Architecture:** 既存の `tabWidgetMainMode`(ワークスペース、バッチタグ、バッチAPI の 3 タブ)を Wireframes v11 のナビ語彙へ揃える。あわせて、マップと結果のスタブページ、および既存 `ErrorLogViewerWidget` を埋め込んだエラータブを追加する。タブインデックスのマジックナンバーはウィジェット同一性ベースへ置換し、後続フェーズでのタブ増減に耐える構造にする。既存ウィジェットの中身(`FilterSearchPanel`、`BatchTagAddWidget`、`ProviderBatchJobWidget`)は一切変更しない。

**Tech Stack:** PySide6、Qt Designer(`.ui` および `scripts/generate_ui.py`)、pytest-qt

---

## 背景: デザインバンドルとロードマップ

### 出典

- Claude Design ハンドオフ: `https://api.anthropic.com/v1/design/h/lLO11YeFNJwtj0F1a0msIA`
- リポジトリ内コピー(本計画と同時に取り込み済み):
  - `docs/design/wireframes-v11/wireframes-v11.html` — ワイヤーフレーム本体(8 フレーム)
  - `docs/design/wireframes-v11/HANDOFF.md` — デザインセッションの引き継ぎメモ
  - `docs/design/wireframes-v11/decisions-impact-on-wireframe.md` — ADR 0019–0055 の影響分析

### 設計の中心仮説(v11 設計メモより)

アノテーション結果は人間が 1 枚ずつレビューするのではなく、**機械にトリアージさせて要レビュー対象だけを人が触る**方針をとる。各画面は「次にとる 1 アクション」を 1 つに絞る。操作フローは「検索 → ステージング → アノテーション →(preflight)→ ジョブ → 完了後に自動で結果へ遷移 → エクスポート」とする。

### v11 フレームと現行実装の対応およびフェーズ分割

| Phase | v11 フレーム | 現状 | 内容 | 依存・未決事項 |
|---|---|---|---|---|
| **1(本計画)** | ナビ全体 | 3 タブ | 6 タブ化、スタブ追加、インデックスのマジックナンバー排除 | なし |
| 2 | Frame 5 Results | **未実装** | 品質トリアージ画面(品質ティア分布サマリ、issue カード集約、画像ごとの行と accept/edit/reject、一括承認)。500 枚で仮想スクロール、9k 枚で個別行を非表示にする | ADR 0029/0027/0028/0031。未決: 閾値スコープ(batch/project/global)、auto-accept の可否 |
| 3 | Frame 4 Errors | フラットなログビューア | トリアージ UI 化(同一原因グルーピング、status×operation×model のクロスフィルタ、日本語タイトルと等幅の技術詳細の 2 段組、retry/resolve/ignore と一括操作、ADR 0034 の worker lifecycle 語彙)。`ErrorLogViewerDialog` の廃止クリーンアップも実施する | errors CLI 作業(`2026-06-11-errors-cli-and-cancellation-fix.md`)と整合させる |
| 4 | Frame 1 Search | `FilterSearchPanel` あり | 品質ティアファセット、AI・手動の 2 軸 rating フィルタと不一致クイックフィルタ、scorer 合意状態・ペア比較ファセット、DATE ヒストグラム。**画像サイズ・拡張子・has_alpha フィルタは追加しない**(設計で削除済み) | ADR 0029/0031/0015。未決: save query を live view とするか snapshot とするか |
| 5 | Frame 7 Export | `DatasetExportWidget`(QDialog) | QWidget 化してエクスポートタブに常設する。対象はステージング集合とし(ADR 0055/0019)、exact-set bypass を可視化する | 未決: discontinued モデルの過去結果の扱い |
| 6 | Frame 2/2B Annotate | `tabBatchTag` あり | ステージ中心パイプライン(TAGS/CAPTION/SCORE/RATING。UPSCALE は別ジョブのため含めない)、multimodal の `↝` shadow chip と「N 推論 × M 枚」表示、rating preflight ゲート表示(ADR 0031/0042)、環境ファースト二段モデルピッカー(ADR 0030) | 未決: multimodal 派生出力の表示方法 |
| 7 | Frame 3 Jobs | 実行はポップアップ、Provider Batch はタブ | 同期実行と Provider Batch の統合 Jobs ビュー | **未決: ポップアップ維持(実装追従 A)か独立タブ化(提案 B)か**。デザインセッションでも未回答のため、着手前にユーザー決定と ADR 作成が必須 |
| 8 | Frame Map | **未実装** | embedding 散布図とクラスタ俯瞰(HDBSCAN など)。バックエンドを新規実装する | 要 ADR(embedding 計算とキャッシュ戦略)。HANDOFF でも優先度は最低 |
| — | Frame 8 CLI | **実装済み** | ワイヤーフレームが実装(ADR 0057–0060)から逆起こしされたもの。GUI 作業はない | — |

各フェーズは着手時に個別の実装計画を作成する。本ドキュメントでは Phase 1 のみを詳細化する。

### Phase 1 のスコープ判断

- v11 のナビゲーションは 8 画面(⌘1–⌘8)だが、Phase 1 で実装するタブは **6 枚**とする。
  - **CLI タブは作らない:** CLI は GUI とは別の操作面であり、ワイヤーフレームの Frame 8 は契約の図解にすぎない。Qt タブとして設ける意味がないため除外する。
  - **エクスポートタブは Phase 5 に先送りする:** `DatasetExportWidget` は QDialog 実装であり、タブへ埋め込むには QWidget 化のリファクタリングが必要になる。骨格フェーズでは既存のダイアログ起動(`btnExportData` および `actionExport`)を維持する。
- タブ名は v11 ナビの日本語語彙(検索、マップ、アノテーション、ジョブ、結果、エラー)に揃える。`objectName`(`tabWorkspace`、`tabBatchTag`)は参照箇所が多いため**変更しない**。タイトル文字列のみを変更する。
- 過去の教訓(lessons-learned「UIファイル生成を忘れると連鎖エラー」)に従い、`.ui` を変更した後は必ず `uv run python scripts/generate_ui.py` を実行する。

---

## ファイル構成

| ファイル | 変更内容 |
|---|---|
| `src/lorairo/gui/designer/MainWindow.ui` | 変更: タブタイトル変更(検索、アノテーション)、`windowTitle` 変更、`tabMap` / `tabResults` / `tabErrors` ページ追加 |
| `src/lorairo/gui/designer/MainWindow_ui.py` | 再生成: `scripts/generate_ui.py` で再生成する(手編集は禁止) |
| `src/lorairo/gui/window/main_window.py` | 変更: ジョブタブ挿入位置、インデックスのマジックナンバー排除、エラータブ埋め込み、通知導線、Ctrl+1–6 ショートカット、`SETTINGS_VERSION` の更新 |
| `src/lorairo/gui/services/tab_reorganization_service.py` | 変更: `REQUIRED_WIDGETS` に新タブ 3 件を追加 |
| `tests/integration/test_main_window_tab_integration.py` | 変更: 6 タブ構成への期待値更新および新規テスト追加 |
| `tests/unit/gui/services/test_tab_reorganization_service.py` | 変更: 定数テストの更新 |
| `docs/design/wireframes-v11/*` | 追加: デザイン資産 3 ファイル(取り込み済み、要 `git add`) |

---

### Task 1: Worktree 準備

実装作業は共有チェックアウトではなく専用ワークツリーで行う(`rules/git-workflow.md`)。共有チェックアウトでは errors CLI の未コミット作業が進行中のため、手を加えない。

- [ ] **Step 1: ワークツリーを作成する**

```bash
cd /workspaces/LoRAIro
git fetch origin
git worktree add .agents/worktree/gui-v11-phase1 -b feat/gui-v11-phase1-nav-skeleton origin/main
cd /workspaces/LoRAIro/.agents/worktree/gui-v11-phase1
```

- [ ] **Step 2: 共有 venv で動作を確認する**

ワークツリー内の `uv run` は、`.claude/settings.json` に常設された `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` により共有 venv を使用する。ワークツリー内に `.venv` を作成してはならない。

```bash
uv run --no-sync python -c "import lorairo; print('ok')"
```

期待結果: `ok` が出力される。

> **注意(lessons-learned: worktree 検証は main checkout を見る):** editable install の影響で、ワークツリーから実行した pytest や mypy がメインチェックアウト側のコードを解決することがある。本計画の各タスクではテストファイルをワークツリーのパスで指定し、最終検証はプッシュ後の CI を信頼源(SSoT)とする。確実にワークツリー側を参照したい場合は、`PYTHONPATH=$(pwd)/src uv run --no-sync pytest ...` を使用する。

### Task 2: デザイン資産の取り込みコミット

デザイン資産は本計画作成時にバンドルから展開し、共有チェックアウトの `docs/design/wireframes-v11/` に配置済みである。これらをワークツリーへコピーしてコミットする。

- [ ] **Step 1: 資産をワークツリーへコピーする**

```bash
mkdir -p docs/design/wireframes-v11
cp /workspaces/LoRAIro/docs/design/wireframes-v11/wireframes-v11.html docs/design/wireframes-v11/
cp /workspaces/LoRAIro/docs/design/wireframes-v11/HANDOFF.md docs/design/wireframes-v11/
cp /workspaces/LoRAIro/docs/design/wireframes-v11/decisions-impact-on-wireframe.md docs/design/wireframes-v11/
```

共有チェックアウト側にファイルが無い場合のフォールバックとして、ハンドオフ URL `https://api.anthropic.com/v1/design/h/lLO11YeFNJwtj0F1a0msIA`(gzip tar バンドル)から `lorairo-01/project/Wireframes v11.html` などを展開して取得する。

- [ ] **Step 2: 計画ドキュメントもコピーしてコミットする**

```bash
cp /workspaces/LoRAIro/docs/superpowers/plans/2026-06-11-gui-wireframes-v11-phase1-nav-skeleton.md docs/superpowers/plans/
git add docs/design/wireframes-v11/ docs/superpowers/plans/2026-06-11-gui-wireframes-v11-phase1-nav-skeleton.md
git commit -m "docs: Wireframes v11 デザイン資産と Phase 1 実装計画を追加"
```

### Task 3: メインタブを 6 枚構成へ再編

**Files:**
- Modify: `tests/integration/test_main_window_tab_integration.py`
- Modify: `src/lorairo/gui/designer/MainWindow.ui`
- Regenerate: `src/lorairo/gui/designer/MainWindow_ui.py`
- Modify: `src/lorairo/gui/window/main_window.py`

- [ ] **Step 1: 統合テストを 6 タブの期待値へ更新する(red)**

`tests/integration/test_main_window_tab_integration.py` を以下のとおり変更する。

まず、`test_three_tabs_created` を以下へ置換する。

```python
    def test_six_tabs_created(self, main_window_with_tabs):
        """6つのタブ(検索/マップ/アノテーション/ジョブ/結果/エラー)が作成される"""
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

次に、新規テストを `TestMainWindowTabInitialization` へ追加する。

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

さらに、インデックスを直書きしている箇所をウィジェット同一性ベースへ更新する。

- `test_batch_tag_tab_structure`、`test_batchtagaddwidget_in_batch_tag_tab`、`test_batchtagaddwidget_placeholder_replaced`、`test_annotation_display_in_batch_tag_tab` の `tab_widget.widget(1)` を `main_window_with_tabs.tabBatchTag` に置換する(`tabWidgetMainMode.widget(...)` 経由をやめ、直接属性を使う)。
- `test_provider_batch_tab_structure` の `widget(2)` を `widget(3)` に変更する。
- `test_can_switch_to_batch_tag_tab`、`test_can_switch_back_to_workspace`、`test_dataset_state_manager_preserved_across_tabs` の `setCurrentIndex(1)` を以下に置換する。

```python
        tab_widget.setCurrentIndex(tab_widget.indexOf(main_window_with_tabs.tabBatchTag))
```

あわせて `assert tab_widget.currentIndex() == 1` も `assert tab_widget.currentWidget() is main_window_with_tabs.tabBatchTag` に変更する。

- `test_can_switch_to_provider_batch_tab` の `setCurrentIndex(2)` と `== 2` を以下に置換する。

```python
        tab_widget.setCurrentIndex(tab_widget.indexOf(main_window_with_tabs.provider_batch_job_widget))
        qtbot.wait(10)
        assert tab_widget.currentWidget() is main_window_with_tabs.provider_batch_job_widget
```

- `test_stage_toolbar_button_treats_clicked_bool_as_selection_request` の `assert main_window_with_tabs.tabWidgetMainMode.currentIndex() == 1` を以下に置換する。

```python
        assert (
            main_window_with_tabs.tabWidgetMainMode.currentWidget()
            is main_window_with_tabs.tabBatchTag
        )
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

期待結果: `tab_widget.count() == 6` が 3 で失敗するなど、テストが失敗する。

- [ ] **Step 3: `MainWindow.ui` を編集する**

`src/lorairo/gui/designer/MainWindow.ui` に以下の 5 箇所の変更を加える。

1. `windowTitle` を変更する。

```xml
  <property name="windowTitle">
   <string>LoRAIro</string>
  </property>
```

2. `tabWorkspace` のタイトルを「ワークスペース」から「検索」へ変更する。

```xml
      <widget class="QWidget" name="tabWorkspace">
       <attribute name="title">
        <string>検索</string>
       </attribute>
```

3. `tabWorkspace` の閉じタグ(`</widget>`、`tabBatchTag` 定義の直前)の直後に `tabMap` ページを挿入する。

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
embedding 散布図によるデータセット俯瞰を予定(Wireframes v11 · Map / 実装ロードマップ Phase 8)。</string>
          </property>
          <property name="alignment">
           <set>Qt::AlignmentFlag::AlignCenter</set>
          </property>
         </widget>
        </item>
       </layout>
      </widget>
```

4. `tabBatchTag` のタイトルを「バッチタグ」から「アノテーション」へ変更する。

```xml
      <widget class="QWidget" name="tabBatchTag">
       <attribute name="title">
        <string>アノテーション</string>
       </attribute>
```

5. `tabBatchTag` の閉じタグの直後(`tabWidgetMainMode` の閉じタグの前)に `tabResults` と `tabErrors` を挿入する。

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
アノテーション品質トリアージ(issue 集約 + accept/edit/reject)を予定(Wireframes v11 · Frame 5 / 実装ロードマップ Phase 2)。</string>
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

- [ ] **Step 4: UI コードを再生成する**

```bash
uv run python scripts/generate_ui.py
```

期待結果: `MainWindow_ui.py` が再生成され、`tabMap`、`tabResults`、`tabErrors`、`labelMapStub`、`labelResultsStub` が含まれる。

```bash
grep -c "tabMap\|tabResults\|tabErrors" src/lorairo/gui/designer/MainWindow_ui.py
```

期待結果: 1 以上の数値が出力される。

- [ ] **Step 5: `main_window.py` のジョブタブ挿入位置を変更し、インデックスのマジックナンバーを排除する**

`src/lorairo/gui/window/main_window.py` に以下の変更を行う。

(a) `_setup_provider_batch_tab` の `addTab` を `insertTab` に変更し、結果タブの直前(ジョブの位置)へ挿入する。

```python
            self.provider_batch_job_widget = widget
            insert_index = self.tabWidgetMainMode.indexOf(self.tabResults)
            self.tabWidgetMainMode.insertTab(insert_index, widget, "ジョブ")
            logger.info("✅ ジョブタブ (Provider Batch) initialized")
```

(b) `_on_main_tab_changed` をインデックス比較からウィジェット同一性比較へ書き換える。

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

なお、スタブタブ切替が警告になるのを防ぐため、`else: logger.warning(f"Unknown tab index: {index}")` は削除する。

(c) アノテーション実行時のタブ判定(旧 line 1513 付近)をウィジェット同一性比較へ変更する。

```python
        # アノテーションタブの場合はステージング画像を使用
        override_image_paths: list[str] | None = None
        if self.tabWidgetMainMode.currentWidget() is self.tabBatchTag:
```

(d) ステージ遷移(旧 line 1689 付近)を `indexOf` ベースへ変更する。

```python
        # アノテーションタブへ移動してステージングタブを表示
        if hasattr(self, "tabWidgetMainMode") and self.tabWidgetMainMode:
            self.tabWidgetMainMode.setCurrentIndex(self.tabWidgetMainMode.indexOf(self.tabBatchTag))
```

(e) UI 構造の変更に伴い、`SETTINGS_VERSION` を 2 へ更新する。

```python
    SETTINGS_VERSION = 2
```

- [ ] **Step 6: テストを実行して通ることを確認する(green)**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

期待結果: 全テストが通る(エラータブ埋め込みのテストは Task 4 で追加するため、この時点では未追加)。

- [ ] **Step 7: コミットする**

```bash
git add src/lorairo/gui/designer/MainWindow.ui src/lorairo/gui/designer/MainWindow_ui.py \
        src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): メインタブを Wireframes v11 ナビ構成 (6タブ) に再編"
```

### Task 4: エラータブ — `ErrorLogViewerWidget` の埋め込みと通知導線

現状のエラーログ表示は、StatusBar の通知クリックで `ErrorLogViewerDialog`(ポップアップ)を開く仕組みである。これをエラータブ常設へ変更し、通知クリック時はエラータブへ遷移させる。`ErrorLogViewerDialog` クラス自体は削除せず、Phase 3(Errors トリアージ)でウィジェットごと刷新する際にクリーンアップする。ここでは `MainWindow` からの参照のみを除去する。

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

- [ ] **Step 1: テストを追加する(red)**

`tests/integration/test_main_window_tab_integration.py` のインポートに以下を追加する。

```python
from lorairo.gui.widgets.error_log_viewer_widget import ErrorLogViewerWidget
```

`TestMainWindowTabInitialization` に以下のテストを追加する。

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

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v -k "errors_tab or error_notification"
```

期待結果: `error_log_viewer_widget` 属性や `_on_error_notification_clicked` メソッドが存在せず失敗する。

- [ ] **Step 3: 実装する**

`src/lorairo/gui/window/main_window.py` に以下の変更を加える。

(a) インポートから `ErrorLogViewerDialog` を外し、`ErrorLogViewerWidget` を追加する。

```python
from ..widgets.error_log_viewer_widget import ErrorLogViewerWidget
```

(b) クラス属性アノテーションから `error_log_dialog: ErrorLogViewerDialog | None` を削除し、以下を追加する。

```python
    error_log_viewer_widget: ErrorLogViewerWidget | None
```

(c) `_setup_error_notification` 内を変更する(`self.error_log_dialog = None` の行は削除する)。

```python
            # クリックでエラータブへ遷移
            self.error_notification_widget.clicked.connect(self._on_error_notification_clicked)

            # Dialog初期化(遅延生成)
            self.tag_management_dialog = None
```

(d) `_show_error_log_dialog` メソッドを丸ごと削除し、代わりに以下を追加する。

```python
    def _on_error_notification_clicked(self) -> None:
        """エラー通知クリックでエラータブへ遷移する。"""
        self.tabWidgetMainMode.setCurrentIndex(self.tabWidgetMainMode.indexOf(self.tabErrors))
```

(e) エラータブ埋め込みメソッドを追加し、`_setup_provider_batch_tab()` の直後で呼び出す。

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

(f) タブ表示のたびに最新化するため、`_on_main_tab_changed` にエラータブの分岐を追加する。

```python
        elif current is getattr(self, "tabErrors", None):
            logger.info("Switched to Errors tab")
            if self.error_log_viewer_widget is not None and self.db_manager:
                self.error_log_viewer_widget.load_error_records()
```

- [ ] **Step 4: テストを実行して通ることを確認する(green)**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

期待結果: 全テストが通る。

- [ ] **Step 5: `ErrorLogViewerDialog` の残参照がないことを確認する**

```bash
grep -rn "ErrorLogViewerDialog\|error_log_dialog" src/lorairo/gui/window/main_window.py
```

期待結果: ヒットしないこと。`grep -rn "error_log_dialog" tests/` でヒットした既存テストがあれば、`error_log_viewer_widget` ベースの検証へ書き換える。ただし、`ErrorLogViewerDialog` を直接インポートするダイアログ単体テストであれば据え置く。

- [ ] **Step 6: コミットする**

```bash
git add src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): エラータブに ErrorLogViewerWidget を常設し通知クリックをタブ遷移化"
```

### Task 5: Ctrl+1〜6 タブ切替ショートカット

v11 ナビの ⌘1–⌘8 に対応する Qt 実装を追加する。

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/integration/test_main_window_tab_integration.py`

- [ ] **Step 1: テストを追加する(red)**

`TestTabSwitching` に以下を追加する。

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

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v -k shortcut
```

期待結果: `currentIndex` が変化せず失敗する。

- [ ] **Step 3: 実装する**

`src/lorairo/gui/window/main_window.py` に以下の変更を加える。

(a) インポートを追加する(既存の `PySide6.QtGui` インポート行に統合し、`functools.partial` は標準ライブラリブロックへ追記する)。

```python
from functools import partial
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
```

既存の `QtGui` インポート内容は維持したまま追記する。

(b) メソッドを追加し、`_setup_errors_tab()` 呼び出しの直後に `self._setup_tab_shortcuts()` を追加する。

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

`Qt` が `PySide6.QtCore` からインポート済みであることを確認し、未インポートであれば追加する。

- [ ] **Step 4: テストを実行して通ることを確認する(green)**

```bash
uv run pytest tests/integration/test_main_window_tab_integration.py -v
```

期待結果: 全テストが通る。

- [ ] **Step 5: コミットする**

```bash
git add src/lorairo/gui/window/main_window.py tests/integration/test_main_window_tab_integration.py
git commit -m "feat(gui): Ctrl+1-6 のメインタブ切替ショートカットを追加"
```

### Task 6: `TabReorganizationService` の必須ウィジェット更新

**Files:**
- Modify: `src/lorairo/gui/services/tab_reorganization_service.py`
- Modify: `tests/unit/gui/services/test_tab_reorganization_service.py`

- [ ] **Step 1: テストを更新する(red)**

`tests/unit/gui/services/test_tab_reorganization_service.py` の `test_required_widgets_contains_tab_structure` に以下を追記する。

```python
        assert "tabMap" in required
        assert "tabResults" in required
        assert "tabErrors" in required
```

- [ ] **Step 2: テストを実行して失敗を確認する**

```bash
uv run pytest tests/unit/gui/services/test_tab_reorganization_service.py -v
```

期待結果: `tabMap` が `REQUIRED_WIDGETS` に存在せず失敗する。

- [ ] **Step 3: 実装する**

`src/lorairo/gui/services/tab_reorganization_service.py` の `REQUIRED_WIDGETS` を以下のように更新する。

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

- [ ] **Step 4: テストを実行して通ることを確認する(green)**

```bash
uv run pytest tests/unit/gui/services/test_tab_reorganization_service.py -v
```

期待結果: 全テストが通る。`test_validate_with_complete_widget_hierarchy` が新規必須ウィジェットの不足で失敗する場合は、そのテストの階層構築部に以下を追加する。

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

- [ ] **Step 5: コミットする**

```bash
git add src/lorairo/gui/services/tab_reorganization_service.py tests/unit/gui/services/test_tab_reorganization_service.py
git commit -m "test(gui): TabReorganizationService の必須ウィジェットに新タブを追加"
```

### Task 7: 全体検証(CI 相当フィルタ)

- [ ] **Step 1: フォーマットと型チェックを実行する**

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
```

期待結果: Ruff のエラーがなく、mypy でも既存エラー以外の新規エラーが出ない。

- [ ] **Step 2: CI 相当フィルタで全テストを実行する**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```

期待結果: 全テストが通る。タブインデックスに依存していた他テストが失敗した場合は、ウィジェット同一性ベース(`currentWidget() is window.tabBatchTag` など)へ修正して再実行する。

- [ ] **Step 3: 修正があればコミットする**

```bash
git add -A
git commit -m "test: タブ index 依存箇所を widget 同一性ベースに修正"
```

修正がなければスキップする。

### Task 8: PR 起票と保守

- [ ] **Step 1: プッシュと PR 作成を行う**

```bash
git push -u origin feat/gui-v11-phase1-nav-skeleton
gh pr create --title "feat(gui): Wireframes v11 Phase 1 — メインナビ 6 タブ骨格" --body "$(cat <<'EOF'
## Summary
- Claude Design「Wireframes v11」ハンドオフのナビ構造への第一歩として、メインタブを 6 枚構成(検索 / マップ / アノテーション / ジョブ / 結果 / エラー)に再編
- マップ / 結果タブはスタブ(それぞれ Phase 8 / Phase 2 で実装予定)
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

- [ ] **Step 2: PR 保守を自走する**

`agent-pr-autoloop` スキルで CI と bot レビューを監視し、安全であればスカッシュマージする。マージ後、ワークツリーを削除する。

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/gui-v11-phase1
```

---

## リスクと注意事項

- **QSettings 互換性:** `restoreState` はタブ構成変更の影響を受けないが、保存済みタブインデックスの意味が変わるため `SETTINGS_VERSION` を 2 へ更新する(Task 3 Step 5e)。
- **タブインデックス依存の他テスト:** Task 7 Step 2 で網羅的に検出する。`tabWidgetMainMode` へのインデックス直書きは、本計画ですべてウィジェット同一性参照へ置換することを原則とする。
- **サブモジュール変更なし:** 本 PR は `local_packages/*` に触れないため、pre-PR サブモジュールフックの対象外である。
- **`ErrorLogViewerDialog`:** クラスは未使用のまま残存する。Phase 3(Errors トリアージ)のウィジェット刷新時に削除する。
- **Export タブなし:** v11 ナビとの差分として PR 説明に明記済みであり、Phase 5 で対応する。

## 後続フェーズ着手時のチェックリスト

1. `docs/design/wireframes-v11/wireframes-v11.html` の該当フレーム(`data-screen-label` で検索)を精読する。
2. `docs/design/wireframes-v11/decisions-impact-on-wireframe.md` と関連 ADR を確認する。
3. 「v11 フレームと現行実装の対応およびフェーズ分割」表の未決事項(Phase 7 の A/B 選択、Phase 8 の ADR)は、ユーザー決定を得てから着手する。
4. フェーズごとに `docs/superpowers/plans/` に個別計画を作成する。
