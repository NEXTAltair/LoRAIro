---
type: ADR
title: CLI Batch Submit Image IDs CSV Contract
status: Accepted
timestamp: 2026-06-07
tags: []
---
# ADR 0063: CLI Batch Submit Image IDs CSV Contract

- **関連 Issue**: #671
- **関連 ADR**: [0057](0057-cli-jsonl-output-and-error-contract.md)、[0059](0059-cli-command-introspection.md)、[0060](0060-cli-bounded-pagination-contract.md)

## Context

従来の `lorairo-cli batch submit` は、対象画像を繰り返し指定可能な `--image-id` オプションで受け取っていた。少数の手入力であれば問題ないが、`images list --fetch` で得た ID 集合を後続の `batch submit` に渡す導線では記述が冗長になる。

CLI 利用者は ID 集合を 1 つのリストとして扱いたい。一方で、引数ごとに同じオプション名を繰り返す契約はその意図と噛み合っていない。

## Decision

`batch submit` の画像 ID 指定は、単一オプションのカンマ区切り CSV に統一する。

```bash
lorairo-cli batch submit \
  --project main_dataset \
  --model openai/omni-moderation-latest \
  --task-type rating_preflight \
  --image-ids 2,7,11
```

旧 `--image-id` 繰り返しオプションは正式な経路から廃止し、CLI のヘルプ、introspection、ドキュメントから削除する。コマンド層は `--image-ids` を `list[int]` に正規化し、既存の `ProviderBatchWorkflowService.submit_images(image_ids=...)` へ渡す。

## Rationale

`batch submit` の責務は、対象画像集合をプロバイダバッチへ投入することである。サービス層の正準入力は今後も `list[int]` のままでよく、変更すべきなのは CLI の入力インターフェースだけである。

互換性のために `--image-id` と `--image-ids` を併存させると、ヘルプ・introspection・ドキュメントの導線が二重化し、利用者がどちらを使うべきか迷う原因になる。Issue #671 では導線を単純に保つため、CSV 形式の単一路線へ統一する。

## Consequences

- `batch submit` の利用者は `--image-ids 2,7,11` を使用する。
- 旧 `--image-id` を使っている既存スクリプトは更新が必要になる。
- introspection の `BatchSubmitInput` は `image_ids: csv[int]` を公開する。
- `images list --fetch` の `image_id` 出力は、後段で CSV 化して `--image-ids` に渡す ID 集合として扱う。
