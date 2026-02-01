# Plan: gentle-yawning-peacock

**Created**: 2026-01-31 05:23:06
**Source**: plan_mode
**Original File**: gentle-yawning-peacock.md
**Status**: planning

---

# 計画: plan_wild_rolling_ripple_2026_01_31.md の不整合修正

## 修正済み（Serena Memoryファイルに直接適用）

### 修正1: 新規ファイル数の整合 (High)
- **問題**: スコープ「プロダクション17 + テスト18」と末尾合計「プロダクション15 + テスト17」が矛盾
- **修正**: Phase表の積み上げに基づき正しい数値を算出
  - Phase 5の `associated_file_reader.py` がプロダクション新規1本（テーブルで0→1に修正）
  - **最終値**: プロダクション16本 + テスト17本 = 33ファイル（スコープ・末尾合計とも統一）

### 修正2: Phase 3↔5 依存関係の明示 (High)
- **問題**: Phase 5で `associated_file_reader.py` を新規作成しつつ、Phase 3のWorker/テストで参照。依存表に未記載
- **修正**:
  - Phase 3 依存欄: `Phase 5（associated_file_reader参照）` を追記
  - Phase 5 依存欄: `なし（Phase 3がPhase 5のassociated_file_readerを参照）` と注記
  - 推奨実施順序: `Phase 2 → 1 → 5 → 3 → 4（並行可: 2+5, 1単独。3はPhase 5後）` に変更
  - Phase 3テスト欄から `associated_file_reader` の言及を削除（Phase 5で管理）、7→6本に修正

### 修正3: __main__対象数の表記統一 (Medium)
- **問題**: 「24対象」と「30中24対象」が併記
- **修正**: スコープ欄を「__main__ハーネス（全30ファイル中24対象）」に統一

## 対象ファイル
- [plan_wild_rolling_ripple_2026_01_31.md](.serena/memories/plan_wild_rolling_ripple_2026_01_31.md) — 修正適用済み

## 検証
- 各Phase新規ファイル列の合計: 1+6+5+2+1+1 = 16（プロダクション）✓
- テスト合計: 1+6+6+2+1+1 = 17 ✓
- 依存関係: Phase 3→Phase 5 が推奨順序に反映 ✓
