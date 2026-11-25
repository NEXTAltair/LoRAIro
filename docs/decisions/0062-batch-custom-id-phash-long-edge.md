---
type: ADR
title: Provider Batch custom_id を pHash + 長辺解像度基準へ統一
status: Accepted
timestamp: 2026-06-05
tags: []
---
# ADR 0062: Provider Batch custom_id を pHash + 長辺解像度基準へ統一

- **関連 Issue**: #629(本 ADR)
- **関連 ADR**: 0038(Provider Batch Job Lifecycle)、0044(Provider Batch Submit Threading)

## Context

ADR 0038 で導入した Provider Batch(OpenAI / Anthropic / Google)では、バッチ内の各リクエストを一意に突合するため `custom_id` を付与する。OpenAI Batch API は出力順が入力順と一致しない契約であるため、結果の取り込みには `custom_id` による突合が不可欠である。

従来の `custom_id` は画像レコード ID に直結した形式(`img-{image_id}`)だった。しかし、この方式には次の 3 つの課題がある。

1. **画像 ID は素材の実体を表さない**: 同一の画素データを持つ画像が解像度違いで複数レコードとして登録され得る。逆に、別レコードであっても素材としては同一である場合がある。バッチ投入の重複排除と結果突合は、レコード ID よりも「アノテーション対象素材の実体」に寄せたほうが合理的である。
2. **同一素材の重複投入を防げない**: 同じバッチに同一素材を複数回投入しても、API 課金が無駄に増えるだけで利点がない。レコード ID 基準では同一素材かどうかを判定できず、重複投入を避ける単位が存在しなかった。
3. **解像度差を区別する必要がある**: 一方で、同じ絵柄であってもアノテーションに使う素材の長辺解像度が異なる場合は、別の入力画像として別リクエストに分けたい。低解像度と高解像度では推論結果が変わり得るためである。

## Decision

`custom_id` を、pHash とアノテーション対象素材の長辺解像度の組み合わせで生成する。

```
custom_id = ph:{phash_hex}:le:{long_edge_px}
```

### 1. 画像 ID ではなく pHash を使う理由

pHash(知覚ハッシュ)は素材の見た目に基づく指紋であり、レコード ID と異なり素材の実体に寄せた突合キーになる。LoRAIro では `Image.phash` が NOT NULL 制約で登録時に必ず計算されるため、追加コストなしで取得できる。

### 2. pHash 単独ではなく長辺解像度も含める理由

同じ絵柄でも、アノテーションに渡す素材の長辺解像度が異なれば推論結果が変わり得るため、別リクエストとして扱いたい。pHash 単独では解像度違いが同一キーに統合されてしまう。

長辺解像度(`max(width, height)`)をキーに含めることで、「同一絵柄・同一解像度」のみを 1 リクエストに統合し、解像度差は別リクエストへ分離できる。幅と高さの両方ではなく長辺のみを使うのは、アスペクト比が保たれる前提では長辺が解像度の代表値になるためである。あわせて、`custom_id` を短く保つ意図もある(OpenAI の `custom_id` は `<=64` 文字の制約がある)。

### 3. pHash は完全一致キーとして扱う

本 ADR の実装では、pHash の完全一致を突合キーとして用いる。pHash は知覚ハッシュであるため、わずかに異なる画像が同一ハッシュになる衝突や、僅差で別ハッシュになる可能性がある。

本設計はこの性質を許容し、「完全一致した pHash と同一長辺」を同一素材とみなす単純な規約とする。ハミング距離による近似 pHash 判定は導入しない。これは Issue #630 の方針とも整合する。

### 4. 同一バッチ内の重複投入禁止と重複排除

同一 `custom_id`(同一 pHash かつ同一長辺)の素材は、バッチ内で 1 リクエストに重複排除する。

- `ProviderBatchJobService._validate_submit_request` は、同一 `custom_id` の重複投入を `InvalidProviderBatchRequest` で拒否する。
- 重複排除は投入リクエスト構築側(`ProviderBatchWorkflowService.build_submit_request`)で行い、最初に出現したレコードを代表 `image_id` として DB アイテムに保存する。

### 5. `custom_id -> image_id[]` 対応表の保持

重複排除によって複数の `image_id` が 1 リクエストに統合されるため、結果取り込み時には統合元のすべての `image_id` へアノテーションを反映する必要がある。

`provider_batch_items` は `UniqueConstraint(job_id, custom_id)` を持ち、アイテムごとに単一の `image_id` 列しか持たない。そこで、統合された重複 `image_id` 群は DB アイテムの `raw_request`(LoRAIro ローカルのペイロードであり、`image-annotator-lib` へは渡されない)に `{"lorairo_image_ids": [...]}` として保持する。

結果取り込み時はこの対応表を読み戻し、1 つの結果アノテーションを統合元の全 `image_id` へ展開して反映する。`raw_request` が欠落している旧フォーマットのジョブでは、代表 `image_id` のみへ反映することで後方互換を保つ。

### 6. 将来、近似 pHash を導入する場合の拡張性

将来的に近似 pHash(近傍クラスタリング)を導入する場合は、クラスタの代表 pHash を 1 つ選んで `custom_id` を生成し、クラスタ内の全 `image_id` を上記の対応表に含める。本 ADR の `custom_id -> image_id[]` 対応表は、この拡張を素直に受け入れられる構造になっている。ただし現時点では近似方式は採用せず、完全一致のみを実装する。

## Consequences

### 利点

- 同一素材の重複投入を構造的に防ぎ、無駄な API 課金を抑制できる。
- 解像度差を別リクエストとして正しく区別できる。
- `custom_id` から素材実体(pHash と長辺)を直接読み戻せる(`parse_custom_id`)。
- DB スキーマを変更せずに実現でき、既存の `provider_batch_items` テーブルをそのまま利用できる。

### 代償・留意点

- **pHash 衝突の許容**: 完全一致前提のトレードオフとして、pHash 衝突時に本来別素材である画像を同一リクエストに統合する可能性がある。これは実運用上、許容範囲とみなす。
- **`raw_request` の非転送前提**: 対応表を `raw_request`(Text)に埋め込むため、`image-annotator-lib` 側の `BatchSubmitItem` がこのキーをプロバイダへ転送しないことが前提となる。現状の `BatchSubmitItem` は `custom_id`、`image_id`、`image_path` のみを扱い、`raw_request` は LoRAIro 側の互換レイヤーで除外される。
- **旧フォーマットとの後方互換**: 旧フォーマット(`img-{image_id}`)で投入済みのジョブについては、取り込み時に代表 `image_id` のみへ反映するフォールバックで後方互換を担保する。
- **長辺解像度の算出元**: 長辺解像度は DB に保存されたオリジナル画像のメタデータ(`width` / `height`)から導出する。`image_paths` の上書き指定でオリジナルと異なる解像度の素材を投入する場合、`custom_id` は上書き側の実解像度ではなくオリジナル解像度基準になる。現行の投入経路(GUI / CLI / moderation preflight)では、上書き解像度差が `custom_id` 衝突を生む状況を作らない前提で運用する。上書き側の実解像度を厳密に反映する必要が生じた場合は、呼び出し元が上書き解像度を渡す拡張で対応する(本 ADR の対応表構造はそのまま流用できる)。
- **レガシー JSONL 取り込み(`BatchImportService`)の制限**: 通常の投入・取り込み経路では `raw_request` の `lorairo_image_ids` 対応表を用いて全画像へ展開するが、外部生成 JSONL を取り込むレガシー経路には対応表が存在しない。同一(pHash、長辺)が複数レコードに重複登録されている場合、`BatchImageMatcher` は代表(昇順先頭)の 1 件を `matched` に返し、重複群は取りこぼし情報として `ImageMatchResult.ambiguous` に保持する。レガシー経路でも全重複へ反映する必要が生じた場合は、`BatchImportService` が `ambiguous` を消費して展開する拡張で対応する。

## Related

- Issue #629
- ADR 0038(Provider Batch Job Lifecycle)
- ADR 0044(Provider Batch Submit Threading)
