---
type: Guide
title: 搜尋與待處理區
description: 從搜尋結果中明確選擇實際要處理的圖片。
sidebar:
  order: 4
---

## 搜尋結果不等於執行目標

在圖形介面以標籤等條件篩選圖片、選取縮圖，再按「選択をステージングへ」（將選取圖片加入待處理區）。只出現在搜尋結果或只選取縮圖，都不會成為執行目標。

AI 標註與匯出共用同一組待處理圖片，最多 500 張，同一圖片不會重複加入。執行前請再次確認圖片內容與數量。

待處理區的「クリア」（清空）只移除處理目標，不會從資料庫刪除圖片。

## 圖形介面搜尋

標籤搜尋支援排除條件（`-tag`）。變更條件後，請確認數量與縮圖，檢查目標圖片是否包含在內。也可搭配評分、缺少模型結果等適合用途的條件。

## 命令列搜尋

為避免在 PowerShell 直接嵌入 JSON 時的引號問題，請建立 UTF-8 編碼的 `query.json`。

```json
{"tags":["cat"],"excluded_tags":["dog"],"limit":100}
```

```powershell
uv run --no-sync lorairo-cli --json images search -p "my-project" --query-file query.json
uv run --no-sync lorairo-cli images show 42 57 -p "my-project"
```

搜尋預設的 `include_nsfw` 為 false。請勿把被條件排除的圖片誤認為尚未匯入。大量結果有數量保護限制；若要列出大量 ID，請在查詢中明確加入 `"emit_ids":true`。

`--json` 的標準輸出為 JSONL，除了結果，也包含帶有訊息類型的資料列。請勿把整份輸出直接當成圖片 ID 檔案使用。另請參閱 [CLI 說明](../cli/)。
