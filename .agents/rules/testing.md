---
trigger: model_decision
description: "テストを書く・実行する・カバレッジを判断するとき (pytest)"
---

# Testing Rules

テストの方針。lint やモデルの既定挙動では決まらない「このプロジェクトの判断」だけを持つ。pytest の書き方そのものはここに書かない。Qt / PySide6 と pytest-bdd 固有の落とし穴は `pytest-qt-bdd` skill (導入していれば) にある。

> **プロジェクト固有:** 実際のカバレッジ数値目標、CI ワークフローの pytest filter 表、テスト実行コマンド (Makefile ターゲット等)、サブモジュール/monorepo package ごとのテスト実行コマンドは導入先で追記する。

## カバレッジ要件

- **最小カバレッジ**: 75% 以上を目安に維持する (数値は導入先で調整)
- **新機能**: 対応するテストを必ず作成
- **バグ修正**: リグレッションテストを追加

### 閾値を一時的に下げない

カバレッジが閾値を割った場合でも、**閾値そのものを一時的に引き下げて CI を green に戻すことはしない**。
一時引き下げは「CI は green だが実質カバレッジは改善しない」状態を正当化し、将来の劣化に対する
感度を下げる。閾値割れの原因 (デッドコード・テスト未整備) を特定し、下記の omit / 削除基準に従って
恒久的に解消する。

### omit 許可・禁止基準

`coverage` の対象除外 (`omit` / `source` 除外) を無秩序に広げると、閾値が品質ゲートとして機能しなく
なる。以下を基準にする:

- **omit 許可** (いずれかに該当するコードのみ):
  - `src` 本体から一切参照されない開発補助・ヘルパー
  - 描画専用 GUI コードなど、ヘッドレス CI でのテストが技術的に困難なもの
  - 自動生成コード
- **omit 禁止**: サービス層・データアクセス層・設定読み込みなどのコア機能
- **`source` 除外** (`omit` より強い除外、計測対象そのものに含めない): 外部 API 呼び出しや
  重い ML モデルロードなど、headless CI 環境で実行できない初期化処理を含む package/module に限る
- **削除許可**: `src` 本体参照 0 かつ テスト参照 0 のコードは即削除可。テスト参照のみある場合は
  変更履歴を確認し、復活予定があれば隔離、無ければ削除、判断困難なら omit + Issue 化

> **プロジェクト固有:** `[tool.coverage.run] omit` / `source` の実際のリストと、それぞれをこの基準の
> どれで許可したかは導入先の記録 (ADR 等) を参照する。

## テスト構造

```
tests/
├── unit/           # ユニットテスト(外部依存はモック)
├── integration/    # 統合テスト(内部コンポーネント結合)
├── gui/            # GUIテスト(pytest-qt 等)
├── bdd/            # BDD振る舞い仕様テスト(pytest-bdd)
└── resources/      # テストリソース
```

マーカーは `unit` / `integration` / `gui` / `bdd` / `slow` を基本とし、`tests/bdd/` 配下の `bdd` は conftest で自動付与する。

## モック戦略

- **モックする**: 外部 API (OpenAI, Anthropic, Google 等)、大量ファイル処理のファイルシステム操作、ネットワーク通信、時間依存処理
- **モックしない**: 内部サービス間の連携 (統合テストで検証)、データベース操作 (テスト DB を使う)、Qt Signal/Slot (配線そのものが検証対象)

## 決定論的 CI テストと実 API / 実モデル検証の分離

CI の必須ゲート (PR ごとに実行する mandatory lane) には、**外部依存の可用性に左右されるテストを
含めない**。具体的には以下を CI 必須ゲートから除外し、開発者がローカルで必要時に手動実行する
on-demand validation として扱う:

- 実 provider API key を使った実 Web API 呼び出し
- 実モデルのダウンロードや実ローカル推論

**理由**:
- 外部 provider の障害や rate limit が PR の pass/fail を左右してしまう
- API 利用料金が CI トリガーに紐づく
- API key / secret の管理負担が増える
- provider のレスポンス schema やモデル可用性が予告なく変わる
- モデルダウンロードが CI 時間とキャッシュ容量を消費する
- 実行時間や環境差 (GPU 有無等) が読みにくく、flake の温床になる

一方、CLI 起動・設定読み込み・DB/出力ファイル作成・workflow の配線確認などは、外部依存境界に
fake / mock backend を注入すれば決定論的に検証できる。これは CI 必須ゲートに残し、
mock-heavy な unit test だけでは拾いにくい「配線 (wiring) の regression」を補完する。

pytest marker で区別する場合の例:

```python
@pytest.mark.calls_real_webapi        # 実 API key で実リクエスト。CI から除外
@pytest.mark.downloads_and_runs_model  # 実モデル DL + 実推論。CI から除外
```

> **プロジェクト固有:** 実 API / 実モデル検証を行う Makefile ターゲットや、fake backend を注入する
> ための環境変数・DI ポイントは導入先の記録を参照する。

## サブモジュール / monorepo package のテスト

複数の独立した package (submodule 等、それぞれ独自の pytest 設定を持つもの) がある場合、
**pytest セッション境界を package 境界に揃える**。それぞれを独立した pytest セッションとして
起動し、単一の pytest invocation に混ぜない。

**分離が必要かどうかの判断基準**: ルート `conftest.py` が重い外部依存 (torch/tensorflow の動的
ロード等) を避けるために `sys.modules` へモジュールレベルの mock を注入している場合、その mock は
import 時点 (collection より前) に有効化されるため、ルートから対象 package 自身のテストまで
collection してしまうと、mock が package 自身のテストにも継承されて意図しない失敗を起こす
(「実体を検証したいテストに、他パッケージ都合の mock が波及する」事故パターン)。conftest の
前提・coverage 対象・依存バージョンのいずれかが package ごとに異なる場合は、単一 pytest invocation
に混ぜず、独立したセッション (作業ディレクトリを package root にして起動) に分離する。

package 間の venv 共有方針は [parallel-execution.md](parallel-execution.md) の「venv 分離粒度: package 間」を参照。

> **プロジェクト固有:** package ごとのテスト実行コマンド (Makefile ターゲット等) をここに追記する。

## CI-equivalent filter で local 検証する

ローカルでの test 検証は CI workflow の pytest filter と **完全一致** の filter で実行する。短縮 filter (`-m unit` 等) のみで「regression なし」と結論しない。

### 理由

pytest markers は独立した分類 (`unit`, `standard`, `fast`, `heavy` 等)。`-m unit` で検証しても `-m standard` の test は collect されないため、CI 失敗を local 再現できない (発端事例は導入先の記録を参照)。

> **プロジェクト固有:** CI ワークフローの job ごとの pytest filter 一覧表をここに追記する。変更時は本表も更新する運用にする。

### 適用タイミング

- サブモジュール pin 更新 PR 起票 **前**
- ライブラリ側 API 変更 / refactor PR 起票 **前**
- "regression なし" を user に報告する **前**

### 例

```bash
cd <package root>
uv run pytest -m "not downloads_and_runs_model and not calls_real_webapi"
```

### Hook gate

`gh pr create` 実行時にサブモジュール (`submodule_globs` に一致するパス) の pin 変更を含む場合、kit の hook (`hook_pre_pr_submodule_check.py`) が CI-equivalent test 実行確認を要求する。bypass は command 内に `CI-EQUIV-TESTED` marker comment を含める。詳細は hook script のヘッダー参照。

### Worktree / I/O 制約 と package test

venv / 実行環境の分離粒度 (worktree 間・package 間でどこまで環境を共有するか) は [parallel-execution.md](parallel-execution.md) に集約している。低速な I/O 環境 (ネットワークマウント上の checkout 等) で package ごとに専用 venv を作ると実用速度を損なう場合があるため、そちらのルールに従い共有 venv を優先する。

> **プロジェクト固有:** devcontainer / CI 環境固有のマウント構成、Makefile ターゲットの詳細をここに追記する。

## Lazy import refactor との関係

重い native 依存 (torch / tensorflow 等) の lazy import 化を行う場合は、対応する skill (`lazy-import-refactor` 等) が test 副作用 (`@patch("module.torch")` 等) を予測し、本セクションの filter で検証することを義務付ける。
