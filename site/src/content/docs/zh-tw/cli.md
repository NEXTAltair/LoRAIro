---
type: Guide
title: 使用命令列
description: 在 PowerShell 確認命令與處理 JSONL 輸出。
sidebar:
  order: 9
---

## 確認命令

從儲存庫目錄使用已建立的環境執行。

```powershell
uv run --no-sync lorairo-cli --help
uv run --no-sync lorairo-cli images --help
uv run --no-sync lorairo-cli export create --help
uv run --no-sync lorairo-cli --json list-commands
uv run --no-sync lorairo-cli --json describe "images update"
```

`list-commands` 與 `describe` 可讓代理程式確認可用操作及參數。舊步驟中的參數若無法辨識，請與目前的 `--help` 比對。

## JSONL 模式

在命令前指定 `--json`，標準輸出便會每行輸出一個 JSON 物件。日誌與進度送到標準錯誤。請確認最後的 `result` 或 `error`。結束碼：成功為 0、輸入或驗證錯誤為 2、其他錯誤為 1。

也支援環境變數 `LORAIRO_CLI_JSON=1`，但互動使用時，明確旗標更容易看出意圖。

JSONL 不是單純的圖片 ID 清單。從搜尋結果擷取 ID 時，請檢查 `kind` 等結構，避免混入訊息資料列。

## 依目的查閱

- [建立專案與匯入圖片](../projects/)
- [使用 JSON 檔案搜尋](../search/)
- [模型清單與同步標註](../annotation/)
- [預覽後套用標籤編輯](../editing/)
- [使用圖片 ID 匯出](../export/)

命令列與圖形介面使用相同的專案資料。大量更新前請先備份，並避免與圖形介面同時寫入。開發者詳細契約請見 [CLI 參考文件](https://github.com/NEXTAltair/LoRAIro/blob/main/docs/cli.md)。
