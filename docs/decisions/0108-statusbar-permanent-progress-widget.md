---
type: ADR
title: 進捗はステータスバー常設の専用部品に出し、showMessage は操作結果の通知だけに使う
status: Accepted
timestamp: 2026-11-11
tags: [gui, statusbar, progress, notification, qt]
---

# ADR 0108: 進捗はステータスバー常設の専用部品に出し、showMessage は操作結果の通知だけに使う

## Context

ステータスバーの一時メッセージ欄 (`QStatusBar.showMessage`) を、worker の進捗表示と操作結果の通知
(「タグを追加しました」「設定を保存しました」等) が共用していた。一時メッセージ欄は 1 本しかないため、
進捗の更新が通知を上書きし、通知が進捗を上書きする。進捗の更新は頻繁なので、通知は読む前に消える。
アノテーションの進捗だけは既に `AnnotationProgressWidget` を `addPermanentWidget` で常設していたが、
同時に `showMessage(phase)` も呼んでおり、通知欄の取り合いは残っていた。

`ProgressStateService` は QObject ではない素の Python クラスで、MainWindow のスロットから呼ばれる。

## Decision

- **進捗は常設の専用部品に出す。** `StatusProgressWidget` (工程名ラベル + `QProgressBar`) を
  `ProgressStateService` が生成し、`QStatusBar.addPermanentWidget` でステータスバーに載せる。
  常設部品は `showMessage` の一時メッセージで隠れないため、進捗と通知が互いを消さない。
- **`showMessage` は操作結果の通知だけに使う。** 進捗を表していた `showMessage` 呼び出し
  (バッチ登録開始、worker 進捗、バッチ進捗、旧バッチアノテーション進捗、アノテーション工程名、
  タグ DB 準備中) は部品へ移す。進捗を消すための `clearMessage` も呼ばない (同時に出ている通知を消すため)。
- **部品の API は素直に保つ。** 部品は `set_progress(text, current=None, total=None)` と `clear()` だけを持つ。
  `total` が無い / 0 以下なら不定進捗 (range 0..0) で表示する。長い工程名は省略表示し、全文はツールチップに出す。
  サービス側は `show_progress(key, text, current, total)` / `finish_progress(key)` を公開し、
  `key` (worker_id 等) ごとに進捗を持って最後に更新されたものを表示する。工程名と進捗状態 (確定 / 不定) を
  外から設定できれば、実行制御の状態表示 (CPU 実行・待機・メモリ不足・中止など) も同じ API で載せられる。
  状態の列挙型や優先度付きの表示キューは作らない (必要になった時点で足す)。
- **進捗が無いときは部品を隠す。** 部品は初期状態で非表示、最後の進捗が消えたら `clear()` で隠す。
  worker の終端 (`WorkerService.worker_terminal`: 成功 / 失敗 / キャンセル) でその worker の進捗を消し、
  終端後に遅れて届いた進捗では復活させない。アノテーション用の `AnnotationProgressWidget` も、
  進行中のジョブが無くなったら隠す (完了・失敗の結果はサマリーダイアログと通知が出す)。
- **`AnnotationProgressWidget` は統合しない。** アノテーションは件数が取れず、対象数と経過時間を
  タイマーで更新する 3 行構成で、ジョブタブの台帳セルとしても使われている。汎用部品 (件数ベースの 1 行)
  と役割が違うため、両者を別の常設部品として並べる。統合は表示要件が揃ってから検討する。
- **ステータスバー全体は作り替えない。** 通知欄 (`showMessage`) は Qt 標準の動作 (タイムアウト・左寄せ) の
  まま残し、既存の常設部品 (エラー通知、レビュー状態) にも触れない。進捗部品を 1 つ足すだけで
  取り合いは解消でき、通知を出す多数の呼び出し元を書き換える必要がない。
- **進捗の更新は GUI スレッドで行う。** `ProgressStateService` は QObject ではないので worker の signal を
  直接受けない。受け口は GUI スレッドに住む QObject (MainWindow のスロット) で、worker スレッドから
  emit された signal は AutoConnection が queued 接続になり GUI スレッドで配送される。素の Python
  callable を受け口にすると emit したスレッドで直接実行されうるため、受け口を QObject にすることが
  スレッド安全性の前提になる。部品の生成・破棄も GUI スレッドで行い、worker スレッドで `deleteLater` しない。

## Consequences

- 進捗表示中に通知を出しても進捗は残り、進捗の更新で通知は消えない。タブを切り替えても常設部品は残る。
- 進捗部品は右寄せの常設領域に出るため、通知欄の幅は進捗表示中にその分狭くなる (工程名は省略表示で抑える)。
- 進捗を出したい新しい処理は `ProgressStateService.show_progress` / `finish_progress` を使い、
  `showMessage` に進捗文言を流さない。
- worker 終端で進捗を消す経路は `worker_terminal` に依存する。終端イベントを出さない処理は
  `finish_progress` を自分で呼ぶ。

## Related

- Issue #1598, #1383, #1468
- ADR 0066 (Jobs 統一 lifecycle ビュー), ADR 0034 (Worker / Operation / Pipeline lifecycle)
