---
type: ADR
title: 生成メタデータを原データと解析結果に分けて保存する
status: Accepted
timestamp: 2026-11-08
tags: [generation-metadata, registration, schema, parser, provenance]
---

# ADR 0105: 生成メタデータを原データと解析結果に分けて保存する

## Context

AI 生成画像には、生成ツールが書き込んだ生成情報(プロンプト、モデル、seed など)が埋め込まれていることがある。これらを画像に紐づけて保存し、後からの表示・検索(#1483)や、`ai generated` タグの自動付与(#1396)の根拠として利用したい。

Infinite Image Browsing(IIB)のパーサ設計は参考になるが、そのまま導入するには問題がある。IIB はインポート時に設定・ログ・プラグインの初期化が走り、読み取りヘルパーが `image.info.pop("parameters")` で原データを破壊するうえ、`.txt` ファイルも生成情報として読み込んでしまう。LoRAIro では、学習用の `.txt` や `.caption`(タグ・キャプション)を生成情報と取り違えてはならない。

## Decision

### 1. 原データと解析結果を別テーブルに分離する

- **`generation_metadata_sources`(原データ)**: 画像ごと・取得元ごとに 1 行を保存する。保持項目は、取得元の種類(`png_text` / `exif`)、キー、原文(`raw_text`)、バイト列(`raw_bytes`、EXIF のみ)、SHA-256 である。プロンプトの順序・重み表記・改行を保つため整形はしない。一度保存した原データは再解析で書き換えず、同じ取得元が既にあれば追加しない。
- **`generation_metadata`(解析結果)**: 1 画像につき 1 行を保存する。保持項目は、解析状態、生成ツール、パーサ名・版、原データ全体のハッシュ(`input_sha256`)、共通項目(正/負プロンプト、生成モデル名・ハッシュ、seed、steps、sampler、CFG、LoRA 参照の JSON、その他の `key: value` の JSON)、エラー内容、解析日時である。解析結果は保存のたびに置き換える。
- **解析状態の定義**: 行が無い画像は「未解析」とする。解析状態は次の 5 種類を CHECK 制約で固定する。
  - `parsed`: 主要項目が揃った
  - `partial`: 対応形式だが項目に欠けがある
  - `unsupported`: 原データはあるが抽出できる形式ではない
  - `no_metadata`: 原データが無い
  - `failed`: 取得・復号・解析に失敗した

### 2. 対応形式と判定根拠(パーサ版 `2`)

取得元は、PNG のテキストチャンク `parameters` / `prompt` / `workflow`(Pillow の `img.info` を参照するだけで `pop` はしない)と、JPEG / WebP の EXIF UserComment に限定する。付属ファイル(`.txt` / `.caption`)は読まず、画像寸法も判定に使わない。

#### SD WebUI(A1111 / Forge など)形式

- 最終行が `Steps` を含む 3 個以上の `key: value` で構成されている場合のみ SD WebUI 形式と認める。それ以外のテキストは `unsupported` とし、生成ツールを特定しない(汎用的なフォールバック一致を生成の証拠にしない)。
- 主要項目はプロンプト・steps・sampler・seed・CFG とする。値を解釈できない項目は NULL とし、推測で補完しない。
- `seed` は 64 bit を超える場合があるため文字列として保持する。

#### ComfyUI 形式(版 `1` で判定のみ、版 `2` / #1503 で単一 sampler グラフの項目抽出を追加)

- `prompt` が全ノードに `class_type` を持つ JSON、または `workflow` が `nodes` 配列を持つ JSON であれば ComfyUI と判定する。
- **単一 sampler 経路(`KSampler` / `KSamplerAdvanced` が 1 つのみ)**:
  - sampler ノードから `seed`(`seed` または `noise_seed`)、`steps`、`sampler_name`、`cfg` を取り出す。
  - `positive` / `negative` リンクを `CLIPTextEncode`(`CLIPTextEncodeSDXL` および標準の conditioning / 文字列プリミティブを含む)まで辿り、正/負プロンプトを抽出する。
  - `model` リンクを `LoraLoader` / `LoraLoaderModelOnly`(`lora_name` と `strength_model` をベースモデルからの適用順に記録)経由で `CheckpointLoaderSimple` / `CheckpointLoader` / `UNETLoader` 等まで辿り、`model_name` を抽出する。
  - `EmptyLatentImage` / `EmptySD3LatentImage` の寸法(`Size`)と `scheduler` / `denoise` は `extra` に記録する。
  - 主要項目(正プロンプト・モデル名・seed・steps・sampler・CFG)がすべて揃い未知ノードが無ければ `parsed`、一部欠落や未知・動的ノードへの参照があれば `partial` とする。
- **複数 sampler 経路(`KSampler` / `KSamplerAdvanced` が 2 つ以上)**:
  - 複数の生成経路を誤って単一の設定へ統合しない。`status="partial"`、`error_message="multiple_samplers"` とし、`extra` に `sampler_count` と `sampler_node_ids` を記録する。
  - 全 sampler が同一のモデル/LoRA 経路を参照する場合のみそのモデル・LoRA を残し、sampler 固有の seed / steps / CFG / プロンプトは NULL にする。
- **`workflow` のみ / sampler なし**:
  - `prompt` ノード辞書を持たない `workflow` のみの画像や、sampler ノードが 0 個のグラフは `unsupported` とする。同じ画像に SD WebUI 形式の `parameters` も含まれていれば、その要約から項目を取り `partial` とする。
- **壊れた JSON と非 ComfyUI テキストの区別**:
  - JSON オブジェクトや配列として始まりながら構文が壊れている `prompt` / `workflow` チャンクは `failed` とする。別ツールが書いた平文の `prompt` チャンクは ComfyUI と判定せず `unsupported`(`tool=None`)とする。

### 3. レイヤー構成

- 共有の結果型: `domain/generation_metadata.py`(Qt / DB 非依存)
- 読み取りと解析: `services/generation_metadata_parser.py`(Qt / DB 非依存、Pillow のみ)
- 永続化: `GenerationMetadataRepository`(SQLAlchemy)と `ImageDatabaseManager` のファサード
- IIB のコード・sqlite3 モデル・画像 ID 体系は取り込まない。

### 4. AI 生成の判定材料

AI 生成の判定材料は、結果型の `is_ai_generation_evidence`(生成ツールが特定でき、状態が `parsed` / `partial` / `unsupported` のいずれか)として提供する。

## Consequences

- 既存画像はマイグレーション後も未解析(行なし)のままであり、既存データには影響しない。登録経路への組み込みと既存画像の再解析は #1482 で対応する。
- 原データを書き換えないため、ファイル側の生成情報が後から変更されても古い原データが残る。一方で、解析結果だけは最新のパーサで置き換わる。
- Pillow は画像データの展開まで読み込まないため、IDAT チャンクより後ろに置かれた PNG テキストチャンクは読まない(主要な生成ツールは IDAT より前に出力する)。
- NovelAI など他の形式や ComfyUI の独自拡張ノードは後続課題とする。対応を追加する際はパーサ版を上げ、`lorairo-cli images analyze-metadata <ID...> --force` で既存の解析結果を置き換える。
- 生成モデル・LoRA・プロンプトでの検索用インデックスは、検索機能を実装する #1483 で設計する(現時点では `tool` のみ)。

## Related

- Issue #1481, #1482, #1483, #1503, #1396, #1398
- ADR 0061(登録時の分類と副作用の統一)
