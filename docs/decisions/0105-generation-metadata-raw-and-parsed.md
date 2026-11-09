---
type: ADR
title: 生成メタデータを原データと解析結果に分けて保存する
status: Accepted
timestamp: 2026-11-08
tags: [generation-metadata, registration, schema, parser, provenance]
---

# ADR 0105: 生成メタデータを原データと解析結果に分けて保存する

## Context

AI 生成画像には、生成ツールが書いた生成情報 (プロンプト、モデル、seed など) が埋め込まれていることがある。
これを画像に紐付けて保存し、後で表示・検索し (#1483)、`ai generated` タグの自動付与 (#1396) の根拠にしたい。
Infinite Image Browsing (IIB) の parser 設計を参考にするが、IIB は import 時に設定・ログ・plugin の初期化が走り、
読み取り helper が `image.info.pop("parameters")` で原データを壊し、`.txt` も生成情報として読む。
LoRAIro では学習用の `.txt` / `.caption` (タグ・キャプション) を生成情報と取り違えてはならない。

## Decision

- **原データと解析結果を別テーブルに持つ。**
  - `generation_metadata_sources`: 画像ごと・取得元ごとに 1 行。取得元の種類 (`png_text` / `exif`)、キー、
    原文 (`raw_text`)、バイト列 (`raw_bytes`、EXIF のみ)、SHA-256。整形しない (プロンプトの順序・重み表記・改行を保つ)。
    一度保存した原データは再解析で書き換えない (同じ取得元が既にあれば追加しない)。
  - `generation_metadata`: 1 画像 1 行の解析結果。解析状態、生成ツール、parser 名・版、原データ全体の
    ハッシュ (`input_sha256`)、共通項目 (正/負プロンプト、生成モデル名・ハッシュ、seed、steps、sampler、CFG、
    LoRA 参照の JSON、その他の key: value の JSON)、エラー内容、解析日時。保存のたびに置き換える。
  - 行が無い画像は「未解析」。解析状態は `parsed` (主要項目が揃った) / `partial` (対応形式だが欠けがある) /
    `unsupported` (原データはあるが抽出できる形式ではない) / `no_metadata` (原データが無い) / `failed`
    (取得・復号・解析に失敗) の 5 つで、CHECK 制約で固定する。
- **対応形式と判定根拠** (parser 版 `2`):
  - 取得元は PNG のテキストチャンク `parameters` / `prompt` / `workflow` (Pillow の `img.info` を参照するだけで pop しない)
    と、JPEG / WebP の EXIF UserComment。付属ファイル (`.txt` / `.caption`) は読まない。
  - SD WebUI (A1111 / Forge など) 形式: 最後の行が `Steps` を含む 3 個以上の `key: value` であるときだけ認める。
    それ以外のテキストは `unsupported` とし、生成ツールを特定しない (汎用の fallback 一致を生成の証拠にしない)。
    主要項目はプロンプト・steps・sampler・seed・CFG。値を解釈できない項目は NULL にし、推測で補完しない。
    seed は 64 bit を超えることがあるため文字列で持つ。
  - ComfyUI (版 `1` で判定のみ、版 `2` / #1503 で単一 sampler グラフの項目抽出を追加):
    - `prompt` が全ノード `class_type` 付きの JSON、または `workflow` が `nodes` 配列を持つ JSON なら
      ComfyUI と判定する。
    - **単一 sampler 経路** (`KSampler` / `KSamplerAdvanced` が 1 つのみ): sampler ノードの `seed`
      (`seed` または `noise_seed`)、`steps`、`sampler_name`、`cfg` を取り出し、`positive` / `negative` リンクを
      `CLIPTextEncode` (`CLIPTextEncodeSDXL`・標準の conditioning / 文字列 primitive を含む) まで辿って
      正/負プロンプトを、`model` リンクを `LoraLoader` / `LoraLoaderModelOnly` (`lora_name` と `strength_model` を
      ベースモデルからの適用順に記録) を経由して `CheckpointLoaderSimple` / `CheckpointLoader` / `UNETLoader` 等まで
      辿って `model_name` を抽出する。`EmptyLatentImage` / `EmptySD3LatentImage` の寸法 (`Size`) と
      `scheduler` / `denoise` は `extra` に記録する。主要項目 (正プロンプト・モデル名・seed・steps・sampler・CFG)
      がすべて揃い未知ノードが無ければ `parsed`、一部欠落や未知・動的ノードへの参照があれば `partial` とする。
    - **複数 sampler 経路** (`KSampler` / `KSamplerAdvanced` が 2 つ以上): 複数の生成経路を誤って単一の設定へ
      統合せず、`status="partial"`、`error_message="multiple_samplers"` とし、`extra` に `sampler_count` と
      `sampler_node_ids` を記録する (全 sampler が同一のモデル/LoRA 経路を参照する場合のみそのモデル・LoRA を残し、
      sampler 固有の seed / steps / CFG / プロンプトは NULL にする)。
    - **workflow のみ / sampler なし**: `prompt` ノード辞書を持たない `workflow` のみの画像や sampler ノードが
      0 個のグラフは `unsupported` とする。同じ画像に SD WebUI 形式の `parameters` もあれば、その要約から項目を
      取り `partial` とする。
    - **壊れた JSON と非 ComfyUI テキストの区別**: JSON オブジェクト/配列として始まりながら構文が壊れている
      `prompt` / `workflow` チャンクは `failed` とし、別ツールが書いた平文の `prompt` チャンクは ComfyUI と
      判定せず `unsupported` (`tool=None`) とする。
  - 画像寸法は判定に使わない。
- **層の分け方**: 共有の結果型は `domain/generation_metadata.py` (Qt / DB 非依存)、読み取りと解析は
  `services/generation_metadata_parser.py` (Qt / DB 非依存、Pillow のみ)、保存は
  `GenerationMetadataRepository` (SQLAlchemy) と `ImageDatabaseManager` の facade。IIB のコード・sqlite3 モデル・
  画像 ID 体系は取り込まない。
- AI 生成の判定材料は結果型の `is_ai_generation_evidence` (生成ツールが特定でき、状態が parsed / partial /
  unsupported) で渡す。

## Consequences

- 既存の画像は migration 後も未解析 (行なし) のままで、既存の行は変わらない。登録経路への組み込みと
  既存画像の再解析は #1482。
- 原データを書き換えないため、ファイル側の生成情報が後から変わっても古い原データが残る。解析結果だけは
  最新の parser で置き換わる。
- IDAT より後ろに置かれた PNG テキストチャンクは読まない (Pillow が画像の展開まで読み込まないため)。
  主要な生成ツールは IDAT より前に書く。
- NovelAI など他の形式や ComfyUI の独自拡張ノードは後続。追加するときは parser 版を上げ、
  `lorairo-cli images analyze-metadata <ID...> --force` で既存の解析結果を置き換える。
- 生成モデル・LoRA・プロンプトでの検索用の index は、検索を入れる #1483 で決める (今は `tool` のみ)。

## Related

- Issue #1481, #1482, #1483, #1503, #1396, #1398
- ADR 0061 (登録時の分類と副作用の統一)
