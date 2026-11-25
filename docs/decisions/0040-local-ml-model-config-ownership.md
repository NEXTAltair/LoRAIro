---
type: ADR
title: Local ML Model Config Ownership
status: Accepted (amended 2026-10-11: OS-local user config and runtime cache)
timestamp: 2026-05-24
tags: []
---
# ADR 0040: Local ML Model Config Ownership

- **関連 Issue**:
  [NEXTAltair/image-annotator-lib#95](https://github.com/NEXTAltair/image-annotator-lib/issues/95),
  [NEXTAltair/LoRAIro#365](https://github.com/NEXTAltair/LoRAIro/issues/365),
  [NEXTAltair/LoRAIro#366](https://github.com/NEXTAltair/LoRAIro/issues/366)
- **関連 ADR**: [ADR 0003](0003-annotator-config-management.md),
  [ADR 0004](0004-annotator-lib-architecture.md),
  [ADR 0023](0023-pydanticai-litellm-webapi-inference-boundary.md),
  [ADR 0024](0024-pytest-test-responsibility-separation.md)

## Context

ADR 0021 および ADR 0023 により、WebAPI モデルの管理は `annotator_config.toml` から切り離され、LiteLLM 同梱 DB を実行時の SSoT とする設計へ移行した。LoRAIro から `image-annotator-lib` へは `litellm_model_id` と `api_keys` を明示的に渡すため、WebAPI モデルの定義、API キー、経路選択はもはや TOML のシステムカタログの責務ではない。

一方で、ローカル ML モデル(ONNX、Transformers、CLIP、TensorFlow)の設定は ADR 0003 および ADR 0004 の方針を引き継ぎ、`annotator_config.toml` と `user_config.toml` を使う設計のまま残っている。その結果、現在の `annotator_config.toml` には以下の複数の責務が混在している。

- 組み込みローカルモデルのカタログ(built-in local model catalog)
- 利用側プロジェクトに配置されるシステム設定
- `add_default_setting()` による不足デフォルト値の永続化先
- モデルローダーが算出した `estimated_size_gb` の保存先
- テストフィクスチャが一時的なモデル設定を注入する対象

この責務混在が原因となり、`image-annotator-lib#95` では `pytest` 実行時にテスト専用モデル定義が `config/annotator_config.toml` へ書き戻され、本番カタログに混入した。

具体的には、複数のテストフィクスチャが `config_registry.add_default_setting(...)` を呼び出し、同メソッドが内部で `save_system_config()` を実行したため、以下のテスト専用エントリがシステムカタログへ永続化された。

- `test_model` / `MockAnnotator`
- `dummy-model` / `DummyTransformersAnnotator`
- `test_base_annotator_model` / `ConcreteAnnotator`
- `test_transformers_base_model` / `TransformersBaseAnnotator`

これらは PR #92(`chore: remove test-only annotator config entries`)で一度削除された。しかし PR #93 の `pytest` 実行時に同じスタブが再混入し、レビューで再び検出された。これは個別テストの後片付け不足ではなく、システムカタログを通常の実行時処理やテストから暗黙に書き換えられる設計自体が根本原因である。

さらに、`LoRAIro#365` ではレーティング対応のローカルタガーの `capabilities` が古い設定由来で `tags` のみに縮退した。`LoRAIro#366` では `TaskCapability.RATINGS` のアダプター変換漏れも表面化した。`capabilities` は単なる表示用設定ではなく、モデルが返却し得る出力型の契約である。ユーザー設定によって組み込みモデルの契約を削除できると、UI フィルタ、DB 同期、結果検証、保存処理の前提が崩れる。

### ADR スコープ

本 ADR は、**ローカル ML モデル設定**の所有権と永続化先を定める。

対象範囲:

- `config/annotator_config.toml`
- `config/user_config.toml`
- 実行時派生メタデータ(`estimated_size_gb` など)
- ローカル ML モデルの `capabilities` マージ規則
- テストが設定ファイルを扱うルール
- LoRAIro と `image-annotator-lib` のローカルモデル設定境界

対象外:

- WebAPI モデルの探索、経路選択、API キー注入
- LiteLLM DB のプロバイダおよびモデルメタデータ
- LoRAIro DB スキーマ上の `models` および `model_types` の正規化

## Decision

### 1. ローカル ML システムカタログは利用側プロジェクト内に配置する

ローカル ML モデルのシステムカタログは、ライブラリ利用側プロジェクトの `config/annotator_config.toml` に配置する。

`image-annotator-lib` は、同ファイルが存在しない場合に限り、パッケージリソースの `resources/system/annotator_config.toml` から初期生成してよい。

生成後の `config/annotator_config.toml` は利用側プロジェクトが管理するカタログである。通常の実行時処理、モデル読み込みの副作用、テストフィクスチャから暗黙に書き換えてはならない。

### 2. パッケージリソースは初期テンプレートとし、実行時の永続化先にしない

パッケージリソースの `resources/system/annotator_config.toml` は初期生成用テンプレートとして扱う。直接編集、実行時の書き戻し、テストフィクスチャからの注入対象にはしない。

### 3. ユーザー上書き設定は OS ユーザー設定ディレクトリへ保存する

ユーザーがローカルモデルの実行設定を変更する場合は、`platformdirs` による `image-annotator-lib` の OS ユーザー設定ディレクトリ配下の `user_config.toml` を使用する。Windows では LocalAppData、Linux では XDG config home となる。共有の `config/user_config.toml` は自動採用せず、内容と所有 OS を確認したうえで明示的に移行する。なお、テスト等で明示的に設定パスを渡す用法は引き続き利用できる。

主なユーザー上書き対象:

- `device`
- `model_path`
- `tag_threshold`
- `batch_size`
- `gpu_memory_limit_gb`
- カスタムローカルモデルのセクション

システムカタログの直接編集は、組み込みカタログの開発、配布更新、および明示的なメンテナンス作業に限定する。

### 4. 実行時派生メタデータはシステムカタログに保存しない

モデルローダーが実行時に計算したメタデータは、`config/annotator_config.toml` へ書き戻さない。`estimated_size_gb` などの実行時派生メタデータは別ファイルに保存する。

保存先の初期候補:

```text
<OS user cache directory>/image-annotator-lib/model_runtime_cache.toml
```

実行時メタデータと `install_markers` は OS ユーザーキャッシュへ分離する。一方で、モデル重みとシステムカタログはポータブルなプロジェクト資産として維持する。これにより、生成ファイルと OS 固有のモデル実行パスを共有チェックアウト上で奪い合う事態を防ぐ。

`estimated_size_gb` の有効値は、以下の優先順位で解決する。

```text
user_config.toml
> model_runtime_cache.toml
> annotator_config.toml
> code/class fallback
```

ユーザーが明示した値を、実行時キャッシュが上書きしてはならない。

### 5. `capabilities` は削除不能な追加マージとする

ローカル ML モデルの `capabilities` は通常の上書きとは異なり、システムカタログと `user_config.toml` の集合和で決定する。

```text
effective_capabilities = system_capabilities ∪ user_capabilities
```

これにより、`user_config.toml` から `capabilities` を追加することはできるが、システムカタログが宣言した `capabilities` を削除することはできない。

マージ例:

```toml
# system catalog
[wd-vit-tagger-v3]
capabilities = ["tags", "ratings"]

# user_config.toml
[wd-vit-tagger-v3]
capabilities = ["tags"]
```

この場合、有効値は次のようになり、`ratings` は削除されない。

```toml
capabilities = ["tags", "ratings"]
```

カスタムローカルモデルの場合は、システムカタログに同名セクションが存在しないため、`user_config.toml` の `capabilities` がそのまま採用される。

```toml
[my-custom-wd]
class = "WDTagger"
model_path = "/models/my-custom-wd/model.onnx"
type = "tagger"
capabilities = ["tags", "ratings"]
tag_threshold = 0.35
device = "cuda"
```

カスタムローカルモデルで `capabilities` が未指定の場合は、`type` や `class` から推論してよい。ただし、その際は明示的な宣言を促す警告(warning)を出力する。

この仕様を採る理由は、`capabilities` が単なる表示用設定ではなくモデル出力型の契約であるためである。システムカタログの契約をユーザー設定で削れてしまうと、UI フィルタ、LoRAIro の DB 同期、結果検証、保存処理の間で不整合が生じる。

### 6. `add_default_setting()` は新規利用を禁止する

`ModelConfigRegistry.add_default_setting()` は新規コードで使用してはならない。理由は以下の 3 点である。

- メソッド名から永続書き込みの発生を予測しづらい。
- テストフィクスチャが一時設定の注入に使うとシステムカタログを汚染する。
- システムカタログの読み取り専用契約と矛盾する。

既存互換のため即座には削除しないが、少なくともテストおよび通常実行経路では使用禁止とする。一時的な設定注入には、`set_system_value()` または分離された `ModelConfigRegistry` インスタンスを使用する。

### 7. `save_system_config()` は通常実行時から呼び出さない

`save_system_config()` は、メンテナンスおよび開発者向けツールの明示的操作に限定する。通常実行時、モデル読み込み、副作用的なメタデータ更新、テストフィクスチャから呼び出してはならない。

特に `loader_base._save_size_to_config()` は、システムカタログではなく実行時キャッシュへ保存する実装へ変更する。

### 8. テストは本番のシステムカタログへ書き込んではならない

`image-annotator-lib` および LoRAIro のテストは、実際の `config/annotator_config.toml` を永続変更してはならない。テストでローカルモデル設定が必要な場合は、以下のいずれかを使用する。

- `tmp_path` に配置した分離設定パス
- 分離された `ModelConfigRegistry()` インスタンス
- `set_system_value()` によるインメモリ注入
- `monkeypatch` で差し替えた設定パス

回帰テストの条件:

```text
pytest 実行後に config/annotator_config.toml に test-only section が追加されない。
```

### 9. LoRAIro は `image-annotator-lib` の TOML を直接編集しない

LoRAIro は、`image-annotator-lib` のローカルモデルカタログを直接編集・同期しない。LoRAIro が利用するライブラリ境界は以下に限定する。

- `list_annotator_info()`
- `annotate(..., model_name_list=..., api_keys=...)`
- その他の公開 API

LoRAIro DB の `models` および `model_types` は、検索・表示・保存のためのキャッシュおよび投影(projection)であり、`image-annotator-lib` の設定正本ではない。

### 10. OS ユーザー設定・キャッシュディレクトリへの移行は今回採用しない

`platformdirs` 等を用いて OS 標準のユーザー設定・キャッシュディレクトリへ保存する案は、将来検討として残す。

今回の最優先事項は `image-annotator-lib#95` の再発防止である。保存先解決、移行処理、テスト差し替え、利用者向け説明が増える OS ディレクトリ移行は、この時点では過剰と判断した。

将来、以下の要件が生じた場合は別 ADR で再検討する。

- フローズンアプリやインストーラー配布でカレントディレクトリ(cwd)が安定しない場合
- 複数アプリから `image-annotator-lib` を共有する場合
- OS 標準のユーザー設定・キャッシュディレクトリに統一する必要がある場合
- プロジェクトローカル設定をポータブルモードに限定したい場合

## Rationale

### プロジェクトローカルの読み取り専用カタログを採用する理由

| 案 | 内容 | 利点 | 欠点 | 評価 |
|---|---|---|---|---|
| A. 現状維持 | `Path.cwd()/config` にシステムカタログを置き、実行時書き戻しも継続する | 実装変更が最小 | #95 が再発しやすい。カタログと実行時状態が混ざる | 不採用 |
| B. プロジェクトローカル維持+読み取り専用契約 | 利用側 `config/annotator_config.toml` をシステムカタログとし、実行時・テストからの書き戻しを禁止する | 既存構造に近い。#95 を小さな変更で解決できる。カスタムローカルモデルも扱いやすい | cwd 依存は残る | 採用 |
| C. OS ユーザー設定・キャッシュ | `platformdirs` 等で OS 標準ディレクトリに保存する | GUI やフローズンアプリで安定し、cwd 依存がない | 実装、移行、テスト差し替えの負担が重い | 将来検討 |
| D. パッケージリソースのみ | システムカタログをパッケージリソースに固定する | 乖離が少ない。読み取り専用性が強い | 利用側でのカタログ拡張が難しい | 不採用 |
| E. 明示 `config_path` 必須 | ライブラリはデフォルトパスを持たず、利用側が必ずパスを渡す | 責務が明確 | API 利用者の負担が大きい | 不採用 |

案 B は、今回の主要目的である #95 の再発防止と、既存構造・テスタビリティ・カスタムローカルモデル対応のバランスが最も良い。

### `capabilities` を集合和にする理由

`capabilities` は `device` や `tag_threshold` と異なり、単なる実行時の好み(preference)ではない。`UnifiedAnnotationResult` の検証、LoRAIro のモデル同期、UI フィルタ、保存処理の前提となる出力契約である。

システムカタログが `["tags", "ratings"]` と宣言した組み込みモデルを、ユーザー設定が `["tags"]` へ上書きできてしまうと、モデル本体は `ratings` を返すにもかかわらず LoRAIro 側がタグ専用と誤認する。一方で、カスタムローカルモデルではユーザー自身がモデル契約の所有者となるため、ユーザー設定で `capabilities` を宣言できる必要がある。集合和マージであれば、組み込みモデルの契約削除を防ぎつつ、カスタムや実験的モデルの追加宣言を許容できる。

### 実行時キャッシュを分離する理由

`estimated_size_gb` は実行時に計算できる補助メタデータであり、組み込みモデルカタログの定義そのものではない。システムカタログへ自動保存すると、以下の問題が発生する。

- `git diff` に実行時の状態が混入する。
- テストや通常実行によってカタログが書き換わる。
- パッケージテンプレートと利用側カタログの乖離が広がる。
- ユーザー明示値と自動計算値の優先順位が曖昧になる。

実行時キャッシュへ分離すれば、いつでも削除可能な一時状態として扱える。

## Consequences

### 良い影響

- `image-annotator-lib#95` のテスト専用設定による汚染を構造的に防止できる。
- システムカタログと実行時キャッシュの責務が分離される。
- 組み込みローカルモデルの `capabilities` 契約がユーザー設定で削除されなくなる。
- カスタムローカルモデルの `capabilities` 宣言は引き続き可能である。
- LoRAIro はライブラリの TOML を直接管理せず、公開 API 境界を維持できる。
- OS ユーザーディレクトリ移行を後回しにすることで、今回の実装スコープを小さく保てる。

### 悪い影響・トレードオフ

- `capabilities` だけ通常の上書きではなく集合和マージとなるため、仕様説明が必要になる。
- プロジェクトローカル設定のため、cwd 依存は完全には解消しない。
- パッケージリソースと利用側 `config/annotator_config.toml` の乖離は残る。
- 実行時キャッシュファイルの新設により、設定ファイルが 1 つ増える。
- `add_default_setting()` および `save_system_config()` に依存するコードの整理が必要になる。

### 実装方針

#### Phase 1:#95 直接対策

- テストフィクスチャにおける `add_default_setting()` の使用を廃止する。
- テストでは `tmp_path`、分離レジストリ、インメモリ注入のいずれかを使用する。
- `config/annotator_config.toml` にテスト専用セクションが戻らないことを検証する回帰テストを追加する。

#### Phase 2:マージ仕様の変更

- `_merge_configs()` において、`capabilities` を集合和マージに変更する。
- 組み込みモデルのシステム `capabilities` がユーザー設定で削除されないことをテストする。
- カスタムローカルモデルのユーザー `capabilities` が採用されることをテストする。

#### Phase 3:実行時キャッシュの分離

- `loader_base._save_size_to_config()` の保存先を実行時キャッシュへ移す。
- `estimated_size_gb` の解決順を `user_config > runtime_cache > system_catalog` にする。
- 通常実行時から `save_system_config()` を呼び出さないようにする。

#### Phase 4:メンテナンス API の整理

- `add_default_setting()` を非推奨(deprecated)として明示する。
- システムカタログの更新が必要な場合は、メンテナンスおよび開発者向けツールの別経路に限定する。
