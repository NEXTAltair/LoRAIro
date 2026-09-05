---
type: Guide
title: 專案與圖片匯入
description: 了解專案儲存內容，安全地匯入圖片。
sidebar:
  order: 3
---

## 儲存的內容

圖片資訊、AI 標註與編輯內容以專案為單位管理。通常儲存在 `lorairo_data/<project>_YYYYMMDD_NNN/`，包含 SQLite 資料庫、`image_dataset/` 等內容。若變更過設定，儲存位置也可能不同。

請區分原始圖片資料夾與 LoRAIro 專案儲存位置。備份需要整個專案，不只是圖片資料庫。

## 在圖形介面匯入圖片

1. 開啟「検索」（搜尋）分頁。
2. 在「データセット」（資料集）的「選択」（選取）中選擇圖片資料夾。
3. 等待匯入完成，再確認搜尋結果與數量。

此處的「選択」是選擇匯入來源資料夾，不是開啟既有專案的按鈕。請先用小型測試資料夾操作，避免意外匯入整個不需要的目錄。

## 在命令列明確指定專案

```powershell
uv run --no-sync lorairo-cli project create "my-project"
uv run --no-sync lorairo-cli project list
uv run --no-sync lorairo-cli images register ./images --project "my-project"
uv run --no-sync lorairo-cli images list --project "my-project" --fetch
```

請將 `my-project` 換成自己的專案名稱。匯入後從清單確認圖片 ID，不要直接使用指南的範例 ID。

命令列匯入預設會略過 pHash 相同的圖片。只有確實需要重複匯入時，才使用 `--include-duplicates`。

## 匯入之後

只匯入圖片不會自動執行標註或匯出。請透過[搜尋與待處理區](../search/)選擇目標後再繼續。請勿同時用圖形介面與命令列執行匯入、編輯等寫入操作。
