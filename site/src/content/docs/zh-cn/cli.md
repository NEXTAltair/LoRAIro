---
type: Guide
title: 使用命令行
description: 在 PowerShell 中确认命令并处理 JSONL 输出。
sidebar:
  order: 9
---

## 确认命令

从仓库目录使用已创建的环境执行。

```powershell
uv run --no-sync lorairo-cli --help
uv run --no-sync lorairo-cli images --help
uv run --no-sync lorairo-cli export create --help
uv run --no-sync lorairo-cli --json list-commands
uv run --no-sync lorairo-cli --json describe "images update"
```

`list-commands` 和 `describe` 可让智能体确认可用操作及参数。如果旧步骤中的参数无法识别，请与当前的 `--help` 对照。

## JSONL 模式

在命令前指定 `--json` 后，标准输出每行包含一个 JSON 对象。日志和进度写入标准错误。请检查最后的 `result` 或 `error`。退出码为：成功 0，输入或验证错误 2，其他错误 1。

也支持环境变量 `LORAIRO_CLI_JSON=1`，但交互使用时，显式标志更容易体现意图。

JSONL 不是单纯的图片 ID 列表。从搜索结果提取 ID 时，请检查 `kind` 等结构，避免混入消息行。

## 按目的查阅

- [创建项目与导入图片](../projects/)
- [使用 JSON 文件搜索](../search/)
- [模型列表与同步标注](../annotation/)
- [预览后应用标签编辑](../editing/)
- [使用图片 ID 导出](../export/)

命令行和图形界面使用相同的项目数据。批量更新前请备份，不要与图形界面同时写入。开发者详细约定见 [CLI 参考文档](https://github.com/NEXTAltair/LoRAIro/blob/main/docs/cli.md)。
