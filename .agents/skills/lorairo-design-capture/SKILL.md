---
name: lorairo-design-capture
version: "1.0.0"
description: "Capture LoRAIro design from the wireframes operation prototype or claude.ai/design recreations correctly. Use when syncing/mirroring design, reconciling Qt (.ui) or the DS AppShell with the design, or when nav/tab order, layout, or grouping looks off between the app and the prototype. The prototype's effective state is produced by render-time JS (e.g. restructureNav), so static-HTML grep alone misses it."
metadata:
  short-description: 操作プロトタイプ/claude.ai/design からの design 取り込みは render 時 JS 変換後の実効状態を正とする（静的HTMLだけで判断しない）。
dependencies:
  - lorairo-mem
---

# LoRAIro Design Capture

LoRAIro の **操作プロトタイプ**（`docs/design/wireframes/wireframes.html`）や claude.ai/design の
recreation から nav・レイアウト・順序・グルーピングを取り込むときの手順。**ユーザーはブラウザで
描画した操作プロトタイプを見て design 確認している**ため、取り込むべきは「描画後の実効状態」であり、
静的 HTML markup ではない。

## 核心ルール

**操作プロトタイプの実効デザインは render 時 JS が決める。静的 DOM の grep だけで判断しない。**

代表例: `wireframes.html` の `restructureNav()` は静的 `topnav`
（検索/マップ/アノテーション/ジョブ/結果/エラー/エクスポート/CLI）を render 時に 2 グループへ
並べ替える:

- **PIPE**（パイプライン）: `search → annotate → jobs → results → export`
- **UTIL**（補助）: `map → errors → cli`
- 実効ナビ順 = **検索 / アノテーション / ジョブ / 結果 / エクスポート / マップ / エラー / CLI**

この実効順が SSoT。DS `AppShell.jsx` や Qt `MainWindow.ui` を揃える先はこの実効順であって、
静的 topnav 順ではない。詳細は記憶 [[project_wireframe_prototype_restructurenav_ssot]]。

## When to Use

- DS ミラー（`docs/design/lorairo-design-system/`）や wireframes を repo へ取り込む / 再同期するとき
- Qt 実機のタブ順・画面順・レイアウトが「デザインと違う」と指摘されたとき
- 操作プロトタイプと DS AppShell / Qt の間で nav 順・グルーピングが食い違うとき
- claude.ai/design の DesignSync で pull した内容を Qt や DS に反映するとき

## Workflow

### Phase 1: 実効状態を取り出す

1. 対象の操作プロトタイプ HTML を特定する（`docs/design/wireframes/wireframes.html` 等）。
2. **静的 markup を grep して終わらない。** render 時に DOM を組み替える JS を探す:
   ```bash
   grep -nE "restructureNav|querySelector.*(nav|tab|vtab)|insertBefore|appendChild|reorder|dataset\.(role|tab)" <prototype>.html
   ```
3. 見つけた変換関数（`restructureNav` 等）を**全文読み**、入力（静的順）→出力（実効順）の写像を確定する。
   配列定数（`PIPE` / `UTIL` 等）がグループ順と要素順を持つことが多い。
4. JS が無ければ静的順がそのまま実効順。ある場合は変換後を採用する。
5. 確信が持てないときは描画結果で確認する（Windows 側ブラウザで `file:///…` を開く、bind mount 経由）。

### Phase 2: repo 側を実効状態へ揃える

- **Qt タブ順**: `src/lorairo/gui/designer/MainWindow.ui` の `tabWidgetMainMode` 直下の
  `<widget>` 宣言順が静的順。runtime 挿入（ジョブ=`insertTab(indexOf(tabResults))` / CLI=`addTab` 末尾）を
  考慮した**実行時順**を実効順に一致させる。`TabReorganizationService` は順序非依存の存在検証のみで
  順序を制御しない。.ui 変更後は `uv run python scripts/generate_ui.py` で `_ui.py` を再生成する。
- **DS ミラー**: `docs/design/lorairo-design-system/ui_kits/lorairo-app/AppShell.jsx` 等の静的順も、
  必要なら実効順へ更新する（DesignSync は静的 markup を mirror するため JS 変換は反映されない）。

### Phase 3: 検証

- Qt タブ順は headless で実測する:
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python -c "from PySide6.QtWidgets import QApplication,QMainWindow; \
  from lorairo.gui.designer.MainWindow_ui import Ui_MainWindow; a=QApplication([]); w=QMainWindow(); \
  u=Ui_MainWindow(); u.setupUi(w); t=u.tabWidgetMainMode; print([t.tabText(i) for i in range(t.count())])"
  ```
  （runtime 挿入を含む完全順は `main_window.py` のロジックを再現して確認する。）
- GUI テスト（`test_main_window_coverage.py` を含む）を CI-equivalent filter で実行する。

## 落とし穴

- 静的 `topnav` が複数あり全て同じでも、それは JS 並べ替え**前**の層。実効順とは別物。
- DS ミラーの DesignSync は repo↔design の DS 部品の片方向同期で、操作プロトタイプの画面/JS は
  自動取り込みされない（[[project_design_sync_is_components_not_screens]]）。画面順は手で揃える。
