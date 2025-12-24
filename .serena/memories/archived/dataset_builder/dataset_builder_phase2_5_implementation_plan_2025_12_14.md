# Phase 2.5 Input Normalization Enhancement - Implementation Plan

## 策定日
2025年12月14日

## Executive Summary

### 2025-12-15 更新（運用確定事項の反映）

- 現状スコープは **ローカルの `tags_v4.db` + `TagDB_DataSource_CSV/**`** を統合して SQLite を生成すること（HF/外部リポジトリ取得は後回し）。
- ここで言う「正則化」は **`TAGS.tag` 側のみ**を対象にする（小文字化 + `_`→スペース + 丸括弧エスケープ `\\(` `\\)`）。
  - **`TAGS.source_tag` 側は丸括弧エスケープしない**（元データの表記を保持）。
  - 顔文字（kaomoji）は破壊しない（小文字化しない）。
- `tag` 列の意味推定（SOURCE/NORMALIZED/UNKNOWN）の基本方針は「安全側」：**SOURCE と断定できないソースはスキップ**。
  - 例外：`dataset_rising_v2`（e621由来）など、`tag` 列が NORMALIZED 推定でも **`source_tag` として扱う**ことを許可し、`deprecated_tags` による alias 情報を取り込む。
- `meta:` / `artist:` などの **カテゴリprefix付きタグは `tags_v4.db` に存在するため保持**する。
  - ただし実利用（SD WebUI等で `:` を避けたい）では **alias解決で prefix 無し側へ寄せる**前提。
  - 「非prefix → prefix」へ寄る逆転（例: e621で `fulllength portrait -> meta:fulllength portrait`）は **データ異常としてレポート→手動修正**。

Phase 2 Data Loss Fix完了後の方針変更に対応し、入力正規化機能を強化します。CSV/JSON/Parquet等の表形式入力に対して、`tag`列の意味を自動推定（正規化済み vs 生タグ）し、誤統合を防止します。
あわせて、**source_tag → TAGS.tag の変換（正則化）ロジックを dataset-builder 側（core）へ集約**し、アダプタ側の責務を「列名の標準化 + 最低限の検証」に寄せます。

**目的**: 入力データのブレ吸収、データ破壊リスクの排除
**スコープ（現状/将来）**:
- 現状（優先）: **ローカルに存在する `tags_v4.db` + CSV（TagDB_DataSource_CSV）** を統合してDB生成
- 将来（後回し）: HuggingFace/外部リポジトリから取得→DB構築（取得元の更新日時/内容を見て優先判断）

---

(以降のセクションは長すぎるため省略)

**策定者**: Claude Sonnet 4.5
**参照**: 
- dataset_builder_phase2_5_input_normalization_gap_analysis_2025_12_14
- dataset_builder_design_plan_2025_12_13
- dataset_builder_phase2_data_loss_fix_implementation_plan_2025_12_14

**次のコマンド**: `/implement`（実装開始、ただし現在は保留）
