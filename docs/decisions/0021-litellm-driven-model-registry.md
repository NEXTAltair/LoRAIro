# ADR 0021: LiteLLM-Driven WebAPI Model Registry

- **日付**: 2026-04-28
- **ステータス**: Proposed
- **Supersedes**: ADR 0003 (partial — WebAPI セクションのみ)
- **関連 ISSUE**: [image-annotator-lib#3](https://github.com/NEXTAltair/image-annotator-lib/issues/3)

## Context

ADR 0003 (2025-11-15) で「全モデル明示的管理」を採用したが、約11ヶ月運用した結果、
WebAPI モデル一覧の追従が破綻している。

### 顕在化した問題

1. **`available_api_models.toml` が約11ヶ月放置** (`last_seen` 最大値 `2025-05-18`)。
   GPT-5 系・Claude 4 系・Gemini 3 系など、約1年分の新規モデルが未反映。
2. **`discover_available_vision_models()` の自動更新トリガーが存在しない**。
   `tools/check_api_model_discovery.py` の手動実行が唯一の更新手段で、運用上トリガー
   されていない。
3. **`deprecated_on` フィールドがフィルタロジックで未参照**。
   `simplified_agent_factory.get_available_models()` は `available_api_models.toml`
   の全モデル ID をそのまま返すため、廃止モデルが UI/CLI に残存する。
4. **`annotator_config.toml` に WebAPI モデルが直書きハードコード**
   (`["GPT-4 Turbo"]`, `["GPT-4o"]`, `["GPT-4o (2024-05-13)"]` 等)。
   discovery 機構の対象外で、OpenAI 公式廃止後も永久に残る。
5. **データソースが OpenRouter のみ**。OpenAI 公式 deprecations
   ([developers.openai.com/api/docs/deprecations](https://developers.openai.com/api/docs/deprecations))
   は反映されず、OpenRouter が掲載を継続する限り廃止検出されない。

### 前提条件の変化

ADR 0003 採用時 (2025-11) には未検討だった選択肢が成熟している:

- **LiteLLM** ([BerriAI/litellm](https://github.com/BerriAI/litellm))
  - 100+ プロバイダー、2600+ モデルの DB を pip パッケージに同梱
  - `litellm.supports_vision(model_id) -> bool` でローカル DB 即時判定
  - `litellm.get_model_info(model_id)` でコスト・コンテキスト長・モダリティ取得
  - `model_prices_and_context_window.json` がリリースごとに更新され、廃止モデルの
    deprecation_date 自動除去機能も Issue
    [#21240](https://github.com/BerriAI/litellm/issues/21240) で議論中
  - **無料・無認証**でユーザーへの追加要求が一切ない

- **Pydantic AI Gateway** (Logfire 統合) は **検討対象外**
  - Logfire アカウント必須・観測 SaaS 前提でコスト発生リスクあり
  - モデル discovery 専用 API が公開されておらず本用途に過剰

- **models.dev** は **補助情報源として保留**
  - スキーマ進化中、deprecation フィールドの存在が確認できない

## Decision

### 採用方針

**LiteLLM 駆動の動的解決**を WebAPI モデルに適用する:

1. WebAPI モデル一覧のソースは **LiteLLM のローカル DB** に切り替える
2. `annotator_config.toml` は **ローカル ML モデル専用**に縮退する
   - 削除対象: `["GPT-4 Turbo"]`, `["GPT-4o*"]`, `["Claude 3.5*"]`, `["Gemini 2.5*"]` 等の WebAPI エントリ
   - 維持対象: ONNX/Transformers/CLIP ベースのローカルモデル定義
3. `available_api_models.toml` は **LiteLLM 出力のキャッシュ** として継続
   - `last_refresh` メタデータを追加し TTL 判定に使用
   - LoRAIro 固有のメタ情報（display_name 整形等）は保持
4. **ライフサイクル API を二系統化**
   - `get_available_models()` → `deprecated_on is None` のみ（active）
   - `list_all_models()` → 全モデル（履歴用）
   - `is_model_deprecated(id)` → 個別判定
5. **追従の三重化**で更新を確実にする
   - TTL ベースの起動時 background refresh（既定 7 日）
   - GUI/CLI からの手動更新トリガー
   - CI による週次 LiteLLM 更新 + 自動 PR 作成
6. **OpenRouter API は補助 fallback** として残す
   - LiteLLM DB に未収録の OpenRouter 限定モデル（free tier 等）を補完
   - 既定では LiteLLM のみ使用、設定で有効化

### スコープ境界

- **対象**: WebAPI モデル（OpenAI / Anthropic / Google / OpenRouter / xAI 等の SaaS LLM）
- **対象外**:
  - ローカル ML モデル（ONNX/Transformers/CLIP/TensorFlow） → ADR 0003 の方針継続
  - PydanticAI 推論パイプライン → 既存実装維持
  - LoRAIro 側の `AnnotationLogic` / `AnnotatorLibraryAdapter` 境界 → ADR 0004/0005 維持
  - Logfire/Pydantic AI Gateway の導入 → 別 ADR で観測ツールとして再検討

## Rationale

### LiteLLM が決定打である理由

| 評価軸 | LiteLLM | Pydantic AI Gateway | OpenRouter のみ継続 | models.dev |
|---|---|---|---|---|
| ユーザー追加要求 | ✓ なし | ✗ Logfire アカウント必須 | ✓ なし | ✓ なし |
| 起動時ネットワーク | ✓ 不要（同梱 DB） | ✗ API キー検証で必要 | ✗ API 取得時に必要 | ✗ JSON fetch 必要 |
| Vision 自動判定 | ✓ `supports_vision()` | △ 推論ベース | △ 自前フィルタ | △ capability 進化中 |
| 廃止追従 | ✓ `deprecation_date` 機構 | △ 不明 | ✗ ソースが偏る | ✗ 未確認 |
| 月額コスト | ✓ $0 | △ 無料枠あり (10M spans) | ✓ $0 | ✓ $0 |
| メンテ持続性 | ✓ BerriAI + 大規模コミュニティ | ✓ Pydantic 公式 | △ サービス依存 | △ 新興 |
| PydanticAI との競合 | ✓ 共存可能 | ✗ 認証層が被る | - | - |

### ADR 0003 で却下された「自動検出」を再採用する根拠

ADR 0003 では「起動時の重い API 取得を避ける」「API 依存」を理由に却下されたが:

- LiteLLM は **モデル DB を pip パッケージにバンドル**しており、起動時 API コール不要
- 推論コール時の動作は変えず、メタデータ参照のみローカル DB 化
- ネットワーク失敗時も既存 toml キャッシュで fallback 可能

→ ADR 0003 の懸念は LiteLLM の登場により解消された。

### 三重化トリガーの根拠

単一トリガーは脆弱（ADR 0003 で実装済の機構が運用されなかったのが実例）。
複数トリガーで「どれかが動けば追従できる」状態を作る:

- **TTL ベース起動時 refresh**: ユーザーがアプリを使い続ければ自動更新
- **手動更新トリガー**: ユーザーが新モデルを使いたい時に明示的更新
- **CI 週次更新**: 開発者が定期的に最新版を取り込む

## Consequences

### 良い影響

- **メンテナンスコスト大幅減**: 新規 WebAPI モデル追加に手動編集が不要
- **廃止モデルの UI 残存問題が構造的に解決**: `deprecated_on` フィルタが動作
- **OpenAI 廃止追従の透明性向上**: LiteLLM の DB 更新ログで追跡可能
- **テスタビリティ改善**: LiteLLM の API を mock すれば discovery のテストが書ける

### 悪い影響・トレードオフ

- **LiteLLM 依存追加**: パッケージサイズ増（`litellm[base]` で最小化）
- **LiteLLM の DB 精度に依存**: 誤判定時は OpenRouter フィルタとの AND 評価で厳格モードを実装
- **既存ユーザー設定の移行が必要**: `annotator_config.toml` の WebAPI セクション削除は
  破壊的変更。migration ガイドを `docs/migration/0021-litellm-migration.md` で提供
- **LiteLLM のメジャーバージョン更新リスク**: `pyproject.toml` で `>=X,<Y` 範囲ピン、
  CI で互換確認

### 移行戦略

1. ADR 0021 (本 ADR) と 7 個の関連 ISSUE を作成（タスク分割は計画書参照）
2. ISSUE B で LiteLLM 依存追加と discovery 移行（fallback 残す）
3. ISSUE C で deprecated フィルタ実装
4. ISSUE D で `annotator_config.toml` の WebAPI セクション削除（破壊的変更）
5. ISSUE E〜G で TTL/UI/CI 等の追従機構を順次追加
6. リリースノートで移行手順を明示

### ADR 0003 への影響

ADR 0003 のステータスは `Superseded by ADR 0021 (partial)` に更新する。
ローカル ML モデル管理に関する決定は引き続き有効。
