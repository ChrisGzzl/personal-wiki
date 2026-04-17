---
name: wiki-capture
description: 知识库捕获——对话中 #wiki 标记自动入库
version: "1.1"
trigger: 消息包含 #wiki 关键字时
---

# Wiki Capture

检测 `#wiki` 关键字 → 提取消息及上下文 → `wiki capture --text "内容"` 写入 raw/。

- 采集只写 raw/，不触发编译
- 手动兜底：`wiki capture --text "内容"` 或 `wiki capture --stdin`
- 不修改/删除 raw/ 文件
