# Logging Rules

LoRAIroプロジェクトのログレベル指針。INFOレベルのログは「1万件処理しても読める量か」を判断基準にする。

## 核心ルール

**INFOレベルでは1件ごとのログを出さない。** バッチ処理のサマリーのみINFOで出力する。
**DEBUGは「デバッグ時に読める量」を保つ。** 1操作で数百件以上出る per-item の大量詳細はTRACEへ回す (ADR 0047)。

## ログレベル定義

### TRACE - per-item firehose (既定では抑制)
loguru の TRACE (level.no=5、DEBUG より下位)。`config/lorairo.toml` の `[log] level = "TRACE"`
または `[log.levels]` でモジュール別に明示有効化したときのみ出力される。1操作で数百〜数千件
出るような per-item 詳細を置く。通常のデバッグ (`level = "DEBUG"`) では埋もれないよう抑制される。

```python
# 正しい: 1操作で大量に出る per-item 詳細は TRACE
logger.trace(f"パス解決: {stored_path} -> {resolved}")          # 画像ごと
logger.trace(f"Formatted annotations: tags={n}, ...")          # 画像ごと
logger.trace(f"  モデル読込: name={model.name}, ...")           # モデルごと (211件)
logger.trace(f"Model selection changed: {model_id} = {state}")  # チェックボックスごと
```

### DEBUG - 開発者向け診断情報 (操作・コンポーネント単位)
- 操作単位の処理詳細・分岐結果・関数の入出力 (1操作で高々十数件に収まるもの)
- 1選択イベント / 1ページ描画など、ユーザー操作単位の診断
- **1操作で数百件以上に膨らむ per-item ログは DEBUG ではなく TRACE に置く**

```python
# 正しい: 操作単位は DEBUG
logger.debug(f"画像をDBに追加: ID={image_id}")
logger.debug(f"重複検出: pHash一致 ID={existing_id}")

# 禁止: オブジェクト生成のたびに出る初期化ログを DEBUG で出さない (削除する)
logger.debug(f"ModelCheckboxWidget initialized for model: {name}")  # widget 生成ごと → 削除
# 禁止: 正常系を毎回確認するログ (異常系のみ残す)
logger.debug(f"画像ID {id} を発見（正常な状態）")  # → 削除、見つからない時だけ残す
```

### INFO - 運用者向け操作記録
- アプリケーション起動/終了
- コンポーネントの初期化完了（1回きりのもの）
- バッチ処理の開始と完了サマリー（件数・結果統計）
- ユーザー操作の開始（ディレクトリ選択、ワーカー起動）
- 設定ファイルの読み込み

```python
# 正しい: バッチサマリーはINFO
logger.info(f"登録対象画像: {total}件")
logger.info(f"登録完了: 成功={ok}, スキップ={skip}, エラー={err}")
logger.info(f"バッチ処理開始: {directory}")
logger.info("MainWindow初期化完了")

# 禁止: 個別アイテムをINFOで出さない
logger.info(f"画像をDBに追加: ID={image_id}")  # DEBUGにすべき
logger.info(f"処理済み画像を保存: {path}")  # DEBUGにすべき
```

### WARNING - 予期しないが継続可能な状況
- リソースが見つからない（フォールバック動作あり）
- 重複データの検出（処理続行）
- 外部サービスの一時的な障害
- APIキー未設定

```python
logger.warning(f"モデル '{name}' がDBに見つかりません")
logger.warning("利用可能なAPIキーがありません")
logger.warning(f"pHashが一致する画像が既に存在: ID {existing_id}")
```

### ERROR - 操作の失敗
- DB操作の例外
- ファイルI/Oの失敗
- 外部API呼び出しの失敗
- 必ず`exc_info=True`を付与する

```python
logger.error(f"画像登録に失敗: {path}", exc_info=True)
logger.error(f"DB接続エラー: {e}", exc_info=True)
```

## 禁止パターン

### 1. 多層重複ログ
同じイベントを複数レイヤーでログ出力しない。最も適切な1箇所だけで出力する。

```python
# 禁止: Repository層とManager層の両方で同じ操作をログ
# db_repository.py
logger.info(f"画像追加: ID={id}")  # ここで出すなら
# db_manager.py
logger.info(f"画像登録完了: ID={id}")  # ここでは出さない

# 正しい: 低レイヤーはDEBUG、高レイヤーのサマリーだけINFO
# db_repository.py
logger.debug(f"画像追加: ID={id}")
# registration_worker.py (バッチ完了時のみ)
logger.info(f"登録完了: {count}件")
```

### 2. 毎回生成されるオブジェクトの初期化ログ
画像1枚ごとに生成・破棄されるオブジェクトの初期化をINFOで出さない。

```python
# 禁止: 画像ごとに生成されるマネージャーの初期化
logger.info(f"ImageProcessingManager初期化完了: resolution={res}")

# 正しい
logger.debug(f"ImageProcessingManager初期化完了: resolution={res}")
```

### 3. ループ内INFO
ループの中でINFOレベルのログを出さない。

```python
# 禁止
for image in images:
    logger.info(f"処理中: {image.name}")

# 正しい: ループ外でサマリー
logger.info(f"処理開始: {len(images)}件")
for image in images:
    logger.debug(f"処理中: {image.name}")
logger.info(f"処理完了: 成功={ok}件")
```

## INFO出力の判断フロー

1. **これは1回きりの操作か?** → YES → INFO可
2. **N件のうちの1件か?** → YES → DEBUG
3. **ユーザー操作の直接的な応答か?** → YES → INFO可
4. **内部コンポーネントの動作詳細か?** → YES → DEBUG
5. **運用者が常時監視で見たい情報か?** → YES → INFO可
