# LoRAIro Design System

**LoRAIro** から抽出したデザインシステムです。LoRAIro は LoRA / ファインチューン学習用の画像データセットを準備する、日本語のデスクトップツール。リサイズ・AI 自動タグ付け・キャプション/スコア生成・SQLite ベースのメタデータ管理を自動化し、**PySide6 (Qt) GUI** とエージェント向けの **Typer CLI** の両方を備えます。

> **LoRAIro** という名前は「**LoRA 用画像を色々（いろいろ）する**」スクリプトを略したもの。ブランドは一般的な開発ツールの冷たいブルーグレーではなく、温かみのある「和紙に墨」のパレットに寄せています。

これは **アプリの視覚言語をコード化したもの** — トークン、ファウンデーションの見本、再利用可能な React プリミティブ、そしてデスクトップ UI のインタラクティブな再現 — であり、デザインエージェントがブランドに沿った LoRAIro の画面・モック・スライド・プロトタイプを作れるようにするものです。

---

## ソース（出典）

ここにあるものはすべて、プロダクト自身のデザインの「真実の源（source of truth）」からリバースエンジニアリングしました。さらに深く知るにはこちらを参照してください:

- **GitHub — [NEXTAltair/LoRAIro](https://github.com/NEXTAltair/LoRAIro)**（MIT）。参照した主なファイル:
  - `src/lorairo/gui/theme.py` — **Theme v1**: 正準のデザイントークン + グローバル Qt スタイルシート（QSS）ジェネレータ。色・形・タイポの唯一の真実の源。
  - `docs/design/theme-v1/hifi-mock.html` — QSS を正規化する元になったハイファイ HTML モック（oklch → hex）。視覚上の SSoT。
  - `docs/design/wireframes-v11/` — `HANDOFF.md` + `wireframes-v11.html`。全画面カタログとプロダクト上の意思決定。
  - `src/lorairo/gui/designer/*.ui` + `widgets/*.py` — Qt の画面レイアウト。
  - `src/lorairo/cli/` + `docs/cli.md` — JSONL の CLI コントラクトとグリフ語彙。

> アップロード `uploads/LoRAIro-01.zip` が参照されていましたが、ワークスペースには空で届きました — そのため上記の GitHub リポジトリを正準のソースとして使用しています。zip に追加のブランドアセットが含まれていたなら、再添付いただければ取り込みます。

---

## プロダクトの文脈

- **1 プロダクト・1 サーフェス**: 単一ウィンドウの **デスクトップアプリケーション**（ウェブサイトでもモバイルアプリでもない）。情報密度が高く、マルチペインで、キーボード駆動。日本語ファーストの UI で、識別子・schema 名・モデル名・コードには英語を維持。
- **ワークフロー中心**: 上部のタブバーがパイプラインを進めます — **検索 Search → マップ Map → アノテーション Annotate → ジョブ Jobs → 結果 Results → エラー Errors → エクスポート Export → CLI**（⌘1–⌘8）。
- **コアループ**: データセットを検索/絞り込み → 画像をステージング → ローカル + API モデルのアノテーションパイプライン（TAGGER → CAPTION → SCORER → RATING → UPSCALE）を構成 → 追跡可能な Job として実行 → 結果をトリアージ → エクスポート。
- **2 つの動作面**: GUI と、構造化されエージェントから駆動できる CLI（stdout に `item` / `result` / `error` の JSONL を出力）。ダークなターミナルペインは、温かい和紙の世界が唯一ダークに転じる場所です。

---

## コンテンツの基本

LoRAIro のコピーの書き方:

- **日本語ファースト、技術用語は英語。** UI のクローム・ラベル・補助テキストは日本語（検索, アノテーション, 実行中, 待機, 失敗）。識別子は英語/原文のまま: モデル名（`claude-haiku-4-5`, `wd-eva02-large-v3`）、schema フィールド（`is_edited_manually`）、ジョブ種別（`model_install`, `provider_batch`）、CLI コマンド。リポジトリの目安: *3 語以上の英語フレーズには日本語を併記、2 語以下の識別子・schema 参照・コード・モデル名は英語のまま。*
- **簡潔で事実ベース。** ラベルは名詞か名詞句 — 「検索結果」「実行中 / キュー」「対象 128 枚（検索から追加）」。マーケティング的な語調・感嘆・二人称呼びかけはなし。ツールは事実と件数を述べる。
- **数値は一級市民で等幅。** 件数（「1,247 件 / 表示 1–48」）、コスト（「$0.0011/img · ~0.8s」）、進捗（「45% (350.0/780.0 MB)」）、時刻（「14:32」）、スコア（「0.82」）がいたるところにあり、常に JetBrains Mono。日本語文脈では全角の 件/枚 カウンタを使う。
- **ステータスは語彙。** 小さく固定された語彙を、そのまま繰り返し使う: `installed` / `API ready` / `needs key` / `discontinued`、実行中 / 待機 / 完了 / 失敗 / 中止。終端状態の語（ADR 0034）: FAILED / CANCELED / TERMINATED / UNRESPONSIVE。
- **絵文字は使わない。** 非テキストのグリフは機能的な Unicode 記号のみ（「アイコノグラフィ」参照）。CLI は Windows cp932 で生き残るため ✓✗ ではなく ASCII マーカー `[OK] [--] [!] [i]` を使う。
- **声のトーン例**: モデルピッカー下の補助行 — *「○ needs key をクリックすると設定の該当プロバイダ欄が開きます」*（機能的・指示的で、日本語の案内と英語のステータス語を混在）。

---

## 視覚のファウンデーション

- **パレット — 温かい和紙と墨。** 背景はオフホワイトの紙（`--paper #fbfaf6`）と少し濃いバンド（`--paper-shade #f1efe6`）、カードは純白。テキストはニアブラックの墨と、2 階調の柔らかいグレー。唯一のアクセントは **テラコッタ / クレイ**（`--accent #c25e3f`, oklch(0.62 0.14 32)）— 主要アクション・選択・アクティブタブの下線に使う。それ以外はすべて暖色の中立スケール。これは意図的に *ブルー系の開発ツールにしない*。
- **ステータス色** は、よくある 4 色を抑えた土っぽいバージョン: ok = モスグリーン `#3c8a55`、warn = オーカー `#b87f1f`、err = ブリック `#b8402c`、info = スレートブルー `#3d6f9e`。各色は 3 点セットで提供（ソリッド / ソフト塗り / 同系の罫線）。
- **ダークなサーフェスは 1 つだけ。** ターミナル / JSONL ペイン（`--terminal #23211d`）のみがダークで、独自のシンタックスパレット（key/string/number/boolean）を持つ。それ以外は反転しない。
- **タイポ。** 本文は **Noto Sans JP**（日本語ファースト）、コードと数値メタは **JetBrains Mono**。コンパクトなデスクトップスケール: 13px ベース、11px スモール、14/18px 見出し、10px 数値メタ。初期ワイヤーフレームで使っていた手書き書体（Kalam）は、このクリーンでモダンなペアリングのため Theme v1 で **廃止**。
- **形。** カード/ボタン/入力は 6px の角丸、チップは 10px、小バッジは 3px、外側のウィンドウは 8px。区切りは罫線が担う: いたるところ 1px の `--line` ヘアライン、アクティブタブには 2px のアクセント下線、選択サムネには 2px のアクセント枠。
- **スペーシング。** 4 / 8 / 12 / 16 / 24 の厳格なスケール。密度の高いデスクトップ級のパディング（カードは 12px、入力は 3–6px）。
- **エレベーションはほぼフラット。** アプリは「影ではなく罫線」。唯一の影は浮遊するウィンドウシェル（`0 2px 10px rgba(26,26,26,.07)`）。加えてローディングオーバーレイ用の半透明の墨スクリム。
- **背景** はフラットな紙の塗り — グラデーションなし（上品な例外が 1 つ: サムネのプレースホルダが控えめな `135deg` の paper-shade グラデーション）、写真なし、イラストなし、テクスチャなし。画像は *ユーザー自身のデータセット* を正方形サムネで見せる — クロームは中立に保ち、画像にすべての色を担わせる。
- **ステート。** Hover = 罫線とテキストをアクセントに寄せる（ボタン）、または paper-shade 塗り（行・ゴーストボタン・サムネ）。Press = accent-soft 塗り。Focus = アクセント罫線 + 柔らかなアクセントのリング。Selected = accent-soft の行 / アクセント枠のタイル。Disabled = paper-shade 塗り + 淡い墨、discontinued モデルは取り消し線を保持（履歴は決して消さない）。
- **モーション** は最小限で素早い: 色/罫線の遷移 ~0.12s、進捗の塗り ~0.3s。バウンスなし、装飾的なループなし、パララックスなし。ショーではなく道具。
- **チップの文法。** ドットが可用性をエンコードする: **● = 利用可**（installed / ready / running、ok か info 色）· **○ = 要対応 または 無効**（needs key = warn、queued = neutral、discontinued = 淡色）。これは覚えること — アプリ全体で使う。

---

## アイコノグラフィ

LoRAIro には **アイコンフォントも、SVG アイコンセットも、ラスターアイコンもない** — そしてロゴ画像もありません。これは意図的で、維持する価値があります:

- **ロゴ** は純粋な文字ワードマーク: `LoRA` を墨、`Iro` を `--accent` で。マークもシンボルもなし。（`guidelines/brand-logo.card.html` 参照。）
- **機能グリフはプレーンな Unicode** で、意味を持つ箇所にのみ控えめに使う:
  - `⚙` 設定の歯車（タイトルバー）· `▾` セレクトのキャレット · `→` パイプラインのステージ矢印 · `▶` 実行 · `▸` レビュー/展開 · `×` タグ削除 · `●` / `○` ステータスドット · `↝` シャドウ/自動取得ステージ。
- **CLI マーカーは ASCII** で、Windows cp932 エンコーディングで生き残らせる: `[OK]` `[--]` `[!]` `[i]`（出典: `src/lorairo/cli/_glyphs.py`）。
- **絵文字はどこにも使わない。**
- したがって `assets/` は意図的にほぼ空です — 出荷するブランドバイナリがありません。*拡張* モックのためにプロダクト自身が持たない補助 UI アイコン（フォルダ・検索など）が必要なら、**[Lucide](https://lucide.dev)** のような細線の CDN セットを使い、**チームに置き換えを明示**してください — ただし実アプリに存在するものには上記の Unicode グリフを優先すること。

---

## インデックス / マニフェスト

ルート:
- **`styles.css`** — 利用側がリンクする唯一のエントリポイント。3 つのトークンファイルのみを `@import` する。
- **`tokens/`** — `colors.css` · `typography.css`（+ Google Fonts の import）· `spacing.css`。ベーストークン + セマンティックエイリアス。
- **`readme.md`** — このガイド。
- **`SKILL.md`** — Claude Code で使うための Agent-Skill フロントマター。
- **`assets/`** — 意図的に最小限（「アイコノグラフィ」参照）。

再利用可能なコンポーネント（`components/<group>/`、ネームスペース `window.LoRAIroDesignSystem_64d8f7`）:
- **forms/** — `Button`（default/primary/ghost · base/small）, `Input`（+ ラベル, 複数行）, `Select`, `SegmentedControl`（status / mode トグル, 件数）, `Checkbox`（ラベル + indeterminate, 複数選択）, `Slider`（quality_score 0–10 のしきい値 / 手動スコア, アクセント塗り + mono 値）, `TagInput`（タグ集合の編集 · Enter/カンマで確定 · canonical 固定）。
- **feedback/** — `Chip`（ok/warn/err/info/neutral/muted/accent + ドット文法）, `TagChip`, `TypeBadge`, `ProgressBar`（info/ok, ストライプ）, `SummaryStat`（KPI タイル）, `Toast`（一時通知 · ステータス色の左ストライプ + グリフ · 自動消去 / floating）。
- **data/** — `Card`, `DataTable`（columns/rows, レンダースロット）, `Thumbnail`（画像タイル + 数値メタ）, `Pagination`（件数・範囲 mono + 前後 + ページ番号, ADR 0006）。
- **surfaces/** — `Tabs`（上部ナビ, アクセント下線）, `Terminal`（ダークな JSONL ペイン + `.K/.S/.N/.B/.Muted` シンタックスヘルパー）, `Dialog`（墨スクリム上のモーダル, ESC/scrim 閉じ, confirm variant）, `Menu`（ドロップダウン / コンテキストメニュー · グリフ + ショートカット · separator / danger · ESC・外側クリックで閉じ）。
- **annotate/** — `StageCard`（パイプラインのステージ, active/shadow）, `ModelRow`（ピッカー行）。

ファウンデーション見本カード（`guidelines/`、Design System タブに表示）: surface / ink & line / accent / status / terminal の各色 · sans / mono / type-scale · spacing / radii · チップ文法 · ロゴ。

UI キット（`ui_kits/lorairo-app/`）— デスクトップアプリのインタラクティブな再現。`index.html` がシェル + 各画面をマウント。タブ（検索 / マップ / アノテーション / ジョブ / 結果 / エラー / エクスポート / CLI）と ⚙ 設定モーダルをクリックできる。画面ファイル:
- `AppShell.jsx`（タイトルバー + ナビ）· `SettingsScreen.jsx`（API キー / モデルルート / インストーラモーダル）。
- `SearchScreen.jsx`（フィルタサイドバー + サムネグリッド）· `MapScreen.jsx`（タグクラスタ散布図）· `AnnotateScreen.jsx`（パイプライン + モデルピッカー）。
- `JobsScreen.jsx`（サマリ + ステージ別の実行中 + 履歴）· `ResultsScreen.jsx`（品質トリアージ）· `ErrorsScreen.jsx`（グループ化された失敗トリアージ）。
- `ExportScreen.jsx`（ステージング対象 + 出力ファイル + フォーマット）· `CLIScreen.jsx`（JSONL コントラクト）· `tagI18n.jsx`（タグ表示翻訳の共有モジュール · Search / Tag Edit 共用）。

---

## 使い方

利用側は単一のスタイルシートをリンクし、コンポーネントをバンドルのネームスペースから読み込みます:

```html
<link rel="stylesheet" href="styles.css">
<script src="_ds_bundle.js"></script>
<script>
  const { Button, Chip, Card, DataTable, Tabs } = window.LoRAIroDesignSystem_64d8f7;
</script>
```

トークンは CSS カスタムプロパティ（`var(--accent)`, `var(--paper)`, `var(--font-mono)`）経由で参照すること — hex を直書きしない。`_ds_bundle.js` と `_ds_manifest.json` はコンパイラが生成します。手で編集しないでください。

---

> **ローカル取り込みメモ (NEXTAltair):** これは Claude Design プロジェクト "LoRAIro Design System"
> (`64d8f727-6f59-44e6-b3a3-26b89f088b63`) を参照用にミラーしたもの。compiled の
> `_ds_bundle.js` / `_ds_manifest.json`、lint 設定、`uploads/` 入力、`screenshots/` は除外。
> token は `src/lorairo/gui/theme.py` から逆生成されており実テーマと 1:1。Qt 実装の見本として使う
> (直接組み込み不可)。`components/data/` は `.gitignore` の `data/` 例外で追跡する。
