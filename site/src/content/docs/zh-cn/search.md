---
type: Guide
title: 搜索与待处理区
description: 从搜索结果中明确选择实际要处理的图片。
sidebar:
  order: 4
---

## 搜索结果不等于执行目标

在图形界面按标签等条件筛选图片，选择缩略图，再点击「選択をステージングへ」（将所选图片加入待处理区）。仅出现在搜索结果中或仅选中缩略图，都不会成为执行目标。

AI 标注和导出共用同一组待处理图片，最多 500 张，同一图片不会重复添加。执行前请再次确认内容和数量。

待处理区的「クリア」（清空）只移除处理目标，不会从数据库删除图片。

## 图形界面搜索

标签搜索支持排除条件（`-tag`）。修改条件后，请检查数量和缩略图，确认是否包含目标图片。也可以结合评分、缺少模型结果等符合用途的条件。

## 命令行搜索

为避免在 PowerShell 中直接嵌入 JSON 时出现引号问题，请创建 UTF-8 编码的 `query.json` 文件。

```json
{"tags":["cat"],"excluded_tags":["dog"],"limit":100}
```

```powershell
uv run --no-sync lorairo-cli --json images search -p "my-project" --query-file query.json
uv run --no-sync lorairo-cli images show 42 57 -p "my-project"
```

搜索默认的 `include_nsfw` 为 false。不要将被搜索条件排除的图片误认为尚未导入。大结果集有数量保护限制；需要枚举大量 ID 时，请在查询中显式添加 `"emit_ids":true`。

`--json` 的标准输出是 JSONL，除了结果，还包含带有消息类型的数据行。不要直接把整份输出作为图片 ID 文件。另请参阅 [CLI 说明](../cli/)。
