---
type: Guide
title: 导出数据集
description: 从待处理区或图片 ID 创建训练用文件。
sidebar:
  order: 7
---

## 在图形界面导出

1. 确认待处理图片及数量。
2. 在「エクスポート」（导出）中选择分辨率和格式。
3. 检查导出用标签调整，执行「検証」（验证）。
4. 确认没有问题后执行「エクスポート」，并检查生成的图片和文本。

分辨率选项为 512、768、1024、1536。格式包括「TXT（タグ分離）」（标签分离）、「TXT（キャプション統合）」（描述文本合并）和「JSON」。请选择训练工具要求的格式。

临时排除输出与数据库 reject 不同。详情见[修改标签](../editing/)。

## 命令行使用图片 ID

当前 `export create` 不接受搜索筛选条件。请先搜索并确认目标 ID。旧版 `--tags cat` 示例已不能使用。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids-file ids.txt -o ./dataset
```

这两行是替代用法，`--image-ids` 与 `--image-ids-file` 不能同时指定。直接指定最多 500 个 ID。批量导出时，使用以换行或逗号分隔 ID 的 `ids.txt`。命令行会同时生成 TXT 和 JSON。

请使用空的专用输出目录，避免意外与现有数据集混合。执行后先检查文件数量、图片和标签，再用于训练。

## 按标签语言分开的数据集

多语言标签导出需在命令行中明确指定。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset --tag-language canonical --tag-language ja
```

指定多种语言时，会在 `canonical/`、`ja/` 等目录中各创建一份包含图片的完整数据集，因此需要更多可用空间。仅指定一种语言时，使用输出根目录。

没有已登记首选译文的标签会回退到 canonical 文本。此功能不会自动翻译描述文本。它与指南支持四种语言是不同功能，也不保证每个标签都有四种语言的译文。目前未提供通过图形界面导出多语言标签的操作流程。
