"""Prompt templates for lint (health check) operation."""

LINT_SYSTEM = """你是一个知识库质量审计员。
你的职责是检查知识库的健康状况，发现问题并给出具体的修复建议。
输出必须是合法的 JSON，格式严格按照指定结构。"""


def build_lint_prompt(
    wiki_files_summary: str,
    index_content: str,
    schema_content: str,
    stale_days: int = 30,
) -> str:
    return f"""## 知识库规则
{schema_content[:1500]}

## wiki/index.md 当前内容
{index_content}

## 所有 wiki 条目摘要（路径 + frontmatter）
{wiki_files_summary}

---

请执行健康检查，输出以下 JSON：

```json
{{
  "summary": "健康状况一句话总结",
  "issues": [
    {{
      "type": "orphan_page",
      "severity": "warning",
      "path": "wiki/concepts/xxx.md",
      "description": "该条目没有被任何其他条目引用",
      "fix": "建议添加到相关条目的关联章节"
    }},
    {{
      "type": "broken_link",
      "severity": "error",
      "path": "wiki/concepts/yyy.md",
      "description": "引用了不存在的 [[nonexistent-page]]",
      "fix": "删除该链接或创建对应条目"
    }},
    {{
      "type": "stale_content",
      "severity": "info",
      "path": "wiki/topics/zzz.md",
      "description": "超过 {stale_days} 天未更新",
      "fix": "检查内容是否仍然有效"
    }}
  ],
  "stats": {{
    "total_pages": 0,
    "orphan_pages": 0,
    "broken_links": 0,
    "stale_pages": 0,
    "unresolved_contradictions": 0
  }},
  "index_sync_needed": false,
  "index_suggested_content": null
}}
```

issue type 枚举：orphan_page, broken_link, stale_content, unresolved_contradiction, 
duplicate_page, missing_index_entry, index_extra_entry
severity 枚举：error, warning, info

只输出 JSON，不要任何额外文字。"""
