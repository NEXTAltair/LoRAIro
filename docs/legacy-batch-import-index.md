# Legacy JSONL 取込みの索引スナップショット

`annotate import-batch` のディレクトリ取込みでは、最初に stem 形式の
`custom_id` を照合した時点でファイル名・alias 索引を取得し、同じ操作の
残りの JSONL ファイルで共有する。phash 形式だけの操作では取得しない。

索引は取込み操作内の一時データで、サービスやプロジェクトをまたいで保持しない。
単一 JSONL の取込みは毎回最新の索引を取得する。ディレクトリ取込み中に別処理が
追加・変更したファイル名や alias は、その操作中の索引には反映せず、次回の
取込みで反映する。phash 照合・注釈保存を含む全体のトランザクション保証を
追加するものではない。

既存の重複 stem の代表選択、実ファイル名優先の alias fallback、未一致・
parse エラー集計、dry-run の保存抑止は維持する。

## 検証

`tests/unit/services/test_batch_import_service.py` で N=1/500/501/1000/10000、
F=1/3、通常保存/dry-run を検証する。各ファイル1レコードの場合、全索引構築は
F 回から1回、合成画像の走査行数は FN から N に減る。alias A 件を含む一般形の
取得量は1操作につき N+A 件。SQL実行時間や速度倍率は測定していない。

`tests/unit/services/test_batch_image_matcher.py` は実 SQLite repository を用いて
alias と重複 stem の選択も確認する。
