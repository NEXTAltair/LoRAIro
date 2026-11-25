---
type: ADR
title: 生成メタデータを根拠に、登録時に ai generated タグを自動で付ける (擬似モデル GENERATION_METADATA)
status: Accepted
timestamp: 2026-11-08
tags: [generation-metadata, registration, tags, provenance]
---

# ADR 0107: 生成メタデータを根拠に、登録時に ai generated タグを自動で付ける(擬似モデル GENERATION_METADATA)

## Context

AI 生成画像に対して毎回手動で `ai generated` タグを付ける手間を減らしたい(#1396)。その根拠には、登録時に保存される生成メタデータ(ADR 0105 / ADR 0106)を用いる。

一方で、メタデータが無いことは非 AI 生成の証明にならず、汎用的な文字列一致や画像寸法だけでは誤判定を招く。また、`Tag` テーブルには由来を表す専用列が無いため、自動付与した行を見分けるには `model_id` を使う必要がある(ADR 0104 と同じ事情)。

## Decision

### 1. 判定の根拠を `is_ai_generation_evidence` に限定する

判定根拠は ADR 0105 の `is_ai_generation_evidence(tool, status)` のみとする。

- 生成ツールが特定でき(`sd_webui` / `comfyui`)、かつ解析状態が `parsed` / `partial` / `unsupported` の場合に AI 生成とみなす。
- 生成ツールを特定できない結果(汎用テキストの `parameters` やカメラの UserComment など)、`no_metadata`、`failed`、および未解析の場合はタグを付けない。
- これらの判定条件はテストで全組み合わせを固定する。

### 2. 付与するタイミング

`register_original_image` が生成メタデータを保存した直後に `apply_ai_generated_tag` を実行する。

- GUI ワーカーと CLI / API が使う `register_image_with_side_effects` では、関連する `.txt` / `.caption` の取り込み後に付与する(同じタグが `.txt` に既にあれば重複追加しないため)。
- データセット取り込みやクロップなど、`register_original_image` を直接呼ぶ経路でも同じ動作になる。

### 3. 擬似モデル `GENERATION_METADATA` と行の属性

付与した行は、専用の擬似モデル `GENERATION_METADATA` の `model_id` に紐づける。

- **モデル属性**: `provider="user"`、`litellm_model_id="__generation_metadata__"`、`model_types` なし、`requires_api_key=False`
- ADR 0104 の `KOHYA_DATASET` と同じ設計により、手入力(`MANUAL_EDIT`)・関連ファイル・AI のタグ行と区別でき、`model_id` 単位で一括取り消しできる。
- モデル行の属性により、推論対象や WebAPI モデルの利用可否調整からは自然に除外される。スキーマ変更は行わず、モデル行は初回利用時に作成する。
- **タグ行の値**: 表記は `ai generated`、`tag_id` は空、`existing=False`(取り込み元ファイルに無かったタグ)、`is_edited_manually=False` とする。

### 4. 重複防止・エラー処理・設定の最小化

- **重複させない**: 対象画像に同じタグ(大文字・小文字、アンダースコア、余分な空白の違いを同一視する)が、どのモデルの行にも存在しない場合だけ追加する。ソフトリジェクト(soft-reject)済みの行がある場合もユーザーの判断を尊重して追加しない。既存のタグ行には触れない。
- **失敗しても登録を続ける**: タグ付与時の DB エラーは警告ログにとどめ、画像登録を中断しない。
- **設定による無効化は設けない**: Issue 本文に要求が無く最小構成とするため、設定フラグは追加しない。不要な行は `GENERATION_METADATA` の `model_id` で一括削除できる。
- **再解析では付与しない**: `images analyze-metadata` は ADR 0106 の方針どおりタグに触れない。既存画像への付与は、未解析状態での再取り込み時、または下記の明示的な一括操作で行う。

### 5. 既存画像への一括付与と取り消し(#1502)

`lorairo-cli images tag-ai-generated` を新設し、保存済みの生成メタデータ(`is_ai_generation_evidence`)を根拠として既存画像へ `ai generated`(`GENERATION_METADATA`)を一括付与できるようにする。

- 重複防止の規則(他由来の同一タグやソフトリジェクト済みの行があれば追加しない)は登録時と同一とする。
- `--dry-run` 指定時はモデル行もタグ行も作成せず、対象件数のみを返す。
- `--revoke` 指定時は `GENERATION_METADATA` のタグ行だけを一括削除する(`--image-ids` で対象画像を絞り込める)。

## Consequences

- `ai generated` は通常のタグとして検索・タグ編集・書き出しに現れる。検索の「モデル」ファセットには `__generation_metadata__` が表示されるため、由来で絞り込める。
- ADR 0106 の「登録はタグ・キャプションに書き込まない」という方針は生成プロンプトを写さない意味で引き続き有効であり、`ai generated` の 1 件のみが本 ADR による例外となる。
- ユーザーがタグを物理削除した画像を再取り込みすると、根拠があれば再び付与される(ソフトリジェクトであれば再付与されない)。
- 設定による無効化は後続課題とする。

## Related

- Issue #1396, #1502, #1481, #1482, #1398
- ADR 0105(生成メタデータの保存)、ADR 0106(登録と再解析)、ADR 0104(擬似モデル `KOHYA_DATASET`)、ADR 0023(`MANUAL_EDIT` 行)
