---
type: ADR
title: タグ欄の TagPanelWidget 切り出しと soft-reject 一本のタグ操作モデル
status: Accepted
timestamp: 2026-06-30
tags: [gui, qt-free-widget, tag-panel, soft-reject, signal-dispatch, tagdb, annotation-display]
---
# ADR 0083: タグ欄の TagPanelWidget 切り出しと soft-reject 一本のタグ操作モデル

- **関連 Issue**: #983 (タグパネル分離とタグ操作責務整理), #978 (refinement ignore の保存先 DB 整合性), #931 (refinement recommendation / ignore), #814 (タグ chip 選択 / コピー)
- **関連 ADR**: 0065 (タグ/キャプション soft-reject), 0068 (タグ正規化の tagdb 委譲), 0080 (エクスポート前タグ編集の2層オーバーレイ), 0009 (Qt Decoupling Design)
- **設計プロト**: Claude Design `LoRAIro-01` プロジェクト `Tag Panel Widget (983).html`

## Context

Search / Export の画像詳細では `AnnotationDataDisplayWidget`（`src/lorairo/gui/widgets/annotation_data_display_widget.py`）が、Caption / Score / Rating と並んで「タグ欄」も担っている。タグ欄の責務はキャプション・スコア・レーティングに比べて突出して大きい:

- chip 表示（FlowLayout）/ 言語切替・翻訳表示 / chip 選択・コピー（#814）
- この画像での soft-reject（無効化）/ 復活 / 手動タグ追加
- refinement 警告表示と ignore（#931 / #978）
- 今後追加したい: 翻訳追加 / タグ種別補正 / サイト別使用頻度表示

このまま `AnnotationDataDisplayWidget` にタグ機能を足し続けると、タグ固有の複雑さがキャプション・スコア・レーティングへ波及する。一方 UX としては、ユーザーに「この画像についたタグの編集」と「タグ情報そのものの編集」の保存先差分を強く意識させたくない。

加えて、#983 検討中に現状実装の事実が確定した:

- chip ✕ ボタンは `tag_reject_requested` → `ImageDatabaseManager.soft_reject_tag()` → `tags.rejected_at` を立てるだけで、**画像 DB から行は消えない**（表示から外れるが復活可能）。ハード削除（行の物理削除）はどこにも実装されていない。
- chip 本体クリックは現状「選択（コピー用、#814）」。
- プロトの「クリック=無効化 / ✕=削除」という2操作モデルは、この現状（✕=soft-reject、クリック=選択）と食い違う。

## Decision

### 1. タグ欄を DB 非依存の `TagPanelWidget` へ切り出す

`AnnotationDataDisplayWidget` からタグ欄を独立ウィジェット `TagPanelWidget` に切り出す。責務境界（#983 §4）:

```
TagPanelWidget（新規）
  - DB を知らない / service_container を知らない
  - 表示状態（tags, lang, metric, density）とユーザー操作だけを持つ
  - 操作要求は Signal で親へ出すだけ

SelectedImageDetailsWidget（親 / 既存）
  - current_image_id を持つ
  - 注入された db_manager / refinement_service / merged_reader を持つ
  - TagPanelWidget の Signal を受けて保存先へ dispatch する
```

ウィジェットを DB / service_container から切り離すことで、#978 で問題化した「保存先の混線」を構造的に防ぐ（注入は親に集約）。これは ADR 0009 の Qt-Free Core / GUI 分離方針の延長で、タグ chip 表示と言語切替は一体で扱う（言語切替が chip の表示名を直接決めるため、分離すると `canonical / display_text / translation` の同期が複雑になる）。

`TagPanelWidget` は Search / Export の画像詳細（`SelectedImageDetailsWidget`）で共用する。さらに、操作が重なる範囲では **export staging の `StagingTagPanel`（ADR 0080）でも同じウィジェットを再利用する**ことを前提に設計する（同じ動作なら同じ部品）。重複範囲と ADR 0080 の出力オーバーレイ層との整合は #987 で確認する。`TagPanelWidget` が Signal だけを出す純表示ウィジェットであることが、この再利用を可能にする。

### 2. signal は image DB 系 / tagdb userdb 系で分離し、現状名を踏襲する

保存先の意味が混ざらないよう Signal を2系統に分ける。#983 §4 の signal 名は提案だが、churn を避けるため**現状の `*_requested` 系を踏襲**する。

```python
# image DB 系（current_image_id 必須）
# 単一操作は Issue #1003 で無効化 / 除外を名前で分離する（受け手の reason 文字列分岐を排除）。
tag_disable_requested = Signal(str)        # canonical — 無効化（reason='not_needed'、破線で残す）
tag_exclude_requested = Signal(str)        # canonical — 除外（reason='incorrect'、非表示）
tag_restore_requested = Signal(str)        # canonical — 復活
tag_add_requested     = Signal(str)        # 生入力（日本語可）— 親が canonical 解決
# 複数選択のバッチ操作（#997）。reload を1回に抑えるため list をまとめて渡す（Codex #1001 P2）。
tags_exclude_requested = Signal(list)               # canonicals — まとめて除外（incorrect）
tags_toggle_requested  = Signal(list, list)         # (to_disable, to_restore) 無効化側は not_needed

# tagdb userdb 系（canonical が主キー / 画像 ID 不要）
refinement_ignored          = Signal(str, str)        # canonical, reason_code（既存）
translation_add_requested   = Signal(str, str, str)   # canonical, language, translation（Phase 2）
tag_metadata_edit_requested = Signal(str, str)        # canonical, type（Phase 2）
```

> **改訂（Issue #1003）**: 旧 `tag_reject_requested(str)` / `tags_reject_requested(list)`
> （無効化・✕ 共通の soft-reject）は上記へ置き換えた。無効化と除外は DB 上の意味と表示種別が
> 異なる（`reject_reason` = `not_needed` / `incorrect`）ため Signal 名で意図を明示し、親
> （`SelectedImageDetailsWidget`）が `soft_reject_tag(..., reason=...)` へ dispatch する。
> `replaced` は chip 操作ではなくバッチ置換機能（`replace_tag_for_images_batch`）が設定する。

UI 文言には「image DB」「tagdb userdb」を出さない。保存先は色レイヤー（image DB 系 = 青 `--info` /「この画像」、tagdb userdb 系 = ティール `--udb` /「タグ情報」）と自然な日本語で示す。

### 3. タグ操作モデルは soft-reject 一本（ハード削除なし・2提示）

タグの是正は soft-reject（`rejected_at`、ADR 0065）一本。**ハード削除（行の物理削除）と `tag_deleted` signal は導入しない**。データ保全・復活可能性を優先する。

soft-rejected には**複数の種別**を持つ。いずれも `rejected_at` をセットし DB 行は残す。種別は
`reject_reason` 列（ADR 0065 改訂 / Issue #1003）で**永続化**し、表示（残す／非表示）を分ける:

| 操作 | `rejected_at` | `reject_reason` | 提示 | 復活 |
|---|---|---|---|---|
| **無効化**（chip 単クリック） | セット | `not_needed` | 破線 chip でインライン表示を継続 | chip 再クリックでトグル復活 |
| **除外**（✕ ボタン） | セット | `incorrect` | パネルから非表示 | **なし**（間違い＝消す。戻す UI は作らない） |
| **置換済み**（バッチ置換） | セット | `replaced` | 非表示 | **なし**（置換先へ移行済み） |

chip 操作割当（プロト準拠・現状の #814 と両立）:

- 単クリック = 無効化⇄復活トグル（破線インライン、`tag_disable_requested` / `tag_restore_requested`）
- ✕ = この画像から除外（非表示、`tag_exclude_requested`）
- Ctrl+クリック = コピー選択（#814）
- ⋯ ボタン（inline）/ 右クリック = タグ情報メニュー（翻訳追加 / タグ情報を編集 / 使用頻度を見る / 警告を無視）

別枠「復活」セクションは作らない（インライン破線のクリック復活で代替し、除外／置換の復活は作らない）。
**表示種別（無効化 = 破線 / 除外・置換 = 非表示）はメモリ状態ではなく DB の `reject_reason` から
reload ごとに再構築する**（Issue #1003）。これにより別画像へ往復してもメモリ state に依存せず表示が
正しく戻り、「無効化したのに✕のように消える」回帰が構造的に解消する。`reject_reason` はエクスポート
抽出（`rejected_at IS NULL`）には影響しない。

> **スコープ外（別 Phase に後送り）**: ① 複数選択のバッチ操作バー（まとめて外す/無効化/復活）— 選択は当面コピー(#814)のみ。② refinement 警告の「修正候補を適用（タグ置換、`refine.suggest`）」— 当面 ignore のみ。③ ✕ で隠したタグの復活 UI。

### 4. 手動タグ追加は親で canonical 解決（日本語入力に対応）

`AddTagRow` は日本語入力も受ける。`TagPanelWidget` は生入力のまま `tag_add_requested(raw_input)` を出し、**親が canonical 解決を担う**:

```
tag_add_requested(raw_input)
  → 親が search_tags(query=raw_input, partial=False, resolve_preferred=True)
      ├─ TAG_TRANSLATIONS 一致 → canonical を取得 → add_manual_tag(canonical)
      └─ 未ヒット → 入力をそのまま add_manual_tag(raw_input)
           （register_tag: format=Lorairo, type=unknown, source_tag=raw_input）
```

tag DB の翻訳テーブル経由で日本語→ canonical を解決し、未解決の日本語は**そのまま登録**（`source_tag` 保持）。任意の未登録日本語を機械翻訳で英語 canonical へ変換する機能は genai-tag-db-tools 公開 API では不可のため**対象外**（必要なら別 ADR / 別 Issue）。オートコンプリート候補は `search_tags(partial=True)`（既存 `tag_suggestion_service`）で日本語・英語両対応。

### 5. 段階移行

- **Phase 1**: `TagPanelWidget` 切り出し（既存機能の移植）＋ 日本語タグ追加の canonical 解決。`AnnotationDataDisplayWidget` をタグ欄委譲の薄い親へ。
- **Phase 2**: tagdb userdb 系の書き込み — 翻訳追加（`translation_add_requested` → `UserTagRepository.write_translation_patch()`）/ type 補正（`tag_metadata_edit_requested` → `update_tags_type_batch()`）。
- **Phase 3**: 使用頻度の第2軸（`metric_source`: なし / Danbooru / e621 / Gelbooru count、`TagReader.get_usage_count()` 経由）。表示言語とは完全に別軸。

各 Phase はサブ Issue 化を検討する。

## Consequences

**Positive**

- タグ固有の複雑さが Caption / Score / Rating に波及しない。`TagPanelWidget` は DB / service を注入せず生成でき、Signal 発火の単体テストが容易。
- 保存先（image DB 系 / tagdb userdb 系）の混線を、ウィジェットの DB 非依存＋親 dispatch という構造で防ぐ（#978 整合）。
- soft-reject 一本によりデータが失われず、誤操作も復活で回復できる。プロトと現状の操作モデル食い違いを最小の再整合で解消。

**Negative / Trade-off**

- soft-reject に「破線で残す（無効化）」「非表示にする（除外）」の複数提示を持たせるため、`rejected_at` に加えた表示状態の区別が必要になる。当初は `TagPanelWidget` のメモリ状態（`_disabled_display` / `_hidden`）だけで区別していたが、別画像往復でメモリ state が失われ「無効化が✕のように消える」回帰が発生した。**Issue #1003 で `reject_reason` 列（`not_needed` / `incorrect` / `replaced`）へ永続化し、reload ごとに DB から表示種別を再構築する形で解消**。✕ で除外／置換したタグの復活 UI は引き続き作らない（間違い＝消す・置換＝移行済みのため）。
- chip 単クリックを無効化トグルに割り当てたため、コピー選択（#814）は Ctrl+クリックへ退避する（単クリック選択からの操作変更）。
- 使用頻度の第2軸・翻訳追加・type 補正・バッチ操作・refinement 修正候補適用は Phase 2 以降に後送りで、Phase 1 単体では既存機能の移植にとどまる。
- 未登録日本語の canonical 解決ができないため、翻訳 DB に無い日本語は `source_tag` のまま残り、後続で翻訳追加（Phase 2）を要する。

## Related

- ADR 0065 — タグ/キャプション soft-reject（タグ操作モデルの基盤。`reject_reason` 改訂 = Issue #1003）
- ADR 0068 — タグ正規化の tagdb 委譲（canonical 解決の意味）
- ADR 0080 — エクスポート前タグ編集の2層オーバーレイ（DB編集層 = 本 ADR の soft-reject を再利用）
- ADR 0009 — Qt Decoupling Design（DB 非依存ウィジェットの方針）
- Issue #983 — 本 ADR の実装仕様（Phase 別 plan・テスト観点を含む）
