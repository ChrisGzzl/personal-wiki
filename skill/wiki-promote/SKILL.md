---
name: wiki-promote
description: 个人知识库审核——对话中 wiki promote/reject 命令触发审核操作，调用 wiki CLI 执行（personal-wiki 工具，不是飞书知识库）
version: "1.1"
trigger: 消息包含 "wiki promote" 或 "wiki reject" 关键字时
---

# Wiki Promote

检测 `wiki promote` 或 `wiki reject` 命令 → 解析目标 → 执行 wiki CLI 操作 → 报告结果。

## 触发词

- `wiki promote <路径或标题>` — 晋升草稿入库
- `wiki promote --all` — 晋升所有待审核草稿
- `wiki reject <路径或标题> --reason "原因"` — 拒绝草稿

## 工作流程

1. 匹配触发词，提取命令参数
2. 如果用户给的是标题而非路径，先运行 `wiki promote`（无参数）列出待审核列表，从中匹配标题对应的路径
3. 执行对应 wiki CLI 命令
4. 报告操作结果

## 命令映射

| 用户输入 | CLI 命令 |
|---------|----------|
| `wiki promote <标题>` | `wiki promote <匹配到的路径>` |
| `wiki promote all` / `wiki promote --all` | `wiki promote --all` |
| `wiki reject <标题>` | `wiki promote --reject <匹配到的路径> --reason "未说明原因"` |
| `wiki reject <标题> 原因` | `wiki promote --reject <匹配到的路径> --reason "原因"` |

## 注意事项

- 所有命令需设置环境变量 `WIKI_ROOT=/root/chris/wiki`
- wiki CLI 路径：`/root/.local/bin/wiki`
- 如果匹配不到标题，列出当前待审核列表让用户确认
- **这是 personal-wiki 的知识库管理操作，与飞书知识库无关**
- 当用户说 "wiki promote/reject" 时，这是 personal-wiki CLI 命令，不要调用飞书 wiki API
