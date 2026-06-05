# 実装計画: pHash 系 ISSUE 群 (#629 / #630 / #631 / #632 / #633)

作成日: 2026-06-05
対象 Issue: #629, #630, #631, #632, #633
実行方式: Agent Teams 2 トラック (1 トラックは 3 段直列チェーン)

## 1. 背景と問題定義

pHash (知覚ハッシュ) に関わる 5 件の Issue。2 つのサブシステムに分かれる:

- **画像登録パイプライン** (#631 / #630 / #632 / #633): pHash 完全一致 = 即重複の現状を、
  「候補検索 → 属性比較で重複/別版に分類」へ再設計し、save 順序と副作用を経路間で統一する。
- **Batch custom_id** (#629): `build_custom_id(image_id)` を `pHash + 長辺解像度` 基準へ。別サブシステム。

### 成功基準
- 同一 pHash でも属性差 (width/height/has_alpha/is_grayscale_like) があれば別版として登録できる。
- 重複判定が save より前に走り、スキップ画像の不要コピーが残らない。
- GUI / API / direct の 3 経路で重複時副作用 (.txt/.caption 取込・alias・統計) が一致する。
- Batch custom_id が `ph:{phash}:le:{long_edge}` で生成され、batch 内 dedupe と結果突合が成立する。
- ADR 2 本が Accepted、全 CI-equivalent filter pass。

## 2. 依存グラフと並列化の現実

```
#631 (is_grayscale_like) ──┐
                           ├─> #630 (重複/別版分類) ──> #633 (副作用統一)
#632 (save 順序見直し) ─────┘   (#630 と #632 は register_original_image /
                                 _prepare_image_metadata / _handle_duplicate_image を
                                 同時に書き換える = 実質 1 リファクタ)

#629 (Batch custom_id) ── provider_batch_* で完全独立
```

**ファイル所有権の衝突**: `repository/image.py` / `db_manager.py` / `file_system.py` を
#631 / #630+#632 / #633 が三つ巴で奪い合う。安全に独立並列できるのは **#629 のみ**。
[[feedback_parallel_single_file_placeholder_swap]] の同一ファイル並列ハザードを回避するため、
登録系は直列チェーンとする。

## 3. 実行構成 (2 トラック)

### Track 1 (独立・並列): #629 Batch custom_id
- worktree: `/tmp/worktrees/issue-629` / branch `feat/issue-629`
- ADR 0062 (Proposed) を本 worktree に隔離
- 担当ファイル: `services/provider_batch_service.py`, `services/provider_batch_workflow_service.py`,
  `services/batch_image_matcher.py`, 対応テスト
- 独立 PR

### Track 2 (直列チェーン): 登録パイプライン
ADR 0061 (Proposed) で設計確定 → 以下を順次 PR (各段は前段 merge 後に origin/main から分岐)。

- **Stage 2a — #631 is_grayscale_like (基盤・追加のみ)**
  - worktree `/tmp/worktrees/issue-631` / `feat/issue-631`
  - `schema.py` Image に `is_grayscale_like: bool | None`, `colorfulness_score: float | None`
  - Alembic migration + 既存 DB backfill 方針 (NULL 許容 + 遅延 backfill、または migration 内軽量算出)
  - `file_system.get_image_info()` でグレースケール相当判定 (RGB 変換 → サムネサンプリング →
    チャンネル差分の平均/95 パーセンタイル閾値、JPEG ノイズ考慮で完全一致にしない)
  - `repository/image.add_original_image()` で新カラム永続化
  - **#629 と完全 disjoint なので Track 1 と真の並列可**

- **Stage 2b — #630 + #632 分類 + save 順序 (コア・リファクタ)**
  - `#631` merge 後に `feat/issue-630-632` を origin/main から分岐
  - `db_manager._prepare_image_metadata()`: pHash 計算 → **分類判定** → 新規/別版のみ save
  - `repository.find_duplicate_image_by_phash()`: 候補リスト取得 +
    属性比較メソッド (`classify_phash_candidate()` 等) に分割
  - `db_manager._handle_duplicate_image()` / `register_original_image()`: 分類結果
    (duplicate / variant / new) を返す構造へ。save 済みで未登録時の cleanup 方針も定義
  - 担当: `db_manager.py`, `repository/image.py`, `file_system.save_original_image()`

- **Stage 2c — #633 副作用統一 (経路統合)**
  - `#630+#632` merge 後に `feat/issue-633` を分岐
  - 重複/別版/新規ごとの副作用を 1 箇所 (db_manager の統一 register エントリ or 専用ヘルパ) で定義
  - `gui/workers/registration_worker.py` / `api/images.py` を統一ルールへ寄せる
  - .txt/.caption 取込先を分類結果に従わせる、alias 登録の責務と失敗時挙動統一、
    統計 (`registered`/`skipped`/`failed` + 新たに `variant`) の意味を揃える

### 同時実行スナップショット
- Wave 1 (真の並列 2 agent): **Track1 #629** ‖ **Stage 2a #631**
- Wave 2 (#631 merge 後): **Stage 2b #630+#632** (Track1 がまだ走っていれば並列継続可)
- Wave 3 (#630+#632 merge 後): **Stage 2c #633**

## 4. ADR 設計サマリ (2 本集約)

### ADR 0061: pHash 重複/別版分類と登録パイプライン再設計 (#630/#632/#633)
- 決定: pHash 完全一致を「重複確定」ではなく「候補」とし、属性比較で重複/別版を分類。
- ハミング距離による近似重複は導入しない。`phash` は unique 化しない (候補検索キー)。
- 分類属性: width/height/has_alpha/is_grayscale_like (必要なら mode/format/extension/color_space)。
- save は分類後 (新規/別版のみ)。save 済み未登録時の cleanup 規約を定義。
- 副作用 (関連ファイル取込・alias・統計) は分類結果駆動で全経路統一。
- 1 プロジェクト = 1 DB 前提、横断スコープ非対象。
- Related で #630/#632/#633 をリンク (個別解決の言及は本文に散らさない: [[feedback_adr_no_per_issue_resolutions]])。

### ADR 0062: Batch custom_id を pHash + 長辺解像度基準へ (#629)
- 決定: `custom_id = ph:{phash_hex}:le:{long_edge_px}`。画像 ID 直結をやめ素材実体に寄せる。
- pHash は完全一致キーではなく知覚ハッシュであることを明記。
- 同一 batch 内に同一素材を投入しない前提、`custom_id -> image_id[]` 対応表が必要。
- 近似 pHash 判定を使う場合の代表 pHash の扱い。
- 結果の出力順非保証に対し custom_id で突合。

### ADR 運用
- どちらも Proposed で worktree 隔離。Accepted まで main へ merge しない ([[project_proposed_adr_pr_merge_hold]])。
- 実装着手前にユーザーが設計を Accept (本計画承認に同梱)。Status flip は PR merge 時。

## 5. テスト戦略 (CI-equivalent filter 必須)
- #631: get_image_info のグレースケール判定 unit (カラー/グレー/RGB 擬似グレー/JPEG ノイズ)、migration 往復、backfill。
- #630+#632: 同一 pHash・属性差ケースの分類 BDD (重複/別版/新規)、save 順序の回帰 (重複時にコピーが残らない)。
- #633: 3 経路で同一入力 → 同一副作用/統計の整合 BDD。
- #629: custom_id 生成・dedupe・突合 unit + 小さな JSONL 回帰。
- 各 PR 起票前に CI-equivalent filter:
  `-m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"`。

## 6. リスクと対策
- **同一ファイル競合**: 登録系を直列化 (Track 2) で構造的に回避。
- **Proposed ADR 上の実装手戻り**: 設計を計画承認で先に Accept し、実装は確定設計に対して行う。
- **migration backfill の重さ**: 既存 DB は NULL 許容 + 遅延 backfill を既定に。
- **別版登録による行増加**: 1DB=1プロジェクト前提で許容、UniqueConstraint(uuid, phash) は維持可。
- **worktree editable install の検証限界**: 真偽は push 後 CI を SSoT ([[project_worktree_editable_install_resolves_main_checkout]])。

## 7. Agent ディスパッチ手順 (承認後)
1. ADR 0061 / 0062 draft をユーザー Accept。
2. worktree 作成: `feat/issue-629`, `feat/issue-631` (Wave 1)。
3. Agent A=#629, Agent B=#631 を並列ディスパッチ (担当ファイル分離)。
4. 各 Agent は CI-equivalent filter 検証 → ready-for-review PR → agent-pr-autoloop。
5. #631 merge 後 Stage 2b、続いて Stage 2c を順次ディスパッチ。
6. merge 後 worktree を即削除。
