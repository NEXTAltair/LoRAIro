---
type: ADR
title: LiteLLM-Driven WebAPI Model Registry
status: Superseded by ADR 0023 (partial)
timestamp: 2026-04-28
superseded_by: ["0023"]
tags: []
---
# ADR 0021: LiteLLM-Driven WebAPI Model Registry

- **Supersedes**: ADR 0003(一部 — WebAPI セクションのみ)
- **Superseded by**:
  [ADR 0023](0023-pydanticai-litellm-webapi-inference-boundary.md)(一部 — WebAPI モデルレジストリの実行時評価化)
- **関連 ISSUE**: [image-annotator-lib#3](https://github.com/NEXTAltair/image-annotator-lib/issues/3),
  [#23](https://github.com/NEXTAltair/image-annotator-lib/issues/23),
  [#25](https://github.com/NEXTAltair/image-annotator-lib/issues/25),
  [#26](https://github.com/NEXTAltair/image-annotator-lib/issues/26)

## 2026-05-07 Amendment

ADR 0023 により、本 ADR のうち WebAPI モデルレジストリの運用方式は一部が置き換えられた。現在有効な決定は ADR 0023 を優先する。

### 置き換えられた範囲

- `available_api_models.toml` を LiteLLM 出力キャッシュとして継続する方針
- `available_api_models.toml` および `_WEBAPI_MODEL_METADATA` を WebAPI メタデータの正本とする方針
- WebAPI 用の `user_config.toml` 上書き設定を残す方針
- TTL 更新、手動更新、OpenRouter による補完取得、強制更新、再生成による追従方針
- `supports_response_schema` や構造化出力対応を WebAPI モデル絞り込みの主要条件とする方針

### 現在の方針

- WebAPI モデルレジストリは、LiteLLM 同梱 DB を実行時に評価する。
- `available_api_models.toml` は廃止する。
- WebAPI 用のユーザー TOML 上書き設定は廃止する。
- OpenRouter による補完取得などのネットワーク取得経路は削除する。
- モデルの絞り込みは、Vision 対応および関数・ツール呼び出し対応を主要条件とする。

ローカル ML モデルを `annotator_config.toml` と `user_config.toml` で扱う方針、および LiteLLM を WebAPI モデル検出・機能メタデータの情報源として使う大枠は、引き続き有効である。

## Context

ADR 0003(2025-11-15)では「全モデルの明示的な管理」を採用した。しかし約 11 か月運用した結果、WebAPI モデル一覧の追従が破綻していた。

### 顕在化した問題

1. **`available_api_models.toml` が約 11 か月間放置されていた**
   `last_seen` の最大値が `2025-05-18` のままであり、GPT-5 系・Claude 4 系・Gemini 3 系など約 1 年分の新規モデルが未反映であった。
2. **`discover_available_vision_models()` に自動更新トリガーが存在しなかった**
   更新手段が `tools/check_api_model_discovery.py` の手動実行に限られており、運用上ほとんど実行されていなかった。
3. **`deprecated_on` フィールドがフィルタロジックで参照されていなかった**
   `simplified_agent_factory.get_available_models()` が `available_api_models.toml` の全モデル ID をそのまま返すため、廃止モデルが UI や CLI に残存していた。
4. **`annotator_config.toml` に WebAPI モデルが直書きされていた**
   `["GPT-4 Turbo"]`、`["GPT-4o"]`、`["GPT-4o (2024-05-13)"]` などがハードコードされており、検出機構の対象外となって OpenAI 公式廃止後も残り続けていた。
5. **データソースが OpenRouter のみに依存していた**
   OpenAI 公式の廃止情報([developers.openai.com/api/docs/deprecations](https://developers.openai.com/api/docs/deprecations))が反映されず、OpenRouter が掲載を続ける限り廃止を検出できなかった。

### 前提条件の変化

ADR 0003 の採用時(2025-11)には検討対象外であった選択肢が成熟していた。

- **LiteLLM**([BerriAI/litellm](https://github.com/BerriAI/litellm))
  - 100 以上のプロバイダー、2,600 以上のモデル情報を pip パッケージに同梱している。
  - `litellm.supports_vision(model_id) -> bool` により、ローカル DB で即時に Vision 対応を判定できる。
  - `litellm.get_model_info(model_id)` でコスト・コンテキスト長・モダリティを取得できる。
  - `model_prices_and_context_window.json` がリリースごとに更新されており、廃止モデルの `deprecation_date` 自動除去機能も Issue [#21240](https://github.com/BerriAI/litellm/issues/21240) で議論されている。
  - 無料かつ無認証で利用でき、ユーザーへの追加要求が一切ない。

- **Pydantic AI Gateway**(Logfire 統合)— **検討対象外**
  - Logfire アカウントが必須であり、観測 SaaS 前提のためコスト発生のリスクがある。
  - モデル検出専用の API が公開されておらず、本用途には過剰である。

- **models.dev** — **補助情報源として保留**
  - スキーマが進化中であり、廃止(deprecation)フィールドの存在を確認できない。

## Decision

### 採用方針

WebAPI モデルに対して、**LiteLLM 駆動の動的解決**を適用する。

1. **WebAPI モデル一覧の情報源を LiteLLM のローカル DB へ切り替える。**
2. **`annotator_config.toml` をローカル ML モデル専用へ縮退する。**
   - 削除対象:`["GPT-4 Turbo"]`、`["GPT-4o*"]`、`["Claude 3.5*"]`、`["Gemini 2.5*"]` などの WebAPI エントリ
   - 維持対象:ONNX・Transformers・CLIP ベースのローカルモデル定義
3. **`available_api_models.toml` を LiteLLM 出力のキャッシュとして継続する。**
   - **Superseded by ADR 0023**:現在は廃止し、LiteLLM 同梱 DB を実行時に評価する。
   - `last_refresh` メタデータを追加し、TTL 判定に利用する。
   - `display_name` 整形など LoRAIro 固有のメタ情報は保持する。
4. **WebAPI モデルメタデータの正本を `available_api_models.toml` と `_WEBAPI_MODEL_METADATA` に集約する。**
   - **Superseded by ADR 0023**:現在は実行時の LiteLLM 呼び出しを正本とする。
   - `api_model_id`、`provider`、トークン上限、機能情報、コスト、廃止情報はユーザー TOML へ分散させない。
   - `litellm.supports_vision(model_id)` および `litellm.get_model_info(model_id)` から得られる `supports_response_schema`、`supports_function_calling`、`supports_tool_choice`、`max_input_tokens`、`max_output_tokens` 等を可能な範囲で保存する。
   - LoRAIro および `image-annotator-lib` のアノテーション用途では、Vision 対応と構造化出力対応を重要な適合条件として扱う。
   - **Superseded by ADR 0023**:現在の主要条件は Vision 対応と関数・ツール呼び出し対応である。`supports_response_schema` は `NativeOutput` 最適化用のメタデータとして扱う。
5. **WebAPI モデルのユーザー TOML を、モデル定義ではなく最小限の実行時上書き設定とする。**
   - **Superseded by ADR 0023**:WebAPI 用のユーザー TOML 上書き設定は廃止する。
   - 公開設定の対象は `api_key`(非推奨・互換用)、`custom_instructions`、および必要に応じて `temperature`・`timeout` までに限定する。
   - `top_p`、`seed`、リトライ、ストリーミング、計装、バッチサイズなどの詳細設定は、原則としてライブラリ側の安定既定値または内部設定へ寄せる。
   - `api_model_id` フォールバックは旧方式の互換経路であり、最終的には削除する。
6. **ライフサイクル API を二系統化する。**
   - `get_available_models()`:`deprecated_on is None` の有効モデルのみ返す。
   - `list_all_models()`:履歴参照用として全モデルを返す。
   - `is_model_deprecated(id)`:個別モデルの廃止状態を判定する。
7. **追従トリガーを三重化し、更新を確実にする。**
   - **Superseded by ADR 0023**:実行時の LiteLLM ローカル DB 呼び出しへ移行するため、キャッシュ更新機構は削除対象とする。
   - TTL ベースの起動時バックグラウンド更新(既定 7 日)
   - GUI および CLI からの手動更新トリガー
   - CI による週次 LiteLLM 更新と自動 PR 作成
8. **OpenRouter API を補助フォールバックとして残す。**
   - **Superseded by ADR 0023**:OpenRouter からの補完取得は削除対象とする。
   - LiteLLM DB に未収録の OpenRouter 限定モデル(無料枠など)を補完する。
   - 既定では LiteLLM のみを使用し、設定で有効化できるようにする。

### スコープ境界

- **対象**:WebAPI モデル(OpenAI、Anthropic、Google、OpenRouter、xAI などの SaaS LLM)
- **対象外**:
  - ローカル ML モデル(ONNX、Transformers、CLIP、TensorFlow)は ADR 0003 の方針を継続する。
  - PydanticAI の推論パイプラインは既存実装を維持する。
    - **Superseded by ADR 0023**:WebAPI の推論境界は PydanticAI のネイティブプロバイダー・モデル構成へ整理する。
  - LoRAIro 側の `AnnotationLogic` および `AnnotatorLibraryAdapter` の境界は ADR 0004・0005 を維持する。
  - LoRAIro DB への WebAPI 実行パラメータ保存は対象外とする。
  - Logfire および Pydantic AI Gateway の導入は、別 ADR で観測ツールとして再検討する。

### LoRAIro DB との責務境界

LoRAIro DB は WebAPI の実行設定を保存する場所ではない。DB に保存する情報は、アノテーション結果が参照する `model_id` と、`models` テーブル上の最小限のモデル識別メタデータに限定する。

- **保存対象**:`name`、`provider`、`api_model_id`、`estimated_size_gb`、`requires_api_key`、`discontinued_at`、`model_types`
- **アノテーション結果側の記録**:`tags`、`captions`、`scores`、`ratings` における `model_id` と `created_at`・`updated_at`
- **保存しないもの**:`temperature`、`top_p`、`timeout`、`custom_instructions`、リトライ設定、ストリーミング設定などの実行時パラメータ

この境界により「いつ、どのモデルでアノテーションしたか」は追跡できる一方、実行時パラメータの完全な再現性までは DB の責務に含めない。

## Rationale

### LiteLLM が決定打である理由

| 評価軸 | LiteLLM | Pydantic AI Gateway | OpenRouter のみ継続 | models.dev |
|---|---|---|---|---|
| ユーザー追加要求 | ✓ なし | ✗ Logfire アカウント必須 | ✓ なし | ✓ なし |
| 起動時ネットワーク | ✓ 不要(同梱 DB) | ✗ API キー検証で必要 | ✗ API 取得時に必要 | ✗ JSON 取得が必要 |
| Vision 自動判定 | ✓ `supports_vision()` | △ 推論ベース | △ 自前フィルタ | △ 機能定義が進化中 |
| 廃止追従 | ✓ `deprecation_date` 機構 | △ 不明 | ✗ ソースが偏る | ✗ 未確認 |
| 月額コスト | ✓ $0 | △ 無料枠あり(10M spans) | ✓ $0 | ✓ $0 |
| メンテ持続性 | ✓ BerriAI と大規模コミュニティ | ✓ Pydantic 公式 | △ サービス依存 | △ 新興 |
| PydanticAI との競合 | ✓ 共存可能 | ✗ 認証層が重複 | - | - |

### ADR 0003 で却下された「自動検出」を再採用する根拠

ADR 0003 では「起動時の重い API 取得を避ける」「外部 API に依存しない」という理由から自動検出を却下していた。しかし LiteLLM の登場により、これらの懸念は解消された。

- LiteLLM は**モデル DB を pip パッケージに同梱**しているため、起動時の API 通信が不要である。
- 推論呼び出し時の挙動は変えず、メタデータ参照のみをローカル DB 化できる。
- ネットワーク障害時も既存の TOML キャッシュへフォールバックできる。
  - **Superseded by ADR 0023**:現在は WebAPI の TOML キャッシュを廃止し、起動時のネットワーク取得自体を行わない。

### 三重化トリガーの根拠

> **Superseded by ADR 0023**:`available_api_models.toml` の更新機構は廃止し、LiteLLM 同梱 DB の実行時評価へ移行する。本節は ADR 0021 採用時点の判断理由としてのみ残す。

単一の更新トリガーは脆弱であり、実際に ADR 0003 で実装済みの機構が運用されなかった。複数のトリガーを用意し「いずれかが動けば追従できる」状態を作る方針であった。

- **TTL ベースの起動時更新**:ユーザーがアプリを使い続けることで自動更新される。
- **手動更新トリガー**:新モデルを使いたいときにユーザーが明示的に更新できる。
- **CI 週次更新**:開発者が定期的に最新版を取り込める。

### user TOML を最小化する根拠

> **Superseded by ADR 0023**:WebAPI 用のユーザー TOML 上書き設定は廃止する。本節は ADR 0021 採用時点の判断理由としてのみ残す。

WebAPI モデルの機能情報やトークン上限は LiteLLM から取得できる。これらをユーザー TOML にも重複して保持すると、値の不整合や優先順位の問題が再発する。そのため、ユーザー TOML は「モデルが何者か」ではなく「ユーザーがどう実行したいか」だけを表す位置づけとした。

一般ユーザーに公開する設定面は最小限にとどめる。詳細な PydanticAI・リトライ・ストリーミング・計装設定は、十分な利用価値が確認されるまで通常のユーザー TOML には露出させない。

## Consequences

### 良い影響

- **メンテナンスコストの大幅削減**:新規 WebAPI モデルの追加時に手動編集が不要になる。
- **廃止モデルの UI 残存問題を構造的に解決**:`deprecated_on` フィルタが確実に機能するようになる。
- **OpenAI 廃止追従の透明性向上**:LiteLLM の DB 更新履歴から変更を追跡できる。
- **テスト容易性の改善**:LiteLLM の API を mock することで、モデル検出ロジックのテストを容易に書ける。

### 悪い影響・トレードオフ

- **LiteLLM 依存の追加**:パッケージサイズが増加する(`litellm[base]` を指定して最小化する)。
- **LiteLLM の DB 精度への依存**:誤判定時は OpenRouter フィルタとの AND 評価による厳格モードで対処する。
  - **Superseded by ADR 0023**:OpenRouter の補完取得は廃止し、LiteLLM 同梱 DB と PydanticAI の実行時エラーで扱う。
- **既存ユーザー設定の移行が必要**:`annotator_config.toml` の WebAPI セクション削除は破壊的変更となる。旧方式のユーザー TOML における `api_model_id` フォールバックも最終的に削除する。移行ガイドは `docs/migration/0021-litellm-migration.md` で提供する。
- **LiteLLM のメジャーバージョン更新リスク**:`pyproject.toml` で `>=X,<Y` の範囲指定を行い、CI で互換性を確認する。

### 移行戦略

1. ADR 0021(本 ADR)と 7 件の関連 ISSUE を作成する(タスク分割は計画書を参照)。
2. ISSUE B で LiteLLM 依存を追加し、検出処理を移行する(フォールバックを残す)。
   - **Superseded by ADR 0023**:フォールバック取得は残さない。
3. ISSUE C で廃止(deprecated)フィルタを実装する。
4. ISSUE D で `annotator_config.toml` の WebAPI セクションを削除する(破壊的変更)。
5. ISSUE #23 で検出由来メタデータの SSoT 化と、`config_registry.set_system_value()` による逆流注入の撤廃を行う。
6. ISSUE #26 で `AnnotatorInfo` の詳細メタデータを SSoT 経由で提供し、LoRAIro DB 同期に必要な最小メタデータをライブラリ側から取得可能にする。
7. ISSUE #25 で旧方式の WebAPI ユーザー TOML 定義と `api_model_id` フォールバックを削除し、完全な SSoT 化を達成する。
8. ISSUE E〜G で TTL・UI・CI などの追従機構を順次追加する。
   - **Superseded by ADR 0023**:`available_api_models.toml` の更新系機能は実装しない。
9. リリースノートで移行手順を明示する。

### ADR 0003 への影響

ADR 0003 のステータスは `Superseded by ADR 0021 (partial)` へ更新する。なお、ローカル ML モデル管理に関する決定は引き続き有効である。
