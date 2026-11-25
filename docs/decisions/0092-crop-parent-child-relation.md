---
type: ADR
title: クロップ画像の親子関係を専用テーブル crop_relations で保持する
status: Accepted
timestamp: 2026-09-07
tags: [database, schema, migration, crop, repository]
---
# ADR 0092: クロップ画像の親子関係を専用テーブル crop_relations で保持する

- **関連 Issue**: #1339(画像クロップ機能)、#1343(親子関係テーブルとマイグレーション)、#1344、#1345、#1346、#1340(物体検出によるクロップ矩形供給)
- **関連 ADR**: 0035(Aggregate 単位 Repository)、0061(画像登録の統一エントリと pHash 分類)、0083(タグ欄の TagPanelWidget 切り出し)

## Context

Issue #1339 では、画像の一部を切り出して新しい画像として扱う機能を求めている。データ層に求められる要件は以下の 3 点である。

1. 切り出した画像が「どの画像のどの矩形から作られたか」(直接の親と切り出し位置)を保存できること。
2. 切り出した画像を通常の画像と同じ `images` テーブルへ独立した ID で登録すること。アノテーション・スコア・エクスポートといった既存機能をそのまま適用するため、専用の画像テーブルは作成しない。
3. 子画像を親としてさらに切り出す再クロップを許容すること。なお、運用上は登録済み画像を削除しない前提で設計する。

一方、既存スキーマには同一画像の派生を表す `processed_images`(リサイズやアップスケールなどの加工画像)が存在する。しかし、`processed_images` は `images.id` に従属しており独立した画像 ID を持たない。クロップ画像はアノテーション対象として独立した画像であるため、`processed_images` とは責務が異なる。

## Decision

### 1. 専用の関係テーブル `crop_relations` を追加する

`crop_relations` には以下の列のみを持たせる。

| 列 | 内容 |
| --- | --- |
| `id` | 関係行の主キー(PK) |
| `parent_image_id` | 直接の親画像(`images.id`、`ON DELETE CASCADE`) |
| `child_image_id` | 子となるクロップ画像(`images.id`、`ON DELETE CASCADE`) |
| `x`、`y`、`width`、`height` | **直接の親画像基準**の切り出し矩形(px) |
| `origin` | 切り出し由来を示す文字列。既定値は `manual` |
| `created_at` | 作成時刻 |

制約として、1 つの子画像に 1 つの親のみを許す `UniqueConstraint("child_image_id")` と、親から子一覧を引くための `Index("ix_crop_relations_parent_image_id")` を設ける。

### 2. 直接の親だけを記録し、祖先は連鎖で表現する

親・子・孫という 3 世代の関係は、「親と子」「子と孫」の 2 行で表現する。祖先 ID や世代数は非正規化して保持しない。

座標も常に**直接の親基準**で保存し、祖先基準への変換が必要になった時点で連鎖を辿って計算する。この設計により、再クロップを特別扱いする必要がなくなり、親側の画像サイズ変更に伴う座標の意味の揺れも防げる。

### 3. 由来は文字列カラム `origin` で持つ

手動の矩形選択には `manual` を、将来の物体検出由来には検出器名などの文字列を格納する。文字列カラムにしておくことで、Issue #1340 の実装時に追加マイグレーションなしで由来を記録できる。

### 4. `processed_images` との整合性を保つ

- クロップ画像は独立した `images` 行として登録し、自身の `processed_images` 行を持つ。通常画像と同じ登録経路とリサイズ加工を通す。
- `processed_images` は「同一画像の加工版」、`crop_relations` は「別画像への切り出し」として責務を分離する。クロップの親子関係を `processed_images` へ混ぜない。
- 既存テーブルのカラムは削除も改名もしない。スキーマ変更は `crop_relations` の新規作成のみにとどめる。

### 5. 座標系は EXIF orientation 適用後の表示向きとする

`crop_relations` の `x`、`y`、`width`、`height` は、**EXIF orientation を適用した後(表示向き)のピクセル座標**で保存する。検証と切り出しは `ImageOps.exif_transpose` 後の画像に対して行い、GUI の矩形選択も同じ見え方(`QImageReader.setAutoTransform(True)`)を基準とする。

- `images.width` と `images.height` は登録時の**生ピクセル値**のままであり、この座標系とは別物である。EXIF orientation が 90 度系の画像では縦横が入れ替わるため、座標の検証や変換に `images.width` および `images.height` を使わない。
- 親画像の寸法は、ファイルの orientation タグから算出する(`crop_service._oriented_parent_size`)。
- `images.width` と `images.height` が生ピクセルを表すという仕様は変更しない。

### 6. アクセスは Repository 経由に統一する(ADR 0035)

`CropRelationRepository`(`add_relation`、`get_children`、`get_parent`)を追加する。`ImageDatabaseManager` は `crop_relation_repo` を依存性注入(DI)と既定生成の両方で保持する。

`add_relation` は子の二重登録や外部キー違反を `IntegrityError` としてそのまま伝播させ、保存されていないのに成功扱いとなる経路を作らない。

## Alternatives and rationale

- **`images` に `parent_id` 列を追加する案(却下)**: 座標 4 列と由来 1 列も `images` に載ることになり、大多数を占める非クロップ画像で常に NULL が並ぶ。`images` は登録・検索の中心テーブルで参照箇所が多いため、列追加の影響範囲が広すぎる。
- **`processed_images` を流用する案(却下)**: `processed_images` は独立した画像 ID を持たない従属行であり、「クロップ画像を通常画像として扱う」という要件と噛み合わない。加工版と切り出しの意味が混在し、既存のリサイズ取得クエリも壊れる。
- **汎用 `image_relations`(`relation_type` 列付き)を作る案(却下)**: 現時点で必要な関係はクロップ 1 種のみであり、汎用化すると座標列が他の関係種別で無意味になる。YAGNI の原則に従い、別種の関係が必要になった時点で専用テーブルを追加する方が低コストである。

## Consequences

- クロップ画像は既存のアノテーション・検索・エクスポート機能をそのまま利用できる。
- 親からの子一覧取得と子からの親取得はいずれも 1 クエリで完了し、再接続後も保持される。
- 祖先を辿るコストは世代数に比例する。実運用では世代が浅い想定のため許容し、深い連鎖の一括取得が必要になった段階で再帰 CTE や非正規化を別途検討する。
- 画像削除は運用上行わない前提だが、外部キーは `ON DELETE CASCADE` のため親削除時に関係行も削除される。切り出し出自を残す要件が生じた場合は別途退避機構を設計する(本 ADR の対象外)。

## #1340 向け拡張点

- **矩形供給元の差し替え点**: `CropCreateRequest`(`src/lorairo/domain/crop_request.py`)を受け取るサービス関数は、矩形の出所を知らない。GUI の矩形選択も物体検出も同じリクエスト型を組み立てて渡す構造のため、検出器を追加してもサービス層は変更不要である。
- **矩形の座標系**: 検出器が返す矩形も**表示向き(EXIF orientation 適用後)の座標**で `CropCreateRequest` へ渡す。検出器が生ピクセル基準の矩形を返す場合は、呼び出し側で変換してから渡す。
- **`origin` カラムの用途**: 手動選択は `manual`、検出器由来は検出器名などの文字列を入れる。由来別の絞り込みと表示はこの列だけで完結する。
- **検出モデル名と信頼度**: `crop_relations` には追加しない。検出実行のメタデータ(モデル名、信頼度、検出時刻など)は、将来別テーブルで `crop_relations.id` を参照して保持する。関係テーブルを検出器の都合で肥大化させない。
- **バッチ処理と部分失敗**: 1 枚の親画像から複数矩形をまとめて切り出す際の進捗管理や部分失敗の扱いは Issue #1340 で設計する。本 ADR のデータ層は 1 件ずつの登録のみを規定する。

## Related

- Issue: #1339, #1343, #1344, #1345, #1346, #1340
- ADR: 0035, 0061, 0083
