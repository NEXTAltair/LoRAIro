---
type: ADR
title: Qt implementation strategy for DS parts without Qt equivalents
status: Proposed
timestamp: 2026-06-20
tags: [gui, design-system]
---
# ADR 0073: Qt implementation strategy for DS parts without Qt equivalents

## Context

Issue #783 (Epic #781 / M1 Foundation)。Design System (`docs/design/lorairo-design-system/components/`)
には LoRAIro の PySide6 GUI にまだ対応物が無いコンポーネントがある。実フレーム
(M2–M6) を v12 / DS に整合させる前に、これらを Qt でどう出すかを方針として確定し、
各 M-issue がその場で設計を再発明しないようにする。

#782 で `theme.py` を DS token と 1:1 に整合させ、token (色・radius・border 幅・
font サイズ・`LETTER_CAPS` 等) は全コンポーネントから参照できる named 定数になった。
本 ADR はその token 基盤の上で「未対応 DS 部品の Qt 化方針」だけを決める
(個別 widget の実装は対応する後続 M-issue が担う)。

### DS 部品の Qt 対応状況

既に Qt primitive + `theme.py` global QSS / 既存 widget でカバー済み:

| DS part | Qt 対応 |
|---|---|
| Button / Input / Select / Checkbox / Slider | QPushButton / QLineEdit / QComboBox / QCheckBox / QSlider (`build_global_qss`) |
| Tabs / Dialog / Card / ProgressBar / DataTable | QTabBar / QDialog / QGroupBox / QProgressBar / QTableView (`build_global_qss`) |
| Chip / TagChip / TypeBadge | `theme.chip_qss` / `tag_chip_untranslated_qss` / `theme.badge_qss` |
| Pagination / Thumbnail | `pagination_nav_widget` / `thumbnail` (M2) |
| Terminal | dark pane token (`TERMINAL_*`) |

対応物が無く、本 ADR で方針を決める対象:

| DS part | 現状 |
|---|---|
| **Toast** (feedback) | 一時表示の浮遊通知。`error_notification_widget` は StatusBar 常設インジケータで別物 |
| **TagInput** (forms) | トークン入力欄 (chip pill + 入力)。Qt primitive 無し |
| **Menu** (surfaces) | trigger に紐づく dropdown / context menu。QMenu はあるが DS 仕様 (glyph / shortcut / danger 行) との対応未確定 |
| **SegmentedControl** (forms) | 横並びの bordered トグル (未解決/解決済/すべて 等)。Qt primitive 無し |

## Decision

未対応 DS 部品ごとに次の Qt 実装方針を確定する。共通原則は
**(a) Qt が primitive を持つものは subclass せず native + QSS を使う、
(b) primitive が無いものだけ `theme.py` token を組んだ custom widget を新設する、
(c) borders-not-shadows / chip 文法 / emoji 不使用 (DS は Unicode glyph) を守る、
(d) 既存資産 (`FlowLayout`, `theme.chip_qss`) を再利用する**。

1. **Toast → 新設 custom `QFrame` 浮遊 overlay**。
   メインウィンドウを親に right-bottom へ anchor し、左 stripe を status 色
   (`theme.job_status_color` / status token) で塗る。title + message label、任意の
   inline action ボタンと ✕ close、`QTimer` による auto-dismiss を持つ。
   `QMessageBox` (modal) や `QSystemTrayIcon.showMessage` (OS 通知) は DS の
   in-app 浮遊通知と挙動が異なるため採らない。

2. **TagInput → 新設 custom `QWidget`**。
   `tag_cloud_widget` の `FlowLayout` を再利用して削除可能な accent chip pill
   (`theme.chip_qss("accent")`) を並べ、末尾に commit 用 `QLineEdit` を置く。
   Enter / セパレータ文字で commit、空入力時 Backspace で末尾 pop、✕ で個別削除。
   値は danbooru canonical を verbatim 保存し翻訳しない ([[0068]] と整合)。

3. **Menu → native `QMenu` + `QAction`**。新規 widget は作らない。
   `build_global_qss` が既に QMenu/`::item`/`::separator` を DS 化済み。
   glyph は action text の先頭 Unicode、shortcut は `QAction.setShortcut`
   (`QKeySequence`)、区切りは `addSeparator`、danger 行は objectName + 個別 QSS で
   `ERR` 系に着色する。共通生成が要れば薄い builder helper に留める。

4. **SegmentedControl → `QButtonGroup` + checkable flat `QPushButton` の連結行**。
   exclusive な横トグルとして、active セグメントを `ACCENT_SOFT` 塗りにする。
   facet sidebar の縦 radio group (M2) とは用途 (横モード切替 vs 縦ファセット) が
   異なるため別パターンとして扱う。

## Rationale

native Qt primitive がある Menu を custom 実装すると、ショートカット・
アクセシビリティ・プラットフォーム挙動を自前で再実装する負債になるため native QMenu を選ぶ。
逆に Toast / TagInput / SegmentedControl は Qt に直接対応する primitive が無く、
QLabel / QMessageBox の流用では DS 挙動 (auto-dismiss・token 編集・連結トグル) を
満たせないため custom widget を新設する。いずれも #782 の token と既存 `FlowLayout` /
chip QSS を組み合わせるだけで構成でき、新しい描画レイヤや shadow を持ち込まない
(borders-not-shadows)。

## Consequences

- 後続 M-issue は本表に従って実装する: Toast / TagInput / SegmentedControl は
  `src/lorairo/gui/widgets/` に新 widget、Menu は呼び出し側で native QMenu を組む。
- 新 widget は `theme.py` の named token のみ参照し、DS 値を直書きしない (#782 の
  parity test と整合)。
- Toast を導入する M-issue は表示位置・重なり順・複数同時表示の制御を併せて決める。
- 本 ADR は方針のみで widget 実装を含まない。実装は各部品の M-issue で行い、
  本 ADR の Related から参照する。
