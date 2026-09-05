---
type: Guide
title: AI 標註與 Jobs
description: 區分本機推論、WebAPI 與 Provider Batch 的執行方式。
sidebar:
  order: 5
---

## 執行前確認

請確認待處理圖片與數量、使用的模型，以及輸出種類（tags、caption、score、rating）。可用模型依環境及服務供應商而異。

| 執行方式 | 處理位置與注意事項 |
| --- | --- |
| 本機模型 | 在本機推論；首次下載模型與標籤資料庫可能需要網路連線。 |
| WebAPI 同步執行 | 將目標圖片與提示詞傳送至外部供應商；請確認費用及傳送權限。 |
| Provider Batch | 將外部提交內容作為非同步工作處理；不是免費處理，也不是本機推論。 |

傳送機密圖片或第三方圖片前，請確認是否有權傳送。本應用程式不管理 API 費用上限。再次執行與重試可能產生額外請求。

## 在圖形介面執行

1. 選擇模型並確認目標圖片數量。
2. 選擇「同期実行」（同步執行）或「Batch API 実行」。模型是否符合 Batch 條件各不相同。
3. 在 Jobs 查看進度、完成與失敗狀態。
4. 完成後檢查圖片標籤與描述文字；失敗時先閱讀原因，再重試。

系統不會自動切換至其他供應商。取消 Batch 不一定能撤銷已完成的處理或已產生的費用。

## 以命令列同步執行

```powershell
uv run --no-sync lorairo-cli models list
uv run --no-sync lorairo-cli annotate run -p "my-project" --model "MODEL_ID" --image-id 42 --image-id 57
```

請將 `MODEL_ID` 換成清單中的模型 ID。重複使用 `--image-id` 指定圖片。`--batch-size` 是同步處理的分組大小，不是提交 Provider Batch 的選項。

## 管理 Provider Batch

命令列提供 `batch submit/list/status/fetch/import/cancel`。請用 `uv run --no-sync lorairo-cli batch --help` 及各子命令的 `--help` 確認參數。取得結果與匯入資料庫是不同操作；`import` 會更新專案資料庫。

並非所有供應商都支援 Batch。請勿公開含有 API 金鑰或圖片的結果檔案。
