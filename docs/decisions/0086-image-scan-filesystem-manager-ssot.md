---
type: ADR
title: 画像登録スキャンを FileSystemManager に集約
status: Accepted
timestamp: 2026-07-07
tags: [cli, public-api, image-registration, filesystem]
---
# ADR 0086: 画像登録スキャンを FileSystemManager に集約

- **関連 Issue**: #1267
- **関連 ADR**: 0061 (登録パイプライン再設計)

## Context

`lorairo-cli images register <path> --project <name>` は `ImageRegistrationService` の独自実装で
ディレクトリ直下だけを走査していた。一方、GUI のディレクトリ登録は `FileSystemManager.get_image_files()`
を使い、サブディレクトリを再帰的に走査する。同じ「ディレクトリから画像登録」機能で CLI / public API と
GUI の挙動が分かれ、サブフォルダで整理されたデータセットが警告なしに取り込み漏れになっていた。

さらに拡張子定義も二重化しており、GUI 側は `.tif` / `.tiff` を含むが、CLI / public API 側は
含まない状態だった。

## Decision

画像登録系サービスのディレクトリ走査と対応拡張子判定は `FileSystemManager` を正準とする。

- `ImageRegistrationService.get_image_files()` はディレクトリ入力時に `FileSystemManager.get_image_files()`
  へ委譲し、戻り値だけ service API としてソートする。
- 単一ファイル入力の拡張子判定も `FileSystemManager.image_extensions` 由来の小文字集合で行う。
- `detect_duplicate_images()` も同じ公開 `get_image_files()` を使い、登録と重複検出の対象集合を一致させる。

## Rationale

`directory.glob()` を `directory.rglob()` に置き換えるだけでは、拡張子リストの二重管理が残る。
画像走査の責務は既に GUI 経路で `FileSystemManager` にあり、CLI / public API だけが別実装を持つ理由は
ない。既存の Qt 非依存サービスは `FileSystemManager.get_image_info()` も利用しているため、
同クラスの静的ファイルシステム helper へ依存を寄せても新しい層依存は増えない。

## Consequences

- CLI / public API / duplicate detection は親ディレクトリ指定でサブディレクトリ内の画像も対象にする。
- `.tif` / `.tiff` は GUI と同じく CLI / public API でも画像として扱われる。
- 今後、対応拡張子を変更する場合は `FileSystemManager.image_extensions` を更新し、登録サービス側へ
  重複定義を戻さない。
