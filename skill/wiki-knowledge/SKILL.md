---
name: wiki-knowledge
description: 个人知识库——查询/沉淀/维护
version: "2.1"
trigger: 用户问及自身观点/偏好/决策，或需要沉淀知识时
---

# Wiki Knowledge

三级流程：capture → compile → promote。命令详情见 `wiki --help`。

## 权限

- Curator：compile/promote/lint/编辑 wiki/
- 其他 Agent：query/search/capture 只读，不执行 promote

## 规则

1. 先查 wiki 再用自身知识，用📚/💡标注来源
2. 优先更新已有条目，而非创建新条目
3. 有价值洞察时提议沉淀，通知 Curator
4. schema.md：只读不写
5. `wiki ingest` 已废弃，用 capture + compile
