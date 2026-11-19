---
trigger: model_decision
description: "ログ出力を追加・変更するとき。レベル設計と量の基準"
---

# Logging Rules

ログレベルの指針。INFOレベルのログは「1万件処理しても読める量か」を判断基準にする。loguru を使うプロジェクト向けの記法例だが、レベル設計 (TRACE/DEBUG/INFO/WARNING/ERROR の使い分け) の原則は他のロガー (標準 `logging`, `structlog` 等) でも同じ。

> **プロジェクト固有:** 実際に使用するロガーライブラリ、設定ファイルのパスと `[log]` セクション形式は導入先で追記する。

## 核心ルール

**INFOレベルでは1件ごとのログを出さない。** バッチ処理のサマリーのみINFOで出力する。
**DEBUGは「デバッグ時に読める量」を保つ。** 1操作で数百件以上出る per-item の大量詳細はTRACEへ回す。
**ロガーは1系統に統一する。** アプリケーションコードは標準 `logging` とサードパーティ製ロガー
(loguru 等) を混在させない。混在すると、片方の sink 設定 (ファイル出力・フォーマット・レベル
フィルタ) がもう片方のログに適用されず、事後調査時にログが欠落する。

## ロガー統一

プロジェクトで採用するロガーライブラリを1つ選び、アプリケーションコード全体でそれに統一する。
標準 `logging.getLogger()` とサードパーティロガーが混在すると、以下の問題が起きる:

- 一方の sink (ファイル出力等) しか設定していない場合、もう一方のログが記録されない
- 例外情報の付与方法がロガーごとに異なる (例: 標準 `logging` の `exc_info=True` は、
  サードパーティロガーでは同じ意味を持つとは限らない。トレースバック付与の正しい API を
  ロガーの実装に合わせて使う)
- 初期化タイミングに注意する: ロガー設定用の初期化関数より前 (モジュール import 時等) に
  出力されるログは、設定が適用される前に評価されるため sink に乗らないことがある。
  モジュールレベルの初期化ログは、実際に処理が実行されるタイミング (初期化関数の後) まで
  遅延させる

> **プロジェクト固有:** 採用するロガーライブラリ名、初期化関数の場所、標準 logging との
> ブリッジが必要かどうかは導入先で追記する。

## placeholder 形式はロガー実装に合わせる

ロガーの遅延フォーマット機構に、そのロガーがサポートしない形式の placeholder を渡すと、
値が展開されずログに残らない (例: `{}` 形式を期待するロガーに `%s` 形式の文字列を渡す、
またはその逆)。使用するロガーの placeholder 形式を統一し、混在させない。f-string への
全面変更よりも、既存の呼び出し形を保ったまま placeholder だけ揃える方が差分が小さく、
不要な文字列評価も避けられる。

## ログレベル定義

### TRACE - per-item firehose (既定では抑制)
DEBUG より下位のレベル (loguru なら `logger.trace`、標準 `logging` なら独自レベルを追加するか DEBUG をさらに細分する)。
設定ファイルで明示的にレベルを下げたときのみ出力される。1操作で数百〜数千件
出るような per-item 詳細を置く。通常のデバッグ (`level = "DEBUG"`) では埋もれないよう抑制される。

```python
# 正しい: 1操作で大量に出る per-item 詳細は TRACE
logger.trace(f"パス解決: {stored_path} -> {resolved}")          # 対象ごと
logger.trace(f"Formatted output: fields={n}, ...")             # 対象ごと
logger.trace(f"  モデル読込: name={model.name}, ...")           # モデルごと (数百件)
logger.trace(f"Selection changed: {item_id} = {state}")         # UI操作ごと
```

### DEBUG - 開発者向け診断情報 (操作・コンポーネント単位)
- 操作単位の処理詳細・分岐結果・関数の入出力 (1操作で高々十数件に収まるもの)
- 1選択イベント / 1ページ描画など、ユーザー操作単位の診断
- **1操作で数百件以上に膨らむ per-item ログは DEBUG ではなく TRACE に置く**

```python
# 正しい: 操作単位は DEBUG
logger.debug(f"レコードをDBに追加: ID={record_id}")
logger.debug(f"重複検出: ハッシュ一致 ID={existing_id}")

# 禁止: オブジェクト生成のたびに出る初期化ログを DEBUG で出さない (削除する)
logger.debug(f"Widget initialized for: {name}")  # インスタンス生成ごと → 削除
# 禁止: 正常系を毎回確認するログ (異常系のみ残す)
logger.debug(f"レコード {id} を発見（正常な状態）")  # → 削除、見つからない時だけ残す
```

### INFO - 運用者向け操作記録
- アプリケーション起動/終了
- コンポーネントの初期化完了（1回きりのもの）
- バッチ処理の開始と完了サマリー（件数・結果統計）
- ユーザー操作の開始（ディレクトリ選択、ワーカー起動）
- 設定ファイルの読み込み

```python
# 正しい: バッチサマリーはINFO
logger.info(f"登録対象: {total}件")
logger.info(f"登録完了: 成功={ok}, スキップ={skip}, エラー={err}")
logger.info(f"バッチ処理開始: {directory}")
logger.info("初期化完了")

# 禁止: 個別アイテムをINFOで出さない
logger.info(f"レコードをDBに追加: ID={record_id}")  # DEBUGにすべき
logger.info(f"処理済みファイルを保存: {path}")  # DEBUGにすべき
```

### WARNING - 予期しないが継続可能な状況
- リソースが見つからない（フォールバック動作あり）
- 重複データの検出（処理続行）
- 外部サービスの一時的な障害
- APIキー未設定

```python
logger.warning(f"モデル '{name}' がDBに見つかりません")
logger.warning("利用可能なAPIキーがありません")
logger.warning(f"ハッシュが一致するレコードが既に存在: ID {existing_id}")
```

**正常系の量的しきい値超過は WARNING にしない。** 検索結果が大量にヒットした、処理対象件数が
多いといった「処理は成功しているが規模が大きい」状態は失敗ではない。UI 側で注意表示をする場合でも、
ログレベルはそれと独立に判断する — 実際に処理が失敗した・入力が不正だった・タイムアウトしたなど、
本当に調査が必要な事象だけを WARNING 以上にする。量が多いだけの正常系は INFO (運用上の観測値として
残したい場合) か DEBUG に置く。

### ERROR - 操作の失敗
- DB操作の例外
- ファイルI/Oの失敗
- 外部API呼び出しの失敗
- 必ずスタックトレース付きで記録する (loguru なら `exc_info=True`)

```python
logger.error(f"登録に失敗: {path}", exc_info=True)
logger.error(f"DB接続エラー: {e}", exc_info=True)
```

## 禁止パターン

### 1. 多層重複ログ
同じイベントを複数レイヤーでログ出力しない。最も適切な1箇所だけで出力する。

```python
# 禁止: Repository層とService層の両方で同じ操作をログ
# repository.py
logger.info(f"レコード追加: ID={id}")  # ここで出すなら
# service.py
logger.info(f"登録完了: ID={id}")  # ここでは出さない

# 正しい: 低レイヤーはDEBUG、高レイヤーのサマリーだけINFO
# repository.py
logger.debug(f"レコード追加: ID={id}")
# batch_worker.py (バッチ完了時のみ)
logger.info(f"登録完了: {count}件")
```

### 2. 毎回生成されるオブジェクトの初期化ログ
リクエスト/アイテム1件ごとに生成・破棄されるオブジェクトの初期化をINFOで出さない。

```python
# 禁止: リクエストごとに生成されるマネージャーの初期化
logger.info(f"ProcessingManager初期化完了: resolution={res}")

# 正しい
logger.debug(f"ProcessingManager初期化完了: resolution={res}")
```

### 3. ループ内INFO
ループの中でINFOレベルのログを出さない。

```python
# 禁止
for item in items:
    logger.info(f"処理中: {item.name}")

# 正しい: ループ外でサマリー
logger.info(f"処理開始: {len(items)}件")
for item in items:
    logger.debug(f"処理中: {item.name}")
logger.info(f"処理完了: 成功={ok}件")
```

## INFO出力の判断フロー

1. **これは1回きりの操作か?** → YES → INFO可
2. **N件のうちの1件か?** → YES → DEBUG
3. **ユーザー操作の直接的な応答か?** → YES → INFO可
4. **内部コンポーネントの動作詳細か?** → YES → DEBUG
5. **運用者が常時監視で見たい情報か?** → YES → INFO可
