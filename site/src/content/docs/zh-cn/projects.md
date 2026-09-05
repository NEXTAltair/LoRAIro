---
type: Guide
title: 项目与图片导入
description: 了解项目保存内容，安全地导入图片。
sidebar:
  order: 3
---

## 保存哪些内容

图片信息、AI 标注和编辑内容按项目管理。通常保存在 `lorairo_data/<project>_YYYYMMDD_NNN/`，其中包含 SQLite 数据库、`image_dataset/` 等。修改过配置的环境可能使用其他保存位置。

请区分原始图片文件夹与 LoRAIro 项目保存位置。备份需要包含整个项目，而不只是图片数据库。

## 在图形界面导入图片

1. 打开「検索」（搜索）选项卡。
2. 在「データセット」（数据集）下点击「選択」（选择），选取图片文件夹。
3. 等待导入完成，然后检查搜索结果和数量。

这里的「選択」用于选择导入来源文件夹，不是打开现有项目的按钮。请先用小型测试文件夹尝试，避免误导入整个不需要的目录。

## 在命令行中明确指定项目

```powershell
uv run --no-sync lorairo-cli project create "my-project"
uv run --no-sync lorairo-cli project list
uv run --no-sync lorairo-cli images register ./images --project "my-project"
uv run --no-sync lorairo-cli images list --project "my-project" --fetch
```

将 `my-project` 替换为自己的项目名。图片 ID 应从导入后的列表中确认，不要照搬指南中的示例 ID。

命令行导入默认跳过 pHash 相同的图片。只有确实需要重复导入时，才使用 `--include-duplicates`。

## 导入之后

仅导入图片不会自动执行标注或导出。请通过[搜索与待处理区](../search/)选择目标后再继续。不要同时通过图形界面和命令行执行导入、编辑等写入操作。
