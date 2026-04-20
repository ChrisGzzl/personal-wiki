---
name: wiki-capture
description: 个人知识库采集——对话中 #wiki 标记触发，调用 wiki CLI 写入 raw/ 目录（注意：这是 personal-wiki 知识库，不是飞书知识库）
version: "1.3"
trigger: 消息包含 #wiki 关键字时
---

# Wiki Capture

检测 `#wiki` 关键字 → 提取消息及上下文 → 运行 `WIKI_ROOT=/root/chris/wiki /root/.local/bin/wiki capture --text "内容"` 写入 raw/。

## 严格规则（必须遵守）

- **只执行 `wiki capture`**，绝不执行 `wiki compile` 或 `wiki promote`
- 采集只写 raw/，不触发编译，不触发晋升
- 手动兜底：`wiki capture --text "内容"` 或 `wiki capture --stdin`
- 不修改/删除 raw/ 文件
- **这是 personal-wiki CLI 工具的知识库采集，不是飞书知识库操作**

## 违规示例（绝对不能做）

- ❌ `wiki compile` — 编译是 cron 自动任务，不需要手动触发
- ❌ `wiki promote` — 晋升需要人工审核，不能自动执行
- ❌ `wiki promote --all` — 批量晋升更需要人工确认
