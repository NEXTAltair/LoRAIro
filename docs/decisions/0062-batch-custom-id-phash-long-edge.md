# ADR 0062: Provider Batch custom_id を pHash + 長辺解像度基準へ統一

- **日付**: 2026-06-05
- **ステータス**: Accepted
- **関連 Issue**: #629 (本 ADR)
- **関連 ADR**: 0038 (Provider Batch Job Lifecycle), 0044 (Provider Batch Submit Threading)

## Context

ADR 0038 で導入した Provider Batch (OpenAI / Anthropic / Google) では、各リクエストを
batch 内で一意に突合するため `custom_id` を付与する。OpenAI Batch API は出力順を入力順と
一致させない契約のため、結果は `custom_id` で突合する必要がある。

従来の `custom_id` は画像レコード ID 直結 (`img-{image_id}`) だった。しかし以下の課題がある。

1. **画像 ID は素材実体を表さない**
   同じ画像 (同一 pixel) が解像度違いで複数レコードとして登録され得る。逆に、別レコードでも
   素材としては同一なことがある。バッチ投入の dedupe と結果突合は、レコード ID よりも
   「アノテーション対象素材の実体」に寄せたほうが意味がある。

2. **同一素材の重複投入を防げない**
   同じ batch に同じ素材を複数投入しても課金が無駄に増えるだけで意味がない。レコード ID 基準
   では「同一素材か」を判定できず、重複投入を avoid する単位が存在しない。

3. **解像度差を区別する必要がある**
   一方で、同じ柄でもアノテーションに使う素材の長辺解像度が異なる場合は、別の入力画像として
   別リクエストにしたい (低解像度と高解像度で推論結果が変わり得る)。

## Decision

`custom_id` を **pHash とアノテーション対象素材の長辺解像度の組み合わせ**で生成する。

```
custom_id = ph:{phash_hex}:le:{long_edge_px}
```

### 1. なぜ画像 ID ではなく pHash か

pHash (知覚ハッシュ) は素材の見た目に基づく指紋であり、レコード ID と違って「素材実体」に
寄せた突合キーになる。LoRAIro では `Image.phash` が NOT NULL 制約で登録時に必ず計算される
ため、追加コストなく取得できる。

### 2. なぜ pHash 単独でなく長辺解像度も含めるか

同じ柄でも、アノテーションに渡す素材の長辺解像度が異なれば別リクエストとして扱いたい
(解像度で推論結果が変わるため)。pHash 単独だと解像度違いが同一キーに潰れてしまう。
長辺解像度 (`max(width, height)`) をキーに含めることで、「同一柄・同一解像度」のみを
同一リクエストに統合し、解像度差は別リクエストに分離できる。長辺のみを使うのは、アスペクト比が
保たれる前提では長辺が解像度の代表値になるためで、custom_id を短く保つ意図もある
(OpenAI custom_id は <=64 文字制約)。

### 3. pHash は完全一致キーであり、知覚ハッシュであること

本 ADR の実装は **pHash の完全一致**を突合キーとして使う。pHash は知覚ハッシュであり、
わずかに異なる画像が同一ハッシュになる (衝突)、または僅差で別ハッシュになる可能性がある。
本設計はこれを許容し、「完全一致した pHash + 同一長辺」を同一素材とみなす単純な規約とする。
近似 pHash (ハミング距離による近傍判定) は導入しない。これは Issue #630 の方針とも整合する。

### 4. 同一 batch 内の重複投入禁止と dedupe

同一 `custom_id` (= 同一 pHash + 同一長辺) の素材は、batch 内で 1 リクエストに dedupe する。
`ProviderBatchJobService._validate_submit_request` は同一 `custom_id` の重複投入を
`InvalidProviderBatchRequest` で拒否する。dedupe は submit request 構築側
(`ProviderBatchWorkflowService.build_submit_request`) が行い、代表 `image_id` (最初に出現した
レコード) を DB item に保存する。

### 5. `custom_id -> image_id[]` 対応表が必要なこと

dedupe で複数の `image_id` が 1 リクエストに統合されるため、結果取り込み時に統合された
**全 `image_id`** へ annotation を反映する必要がある。`provider_batch_items` は
`UniqueConstraint(job_id, custom_id)` を持ち item ごとに単一 `image_id` 列のため、統合された
重複 `image_id` 群は DB item の `raw_request` (LoRAIro local payload; image-annotator-lib へは
渡されない) に `{"lorairo_image_ids": [...]}` として保持する。import 時はこれを読み戻し、
1 つの result annotation を統合元の全 `image_id` へ fan-out する。`raw_request` が欠落する旧
フォーマット job では代表 `image_id` のみへ反映する (後方互換)。

### 6. 近似 pHash を導入する場合の代表 pHash の扱い

将来、近似 pHash (近傍クラスタリング) を導入する場合は、クラスタの代表 pHash を 1 つ選び、
その代表値で `custom_id` を生成し、クラスタ内の全 `image_id` を上記対応表に含める。本 ADR の
`custom_id -> image_id[]` 対応表はこの拡張を素直に受け入れられる構造になっている。ただし
現時点では近似は採用せず、完全一致のみを実装する。

## Consequences

- **利点**
  - 同一素材の重複投入を構造的に避けられ、無駄な API 課金を抑制する。
  - 解像度差を別リクエストとして正しく区別できる。
  - `custom_id` から素材実体 (pHash + 長辺) を直接読み戻せる (`parse_custom_id`)。
  - スキーマ変更なしで実現でき、既存 `provider_batch_items` テーブルをそのまま使える。

- **代償 / 留意点**
  - pHash 衝突時、本来別素材を同一リクエストに統合する可能性がある (完全一致前提のトレード
    オフ)。実運用上は許容範囲とみなす。
  - 対応表を `raw_request` (Text) に埋め込むため、image-annotator-lib 側の
    `BatchSubmitItem` がこのキーを provider へ転送しないことが前提となる
    (現状 `BatchSubmitItem` は `custom_id` / `image_id` / `image_path` のみで、
    `raw_request` は LoRAIro 側 compat layer で除外される)。
  - 旧フォーマット (`img-{image_id}`) で投入済みの job との後方互換は、import 時に代表
    `image_id` のみへ反映する fallback で担保する。

## Related

- Issue #629
- ADR 0038 (Provider Batch Job Lifecycle)
- ADR 0044 (Provider Batch Submit Threading)
