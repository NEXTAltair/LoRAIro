# ADR 0063: CLI Batch Submit Image IDs CSV Contract

- **日付**: 2026-06-07
- **ステータス**: Accepted
- **関連 Issue**: #671
- **関連 ADR**: [0057](0057-cli-jsonl-output-and-error-contract.md), [0059](0059-cli-command-introspection.md), [0060](0060-cli-bounded-pagination-contract.md)

## Context

`lorairo-cli batch submit` は対象画像を repeatable な `--image-id` で受け取っていた。
この形は少数の手入力では動くが、`images list --fetch` で得た ID 集合を後続の batch submit
に渡す導線では冗長になる。CLI の利用者は ID 集合を「リスト」として扱いたい一方、引数ごとに
同じ option 名を繰り返す契約はその意図とずれる。

## Decision

`batch submit` の画像 ID 指定は、単一 option のカンマ区切り CSV に統一する。

```bash
lorairo-cli batch submit \
  --project main_dataset \
  --model openai/omni-moderation-latest \
  --task-type rating_preflight \
  --image-ids 2,7,11
```

旧 `--image-id` repeatable option は authoritative な経路ではなくなり、CLI help、
introspection、docs から削除する。command 層は `--image-ids` を `list[int]` に正規化し、
既存の `ProviderBatchWorkflowService.submit_images(image_ids=...)` へ渡す。

## Rationale

`batch submit` の責務は「対象画像集合を provider batch に投入する」ことであり、サービス層の
canonical input は今後も `list[int]` のままでよい。変更すべきなのは CLI の入力表面である。
互換追加として `--image-id` と `--image-ids` を併存させると、help / introspection / docs の
導線が二重化し、利用者がどちらを使うべきか迷う。Issue #671 では導線を単純にするため、
CSV の単一路線へ寄せる。

## Consequences

- `batch submit` 利用者は `--image-ids 2,7,11` を使う。
- 旧 `--image-id` を使う既存スクリプトは更新が必要。
- introspection の `BatchSubmitInput` は `image_ids: csv[int]` を公開する。
- `images list --fetch` の `image_id` 出力は、後段で CSV 化して `--image-ids` に渡す ID 集合として扱う。
