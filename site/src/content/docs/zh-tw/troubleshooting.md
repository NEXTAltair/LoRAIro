---
type: Guide
title: 設定、備份與疑難排解
description: 保護機密資訊與專案，排查復原時的問題。
sidebar:
  order: 8
---

## 設定

在 GUI 的「設定」（Ctrl+,）查看設定。`config/lorairo.toml` 包含儲存位置及 API 金鑰等資訊。請勿公開 API 金鑰、完整設定檔，或顯示私人圖片路徑的螢幕擷取畫面。

主要設定包括 API 金鑰、專案與匯出及 Batch 結果位置、額外提示詞、模型連線路由、資料庫等待時間與日誌層級。復原時請確認是否殘留原電腦的絕對路徑。

## 備份

1. 結束 GUI、CLI、Batch 匯入等會寫入資料庫的程序。
2. 將實際儲存位置的整個專案複製到別處，通常位於 `lorairo_data/`。
3. 除了 `image_database.db`，也保存 `image_dataset/`、使用者標籤資料庫（`user_tags.sqlite`）等內容。
4. 將 `config/lorairo.toml` 及必要的 Batch 結果視為機密資訊，另外保存。

避免只複製使用中的 SQLite 資料庫檔案。復原時不要覆寫備份原本；請使用復原副本檢查圖片、標籤與設定。

## 啟動或相依套件錯誤

Windows 與 Linux 的 `.venv` 不同。不要直接使用從另一個作業系統複製的環境，應在目標系統安裝相依套件。重建共用環境前，先停止使用中的應用程式、測試與代理程式。

GUI 未顯示時，請確認 Windows 是否設定了 `QT_QPA_PLATFORM=offscreen`。容器測試使用 offscreen 則是正常情況。

## 無法辨識 GPU

```powershell
nvidia-smi
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
```

預期使用 GPU 卻顯示 false 時，請檢查驅動程式、GPU 相容性與 PyTorch 環境。刪除應用程式資料無法解決 GPU 設定問題。

## 資料庫衝突與外部連線

出現 `CONFLICT` 時，請等待其他寫入作業結束後再試。不要同時用 GUI 與 CLI 寫入。首次取得標籤資料庫失敗時，請檢查網路，必要時確認 Hugging Face 驗證設定。

WebAPI 錯誤請檢查驗證、用量上限、模型支援及傳送限制，先調查原因再重複操作。

## 回報問題

請附上操作步驟、作業系統、重現條件及一小段相關日誌。主要日誌為 `logs/lorairo.log`、`logs/image-annotator-lib.log`、`logs/lorairo-cli.log`。請遮蔽 API 金鑰、個人資訊與不希望公開的圖片路徑。
