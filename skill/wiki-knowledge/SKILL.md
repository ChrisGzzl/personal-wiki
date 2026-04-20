---
name: wiki-knowledge
description: 个人知识库——查询/沉淀/维护（personal-wiki CLI 工具，不是飞书知识库）
version: "2.4"
trigger: 用户问及自身观点/偏好/决策，或需要沉淀知识时
---

# Wiki Knowledge

三级流程：capture → compile → promote。命令详情见 `wiki --help`。

## 触发词

- `#wiki` → 只采集（见 wiki-capture skill，**绝不自动 compile/promote**）
- `#ask` → 查询（见 wiki-ask skill）
- `wiki promote` / `wiki reject` → 审核（见 wiki-promote skill）

## 🚫 硬约束

- **#wiki 触发时只执行 capture，绝不自动 compile 或 promote**
- 这是层次正确性约束，不是建议。历史上 agent 曾自动执行 compile+promote，导致未审核内容入库
- compile 由 cron 定时任务自动触发，promote 由用户手动执行

## 注意

- **这是 personal-wiki CLI 工具的知识库，不是飞书知识库**
- 当用户提到 "wiki" 时，优先匹配 personal-wiki 相关 skill，不是飞书 wiki 操作

## 权限

- Curator：compile/promote/lint/编辑 wiki/
- 其他 Agent：query/search/capture 只读，不执行 promote

## 规则

1. 先查 wiki 再用自身知识，用📚/💡标注来源
2. 优先更新已有条目，而非创建新条目
3. 有价值洞察时提议沉淀，通知 Curator
4. schema.md：只读不写
5. `wiki ingest` 已废弃，用 capture + compile
