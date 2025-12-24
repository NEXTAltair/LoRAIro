from pathlib import Path
path=Path('.serena/memories/plan_immutable_tumbling_quokka_2025_12_23.md')
text=path.read_text(encoding='utf-8')
marker='## 実裁E??ケジュール'
pos=text.index(marker)
section='\n## 最新決定\n\n- GUIサービスは core_api 経由のみとし、legacy 互換コードを削除して全面書き直す。\n- TagRegisterService／TagStatisticsService は core_api での検索・登録・統計処理を別モジュールに実装。\n- 非同期処理は QThreadPool + QRunnable（WorkerService）で統一し、進捗やキャンセルは省いて inished と error だけを利用。\n- showEvent 初期化はサービスが揃っている前提で、UI 内で DB 初期化や重い処理を行わない。\n- closeEvent はサービス close → DB close → super().closeEvent の順で処理し、例外をログに記録しつつ続行。\n- エラーハンドリング規約：ValidationError/ValueError→warning + UI + signal、FileNotFoundError→warning + signal、それ以外→critical + signal + logger.exception。\n- Ruff はコード全体と 	ests/ を含めて実行し、Phase 4 で全体 75% のカバレッジを目指す。\n\n'
path.write_text(text[:pos]+section+text[pos:], encoding='utf-8')
