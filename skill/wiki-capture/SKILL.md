---
name: wiki-capture
description: 个人知识库采集——对话中 #wiki 标记触发，调用 wiki CLI 写入 raw/ 目录（注意：这是 personal-wiki 知识库，不是飞书知识库）
version: "1.4"
trigger: 消息包含 #wiki 关键字时
---

# Wiki Capture

检测 `#wiki` 关键字 → 提取消息及上下文 → 运行 `WIKI_ROOT=/root/chris/wiki /root/.local/bin/wiki capture --text "内容"` 写入 raw/。

## 🚫 硬约束（违反 = 严重错误）

**capture 只做采集，绝不编译、绝不晋升。** 这不是建议，是系统的层次正确性约束。

- ✅ `wiki capture --text "内容"` — 唯一允许的命令
- ✅ `wiki capture --stdin` — 手动兜底
- ❌ `wiki compile` — **绝对禁止**。编译由 cron 定时任务自动触发
- ❌ `wiki promote` — **绝对禁止**。晋升需要人工审核
- ❌ `wiki promote --all` — **绝对禁止**。批量晋升更需要人工确认
- ❌ 任何 "采集并编译"、"找到草稿正在晋升" 等自动后续操作 — **绝对禁止**

## 为什么不能自动编译/晋升？

1. **层次正确性**：Capture 层只负责采集，Compile 和 Promote 是独立层次，有各自的触发条件
2. **人工审核是核心**：promote 需要人判断价值，agent 自动 promote 等于跳过了质量关卡
3. **历史教训**：agent 曾在 #wiki 后自动执行 compile + promote，导致未审核内容直接入库

## 正确流程

用户说 `#wiki` → 你只做 `wiki capture` → 回复"已采集到 raw/" → 结束。
编译由 cron 自动完成，晋升由用户手动执行 `wiki promote`。
