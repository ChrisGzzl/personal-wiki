---
name: wiki-knowledge
description: 个人知识库管理技能——查询、沉淀、维护 LLM Wiki 知识库
version: "1.1"
trigger: 当需要查询用户个人认知、历史决策、思维偏好，或需要沉淀新知识时自动激活
---

# Wiki Knowledge Base Skill

## 角色与分工

本知识库有明确的角色分工，参见 `PRINCIPLES.md`：

- **Curator Agent** — 核心 Curator，对知识库内容有完整的读写和管理权限。所有进入 `wiki/` 的内容由 Curator 审核确认后才正式沉淀。
- **Wiki CLI** — 辅助工具，负责"粗加工"：把原始素材编译成草稿，供 Curator 审核。
- **其他 Agent** — 只读权限，可查询、可建议沉淀，但不应直接写入 `wiki/`。

**如果你是 Curator**：你有完整的 curator 权限，可以直接执行 ingest/promote/lint，也可以跳过工具直接编辑 wiki 条目。

**如果你是其他 Agent**：遇到值得沉淀的内容，通知 Curator 或告知用户，由 Curator 决定是否入库。不要自行执行 promote。

## 标准工作流

```
素材 → wiki ingest（CLI 粗加工）→ Curator 审核 → wiki promote（确认入库）
工作对话中的优质内容 → Curator 直接判断入库
```

## 何时使用知识库

**主动查询（Query）**，当用户问：
- 关于他/她自己的观点、偏好、认知框架
- "我之前对 XX 的看法是什么？"
- 需要参考用户历史决策或项目背景的问题

**主动沉淀（Ingest）**，当：
- 用户分享了有价值的文章、论文、想法
- 对话中产生了重要洞察或决策
- 用户明确要求记录某个内容

**提醒维护（Lint/Status）**，当：
- 用户问知识库状态
- 长时间（>7天）未见 ingest 操作

## 操作方式

所有操作通过 shell 命令执行：

```bash
# 查询知识库
wiki query "用户的问题"
wiki query --deep "需要深度分析的问题"

# 粗加工（任何 agent 均可触发）
wiki ingest --text "需要沉淀的内容"
wiki ingest --url "https://..."
wiki ingest  # 编译 raw/ 中的新文件

# 审核入库（Curator 专属）
wiki promote <output-file>        # 交互式 review 后确认入库
wiki promote --dry-run <file>     # 只看预览，不写入

# 状态与维护
wiki status
wiki lint
wiki log --last 3

# 搜索
wiki search "关键词"
```

## 操作优先级

1. 优先查询 wiki，再结合自身知识回答
2. 优先更新已有条目，而非创建冗余新条目
3. 问答中出现有价值的新洞察时，主动提议沉淀（通知 Curator）

## 环境要求

- `wiki` CLI 已安装（`pip install -e /path/to/personal-wiki`）
- `WIKI_ROOT` 环境变量已设置，指向知识库数据目录
- LLM API key 配置在 `$WIKI_ROOT/config.yaml`

## 注意事项

- 知识库是用户的私人内容，不要将其内容发送给第三方
- 编译操作会消耗 API token，避免重复编译相同内容
- 不要自动删除任何 wiki 条目，只标记或标注问题

## schema.md 所有权规则（重要）

`$WIKI_ROOT/schema.md` 是用户的人工配置文件，定义了知识库的编译规则和个人偏好。

**所有 Agent 对 schema.md 的权限是：只读，永不修改。**

原因：
- schema.md 里的"个人偏好"部分决定了 LLM 如何理解和编译知识，是高度主观的人类判断
- 如果 agent 自行修改 schema.md，会产生偏差漂移（drift），且很难察觉
- 如果用户要求修改 schema.md，提示他直接手动编辑

你唯一应该对 schema.md 做的操作：读取以了解规则（`cat $WIKI_ROOT/schema.md`）。
