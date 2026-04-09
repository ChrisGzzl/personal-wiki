"""Prompt templates for query operation."""

QUERY_SYSTEM = """你是一个基于个人知识库回答问题的助手。
你有两个知识来源：
1. 用户的个人知识库（wiki 条目）—— 优先使用
2. 你自身的通用知识 —— 作为补充，但必须明确标注

在回答中，用以下标记区分来源：
- 📚 **来自知识库**：...（来源于 wiki 条目）
- 💡 **LLM 补充**：...（来源于模型自身知识）

如果回答中包含有价值的新洞察，在末尾建议用户沉淀回 wiki。"""


def build_query_prompt(
    question: str,
    wiki_context: str,
    schema_content: str,
    deep: bool = False,
) -> str:
    mode_note = ""
    if deep:
        mode_note = "\n\n**深度研究模式**：请生成一篇结构完整的长文，梳理相关知识脉络。"

    return f"""## 用户的知识库规则（schema.md 节选）
{schema_content[:2000]}

## 相关知识库条目
{wiki_context}

---

## 用户问题
{question}{mode_note}

请基于上面的知识库内容回答。如知识库内容不足，可补充通用知识但需标注。
回答结束后，如果有值得沉淀的新洞察，请在末尾加一行：

---
💾 **建议沉淀**：（一句话描述可以沉淀什么内容）"""
