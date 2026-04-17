# personal-wiki

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/ChrisGzzl/personal-wiki?style=social)](https://github.com/ChrisGzzl/personal-wiki)

个人知识库 CLI 工具，基于 Karpathy 的 LLM Wiki 理念。

让 LLM "编译"知识，而不是每次"检索"知识。

## 核心理念

传统 RAG 是"开卷考试"——每次问题都重新翻原始文档。

这个工具让 LLM 先把材料读完、理解完、做好结构化笔记，之后基于笔记回答问题。知识会积累，好的回答会沉淀回知识库，形成飞轮效应。

v0.2.0 引入 **Harness 原则**驱动的三级模型：**Capture → Compile → Promote**。

## Harness 原则

1. **存在成本 vs 触发收益** — 被动存在成本趋近于零
2. **反馈闭环度** — 开环/半闭环/全闭环三分法
3. **触发确定性** — 确定性 > 条件性 > 概率性 > 祈祷式
4. **层次正确性** — 编译层不做审计，审计层不做编译

## 安装

```bash
git clone <repo> personal-wiki
cd personal-wiki
bash install.sh ~/wiki
```

脚本会交互式引导你完成：

1. 选择 LLM provider（Anthropic / OpenAI / 兼容接口）
2. 填写 model 和 API key
3. 自动生成 `config.yaml`
4. 自动写入 `WIKI_ROOT` 到 `~/.bashrc`

安装完直接可用，只需最后编辑一下 `~/wiki/schema.md` 填写你的个人偏好。

依赖：Python 3.10+

## 快速开始

```bash
export WIKI_ROOT=~/wiki

# 采集素材（零成本入库）
wiki capture --text "今天学到了一个重要概念..."
wiki capture --url "https://example.com/article"
wiki capture --file ~/Downloads/paper.md

# 编译（LLM 粗加工 → compiled/ 暂存区）
wiki compile

# 审核晋升（人工闸门 → wiki/ 正式知识库）
wiki promote              # 列出待审核草稿
wiki promote <file>       # 晋升指定草稿
wiki promote --reject <file> --reason "原因"  # 拒绝并反馈

# 查询
wiki query "我对知识管理的看法是什么？"
wiki query --deep "梳理 AI Agent 相关的知识脉络"

# 维护
wiki status
wiki lint
wiki gc                   # 垃圾回收
```

## 目录结构

工具代码（此仓库）与数据目录分离：

```
personal-wiki/    # 工具代码（进 git）
~/wiki/           # 知识库数据（不进 git，私人内容）
├── raw/          # 原始素材（Capture 写入，有 TTL）
│   └── archive/  # 90天未编译的归档
├── compiled/     # 编译暂存区（按年月归档）
│   └── 2026/04/
├── wiki/         # 正式知识库（Promote 确认后）
├── outputs/      # 问答存档
├── schema.md     # 知识库规则（个性化配置）
├── compile_feedback.md  # 编译反馈信号
└── config.yaml   # 工具配置
```

## 完整命令

| 命令 | 说明 |
|------|------|
| `wiki init [path]` | 初始化知识库 |
| `wiki capture --text "..."` | 采集文本到 raw/ |
| `wiki capture --url <url>` | 抓取 URL 到 raw/ |
| `wiki capture --file <path>` | 采集本地文件到 raw/ |
| `wiki capture --stdin` | 从 stdin 读取内容 |
| `wiki compile` | 编译 raw/ 新素材 → compiled/ |
| `wiki compile --file <path>` | 编译指定 raw 文件 |
| `wiki promote` | 列出待审核草稿（按频率排序） |
| `wiki promote <file>` | 晋升草稿到 wiki/ |
| `wiki promote --all` | 晋升所有草稿 |
| `wiki promote --reject <f> --reason "..."` | 拒绝草稿并反馈 |
| `wiki query "<question>"` | 查询知识库 |
| `wiki query --deep "<question>"` | 深度研究模式 |
| `wiki lint` | 健康检查 |
| `wiki lint --auto` | 健康检查 + 自动修复 index |
| `wiki status` | 状态概览（无 LLM 调用） |
| `wiki search "<keyword>"` | 全文搜索 |
| `wiki browse [path]` | 终端浏览 wiki |
| `wiki gc` | 垃圾回收（raw TTL + compiled 超时） |
| `wiki gc --dry-run` | 预览清理内容 |
| `wiki log` | 查看编译日志 |
| `wiki chat` | 交互式对话模式 |
| `wiki ingest` | [已废弃] 使用 capture + compile 替代 |

## 多模型配置（可选）

为不同操作指定不同模型，降低成本：

```yaml
# config.yaml
models:
  compile: "gpt-4o"        # 编译原始材料，需要强模型
  query: "gpt-4o-mini"    # 知识库问答，可用较快模型
  lint: "gpt-4o-mini"     # 健康检查，可用较弱模型
```

不填则全部使用 `llm.model`。

## Agent 集成（openclaw）

如果你使用 openclaw agent 框架，可以安装两个 skill：

```bash
# 安装采集 + 知识库技能
bash install-skill.sh
```

- **wiki-capture**：监听 `#wiki` 关键字，自动提取上下文入库到 raw/
- **wiki-knowledge**：查询、沉淀、维护知识库

默认搜索 `~/openclaw/orchestrator-framework` 和 `~/openclaw/parallel-framework` 下的所有 agents。也可以直接手动 symlink：

```bash
ln -s /path/to/personal-wiki/skill/wiki-capture /path/to/agent/skills/wiki-capture
ln -s /path/to/personal-wiki/skill/wiki-knowledge /path/to/agent/skills/wiki-knowledge
```

skill 的角色分工说明详见各 `SKILL.md`。

## 隐私设计

- API key 通过环境变量或本地 config.yaml 传入，不进 git
- `schema.md` 的个人偏好部分由你自己填写，模板只提供空白占位
- 知识库数据目录（`~/wiki/`）完全独立于此代码仓库
- `.gitignore` 已排除所有个人数据

## 适用规模

适合个人知识库场景（几十到几百篇文档）。超过千篇文档建议考虑 RAG 方案。
