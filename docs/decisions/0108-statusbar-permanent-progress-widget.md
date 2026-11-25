---
type: ADR
title: 進捗はステータスバー常設の専用部品に出し、showMessage は操作結果の通知だけに使う
status: Accepted
timestamp: 2026-11-11
tags: [gui, statusbar, progress, notification, qt]
---

# ADR 0108: 進捗はステータスバー常設の専用部品に出し、showMessage は操作結果の通知だけに使う

## Context

従来、ステータスバーの一時メッセージ欄(`QStatusBar.showMessage`)を、ワーカーの進捗表示と操作結果の通知(「タグを追加しました」「設定を保存しました」等)が共用していた。一時メッセージ欄は 1 本しかないため、進捗の更新が通知を上書きし、逆に通知が進捗を上書きする問題が起きていた。特に進捗は高頻度で更新されるため、通知が読まれる前に消えてしまう。

アノテーションの進捗だけは既に `AnnotationProgressWidget` を `addPermanentWidget` で常設していたが、同時に `showMessage(phase)` も呼んでいたため、通知欄の取り合いは解消されていなかった。

なお、`ProgressStateService` は `QObject` ではない素の Python クラスであり、`MainWindow` のスロットから呼び出される構造になっている。

## Decision

### 1. 進捗はステータスバー常設の専用部品に出す

`ProgressStateService` が `StatusProgressWidget`(工程名ラベルと `QProgressBar` の組み合わせ)を生成し、`QStatusBar.addPermanentWidget` でステータスバーへ常設する。常設部品は `showMessage` の一時メッセージで隠れないため、進捗と通知が互いを消し合うことがなくなる。

### 2. `showMessage` は操作結果の通知だけに使う

従来 `showMessage` で出していた進捗表示(バッチ登録開始、ワーカー進捗、バッチ進捗、旧バッチアノテーション進捗、アノテーション工程名、タグ DB 準備中)はすべて専用部品へ移す。また、進捗を消す目的での `clearMessage` 呼び出しも廃止する(同時に表示中の通知まで消してしまうため)。

### 3. 部品とサービスの API は簡潔に保つ

- `StatusProgressWidget` は `set_progress(text, current=None, total=None)` と `clear()` のみを持つ。
- `total` が未指定または 0 以下の場合は不定進捗(range 0..0)で表示する。長い工程名は省略表示し、全文はツールチップで示す。
- `ProgressStateService` は `show_progress(key, text, current, total)` と `finish_progress(key)` を公開し、`key`(`worker_id` 等)ごとに進捗を保持して最後に更新されたものを表示する。
- 工程名と進捗状態(確定・不定)を外部から設定できれば、実行制御の状態表示(CPU 実行・待機・メモリ不足・中止など)も同じ API に載せられる。状態の列挙型や優先度付き表示キューは現時点で作らず、必要になった時点で追加する。

### 4. 進捗が無いときは部品を隠す

- `StatusProgressWidget` は初期状態で非表示とし、最後の進捗が消えたら `clear()` で再び隠す。
- ワーカーの終端イベント(`WorkerService.worker_terminal`: 成功・失敗・キャンセル)で該当ワーカーの進捗を消し、終端後に遅れて届いた進捗通知では復活させない。
- アノテーション用の `AnnotationProgressWidget` も進行中のジョブが無くなったら隠す(完了・失敗の結果はサマリーダイアログと通知で伝える)。

### 5. `AnnotationProgressWidget` は統合せず並存させる

アノテーションは件数を取得できず、対象数と経過時間をタイマーで更新する 3 行構成になっており、ジョブタブの台帳セルとしても再利用されている。件数ベースの 1 行表示を担う汎用部品とは役割が異なるため、両者を別の常設部品として並べる。統合は表示要件が揃ってから検討する。

### 6. ステータスバー全体は作り替えない

通知欄(`showMessage`)は Qt 標準の挙動(タイムアウト・左寄せ)のまま残し、既存の常設部品(エラー通知、レビュー状態)にも触れない。進捗部品を 1 つ追加するだけで取り合いは解消でき、通知を送出する多数の呼び出し元を書き換える必要がない。

### 7. 進捗の更新と部品のライフサイクルは GUI スレッドで行う

- `ProgressStateService` は `QObject` ではないため、ワーカーのシグナルを直接受け取らない。
- 受け口は GUI スレッドに属する `QObject`(`MainWindow` のスロット)とする。これにより、ワーカースレッドから送出(emit)されたシグナルは `AutoConnection` によってキュー接続(queued)となり、GUI スレッド上で安全に配送される。
- 素の Python 呼び出し可能オブジェクト(callable)を受け口にすると送出元スレッドで直接実行され得るため、受け口を `QObject` にすることがスレッド安全性の前提となる。
- 部品の生成・破棄も GUI スレッドで行い、ワーカースレッドから `deleteLater` は呼ばない。

## Consequences

- 進捗表示中に通知を出しても進捗は残り、進捗が更新されても通知は消えない。タブを切り替えても常設部品の表示は維持される。
- 進捗部品が右寄せの常設領域を占有するため、進捗表示中は通知欄の幅がその分狭くなる(工程名の省略表示で幅を抑える)。
- 今後、進捗を表示したい処理は `ProgressStateService.show_progress` / `finish_progress` を使用し、`showMessage` に進捗文言を流さない。
- ワーカー終端での自動消去は `worker_terminal` に依存するため、終端イベントを出さない処理は明示的に `finish_progress` を呼ぶ必要がある。

## Related

- Issue #1598, #1383, #1468
- ADR 0066(Jobs 統一 lifecycle ビュー)、ADR 0034(Worker / Operation / Pipeline lifecycle)
