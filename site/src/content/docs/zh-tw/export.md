---
type: Guide
title: 匯出資料集
description: 從待處理區或圖片 ID 建立訓練用檔案。
sidebar:
  order: 7
---

## 在圖形介面匯出

1. 確認待處理圖片及數量。
2. 在「エクスポート」（匯出）選擇解析度與格式。
3. 確認匯出用標籤調整，執行「検証」（驗證）。
4. 沒有問題後執行「エクスポート」，並檢查產生的圖片與文字。

解析度選項為 512、768、1024、1536。格式包括「TXT（タグ分離）」（標籤分開）、「TXT（キャプション統合）」（描述文字合併）與「JSON」。請選擇訓練工具需要的格式。

暫時排除輸出與資料庫 reject 不同。詳見[修改標籤](../editing/)。

## 命令列使用圖片 ID

目前的 `export create` 不接受搜尋篩選條件。請先搜尋並確認目標 ID。舊版的 `--tags cat` 範例已不能使用。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids-file ids.txt -o ./dataset
```

這兩行是替代用法，`--image-ids` 與 `--image-ids-file` 不能同時指定。直接指定最多 500 個 ID。大量匯出時，請使用以換行或逗號分隔 ID 的 `ids.txt`。命令列會同時產生 TXT 與 JSON。

請使用空的專用輸出目錄，避免意外與既有資料集混在一起。執行後先檢查檔案數量、圖片與標籤，再交給訓練工具。

## 依標籤語言分開的資料集

多語言標籤匯出需在命令列明確指定。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset --tag-language canonical --tag-language ja
```

指定多種語言時，會在 `canonical/`、`ja/` 等目錄中各建立一份包含圖片的完整資料集，因此需要更多可用空間。只指定一種語言時，使用輸出根目錄。

沒有已登錄主要譯文的標籤會改用 canonical 文字。此功能不會自動翻譯描述文字，與指南支援四種語言是不同功能，也不保證每個標籤都有四種語言的譯文。目前未提供從圖形介面匯出多語言標籤的操作流程。
