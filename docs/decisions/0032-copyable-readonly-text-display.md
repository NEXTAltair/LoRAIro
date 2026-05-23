# ADR 0032: Copyable Read-Only Text Display Policy

- **日付**: 2026-05-23
- **ステータス**: Accepted

## Context

LoRAIro の Qt GUI では、画像詳細・アノテーション結果・メタデータ・ログ的な補助情報など、
ユーザーが読み取り専用のテキストを確認する場面が多い。これらの文字列は、検索条件の再利用、
外部ツールへの貼り付け、Issue 報告、プロンプト調整などでコピーされる。

一方で、既存 UI では表示目的の `QLabel`、編集可能に見える `QTextEdit`、表形式の
`QTableWidget` などが混在し、以下の問題が起きやすい。

- 見えている文字列を選択・コピーできない。
- 読み取り専用情報なのに編集可能に見える。
- 複数行テキストや長文を `QLabel` で表示し、選択・スクロール・折り返しが不自然になる。
- 表のセルコピー、行コピー、詳細全体コピーの責務が曖昧になる。
- 右クリックメニューの有無がウィジェットごとに揃わない。

Qt では、単純な表示には `QLabel` が軽量だが、長文や editor-like な表示では
`QTextEdit` / `QPlainTextEdit` / `QLineEdit` の read-only 運用の方が、選択・コピー・
スクロール・コンテキストメニューを自然に扱える。LoRAIro では、この使い分けを GUI 実装の
共通方針として明文化する。

## Decision

LoRAIro の Qt GUI では、読み取り専用テキスト表示を以下の方針に統一する。

1. **単一行・コンパクトなラベルは `QLabel` を使い、選択可能にする。**
   ファイル名、モデル名、rating、score、短い status、カウント、固定ラベル横の値などは
   `QLabel` のまま表示してよい。ただし、ユーザーが値を再利用する可能性がある表示値には
   `Qt.TextSelectableByMouse` を設定する。キーボード選択が必要なフォーム状の値では
   `Qt.TextSelectableByKeyboard` も併用してよい。

2. **複数行・長文・editor-like な表示は read-only text widget を使う。**
   caption、prompt、タグ一覧、エラー詳細、JSON 断片、複数行 metadata、生成結果の詳細などは
   `QLabel` ではなく、用途に応じて `QTextEdit`、`QPlainTextEdit`、または `QLineEdit` を
   read-only で使う。

   - リッチテキストやリンクを扱う場合: read-only `QTextEdit`
   - プレーンテキスト、ログ、JSON、固定幅表示が自然な場合: read-only `QPlainTextEdit`
   - 単一行だがフォーム入力欄のように全選択・コピーしたい場合: read-only `QLineEdit`

3. **read-only text widget は編集不可であることを明確にする。**
   `setReadOnly(True)` を必須とし、必要に応じて frame、palette、focus policy、placeholder を
   調整して「編集欄」ではなく「コピー可能な表示」であることを示す。読み取り専用なのに
   `textChanged` を通常入力として扱う実装は避ける。

4. **`QTableWidget` はセル選択とコピー動作を明示する。**
   表形式データは `QTableWidget` / table view の selection behavior と selection mode を
   画面の用途に合わせて決める。メタデータや結果一覧のようにセル値の再利用が主目的なら
   セル選択を許可し、`Ctrl+C` で選択セルをタブ区切り・改行区切りの plain text としてコピーする。
   行単位の操作が主目的の一覧では行選択を優先してよいが、その場合もコピーされる範囲を
   tooltip、context menu action、または action 名で明確にする。

5. **context menu はコピー対象に合わせて標準化する。**
   コピー可能な text widget は Qt 標準 context menu を基本とする。`QLabel` や table で
   標準メニューが不十分な場合は、少なくとも `Copy` を提供する。長文表示では `Select All` も
   提供する。独自 action を追加する場合でも、標準のコピー操作 (`Ctrl+C`) と競合させない。

6. **per-field copy と whole-details copy の責務を分ける。**
   個別フィールドのコピーは、その値を表示する widget 自身が担う。画像詳細・アノテーション詳細・
   metadata summary のような複数フィールドの一括コピーは、詳細パネルや dialog などの
   aggregate owner が `Copy Details` / `Copy All` action として提供する。

7. **whole-details copy は安定した plain text を出力する。**
   一括コピーは UI の見た目ではなく、ラベル付きの plain text に整形する。例:
   `File: ...`、`Caption: ...`、`Tags: ...`。表データを含む場合は、TSV など貼り付け先で
   扱いやすい形式を使う。HTML や装飾付き rich text を唯一のコピー形式にしない。

8. **読み取り専用表示のために source model を変更しない。**
   コピー可能化は GUI 表示層の責務であり、DB schema、annotation model、repository、
   image processing pipeline には影響させない。

## Rationale

### なぜ `QLabel` を全面禁止しないか

短い値や密度の高い panel では `QLabel` が最も軽量で、既存 Qt Designer UI とも相性が良い。
ただし `QLabel` の初期状態は選択できないため、ユーザーが値を再利用する表示では selectable flag を
明示する必要がある。

### なぜ長文を read-only editor に寄せるか

複数行テキストは、選択範囲、スクロール、折り返し、全選択、context menu、キーボードコピーの
期待値が editor に近い。`QLabel` で長文を表示すると、layout の伸縮やコピー操作が画面ごとに
不安定になりやすい。read-only `QTextEdit` / `QPlainTextEdit` は編集を許可せずに、これらの
操作を標準機能として提供できる。

### なぜ table copy policy を明示するか

表は「行を選ぶ UI」と「セル値をコピーする UI」の両方に使われる。選択単位を曖昧にすると、
ユーザーはコピー結果を予測できない。セル選択・行選択・コピー形式を画面ごとに決めることで、
一覧操作と値の再利用を両立できる。

### なぜ per-field copy と whole-details copy を分けるか

単一の値をコピーしたい場合と、Issue 報告や外部処理のために詳細全体をコピーしたい場合では
必要な形式が違う。個別 widget が自分の表示値をコピー可能にし、aggregate owner が全体を
ラベル付き plain text にまとめることで、責務と出力形式が明確になる。

## Consequences

### 良い点

- 画像詳細・アノテーション結果・メタデータの値を、見えている場所から直接コピーできる。
- 長文表示が editor-like な標準操作を持ち、`QLabel` の layout 問題を避けやすくなる。
- table のコピー結果が予測しやすくなり、spreadsheet や Issue 本文へ貼り付けやすくなる。
- 「個別値のコピー」と「詳細全体のコピー」の実装責務が分かれる。

### 悪い点・トレードオフ

- `QTextEdit` / `QPlainTextEdit` は `QLabel` より重く、密な一覧の全セルに使うべきではない。
- Qt Designer 上の既存 `QLabel` を置き換える場合、layout と tab order の再確認が必要になる。
- `QTableWidget` の `Ctrl+C` copy は Qt 標準だけでは不足する場合があり、画面側で action 実装が
  必要になる。
- whole-details copy の出力形式は、画面追加時に aggregate owner 側で保守する必要がある。

### 実装方針

実装 Issue では以下の順で進める。

1. 詳細パネルや dialog の単一行値 `QLabel` に selectable flag を設定する。
2. caption、prompt、タグ一覧、metadata などの長文表示を read-only text widget へ寄せる。
3. table view / `QTableWidget` ごとに selection behavior、selection mode、`Ctrl+C` のコピー形式を
   明示する。
4. 必要な widget には `Copy` / `Select All` context menu action を追加する。
5. 詳細パネルや dialog の owner に `Copy Details` / `Copy All` を実装し、ラベル付き plain text を
   clipboard に設定する。
6. GUI テストでは、代表 widget の read-only 状態、selectable flag、copy action の有無、
   whole-details copy の出力文字列を確認する。

## Related

- Issue: NEXTAltair/LoRAIro#374
- ADR 0009: Qt Decoupling Design
- ADR 0011: MainWindow UI Redesign
- ADR 0030: Batch Annotation Model Selection UI
