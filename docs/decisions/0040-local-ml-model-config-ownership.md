---
type: ADR
title: Local ML Model Config Ownership
status: Accepted
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

ADR 0021 / ADR 0023 により、WebAPI モデル管理は `annotator_config.toml` から離れ、
LiteLLM 同梱 DB を runtime SSoT とする設計へ移行した。LoRAIro から image-annotator-lib へは
`litellm_model_id` と `api_keys` を明示的に渡すため、WebAPI モデル定義・API key・route selection
は TOML system catalog の責務ではなくなっている。

一方、ローカル ML モデル (ONNX / Transformers / CLIP / TensorFlow) の設定は ADR 0003 / ADR 0004
の方針を引き継ぎ、`annotator_config.toml` と `user_config.toml` を使う設計のまま残っている。
このため、現在の `annotator_config.toml` は以下の複数の責務を兼ねている。

- built-in local model catalog
- 利用側プロジェクトに配置される system config
- `add_default_setting()` による不足 default の永続化先
- model loader が計算した `estimated_size_gb` の保存先
- test fixture が一時モデル設定を注入する対象

この責務混在により、image-annotator-lib#95 では pytest 実行時に test-only モデル定義が
`config/annotator_config.toml` へ書き戻され、production catalog に混入した。

具体的には、複数の test fixture が `config_registry.add_default_setting(...)` を呼び、
同メソッドが `save_system_config()` を実行するため、以下のような test-only entry が system
catalog に永続化された。

- `test_model` / `MockAnnotator`
- `dummy-model` / `DummyTransformersAnnotator`
- `test_base_annotator_model` / `ConcreteAnnotator`
- `test_transformers_base_model` / `TransformersBaseAnnotator`

PR #92 (`chore: remove test-only annotator config entries`) で一度削除されたが、PR #93 の pytest
実行時に同じ stub が再混入し、review で再検出された。これは個別 test の cleanup 不足ではなく、
system catalog が通常 runtime/test から暗黙に書き換え可能な設計であることが根本原因である。

また、LoRAIro#365 では rating 対応 local tagger の `capabilities` が古い config 由来で `tags`
のみに落ち、LoRAIro#366 では `TaskCapability.RATINGS` の adapter 変換漏れが表面化した。
`capabilities` は単なる表示設定ではなく、モデルが返してよい出力型の契約であり、user config
によって built-in model の契約を削除できると、UI filter / DB sync / result validation / 保存処理の
前提が崩れる。

### ADR スコープ

本 ADR は **ローカル ML モデル設定** の所有権と永続化先を定める。

対象:

- `config/annotator_config.toml`
- `config/user_config.toml`
- runtime-derived metadata (`estimated_size_gb` など)
- local ML model の `capabilities` merge 規則
- test が config を扱うルール
- LoRAIro と image-annotator-lib の local model config 境界

対象外:

- WebAPI モデル discovery / route selection / API key injection
- LiteLLM DB の provider/model metadata
- LoRAIro DB schema 上の `models` / `model_types` の正規化
- OS user config/cache directory への移行

## Decision

### 1. local ML system catalog は利用側 project-local config に配置する

ローカル ML モデルの system catalog は、ライブラリ利用側プロジェクトの
`config/annotator_config.toml` に配置する。

image-annotator-lib は、同ファイルが存在しない場合に限り、package resource の
`resources/system/annotator_config.toml` から初期生成してよい。

生成後の `config/annotator_config.toml` は利用側プロジェクトが管理する catalog であり、
通常 runtime 処理・model load 副作用・test fixture によって暗黙に書き換えてはならない。

### 2. package resource は初期テンプレートであり、通常 runtime の永続化先ではない

package resource の `resources/system/annotator_config.toml` は、初期生成用 template として扱う。
直接編集・runtime 書き戻し・test fixture 注入の対象ではない。

### 3. user override は `config/user_config.toml` に保存する

ユーザーまたは利用側 project が local model の実行設定を変える場合、`config/user_config.toml`
を使う。

主な user override 対象:

- `device`
- `model_path`
- `tag_threshold`
- `batch_size`
- `gpu_memory_limit_gb`
- custom local model の section

system catalog を直接編集する運用は、built-in catalog の開発・配布更新・明示的な maintenance
作業に限定する。

### 4. runtime-derived metadata は system catalog に保存しない

model loader が実行時に計算した metadata は `config/annotator_config.toml` に書き戻さない。

`estimated_size_gb` などの runtime-derived metadata は、別ファイルに保存する。

初期候補:

```text
config/model_runtime_cache.toml
```

`estimated_size_gb` の有効値は以下の優先順位で解決する。

```text
user_config.toml
> model_runtime_cache.toml
> annotator_config.toml
> code/class fallback
```

ユーザーが明示した値を runtime cache が上書きしてはならない。

### 5. `capabilities` は削除不能な追加マージとする

local ML model の `capabilities` は、通常の user override とは異なり、system catalog と
`user_config.toml` の集合和で決定する。

```text
effective_capabilities = system_capabilities ∪ user_capabilities
```

これにより、`user_config.toml` は `capabilities` を追加できるが、system catalog が宣言した
`capabilities` を削除できない。

例:

```toml
# system catalog
[wd-vit-tagger-v3]
capabilities = ["tags", "ratings"]

# user_config.toml
[wd-vit-tagger-v3]
capabilities = ["tags"]
```

有効値:

```toml
capabilities = ["tags", "ratings"]
```

`ratings` は削除されない。

custom local model の場合、system catalog に同名 section がないため、`user_config.toml` の
`capabilities` がそのまま採用される。

```toml
[my-custom-wd]
class = "WDTagger"
model_path = "/models/my-custom-wd/model.onnx"
type = "tagger"
capabilities = ["tags", "ratings"]
tag_threshold = 0.35
device = "cuda"
```

custom local model で `capabilities` が未指定の場合は、`type` / `class` から推論してよい。
ただし、その場合は明示宣言を促す warning を出す。

理由: `capabilities` は単なる表示用設定ではなく、モデルが返してよい出力型の契約である。
system catalog が宣言した built-in model の契約を user override で落とせると、UI filter /
LoRAIro DB sync / result validation / 保存処理が不整合になる。

### 6. `add_default_setting()` は新規利用禁止とする

`ModelConfigRegistry.add_default_setting()` は、新規コードで使用してはならない。

理由:

- 名前から永続書き込みが予測しづらい
- test fixture が一時設定注入に使うと system catalog を汚染する
- system catalog read-only contract と矛盾する

既存互換のため即削除はしないが、少なくとも test/runtime 経路では使用禁止とする。
一時設定注入には `set_system_value()` または isolated `ModelConfigRegistry` を使う。

### 7. `save_system_config()` は通常 runtime から呼ばない

`save_system_config()` は maintenance / developer tooling 用の明示操作に限定する。

通常 runtime、model load、副作用的な metadata 更新、test fixture から呼んではならない。

特に `loader_base._save_size_to_config()` は、system catalog ではなく runtime cache へ保存する
実装へ変更する。

### 8. test は real system catalog に書いてはならない

image-annotator-lib と LoRAIro の test は、real `config/annotator_config.toml` を永続変更してはならない。

test で local model config が必要な場合は、以下のいずれかを使う。

- `tmp_path` に配置した isolated config path
- isolated `ModelConfigRegistry()` instance
- `set_system_value()` による in-memory 注入
- monkeypatch された config path

regression 条件:

```text
pytest 実行後に config/annotator_config.toml に test-only section が追加されない。
```

### 9. LoRAIro は image-annotator-lib の TOML を直接編集しない

LoRAIro は image-annotator-lib の local model catalog を直接編集・同期しない。

LoRAIro が使う lib 境界:

- `list_annotator_info()`
- `annotate(..., model_name_list=..., api_keys=...)`
- その他の公開 API

LoRAIro DB の `models` / `model_types` は検索・表示・保存関連の cache / projection であり、
image-annotator-lib の config 正本ではない。

### 10. OS user config/cache directory への移行は今回採用しない

`platformdirs` 等を使って OS user config/cache directory に保存する案は、将来検討として残す。

今回の優先事項は image-annotator-lib#95 の再発防止であり、保存先解決・migration・テスト差し替え・
利用者説明が増える OS directory 移行は過剰と判断する。

将来、以下が必要になった場合は別 ADR で再検討する。

- frozen app / installer で cwd が安定しない
- 複数アプリから image-annotator-lib を共有する
- OS 標準の user config/cache directory に統一する必要がある
- project-local config を portable mode に限定したい

## Rationale

### project-local read-only catalog を採用する理由

| 案 | 内容 | 利点 | 欠点 | 評価 |
|---|---|---|---|---|
| A. 現状維持 | `Path.cwd()/config` に system catalog を置き、runtime 書き戻しも継続 | 実装変更が最小 | #95 が再発しやすい。catalog と runtime state が混ざる | 不採用 |
| B. project-local 維持 + read-only contract | 利用側 `config/annotator_config.toml` を system catalog とし、runtime/test 書き戻しは禁止 | 既存構造に近い。#95 を小さい変更で解決できる。custom local model も扱いやすい | cwd 依存は残る | 採用 |
| C. OS user config/cache | `platformdirs` 等で OS 標準 directory に保存 | GUI/frozen app で安定。cwd 依存なし | 実装・migration・テスト差し替えが重い | 将来検討 |
| D. package resource のみ | system catalog は package resource に固定 | drift が少ない。read-only が強い | 利用側 catalog 拡張が難しい | 不採用 |
| E. 明示 config_path 必須 | lib は default path を持たず、利用側が必ず path を渡す | 責務が明確 | API 利用者の負担が大きい | 不採用 |

B 案は、今回の主要目的である #95 の再発防止と、既存構造・テスタビリティ・custom local model
サポートのバランスが最も良い。

### `capabilities` を集合和にする理由

`capabilities` は `device` や `tag_threshold` と違い、単なる実行時 preference ではない。
`UnifiedAnnotationResult` validation、LoRAIro model sync、UI filter、保存処理の前提になる
出力契約である。

system catalog が `["tags", "ratings"]` と宣言した built-in model を、user config が
`["tags"]` に上書きできると、モデル本体が `ratings` を返すにもかかわらず、LoRAIro は
tags-only と誤認する。

一方、custom local model ではユーザーが model contract の owner になるため、user config で
`capabilities` を宣言できる必要がある。

集合和 merge は、built-in model の契約削除を防ぎつつ、custom / experimental model の追加宣言を
許可できる。

### runtime cache を分離する理由

`estimated_size_gb` は実行時に計算できる補助 metadata であり、built-in model catalog の定義そのもの
ではない。

system catalog に自動保存すると、以下の問題が起きる。

- git diff に runtime state が混ざる
- test / runtime 実行で catalog が変わる
- package template と利用側 catalog の drift が増える
- ユーザー明示値と自動計算値の優先順位が曖昧になる

runtime cache へ分離すれば、削除可能な state として扱える。

## Consequences

### 良い影響

- image-annotator-lib#95 の test-only config 汚染を構造的に防げる
- system catalog と runtime cache の責務が分かれる
- built-in local model の `capabilities` 契約が user config で削除されない
- custom local model の `capabilities` 宣言は引き続き可能
- LoRAIro は lib TOML を直接管理せず、公開 API 境界を維持できる
- OS user directory 移行を後回しにでき、今回の実装 scope を小さく保てる

### 悪い影響・トレードオフ

- `capabilities` だけ通常 override ではなく集合和 merge になるため、仕様説明が必要
- project-local config のため、cwd 依存は完全には解消しない
- package resource と利用側 `config/annotator_config.toml` の drift は残る
- runtime cache file の新設により、config file が 1 つ増える
- `add_default_setting()` / `save_system_config()` 依存コードの整理が必要

### 実装方針

Phase 1: #95 直接対策

- test fixture の `add_default_setting()` 使用をやめる
- test は `tmp_path` / isolated registry / in-memory injection を使う
- `config/annotator_config.toml` に test-only section が戻らない regression test を追加する

Phase 2: merge semantics

- `_merge_configs()` で `capabilities` を集合和 merge にする
- built-in model の system `capabilities` が user config によって削除されないことを test する
- custom local model の user `capabilities` が採用されることを test する

Phase 3: runtime cache 分離

- `loader_base._save_size_to_config()` を runtime cache 保存へ移す
- `estimated_size_gb` の解決順を `user_config > runtime_cache > system_catalog` にする
- `save_system_config()` を通常 runtime から呼ばないようにする

Phase 4: maintenance API 整理

- `add_default_setting()` を deprecated として明示する
- system catalog 更新が必要な場合は maintenance / developer tooling として別経路に限定する