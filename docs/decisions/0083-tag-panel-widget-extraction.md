---
type: ADR
title: タグ欄の TagPanelWidget 切り出しと soft-reject 一本のタグ操作モデル
status: Accepted
timestamp: 2026-06-30
tags: [gui, qt-free-widget, tag-panel, soft-reject, signal-dispatch, tagdb, annotation-display]
---
# ADR 0083: タグ欄の TagPanelWidget 切り出しと soft-reject 一本のタグ操作モデル

- **関連 Issue**: #983(タグパネル分離とタグ操作責務の整理)、#978(refinement ignore の保存先 DB 整合性)、#931(refinement の推奨と ignore)、#814(タグチップ選択とコピー)
- **関連 ADR**: 0065(タグ・キャプションの soft-reject)、0068(タグ正規化の tagdb 委譲)、0080(エクスポート前タグ編集の 2 層オーバーレイ)、0009(Qt Decoupling Design)
- **設計プロトタイプ**: Claude Design `LoRAIro-01` プロジェクト `Tag Panel Widget (983).html`

## Context

Search および Export の画像詳細画面では、`AnnotationDataDisplayWidget`(`src/lorairo/gui/widgets/annotation_data_display_widget.py`)が Caption、Score、Rating と並んで「タグ欄」も担当している。しかし、タグ欄の責務は他の項目と比べて突出して大きい。

- チップ表示(FlowLayout)、言語切替・翻訳表示、チップ選択・コピー(#814)
- 対象画像での soft-reject(無効化)、復活、手動タグ追加
- refinement 警告の表示と無視(#931、#978)
- 今後の追加予定機能: 翻訳追加、タグ種別補正、サイト別使用頻度の表示

このまま `AnnotationDataDisplayWidget` へタグ機能を追加し続けると、タグ固有の複雑さがキャプション、スコア、レーティングへ波及する。一方で UX の観点では、「この画像に付いたタグの編集」と「タグ情報そのものの編集」の保存先の違いを、ユーザーへ強く意識させたくない。

加えて、#983 の検討過程で現行実装について次の事実が確定した。

- チップの ✕ ボタンは `tag_reject_requested` から `ImageDatabaseManager.soft_reject_tag()` を呼び、`tags.rejected_at` を設定するだけである。**画像 DB から行は物理削除されず**、表示から外れるのみで復活可能である。ハード削除(行の物理削除)はどこにも実装されていない。
- チップ本体のクリックは、現状ではコピー用の選択操作となっている(#814)。
- 設計プロトタイプの「クリック = 無効化、✕ = 削除」という 2 操作モデルは、この現行実装(✕ = soft-reject、クリック = 選択)と食い違っていた。

## Decision

### 1. タグ欄を DB 非依存の `TagPanelWidget` へ切り出す

`AnnotationDataDisplayWidget` からタグ欄を独立したウィジェット `TagPanelWidget` として切り出す。責務境界(#983 §4)は次のとおりとする。

```
TagPanelWidget(新規)
  - DB を知らない / service_container を知らない
  - 表示状態(tags, lang, metric, density)とユーザー操作だけを持つ
  - 操作要求は Signal で親へ出すだけ

SelectedImageDetailsWidget(親 / 既存)
  - current_image_id を持つ
  - 注入された db_manager / refinement_service / merged_reader を持つ
  - TagPanelWidget の Signal を受けて保存先へ dispatch する
```

ウィジェットを DB および `service_container` から切り離し、依存注入を親へ集約することで、#978 で問題となった「保存先の混線」を構造的に防ぐ。これは ADR 0009 の Qt 非依存コアと GUI の分離方針の延長である。なお、言語切替はチップの表示名を直接決定するため、分離すると `canonical`、`display_text`、`translation` の同期が複雑になる。よって、タグチップ表示と言語切替は一体として扱う。

`TagPanelWidget` は Search および Export の画像詳細(`SelectedImageDetailsWidget`)で共用する。さらに、操作が重なる範囲では**エクスポートのステージング画面にある `StagingTagPanel`(ADR 0080)でも同じウィジェットを再利用する**ことを前提に設計する。重複範囲と ADR 0080 の出力オーバーレイ層との整合は #987 で確認する。`TagPanelWidget` が Signal のみを送出する純粋な表示ウィジェットであることで、この再利用が可能になる。

### 2. Signal を画像 DB 系と tagdb userdb 系に分離し、現行命名を踏襲する

保存先の意味が混ざらないよう、Signal を 2 系統に分離する。#983 §4 では別名も提案されたが、既存の呼び出し側への不要な変更を避けるため、**現行の `*_requested` 系の命名を踏襲**する。

```python
# image DB 系(current_image_id 必須)
# 単一操作は Issue #1003 で無効化 / 除外を名前で分離する(受け手の reason 文字列分岐を排除)。
tag_disable_requested = Signal(str)        # canonical — 無効化(reason='not_needed'、破線で残す)
tag_exclude_requested = Signal(str)        # canonical — 除外(reason='incorrect'、非表示)
tag_restore_requested = Signal(str)        # canonical — 復活
tag_add_requested     = Signal(str)        # 生入力(日本語可)— 親が canonical 解決
# 複数選択のバッチ操作(#997)。reload を1回に抑えるため list をまとめて渡す(Codex #1001 P2)。
tags_exclude_requested = Signal(list)               # canonicals — まとめて除外(incorrect)
tags_toggle_requested  = Signal(list, list)         # (to_disable, to_restore) 無効化側は not_needed

# tagdb userdb 系(canonical が主キー / 画像 ID 不要)
refinement_ignored          = Signal(str, str)        # canonical, reason_code(既存)
translation_add_requested   = Signal(str, str, str)   # canonical, language, translation(Phase 2)
tag_metadata_edit_requested = Signal(str, str)        # canonical, type(Phase 2)
```

> **改訂(Issue #1003)**: 旧 `tag_reject_requested(str)` および `tags_reject_requested(list)`(無効化と ✕ で共通の soft-reject)は上記の定義へ置き換えた。無効化と除外では DB 上の意味と表示種別が異なる(`reject_reason` が `not_needed` か `incorrect` か)ため、Signal 名で意図を明示する。親(`SelectedImageDetailsWidget`)が受け取って `soft_reject_tag(..., reason=...)` へ振り分ける。なお、`replaced` はチップ操作ではなくバッチ置換機能(`replace_tag_for_images_batch`)が設定する。

UI 文言には「image DB」「tagdb userdb」といった内部用語を出さない。保存先の区別は、色レイヤー(画像 DB 系は青 `--info` と「この画像」、tagdb userdb 系はティール `--udb` と「タグ情報」)と自然な日本語で示す。

### 3. タグ操作モデルを soft-reject 一本に統一する(ハード削除なし・2 種類の表示)

タグの是正は soft-reject(`rejected_at`、ADR 0065)に一本化する。データ保全と復活可能性を優先し、**ハード削除(行の物理削除)および `tag_deleted` Signal は導入しない**。

soft-reject されたタグには複数の種別を持たせる。いずれも `rejected_at` を設定して DB 行を残したうえで、種別を `reject_reason` 列(ADR 0065 改訂、Issue #1003)に**永続化**し、表示方法(破線で残すか非表示にするか)を切り替える。

| 操作 | `rejected_at` | `reject_reason` | 表示 | 復活 |
|---|---|---|---|---|
| **無効化**(チップ単クリック) | セット | `not_needed` | 破線チップでインライン表示を継続 | チップ再クリックでトグル復活 |
| **除外**(✕ ボタン) | セット | `incorrect` | パネルから非表示 | **なし**(誤りのため消去。戻す UI は作らない) |
| **置換済み**(バッチ置換) | セット | `replaced` | 非表示 | **なし**(置換先へ移行済み) |

チップの操作割当は、プロトタイプに準拠しつつ既存の #814 とも両立させる。

- **単クリック**: 無効化と復活のトグル(破線インライン表示、`tag_disable_requested` / `tag_restore_requested`)
- **✕ ボタン**: この画像から除外(非表示、`tag_exclude_requested`)
- **Ctrl + クリック**: コピー選択(#814)
- **⋯ ボタン(インライン)または右クリック**: タグ情報メニュー(翻訳追加、タグ情報を編集、使用頻度を見る、修正候補を適用(#1007・編集モードのみ)、警告を無視)

別枠の「復活」セクションは設けない。無効化はインライン破線チップの再クリックで復活させ、除外および置換済みの復活 UI は作らない。

**表示種別(無効化は破線、除外・置換は非表示)はメモリ上の状態ではなく、DB の `reject_reason` から再読込ごとに再構築する**(Issue #1003)。これにより、別画像へ移動して戻った際にメモリ状態へ依存せず表示が正しく復元され、「無効化したタグが ✕ で除外したように消える」回帰を構造的に防げる。なお、`reject_reason` の値はエクスポート時の抽出条件(`rejected_at IS NULL`)には影響しない。

#### スコープ外および段階対応の整理

- **複数選択のバッチ操作バー(まとめて外す・無効化・復活)**: 当初スコープ外としたが、#997 および #1001 で実装済みである。
- **refinement 警告の「修正候補を適用」(タグ置換、`refine.suggest`)**: #1007 で実装済みである。編集モードかつアクティブなチップに限り、右クリックメニューへ `correction_candidate` の候補を並べる。選択時は `tag_replace_requested(from, to)` を送出し、親が `replace_tag_for_images_batch`(置換元の `reject_reason='replaced'`、Issue #1003)へ振り分けて 1 回だけ再読込する。対象は表示中の画像のみとし(全画像一括は CLI の `lorairo tags replace` が担う)、複数警告のバッチ適用と自動適用は引き続き対象外とする。
- **✕ で除外したタグの復活 UI**: 引き続き先送りとする。

### 4. 手動タグ追加は親で canonical 解決を行う(日本語入力対応)

`AddTagRow` は日本語入力も受け付ける。`TagPanelWidget` は生入力のまま `tag_add_requested(raw_input)` を送出し、**親ウィジェットが canonical 解決を担う**。

```
tag_add_requested(raw_input)
  → 親が search_tags(query=raw_input, partial=False, resolve_preferred=True)
      ├─ TAG_TRANSLATIONS 一致 → canonical を取得 → add_manual_tag(canonical)
      └─ 未ヒット → 入力をそのまま add_manual_tag(raw_input)
           (register_tag: format=Lorairo, type=unknown, source_tag=raw_input)
```

タグ DB の翻訳テーブル経由で日本語から canonical タグを解決し、一致しない日本語はそのまま登録する(`source_tag` を保持する)。任意の未登録日本語を機械翻訳で英語の canonical タグへ変換する機能は、`genai-tag-db-tools` の公開 API では実現できないため**対象外**とする(必要になれば別 ADR または別 Issue で検討する)。オートコンプリート候補は既存の `tag_suggestion_service` が提供する `search_tags(partial=True)` を用い、日本語・英語の双方に対応する。

### 5. 段階移行計画

各フェーズは必要に応じてサブ Issue 化して進める。

- **Phase 1**: `TagPanelWidget` の切り出し(既存機能の移植)と、日本語タグ追加時の canonical 解決を実装する。`AnnotationDataDisplayWidget` はタグ欄を委譲する薄い親へ整理する。
- **Phase 2**: tagdb userdb 系の書き込み機能を追加する。具体的には、翻訳追加(`translation_add_requested` から `UserTagRepository.write_translation_patch()`)と type 補正(`tag_metadata_edit_requested` から `update_tags_type_batch()`)を実装する。
- **Phase 3**: 表示言語とは完全に独立した第 2 軸として、使用頻度表示(`metric_source`: なし、Danbooru、e621、Gelbooru の件数を `TagReader.get_usage_count()` 経由で取得)を追加する。

## Consequences

### 良い点

- タグ固有の複雑さが Caption、Score、Rating へ波及しなくなる。`TagPanelWidget` は DB やサービスを注入せずに生成できるため、Signal 発火の単体テストが容易になる。
- ウィジェットの DB 非依存化と親での振り分けにより、保存先(画像 DB 系と tagdb userdb 系)の混線を構造的に防げる(#978 との整合)。
- soft-reject 一本化によりデータが失われず、誤操作も復活操作で回復できる。プロトタイプと現行実装の操作モデルの食い違いも、最小限の再整合で解消できる。

### 悪い点・トレードオフ

- soft-reject に「破線で残す(無効化)」と「非表示にする(除外)」の 2 種類の表示を持たせるため、`rejected_at` に加えて表示種別の区別が必要になった。当初は `TagPanelWidget` のメモリ状態(`_disabled_display` と `_hidden`)のみで区別していたが、別画像との往復時にメモリ状態が失われ「無効化が ✕ のように消える」回帰が発生した。**この問題は Issue #1003 で `reject_reason` 列(`not_needed`、`incorrect`、`replaced`)へ永続化し、再読込ごとに DB から表示種別を再構築する方式で解消した**。なお、✕ で除外または置換したタグの復活 UI は引き続き作らない。
- チップの単クリックを無効化トグルへ割り当てたため、コピー選択(#814)は Ctrl + クリックへ変更される。
- 使用頻度の第 2 軸、翻訳追加、type 補正、バッチ操作、refinement 修正候補適用は Phase 2 以降へ先送りとなるため、Phase 1 単体では既存機能の移植にとどまる。
- 未登録の日本語入力は canonical 解決ができないため `source_tag` のまま登録され、後から翻訳追加(Phase 2)を行う必要がある。

## Related

- ADR 0065: タグ・キャプションの soft-reject(タグ操作モデルの基盤。`reject_reason` の改訂は Issue #1003)
- ADR 0068: タグ正規化の tagdb 委譲(canonical 解決の意味)
- ADR 0080: エクスポート前タグ編集の 2 層オーバーレイ(DB 編集層で本 ADR の soft-reject を再利用)
- ADR 0009: Qt Decoupling Design(DB 非依存ウィジェットの方針)
- Issue #983: 本 ADR の実装仕様(フェーズ別計画とテスト観点を含む)
