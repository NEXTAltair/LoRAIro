# deepghs/site_tags: Tag Type/Category Number Mappings

策定日: 2025年12月18日

目的: TAG_TYPE_FORMAT_MAPPING への投入に必要な、各サイトのカテゴリID（整数）とカテゴリタイプ（意味）の対応を確定する。

---

## Danbooru系（danbooru.donmai.us / safebooru.donmai.us / booru.allthefallen.moe）

```
0 = General
1 = Artist
3 = Copyright
4 = Character
5 = Meta
```

**注意**:
- category 2 は未使用（欠番）
- 6以上は invalid region

**出典**: [Danbooru Tag System](https://deepwiki.com/danbooru/danbooru/4.1-tag-system), [Danbooru2021 Dataset](https://gwern.net/danbooru2021), [danbooru/tag.rb](https://github.com/danbooru/danbooru/blob/master/app/models/tag.rb)

---

## e621.net

```
0 = General
1 = Artist
3 = Copyright
4 = Character
5 = Species
6 = Meta
7 = Invalid
8 = Lore
```

**注意**:
- category 2 は未使用（欠番）
- species (5) が e621 固有の追加カテゴリ
- lore (8) は新しいカテゴリ（canonical gender identities等）

**出典**: [e621 API Documentation](https://e621.wiki/), [E621-Tag-Categories](https://github.com/Sasquire/E621-Tag-Categories), [e621 lore category support](https://github.com/Bionus/imgbrd-grabber/issues/3059)

---

## Moebooru系（yande.re）

```
0 = General
1 = Artist
3 = Copyright
4 = Character
5 = Copyright (circle)
6 = Metadata
```

**出典**: [ahoviewer/site.cc](https://github.com/ahodesuka/ahoviewer/blob/master/src/booru/site.cc)

---

## Moebooru系（konachan.com / konachan.net）

```
0 = General
1 = Artist
3 = Copyright
4 = Character
5 = Metadata
6 = Copyright (circle)
```

**注意**:
- konachan は yande.re と type 5/6 が逆転

**出典**: [ahoviewer/site.cc](https://github.com/ahodesuka/ahoviewer/blob/master/src/booru/site.cc)

---

## Moebooru系（その他: rule34.xxx / xbooru.com / hypnohub.net）

```
0 = General
1 = Artist
3 = Copyright
4 = Character
5 = Metadata
```

**推定**: konachan系と同じ（type 6 は未使用の可能性）

---

## Gelbooru

**文字列カテゴリ（type列は文字列）**:
- `general`
- `artist`
- `copyright`
- `character`
- `metadata`

**注意**:
- gelbooru は整数型ではなく文字列型でカテゴリを表現
- TAG_TYPE_FORMAT_MAPPING への投入時は文字列→整数への変換が必要

**出典**: [Gelbooru Guide](https://www.bonjouridee.com/en/gelbooru-guide-how-it-works-tagging-system-safety/), [What Are Booru Tags](https://apatero.com/blog/what-are-booru-tags-complete-guide-2025)

---

## anime-pictures.net

**実データ観察からの推定**:
```
0 = Meta/System (例: tagme, private)
1 = Character
2 = General (記述語が多い)
3 = Copyright/Series
4 = Artist
5 = Franchise (大規模フランチャイズ/ゲーム/作品群)
6 = Studio/Company (制作会社/領域)
7 = Unknown (要追加調査)
```

**注意**:
- type 5/6 は実データ観察からの推定（要検証）
- type 7 の意味は未確定

**出典**: [deepghs/site_tags dataset](https://huggingface.co/datasets/deepghs/site_tags)

---

## Sankaku Complex (chan.sankakucomplex.com)

**文字列カテゴリ（type列は整数だが詳細不明）**:
- `artist` (red)
- `character` (green)
- `copyright` (purple)
- `general` (blue)
- `meta` (orange)

**追加カテゴリ**:
- `studio`
- `genre`
- `medium`

**注意**:
- 整数型のtype値とカテゴリ名の対応は未確定
- gallery-dlでは tags_artist, tags_character, tags_copyright, tags_studio, tags_general, tags_genre, tags_medium, tags_meta に分割

**出典**: [Sankaku tag categories](https://zerex290.github.io/sankaku/clients/tag-client/), [gallery-dl sankaku extractor](https://github.com/mikf/gallery-dl/issues/2106)

---

## その他サイト（未調査）

### lolibooru.moe
- moebooru系と同じ可能性（要検証）
- `tag_type` 列が存在

### wallhaven.cc
- `category_id` / `category_name` の組み合わせ
- 整数型と文字列型のペア

### zerochan.net
- 文字列カテゴリ（`type` 列）
- 例: `mangaka`, `character`, `series`, `theme`, `game`
- カンマ区切りで複数カテゴリ（例: `game,theme`）

### pixiv.net / en.pixiv.net
- boolean flags による複数カテゴリ
- `is_anime`, `is_manga` 等
- 単一整数型への変換は非自明

---

## TAG_TYPE_FORMAT_MAPPING への投入方針

### 直接マッピング可能（整数型 → 整数型）

- Danbooru系: 0→General, 1→Artist, 3→Copyright, 4→Character, 5→Meta
- e621: 0→General, 1→Artist, 3→Copyright, 4→Character, 5→Species, 6→Meta, 8→Lore
- Moebooru系: サイトごとに type 5/6 が異なるので注意
- anime-pictures: 推定値を使用（要検証）

### 変換が必要（文字列型 → 整数型）

- Gelbooru: 文字列→整数への変換テーブル作成
- Sankaku: 文字列→整数への変換テーブル作成（または文字列のまま）
- zerochan: 文字列→整数への変換テーブル作成

### 複雑な変換（要設計検討）

- pixiv: boolean flags → 単一整数型への変換ロジック
- zerochan: 複数カテゴリ（カンマ区切り）の扱い

---

## 実装時の注意点

1. **format別のマッピング**:
   - TAG_TYPE_FORMAT_MAPPING は format_id ごとに異なるマッピングを持つ
   - 同じ整数値でもformatによって意味が異なる（例: moebooru系の type 5/6）

2. **欠番への対応**:
   - category 2 は多くのサイトで欠番
   - 存在しない type 値は無視するか、警告を出す

3. **文字列型の扱い**:
   - Gelbooru/Sankaku等は文字列カテゴリ
   - TAG_TYPE_NAME.type_name との対応付けが必要

4. **複数カテゴリの扱い**:
   - zerochan/pixiv等は1タグに複数カテゴリ
   - 現行DBは単一type運用なので、優先順位ルールが必要

5. **未確定値の扱い**:
   - anime-pictures type 5/6/7
   - Sankaku の整数型マッピング
   - これらは実装時に実データ検証が必要

---

## 次のアクション

1. **Week 2-3 で実データ検証**:
   - anime-pictures type 5/6/7 の意味確定
   - Sankaku の整数型マッピング確定
   - lolibooru の type 値確認

2. **TAG_TYPE_NAME への標準カテゴリ追加**:
   - Species (e621固有)
   - Lore (e621固有)
   - Studio/Genre/Medium (Sankaku固有)
   - Franchise/Company (anime-pictures推定)

3. **変換テーブル実装**:
   - 文字列→整数型変換（Gelbooru/Sankaku/zerochan）
   - format別マッピングテーブル（TAG_TYPE_FORMAT_MAPPING）

---

**策定者**: Claude Sonnet 4.5  
**情報源**: Web検索結果（2025年12月18日）
