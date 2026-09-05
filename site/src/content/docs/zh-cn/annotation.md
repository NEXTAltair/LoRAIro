---
type: Guide
title: AI 标注与 Jobs
description: 区分本地推理、WebAPI 和 Provider Batch 的执行方式。
sidebar:
  order: 5
---

## 执行前检查

请确认待处理图片及数量、使用的模型，以及生成类型（tags、caption、score、rating）。可用模型因环境和服务提供商而异。

| 执行方式 | 处理位置和注意事项 |
| --- | --- |
| 本地模型 | 在本地进行推理；首次下载模型或标签数据库可能需要联网。 |
| WebAPI 同步执行 | 将目标图片和提示词发送到外部提供商；请确认费用和发送权限。 |
| Provider Batch | 将外部提交内容作为异步任务处理；不是免费处理，也不是本地推理。 |

发送机密图片或第三方图片前，请确认是否有权发送。应用不管理 API 费用上限。重新执行和重试可能产生额外请求。

## 在图形界面执行

1. 选择模型并确认目标图片数量。
2. 选择「同期実行」（同步执行）或「Batch API 実行」。是否符合 Batch 条件取决于模型。
3. 在 Jobs 中检查进度、完成和失败状态。
4. 完成后检查图片标签和描述文本。失败时请先阅读原因，再重试。

系统不会自动切换到其他提供商。取消 Batch 不一定能撤销已经完成的处理或已经产生的费用。

## 在命令行同步执行

```powershell
uv run --no-sync lorairo-cli models list
uv run --no-sync lorairo-cli annotate run -p "my-project" --model "MODEL_ID" --image-id 42 --image-id 57
```

将 `MODEL_ID` 替换为列表中的模型 ID。重复使用 `--image-id` 指定图片。`--batch-size` 是同步处理的分块大小，不是提交 Provider Batch 的选项。

## 管理 Provider Batch

命令行提供 `batch submit/list/status/fetch/import/cancel`。请使用 `uv run --no-sync lorairo-cli batch --help` 及各子命令的 `--help` 确认参数。获取结果和导入数据库是两个不同操作；`import` 会更新项目数据库。

并非所有提供商都支持 Batch。不要公开含有 API 密钥或图片的结果文件。
