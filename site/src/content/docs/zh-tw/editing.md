---
type: Guide
title: 修改標籤與檢查描述文字
description: 區分資料庫編輯與僅在匯出時生效的調整。
sidebar:
  order: 6
---

## 先檢查產生結果

選取圖片，在詳細資訊面板檢查標籤、描述文字與評分。AI 結果不一定正確；請找出訓練不需要的標籤或與圖片不符的文字。

目前的描述文字顯示為唯讀。請勿假設有可自由輸入的描述文字編輯欄位。可從標籤選單使用將標籤移至描述文字的功能。

## 永久變更與匯出調整

- 新增、取代、reject 標籤會影響資料庫內容。
- 匯出 overlay 的「出力除外」（排除輸出）只是匯出時的暫時調整。
- 「reject(DB)」不是暫時排除。請確認影響範圍，不要假設操作可以復原。

模型可能不會回傳 AI 標籤各自的 confidence。並非隨時都能依 confidence 自動去除雜訊標籤。

## 命令列先預覽再套用

標籤變更預設為 dry-run。請先不加 `--apply`，確認目標。

```powershell
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor"
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor" --apply
uv run --no-sync lorairo-cli tags remove -p "my-project" --image-ids 42 --tags "bad_tag" --apply
uv run --no-sync lorairo-cli tags replace -p "my-project" --image-ids 42 --from "bad tag" --to "good_tag" --apply
```

移除會以 soft-reject 處理，但這不保證有通用的「復原」操作。大量變更前請先備份。命令列修改後，請在圖形介面重新搜尋或重新載入，確認最新狀態。
