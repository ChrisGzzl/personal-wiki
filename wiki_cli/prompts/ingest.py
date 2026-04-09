"""Prompt templates for ingest (compile) operation."""

INGEST_SYSTEM = """你是一个个人知识库编译器（LLM Wiki Compiler）。
你的职责是将原始素材"编译"成结构化的、可互相引用的知识条目。

"编译"不是简单摘要，而是：理解 → 提炼 → 关联 → 结构化。
最终产出是可以独立支撑问答的 Markdown 知识条目。

输出必须是合法的 JSON，格式严格按照指定结构。不要输出任何 JSON 之外的内容。"""


def build_ingest_prompt(
    raw_content: str,
    raw_filename: str,
    existing_index: str,
    schema_content: str,
    existing_wiki_stems: list[str] | None = None,
) -> str:
    # Build the existing pages reference block
    if existing_wiki_stems:
        stems_list = "\n".join(f"  - {s}" for s in sorted(existing_wiki_stems))
        wiki_pages_block = f"""## 当前已有的 wiki 条目文件名（stem）
以下是所有可以被 [[wikilink]] 引用的合法名称：
{stems_list}

"""
    else:
        wiki_pages_block = ""

    return f"""## 知识库规则（schema.md）
{schema_content}

## 当前知识库索引（wiki/index.md）
{existing_index}

{wiki_pages_block}## 待编译的新素材
文件名：{raw_filename}

{raw_content}

---

请分析上面的素材，并输出以下 JSON 结构：

```json
{{
  "summary": "一句话说明这个素材的核心内容",
  "actions": [
    {{
      "type": "create",
      "path": "wiki/concepts/xxx.md",
      "content": "完整的 Markdown 文件内容（含 frontmatter）"
    }},
    {{
      "type": "update",
      "path": "wiki/topics/yyy.md",
      "section": "## 关键观点",
      "append": "需要追加的内容（Markdown）"
    }}
  ],
  "journal_entry": "编译日志内容（Markdown，记录本次编译做了什么）",
  "affected_pages": ["wiki/concepts/xxx.md", "wiki/topics/yyy.md"]
}}
```

每个 wiki 条目的 frontmatter 格式：
```yaml
---
title: "条目标题"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
tags: ["tag1", "tag2"]
sources: ["来源描述或文件名"]
---
```

每个条目正文结构：
```
## 概述
（简洁说明）

## 关键观点
（要点列表）

## 与其他主题的关联
（使用 [[wikilink]] 格式引用）

## 来源与参考
（来源列表）
```

矛盾标注格式：`> ⚠️ 矛盾标注：...`
时效提醒格式：`> ⏰ 时效提醒：...`

wikilink 规则（严格遵守）：
- [[wikilink]] 中的名称必须是英文 kebab-case 文件名的 stem（不含 .md）
- 只能引用"当前已有的 wiki 条目文件名"列表中的名称，或本次 actions 中新建的条目名称
- 禁止使用中文、原始文件名、标题文字作为 wikilink
- 正确示例：[[ai-agent-self-evolution]]、[[knowledge-management]]
- 错误示例：[[AI Agent 自进化]]、[[知识管理]]、[[AI-Agent自进化工程哲学]]

其他规则：
- 如果素材与已有条目高度相关，优先更新已有条目而非创建新条目
- 文件名使用英文 kebab-case（如 knowledge-management.md）
- 只输出 JSON，不要有任何额外文字
"""
