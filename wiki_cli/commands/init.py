"""wiki init command - initialize knowledge base directory structure."""
from datetime import date
from pathlib import Path

import click
from rich.console import Console

console = Console()

SCHEMA_TEMPLATE = """\
# Wiki Schema
# 所有权：此文件由【人类】维护，Agent 只读不写。
# Agent 读取此文件以了解编译规则和用户偏好，但永远不应修改此文件。

## 身份与目标
你是我的个人知识库管理 Agent。你的职责是帮我维护一个结构化的、持续积累的个人知识库。
这个知识库的核心目的不是存储通用知识（LLM 已经知道的），而是维护：
- 我个人的认知框架和思维方式
- 我的兴趣图谱和研究方向
- 我独特的观点、判断和决策偏好
- 从我阅读的素材中提炼的、与我相关的洞察

## 目录结构（v0.2.0 三级模型）
- raw/        — 原始素材（Capture 写入，只增不改，有 TTL）
- compiled/   — 编译暂存区（Compile 产出，待审核草稿）
- wiki/       — 正式知识库（Promote 确认后才进入）
- outputs/    — 问答存档

## 三级流程
1. Capture — 采集素材到 raw/（#wiki 标签触发或手动 wiki capture）
2. Compile — 编译 raw/ 到 compiled/（wiki compile，LLM 粗加工）
3. Promote — 审核 compiled/ 并晋升到 wiki/（wiki promote，人工闸门）

## 编译规则
1. 每个概念/主题一个独立的 .md 文件，文件名用英文 kebab-case（如 knowledge-management.md）
2. 文件头部使用 YAML frontmatter：title、created、updated、tags、sources
3. 正文结构：## 概述 → ## 关键观点 → ## 与其他主题的关联 → ## 来源与参考
4. 使用 [[wikilink]] 格式做交叉引用
5. 发现素材之间的矛盾时，使用 `> ⚠️ 矛盾标注：...` 格式明确标出
6. 发现信息过时时，使用 `> ⏰ 时效提醒：...` 格式标注
7. 编译产出进入 compiled/ 暂存区，不直接写入 wiki/
8. 只有经过 Promote（人工确认）的内容才进入 wiki/
9. 每次编译后更新 wiki/index.md 和 journal/

## 问答规则
1. 回答问题时，优先基于 wiki/ 中已有的知识
2. 如果 wiki/ 中没有相关内容，结合 LLM 自身知识回答，但明确标注来源
3. 用 📚 标注来自知识库的内容，用 💡 标注 LLM 补充的内容

## Lint 规则
1. 检查孤立条目（没有被任何其他条目引用）
2. 检查死链接（引用了不存在的条目）
3. 检查超过 30 天未更新的条目
4. 检查 raw/ 中未被编译的素材
5. 检查标注了矛盾但未解决的条目
6. 检查 index.md 与实际文件结构的一致性

## 我的个人偏好与关注领域
<!-- 请在这里填写你的个人信息，Agent 会据此调整知识编译和回答的角度 -->
<!-- 例如：
- 我主要关注 AI/LLM 领域的工程实践
- 我的技术背景是后端开发
- 我偏好实用主义，重视可落地的方案而非纯理论
-->

（待填写）
"""

CONFIG_TEMPLATE = """\
# LLM Wiki 配置文件
# 注意：API key 通过环境变量读取，不要在此文件中填写密钥

llm:
  provider: "anthropic"
  model: "claude-3-5-sonnet-latest"
  api_key_env: "ANTHROPIC_API_KEY"
  max_tokens: 16000
  temperature: 0.3

# OpenAI 兼容接口示例（取消注释并修改）：
# llm:
#   provider: "openai"
#   base_url: "https://api.openai.com/v1"
#   model: "gpt-4o"
#   api_key_env: "OPENAI_API_KEY"

# 可选：为不同操作指定不同模型（不填则都使用 llm.model）
# models:
#   compile: "gpt-4o"        # 编译原始材料，需要强模型
#   query: "gpt-4o-mini"    # 知识库问答，可用较快模型
#   lint: "gpt-4o-mini"     # 健康检查，可用较弱模型

paths:
  wiki_root: "{wiki_root}"
  raw_dir: "raw"
  wiki_dir: "wiki"
  outputs_dir: "outputs"
  schema_file: "schema.md"
  state_file: ".wiki_state.json"
  compiled_dir: "compiled"
  compile_feedback_file: "compile_feedback.md"

behavior:
  lint_stale_days: 30
  max_raw_batch: 10
  language: "zh-CN"
  raw_archive_days: 90
  raw_delete_days: 180
"""

INDEX_TEMPLATE = """\
# 知识库索引

_最后更新：{today}_

（知识库为空，运行 `wiki compile` 编译素材、`wiki promote` 审核后自动更新此索引）
"""

COMPILE_FEEDBACK_TEMPLATE = """\
# Compile 反馈记录
# 此文件由 wiki promote --reject 自动追加，供 Compile 阶段参考
# 你也可以手动编辑此文件来引导 Compile 的行为
"""


def init_command(wiki_root: Path):
    """Initialize wiki directory structure."""
    wiki_root = wiki_root.expanduser().resolve()

    if wiki_root.exists() and any(wiki_root.iterdir()):
        console.print(f"[yellow]Warning:[/yellow] {wiki_root} already exists and is not empty.")
        if not click.confirm("Continue initialization anyway?", default=False):
            return

    console.print(f"\n[bold]Initializing wiki at[/bold] {wiki_root}\n")

    # Create directory structure
    dirs = [
        wiki_root / "raw" / "articles",
        wiki_root / "raw" / "papers",
        wiki_root / "raw" / "notes",
        wiki_root / "raw" / "images",
        wiki_root / "raw" / "misc",
        wiki_root / "raw" / "archive",
        wiki_root / "compiled",
        wiki_root / "wiki" / "concepts",
        wiki_root / "wiki" / "topics",
        wiki_root / "wiki" / "people",
        wiki_root / "wiki" / "meta",
        wiki_root / "wiki" / "journal",
        wiki_root / "outputs",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]created[/dim] {d.relative_to(wiki_root)}/")

    # Write schema.md
    schema_path = wiki_root / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(SCHEMA_TEMPLATE, encoding="utf-8")
        console.print(f"\n  [green]✓[/green] schema.md — edit this to set your preferences")

    # Write config.yaml
    config_path = wiki_root / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            CONFIG_TEMPLATE.format(wiki_root=str(wiki_root)),
            encoding="utf-8",
        )
        console.print(f"  [green]✓[/green] config.yaml")

    # Write compile_feedback.md
    feedback_path = wiki_root / "compile_feedback.md"
    if not feedback_path.exists():
        feedback_path.write_text(COMPILE_FEEDBACK_TEMPLATE, encoding="utf-8")
        console.print(f"  [green]✓[/green] compile_feedback.md")

    # Write wiki/index.md
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text(
            INDEX_TEMPLATE.format(today=date.today().isoformat()),
            encoding="utf-8",
        )
        console.print(f"  [green]✓[/green] wiki/index.md")

    # Write .gitignore for the data dir (for users who version their wiki)
    gitignore_path = wiki_root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "# Personal data - adjust as needed\n"
            ".wiki_state.json\n",
            encoding="utf-8",
        )

    console.print(f"""
[bold green]✓ Wiki initialized at {wiki_root}[/bold green]

Next steps:
  1. Edit [cyan]{wiki_root}/schema.md[/cyan] — fill in your personal preferences
  2. Configure LLM in [cyan]{wiki_root}/config.yaml[/cyan]
  3. Capture content: [cyan]wiki capture --text "..."[/cyan] or use #wiki in chat
  4. Compile: [cyan]wiki compile[/cyan]
  5. Review & promote: [cyan]wiki promote[/cyan]
""")
