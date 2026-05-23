# language: ja
機能: AnnotationWorker の部分失敗階層伝播
  ADR 0033 Decision 2 / 3 / 4 に従い、AnnotationWorker は失敗を 3 階層に分類する。
  L1 (lib `result.error` で表現される期待された失敗) は `error_records` に保存せず、
  L2 (lib 呼び出しの想定外例外) と L3 (Worker 自身の前提崩れ) のみを記録する。
  内部整合性違反は `error_type='integrity_violation'` で別カテゴリとして記録する。

  背景:
    前提 AnnotationWorker が 2 モデル × 3 画像のタスクで初期化されている
    かつ db_manager および model_registry が利用可能である

  シナリオ: L1 - lib が result.error で rate_limited を返す
    前提 image-annotator-lib がモデル "model-a" で全画像に対し result.error="rate_limited" を返す
    かつ モデル "model-b" は全画像で成功する
    もし AnnotationWorker を実行する
    ならば error_records テーブルに該当 row は追加されない
    かつ model_statistics の "model-a" の error_count は 3 である
    かつ model_statistics の "model-b" の success_count は 3 である
    かつ サマリーダイアログの model_errors に "model-a" のエラーが含まれる

  シナリオ: L2 - モデルの lib 呼び出しが RuntimeError を raise
    前提 image-annotator-lib がモデル "model-b" の呼び出しで RuntimeError を raise する
    かつ モデル "model-a" は全画像で成功する
    もし AnnotationWorker を実行する
    ならば error_records テーブルに 3 行追加される (対象モデル="model-b")
    かつ 各 row の error_type は "lib_call_exception" または例外型名である
    かつ モデル "model-a" の処理は完了する

  シナリオ: L3 - refusal filter で致命例外が発生してバッチ中断
    前提 refusal filter が ValueError を raise する
    もし AnnotationWorker を実行する
    ならば error_records テーブルに 3 行追加される (model_name は NULL)
    かつ 各 row の error_type は "fatal" または例外型名である
    かつ Worker は失敗 Signal を emit する

  シナリオ: integrity_violation - 想定外の model_id が結果に含まれる
    前提 image-annotator-lib が litellm_model_ids に含まれない model_id "unknown-model" を結果に混入させる
    もし AnnotationWorker を実行する
    ならば error_records テーブルに該当 row が追加され error_type は "integrity_violation" である
    かつ サマリーダイアログの integrity_violation 専用セクションに該当エントリが表示される
