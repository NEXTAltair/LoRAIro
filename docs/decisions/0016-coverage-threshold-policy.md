# ADR 0016: Coverage Threshold Policy

- **日付**: 2026-04-19
- **ステータス**: Accepted

## Context

Issue #131 の coverage-gate 新設により、長く aspirational だった `fail_under=75` が CI で初めて検証され、
合算カバレッジが **58%** であることが顕在化した。75% への到達経路の判断が必要になった。

### Issue #135 Phase 2 調査の発見

`grep` ベースの import graph 解析で、`src/` 本体から一切参照されないモジュール (デッドコード)
を 9 件 / 4,257 LOC (全体 18,420 行の 23%) 検出した:

| ファイル | LOC | src 参照 | test 参照 | 性質 |
|---------|-----|---------|----------|------|
| `gui/widgets/annotation_results_widget.py` | 678 | 0 | 0 | 完全 dead |
| `gui/widgets/annotation_status_filter_widget.py` | 276 | 0 | 0 | 完全 dead |
| `services/ui_responsive_conversion_service.py` | 1,225 | 0 | 1 | テスト経由のみ |
| `gui/widgets/model_selection_table_widget.py` | 397 | 0 | 4 | テスト経由のみ |
| `services/annotator_library_adapter.py` | 179 | 0 | 3 | テスト経由のみ |
| `services/batch_processor.py` | 298 | 0 | 7 | テスト経由のみ |
| `services/batch_utils.py` | 205 | 0 | 4 | テスト経由のみ |
| `services/model_info_manager.py` | 354 | 0 | 33 | テスト経由のみ |
| `services/openai_batch_processor.py` | 345 | 0 | 3 | テスト経由のみ |
| **合計** | **4,257** | **0** | — | **全体の 23%** |

この発見により、58 → 75% への到達経路として 2 つの判断分岐が生じた:

- **短期案**: `fail_under` を 60% に一時引き下げ (CI を green に戻す)
- **中長期案**: omit 整備 + デッドコード削除/omit 化で 75% を堅持

現在 `[tool.coverage.run] omit` はインフラ層のみで、アプリケーションコードへの omit 基準が未定義である点も課題。

### 判断分岐の影響

場当たり的な決定は「またカバレッジが下がったら一時引き下げ」という前例を生み、
将来のカバレッジ低下に対する感度を低下させる恐れがある。
したがって、**omit 許可基準**・**削除許可基準**・**fail_under 堅持ポリシー** を明文化し、
Issue #138–142 群の前提判断材料として固定することが必要。

## Decision

1. **`fail_under=75` を恒久的に維持する。**
   段階的引き下げ (60→65→70→75) は採用しない。

2. **omit 許可基準** (以下いずれかに該当するコードのみ omit 可):
   - (a) `src/` 本体から一切参照されない開発補助・ヘルパー
   - (b) Qt 描画専用 GUI (ヘッドレス CI でのテストが技術的に困難)
   - (c) 自動生成コード (`gui/designer/*` 等)

3. **omit 禁止**:
   - `services/`, `database/`, `storage/`, `configuration_service` 等のコア機能は omit 不可。

4. **削除許可基準**:
   - `src/` 本体参照 0 かつ テスト参照 0 → **即削除可**
   - `src/` 本体参照 0 かつ テスト参照あり → `git log --all -- <file>` で削除経緯を確認し、
     (a) 機能復活予定があれば `scripts/legacy/` 移動、
     (b) 単なる残存物なら削除、
     (c) 判断困難なら omit 追加後に Issue 起票

5. **ポリシー参照義務**:
   `[tool.coverage.run] omit` への新規追加、および `src/` 配下のファイル削除を伴う PR は
   本 ADR (0016) をコミットメッセージまたは PR 説明で参照すること。

## Rationale

### なぜ `fail_under=75` を堅持するか

- Issue #138 単独で +17pt (58→75%) 到達見込み。一時引き下げは不要。
- 一時引き下げは「CI は green だが実質カバレッジは改善しない」状態を正当化し、
  将来のカバレッジ劣化に対する感度を下げる。
- 75% はプロジェクト発足以来の aspirational 目標。
  一度でも下げると再引き上げが政治的に困難になる。

### なぜ omit 許可基準を明文化するか

- Qt ヘッドレス CI でのテストが技術的に困難なコード (`ui_responsive_conversion_service.py` 等)
  と、単なるテスト整備遅延を混同させないため。
- 新規 PR レビューで omit 追加の可否を一貫して判断可能にするため。

### なぜコア機能の omit を禁止するか

- `fail_under` を品質ゲートとして機能させるには、計測対象からコア機能を除外しないことが前提。
- コア機能を omit 可とすると「カバレッジ低下 → omit で回避」の安易なパスが開く。

### 却下した選択肢

| 選択肢 | 却下理由 |
|--------|---------|
| A: `fail_under=60` へ一時引き下げ | CI は green になるが実質カバレッジは改善しない。将来の劣化検知感度が低下し、再引き上げも政治的困難。 |
| B: 段階的引き上げ (60→65→70→75) | Issue #138 単独で 75% 到達見込みのため引き下げ自体が不要。段階管理の運用コストが純粋な負債。 |
| C: コアとテスト困難コードで fail_under を分離 | coverage.py の単一 `fail_under` では実装困難。複数 coverage 実行で運用複雑化。 |
| D: omit ポリシー非定義のまま運用 | PR ごとに omit 可否が議論され一貫性が失われる。現状の暗黙ルール化が温床。 |

## Consequences

### 良い点

- omit/削除判断の一貫性が確保され、PR レビューで基準ベースの議論が可能になる。
- コア機能のテスト追加が構造的に強制される (omit で逃げられない)。
- Issue #138 実施で CI `coverage-gate` が green に復帰し、
  以降は 75% 維持が技術的ゲートとして機能する。

### 悪い点・トレードオフ

- omit リストの継続メンテナンスコスト。
  新規開発ヘルパー追加時に omit 要否判断が必要。
- Qt 描画専用コード (例: `ui_responsive_conversion_service.py` 相当)
  は恒久的にカバー外となる。
  ただし ADR 0009 (Qt Decoupling) でコアロジックは Qt-free 層に分離済みのため、
  ビジネスロジック品質は担保される。
- 本 ADR は `pyproject.toml` とセットで運用される。
  `fail_under` 変更時は必ず本 ADR の Status を見直すこと。

## Roadmap

Issue #135 サブ Issue 群の実施優先順位:

| Phase | Issue | 内容 | 期待効果 |
|-------|-------|------|---------|
| **Phase 1 (最優先)** | #143 (本 ADR) | ポリシー確立 | 判断基準の明確化 |
| **Phase 2 (最優先)** | #138 | デッドコード 9 モジュール/4,257 LOC の処遇判定・削除/omit 化 | 58 → **≈75%** |
| **Phase 3 (並列実施可)** | #139 | `image_processing_service.py` テスト新規 (14%→75%+) | +~5pt |
| **Phase 3 (並列実施可)** | #140 | `model_registry_protocol.py` テスト新規 (34%→80%+) | +~2pt |
| **Phase 3 (並列実施可)** | #141 | `storage/file_system.py` テスト拡充 (59%→80%+) | +~2pt |
| **Phase 3 (並列実施可)** | #142 | `configuration_service.py` テスト拡充 (56%→80%+) | +~2pt |
| **Phase 4 (長期)** | 追加調査 Issue | 定期的カバレッジ改善 | バッファ確保 |

Phase 1+2 完了で CI 復旧、Phase 1–3 完了で 75 → 76.5% のバッファ確保予定。

## Related

- **Meta Issue**: #135 (カバレッジ 58% 問題の背景調査)
- **派生 Issue**: #138 (デッドコード一掃), #139–142 (コアテスト拡充)
- **前提 Issue**: #131 (coverage-gate 新設)
- **関連 ADR**: 0009 (Qt Decoupling Design — コアを Qt-free に分離している前提が本 ADR を成立させる)
- **関連ファイル**: `pyproject.toml` (`[tool.coverage.report]`, `[tool.coverage.run]`)
