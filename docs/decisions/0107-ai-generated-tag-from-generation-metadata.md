---
type: ADR
title: 生成メタデータを根拠に、登録時に ai generated タグを自動で付ける (擬似モデル GENERATION_METADATA)
status: Accepted
timestamp: 2026-11-08
tags: [generation-metadata, registration, tags, provenance]
---

# ADR 0107: 生成メタデータを根拠に、登録時に ai generated タグを自動で付ける (擬似モデル GENERATION_METADATA)

## Context

AI 生成画像に毎回手で `ai generated` を付ける手間を減らしたい (#1396)。根拠には、登録時に保存する
生成メタデータ (ADR 0105 / 0106) を使う。メタデータが無いことは非 AI 生成の証明にならず、汎用の
文字列一致や画像寸法だけでは誤判定になる。`Tag` には由来の列が無く、自動で付けた行を見分けるには
`model_id` を使うしかない (ADR 0104 と同じ事情)。

## Decision

- **判定の根拠**は ADR 0105 の `is_ai_generation_evidence(tool, status)` だけとする。生成ツールが特定でき
  (`sd_webui` / `comfyui`)、解析状態が `parsed` / `partial` / `unsupported` のときに AI 生成とみなす。
  生成ツールが特定できない結果 (汎用テキストの `parameters`、カメラの UserComment など)、`no_metadata`、
  `failed`、未解析は付けない。条件はテストで全組み合わせを固定する。
- **付ける場所**: `register_original_image` が生成メタデータを保存した後 (`apply_ai_generated_tag`)。
  GUI worker と CLI / API が使う `register_image_with_side_effects` では、関連 `.txt` / `.caption` の
  取り込みの後に付ける (同じタグが `.txt` にあれば足さないため)。データセット取り込み・クロップなど
  `register_original_image` を直接呼ぶ経路でも同じ動作になる。
- **由来の区別**: 付けた行は専用の擬似モデル `GENERATION_METADATA` (`provider="user"`,
  `litellm_model_id="__generation_metadata__"`, `model_types` なし, `requires_api_key=False`) の `model_id` で持つ。
  ADR 0104 の `KOHYA_DATASET` と同じ考え方で、手入力 (`MANUAL_EDIT`)・関連ファイル・AI の行と区別でき、
  `model_id` で一括して取り消せる。推論の対象と WebAPI モデルの availability 調整からは、モデル行の属性で
  自然に外れる。スキーマ変更はしない (モデル行は初回に作る)。
- **行の値**: 表記は `ai generated`、`tag_id` は空、`existing=False` (取り込み元のファイルに無かったタグ)、
  `is_edited_manually=False`。
- **重複させない**: 画像に同じタグ (大小・アンダースコア・余分な空白の違いを同じとみなす) の行が、
  どのモデルの行にも無いときだけ足す。soft-reject 済みの行があるときも足さない (ユーザーの判断を保つ)。
  既存のタグには触れない。
- **失敗しても登録を続ける**: 付与の DB エラーは警告に留める。
- **設定で無効にする仕組みは入れない** (Issue 本文に要求が無く、最小の形にする)。付けた行は
  `GENERATION_METADATA` の `model_id` で取り除ける。
- **再解析 (`images analyze-metadata`) では付けない** (ADR 0106 のとおり再解析はタグに触れない)。
  既存の画像は、再取り込みで未解析だったときに解析されて付くか、または明示的な一括操作で付ける。
- **既存画像への一括付与と取り消し (#1502)**: `lorairo-cli images tag-ai-generated` で、保存済みの生成メタデータを
  根拠 (`is_ai_generation_evidence`) として既存画像へ `ai generated` (`GENERATION_METADATA`) を一括で付ける。
  重複させない規則 (他の出所の同じタグや soft-reject 済みの行があれば足さない) は登録時と同じにする。
  `--dry-run` はモデル行もタグ行も作らずに件数だけを返し、`--revoke` は `GENERATION_METADATA` のタグ行だけを
  一括で削除する (`--image-ids` で対象画像を絞れる)。

## Consequences

- `ai generated` は通常のタグとして検索・タグ編集・書き出しに出る。検索の「モデル」ファセットに
  `__generation_metadata__` が出るため、由来で絞り込める。
- ADR 0106 の「登録はタグ・キャプションに書き込まない」は、生成プロンプトを写さないという意味で引き続き
  有効で、`ai generated` の 1 件だけが本 ADR による例外になる。
- ユーザーがタグを物理削除した画像を再取り込みすると、根拠があれば再び付く (soft-reject なら付かない)。
- 設定での無効化は後続。

## Related

- Issue #1396, #1502, #1481, #1482, #1398
- ADR 0105 (生成メタデータの保存), ADR 0106 (登録と再解析), ADR 0104 (擬似モデル KOHYA_DATASET), ADR 0023 (MANUAL_EDIT 行)
