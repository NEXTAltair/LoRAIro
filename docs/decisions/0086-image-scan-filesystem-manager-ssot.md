---
type: ADR
title: 画像登録スキャンを FileSystemManager に集約
status: Accepted
timestamp: 2026-07-07
tags: [cli, public-api, image-registration, filesystem]
---
# ADR 0086: 画像登録スキャンを FileSystemManager に集約

- **関連 Issue**: #1267
- **関連 ADR**: 0061(登録パイプライン再設計)

## Context

`lorairo-cli images register <path> --project <name>` は、`ImageRegistrationService` 内の独自実装によりディレクトリ直下のみを走査していた。一方、GUI のディレクトリ登録は `FileSystemManager.get_image_files()` を使用し、サブディレクトリを再帰的に走査する。

同じ「ディレクトリからの画像登録」でありながら CLI・公開 API と GUI で挙動が食い違い、サブフォルダで整理されたデータセットが警告なしに取り込み漏れになっていた。さらに、対応拡張子の定義も二重化しており、GUI 側は `.tif` と `.tiff` を含む一方で、CLI・公開 API 側は含まない状態だった。

## Decision

画像登録系サービスにおけるディレクトリ走査と対応拡張子の判定は、`FileSystemManager` を正準(SSoT)とする。

- `ImageRegistrationService.get_image_files()` はディレクトリ入力時に `FileSystemManager.get_image_files()` へ委譲し、サービス API としての戻り値のみソートして返す。
- 単一ファイル入力時の拡張子判定も、`FileSystemManager.image_extensions` 由来の小文字集合で行う。
- `detect_duplicate_images()` も同じ公開メソッド `get_image_files()` を使用し、登録処理と重複検出の対象集合を一致させる。
- `project_dir` を指定した直接コピー経路では、ディレクトリ入力時に `source` からの相対パスを保持したまま `image_dataset/original_images/` へコピーする。

## Rationale

`directory.glob()` を `directory.rglob()` へ置き換えるだけでは、拡張子リストの二重管理が残ってしまう。画像走査の責務はすでに GUI 経路で `FileSystemManager` が担っており、CLI や公開 API だけが別実装を持つ理由はない。

既存の Qt 非依存サービスもすでに `FileSystemManager.get_image_info()` を利用しているため、同クラスの静的ファイルシステムヘルパーへ依存を集約しても、新しい層間の依存は増えない。

## Consequences

- CLI、公開 API、および重複検出は、親ディレクトリを指定した際にサブディレクトリ内の画像も対象とする。
- `.tif` と `.tiff` が、GUI と同様に CLI および公開 API でも画像ファイルとして扱われる。
- サブディレクトリごとに同名ファイルが存在する直接コピー経路でも、一方のファイルが黙って上書き・欠落する事態を防げる。
- 今後、対応拡張子を変更する場合は `FileSystemManager.image_extensions` を更新し、登録サービス側へ重複定義を戻さない。
