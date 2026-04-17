---
name: wiki-capture
description: 知识库捕获技能——监听对话中的 #wiki 标记，自动提取上下文入库
version: "1.0"
trigger: 检测到 #wiki 关键字时自动激活
---

# Wiki Capture Skill

## 功能

在对话过程中自动捕获有价值的内容到知识库 raw/ 目录。用户只需在消息中标记 `#wiki`，系统自动提取上下文并保存。

## 触发条件

当消息中出现 `#wiki` 关键字时激活。关键字不区分大小写。

## 工作流程

1. **检测** — 扫描每条用户消息，匹配 `#wiki` 关键字
2. **提取** — 提取当前消息 + 前后 N 条上下文（默认 N=3）
3. **格式化** — 生成带 frontmatter 的 markdown 文件
4. **保存** — 写入 `$WIKI_ROOT/raw/notes/`

## 操作方式

```bash
# 自动触发（对话中包含 #wiki）
# 无需手动操作

# 手动兜底
wiki capture --text "内容"
wiki capture --stdin
```

## 上下文提取规则

- 提取标记消息前后各 N 条对话（N 默认 3，可通过 config 配置）
- 上下文格式：
  ```
  ## 上下文（前3条）
  [User]: xxx
  [Assistant]: xxx
  ...

  ## 标记内容
  [User]: 这段内容很重要 #wiki

  ## 上下文（后3条）
  [Assistant]: xxx
  ...
  ```

## 输出格式

文件保存到 `$WIKI_ROOT/raw/notes/`，frontmatter 格式：

```yaml
---
title: "Captured 2026-04-17"
source: "openclaw"
capture_trigger: "#wiki"
date_added: "2026-04-17"
captured_at: "2026-04-17T10:30:00Z"
conversation_id: "conv-xxx"
tags: []
---
```

## 与 wiki-knowledge 的关系

- **wiki-capture**（本技能）：负责自动采集，零成本入库
- **wiki-knowledge**：负责查询和沉淀，与采集互补

两者可同时部署在同一 agent 上，互不冲突。

## 配置

在 `$WIKI_ROOT/config.yaml` 中可配置：

```yaml
capture:
  context_depth: 3      # 前后各提取多少条上下文
  keyword: "#wiki"      # 触发关键字
```

## 注意事项

- 采集只写入 raw/，不触发编译
- 编译需要单独运行 `wiki compile`
- 不要修改或删除 raw/ 中的文件
- 同一消息中多次出现 #wiki 只生成一个文件
