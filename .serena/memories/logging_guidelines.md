# ロギングガイドライン

## ログ出力の頻度・タイミング

- **INFOレベル以上のログ**: ユーザー操作や主要な処理の開始・終了ごとに必ず残す
  - 例: アプリ起動・終了、主要なバッチ処理の開始/完了、設定ファイルの読み込み、DB接続の確立/切断
  
- **WARNING/ERROR/CRITICAL**: 例外発生時、想定外の分岐、リトライやフォールバック発生時に必ず残す
  - 例: ファイルが見つからない、外部APIの失敗、データ不整合、リカバリ処理の発動
  
- **DEBUGレベル**: 開発・デバッグ時のみ有効化し、詳細な変数値や分岐の通過を記録する
  - 例: ループ内の変数値、関数の入出力、条件分岐の判定結果

## ベストプラクティス

- 同じ内容のログを多重に出さない（ループ内での過剰な出力は避ける）
- ログメッセージは「何が起きたか」「どのデータに対してか」「次に何をするか」を簡潔に記述
- ユーザー入力や外部データは必ずログに残す（個人情報・機密情報はマスキング）
- ログ出力箇所には「なぜこのログが必要か」コメントを添えると保守性向上

## 例外エラーのハンドリング

- 例外をキャッチしたら、必ず`logger.error(..., exc_info=True)`でトレースバックを記録する
- recoverできない例外は`raise`で再送出し、上位でハンドリングする
- recover可能な場合は、エラー内容・対応内容をINFO/WARNINGで必ず記録する
- トレースバックは`exc_info=True`で自動的に付与されるため、`traceback.format_exc()`等の手動出力は原則不要
- 複数箇所で例外を握りつぶさず、必ずどこかでログに残すこと

## サンプルコード

```python
from lorairo.utils.log import logger

logger.info("画像データベースの初期化を開始: %s", db_path)
try:
    db.connect()
    logger.info("DB接続成功: %s", db_path)
except FileNotFoundError as e:
    logger.error("DBファイルが見つかりません: %s", db_path, exc_info=True)
    raise  # recoverできない場合は必ず再送出
except Exception as e:
    logger.error("予期しないエラー: %s", e, exc_info=True)
    # recover可能ならここで対応内容をINFO/WARNINGで記録
```

## 推奨頻度まとめ

- 主要な処理の開始・終了: 必ずINFOで残す
- 例外・異常系: 必ずWARNING/ERROR/CRITICALで残す(exc_info=True推奨)
- ループや細かい処理: DEBUGで必要最小限に
- 設定・外部入力: INFOまたはDEBUGで残す(機密情報は除外)