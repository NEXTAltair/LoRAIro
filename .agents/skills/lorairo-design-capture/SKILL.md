---
name: lorairo-design-capture
version: "1.0.0"
description: "Capture LoRAIro design from the wireframes operation prototype or claude.ai/design recreations correctly. Use when syncing/mirroring design, reconciling Qt (.ui) or the DS AppShell with the design, or when nav/tab order, layout, or grouping looks off between the app and the prototype. The prototype's effective state is produced by render-time JS (e.g. restructureNav), so static-HTML grep alone misses it."
metadata:
  short-description: 操作プロトタイプ/claude.ai/design からの design 取り込みは render 時 JS 変換後の実効状態を正とする(静的HTMLだけで判断しない)。
---

# LoRAIro Design Capture

LoRAIro の**操作プロトタイプ**(`docs/design/wireframes/wireframes.html`)や `claude.ai/design` の再現物から、ナビゲーション・レイアウト・並び順・グルーピングを取り込むための手順である。

**ユーザーはブラウザで描画された操作プロトタイプを見てデザインを確認している。** したがって、取り込む対象は静的な HTML マークアップではなく、描画後の「実効状態」でなければならない。

## 核心ルール

**操作プロトタイプの実効デザインは描画時の JavaScript が決定する。静的 DOM の grep だけで判断してはならない。**

代表例として、`wireframes.html` の `restructureNav()` がある。この関数は静的な `topnav`(検索・マップ・アノテーション・ジョブ・結果・エラー・エクスポート・CLI)を、描画時に次の 2 グループへ並べ替える。

- **PIPE(パイプライン)**: `search → annotate → jobs → results → export`
- **UTIL(補助)**: `map → errors → cli`
- **実効ナビ順**: 検索・アノテーション・ジョブ・結果・エクスポート・マップ・エラー・CLI

この実効順が SSoT(単一の信頼できる情報源)である。DS(デザインシステム)の `AppShell.jsx` や Qt の `MainWindow.ui` は、静的な `topnav` の順序ではなく、この実効順に合わせて揃える。詳細は記憶 [[project_wireframe_prototype_restructurenav_ssot]] を参照する。

## 適用場面

- DS ミラー(`docs/design/lorairo-design-system/`)やワイヤーフレームをリポジトリへ取り込む・再同期するとき
- Qt 実機のタブ順・画面順・レイアウトが「デザインと違う」と指摘されたとき
- 操作プロトタイプと DS `AppShell` または Qt の間で、ナビゲーション順やグルーピングが食い違うとき
- `claude.ai/design` の DesignSync で取得した内容を Qt や DS に反映するとき

## ワークフロー

### Phase 1: 実効状態を取り出す

1. 対象の操作プロトタイプ HTML(`docs/design/wireframes/wireframes.html` など)を特定する。
2. **静的マークアップを grep するだけで終えない。** 描画時に DOM を組み替える JavaScript を探す。
   ```bash
   grep -nE "restructureNav|querySelector.*(nav|tab|vtab)|insertBefore|appendChild|reorder|dataset\.(role|tab)" <prototype>.html
   ```
3. 見つかった変換関数(`restructureNav` など)を**全文読み込み**、入力(静的順)から出力(実効順)への対応関係を確定する。多くの場合、`PIPE` や `UTIL` のような配列定数がグループ順と要素順を定義している。
4. 変換用の JavaScript が存在しない場合は静的順をそのまま実効順とし、存在する場合は変換後の順序を採用する。
5. 確信が持てないときは、Windows 側のブラウザから bind mount 経由で `file:///…` を開き、実際の描画結果を確認する。

### Phase 2: リポジトリ側を実効状態へ揃える

- **Qt タブ順**: `src/lorairo/gui/designer/MainWindow.ui` の `tabWidgetMainMode` 直下にある `<widget>` の宣言順が静的順である。さらに実行時には、`MainWindow._setup_*_tab()` によって `src/lorairo/gui/tab/*_tab.py` が埋め込まれ、ジョブタブは `insertTab(indexOf(tabResults))`、CLI タブは末尾への `addTab` で挿入される。これらを含めた**実行時の最終順**を実効順に一致させる。`.ui` ファイルを変更したら、`uv run --no-sync python scripts/generate_ui.py` で `_ui.py` を再生成する。
- **DS ミラー**: `docs/design/lorairo-design-system/ui_kits/lorairo-app/AppShell.jsx` などの静的順も、必要に応じて実効順へ更新する。DesignSync は静的マークアップをミラーするため、JavaScript による変換結果は反映されない。

### Phase 3: 検証

- Qt のタブ順をヘッドレス環境で実測する。
  ```bash
  QT_QPA_PLATFORM=offscreen uv run --no-sync python -c "from PySide6.QtWidgets import QApplication,QMainWindow; \
  from lorairo.gui.designer.MainWindow_ui import Ui_MainWindow; a=QApplication([]); w=QMainWindow(); \
  u=Ui_MainWindow(); u.setupUi(w); t=u.tabWidgetMainMode; print([t.tabText(i) for i in range(t.count())])"
  ```
  実行時の動的挿入を含む完全な順序は、`src/lorairo/gui/window/main_window.py` のロジックを再現して確認する。
- `tests/unit/gui/window/test_main_window_coverage.py` および `tests/unit/gui/tab/test_*_tab.py` を含む GUI テストを実行する。

## 落とし穴

- 静的な `topnav` が複数箇所にありすべて一致していても、それは JavaScript による並べ替え**前**の定義にすぎない。実効順とは別物である。
- DS ミラーの DesignSync はリポジトリとデザイン間の DS 部品を対象とした片方向同期であり、操作プロトタイプの画面構成や JavaScript は自動取り込みされない([[project_design_sync_is_components_not_screens]])。画面順は手動で揃える必要がある。
