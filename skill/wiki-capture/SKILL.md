---
name: wiki-capture
description: 个人知识库采集——对话中 #wiki 标记触发，调用 wiki CLI 写入 raw/ 目录（注意：这是 personal-wiki 知识库，不是飞书知识库）
version: "1.2"
trigger: 消息包含 #wiki 关键字时
---

# Wiki Capture

检测 `#wiki` 关键字 → 提取消息及上下文 → 运行 `WIKI_ROOT=/root/chris/wiki /root/.local/bin/wiki capture --text "内容"` 写入 raw/。

- 采集只写 raw/，不触发编译
- 手动兜底：`wiki capture --text "内容"` 或 `wiki capture --stdin`
- 不修改/删除 raw/ 文件
- **这是 personal-wiki CLI 工具的知识库采集，不是飞书知识库操作**
