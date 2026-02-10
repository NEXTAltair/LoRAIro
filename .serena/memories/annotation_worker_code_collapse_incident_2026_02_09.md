# AnnotationWorker コード崩壊インシデント (2026-02-09)

## 概要
コミット `3dc9635` (Claude Sonnet 4.5 の「コードフォーマット改善」) で
`annotation_worker.py` の359行が1行に圧縮され、全メソッドが消失。

## 根本原因
- `_save_error_records` docstring以降のコードが全て1行に結合された
- 先頭が `#` コメントのため、Python はその行全体をコメントとして解釈
- `execute()`, `_run_annotation()`, `_save_results_to_database()` 等が全て消失

## なぜエラーが出なかったか
1. Qt のメタクラス (Shiboken) が ABCMeta を上書き → 抽象メソッド未実装でもインスタンス化可能
2. ベースクラスの `execute()` は `pass` で `None` を返す
3. `run()` は `None` を受け取り `finished.emit(None)` → 正常完了として扱われた

## 教訓
- AIによるコードフォーマット変更は特に大きなファイルで破壊的な結果を招くことがある
- Qt クラスの ABC 保護は信頼できない（メタクラス競合）
- ワーカーが即座に完了する場合は、実際にコードが実行されているか確認すべき
