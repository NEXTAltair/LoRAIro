---
type: ADR
title: Qt implementation strategy for DS parts without Qt equivalents
status: Accepted
timestamp: 2026-06-20
tags: [gui, design-system]
---
# ADR 0073: Qt implementation strategy for DS parts without Qt equivalents

## Context

Issue #783(Epic #781 / M1 Foundation)に関連する設計判断である。Design System(`docs/design/lorairo-design-system/components/`)には、LoRAIro の PySide6 GUI にまだ対応ウィジェットが存在しない部品がある。実画面(M2–M6)を v12 および Design System に整合させる前に、これらの部品を Qt でどう実現するかの方針を確定し、後続の各 M-issue で設計が再発明されるのを防ぐ。

Issue #782 により、`theme.py` は Design System のトークンと 1 対 1 で整合した。色、角丸半径、枠線幅、フォントサイズ、`LETTER_CAPS` などのトークンは、全コンポーネントから参照可能な名前付き定数になっている。本 ADR はそのトークン基盤の上で「未対応 DS 部品の Qt 実装方針」のみを定める。個別ウィジェットの実装自体は、対応する後続の M-issue が担う。

### DS 部品の Qt 対応状況

すでに Qt の標準部品と `theme.py` のグローバル QSS、または既存ウィジェットで対応済みの部品は次のとおりである。

| DS part | Qt 対応 |
|---|---|
| Button / Input / Select / Checkbox / Slider | `QPushButton` / `QLineEdit` / `QComboBox` / `QCheckBox` / `QSlider`(`build_global_qss`) |
| Tabs / Dialog / Card / ProgressBar / DataTable | `QTabBar` / `QDialog` / `QGroupBox` / `QProgressBar` / `QTableView`(`build_global_qss`) |
| Chip / TagChip / TypeBadge | `theme.chip_qss` / `tag_chip_untranslated_qss` / `theme.badge_qss` |
| Pagination / Thumbnail | `pagination_nav_widget` / `thumbnail`(M2) |
| Terminal | ダークペイントークン(`TERMINAL_*`) |

対応物がなく、本 ADR で方針を確定する対象は次の 4 部品である。

| DS part | 現状 |
|---|---|
| **Toast**(feedback) | 一時表示の浮遊通知。`error_notification_widget` はステータスバー常設インジケータであり別物 |
| **TagInput**(forms) | チップピルと入力欄を組み合わせたトークン入力欄。対応する Qt 標準部品がない |
| **Menu**(surfaces) | トリガーに紐づくドロップダウンおよびコンテキストメニュー。`QMenu` は存在するが、DS 仕様(グリフ、ショートカット、危険操作行)との対応が未確定 |
| **SegmentedControl**(forms) | 横並びの枠付きトグル(未解決/解決済/すべて等)。対応する Qt 標準部品がない |

## Decision

未対応 DS 部品ごとの Qt 実装方針を次のとおり確定する。共通原則は以下の 4 点とする。

- Qt に標準部品がある場合はサブクラス化せず、ネイティブ部品と QSS の組み合わせで実現する。
- 標準部品がないものだけを、`theme.py` のトークンを用いたカスタムウィジェットとして新設する。
- 影ではなく枠線で区切る方針(borders-not-shadows)、チップ文法、絵文字不使用(DS では Unicode グリフを使用)を順守する。
- `FlowLayout` や `theme.chip_qss` といった既存資産を再利用する。

### 1. Toast → カスタム `QFrame` による浮遊オーバーレイを新設する

メインウィンドウを親として右下へ配置し、左端のストライプを状態色(`theme.job_status_color` およびステータストークン)で塗る。タイトルとメッセージのラベル、任意のインラインアクションボタン、閉じるボタン(✕)、および `QTimer` による自動消去機能を持たせる。

モーダルな `QMessageBox` や OS 通知を出す `QSystemTrayIcon.showMessage` は、DS が求めるアプリ内浮遊通知と挙動が異なるため採用しない。

### 2. TagInput → カスタム `QWidget` を新設する

`tag_cloud_widget` の `FlowLayout` を再利用し、削除可能なアクセントチップ(`theme.chip_qss("accent")`)を並べ、末尾に確定用の `QLineEdit` を配置する。Enter キーまたは区切り文字で確定、空入力時の Backspace で末尾のチップを削除、✕ ボタンで個別削除とする。

保持する値は danbooru 正規形をそのまま保存し、翻訳は行わない([[0068]] と整合させる)。

### 3. Menu → ネイティブ `QMenu` と `QAction` を使用する

新規ウィジェットは作成しない。`build_global_qss` がすでに `QMenu`、`::item`、`::separator` のスタイルを DS 化済みである。

- グリフはアクションテキスト先頭の Unicode 文字で表現する。
- ショートカットは `QAction.setShortcut`(`QKeySequence`)で設定する。
- 区切り線は `addSeparator` を用いる。
- 危険操作行(danger 行)は `objectName` と個別 QSS で `ERR` 系カラーに着色する。

共通の生成処理が必要になった場合でも、薄いビルダーヘルパーに留める。

### 4. SegmentedControl → `QButtonGroup` とチェック可能なフラット `QPushButton` の連結行とする

排他的な横方向トグルとして構成し、選択中(active)のセグメントを `ACCENT_SOFT` で塗りつぶす。ファセットサイドバーの縦方向ラジオグループ(M2)とは用途(横方向のモード切替と縦方向のファセット選択)が異なるため、別パターンとして扱う。

## Rationale

Qt に標準部品がある `Menu` を独自実装すると、ショートカット処理、アクセシビリティ、プラットフォーム固有の挙動を自前で再実装する保守負債を抱えることになる。そのためネイティブの `QMenu` を選択する。

一方、`Toast`、`TagInput`、`SegmentedControl` には直接対応する Qt 標準部品が存在しない。`QLabel` や `QMessageBox` の流用では、自動消去、トークン編集、連結トグルといった DS の挙動を満たせないため、カスタムウィジェットを新設する。いずれの部品も #782 で整備したトークンと既存の `FlowLayout` およびチップ QSS の組み合わせだけで構成でき、新たな描画レイヤーや影表現を持ち込まずに済む(borders-not-shadows)。

## Consequences

- 後続の M-issue は本方針に従って実装する。`Toast`、`TagInput`、`SegmentedControl` は `src/lorairo/gui/widgets/` に新規ウィジェットとして追加し、`Menu` は呼び出し側でネイティブ `QMenu` を組み立てる。
- 新規ウィジェットは `theme.py` の名前付きトークンのみを参照し、DS の色やサイズ値を直書きしない(#782 のパリティテストと整合させる)。
- `Toast` を導入する M-issue では、表示位置、重なり順、複数同時表示時の制御も併せて決定する。
- 本 ADR は実装方針のみを定め、ウィジェット本体の実装は含まない。実装は各部品を担当する M-issue で行い、本 ADR の Related から参照する。
