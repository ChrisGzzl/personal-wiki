---
name: wiki-ask
description: 知识库查询——对话中 #ask 标记触发查询
version: "1.0"
trigger: 消息包含 #ask 关键字时
---

# Wiki Ask

检测 `#ask` 关键字 → 提取问题及上下文 → `wiki query "问题"` 查询知识库 → 用📚标注知识库来源回答。

- 仅查询 wiki/，不写入任何文件
- 回答必须标注来源：📚=知识库，💡=AI补充
- 知识库无相关内容时，明确告知并仅用💡回答
- 手动兜底：`wiki query "问题"`
