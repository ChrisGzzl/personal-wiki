# 知识库运作原则

## 核心理念：Harness 原则

知识库系统的每个模块必须通过 Harness 四维度检验：

1. **存在成本 vs 触发收益** — 被动存在成本趋近于零，主动执行成本与收益成正比
2. **反馈闭环度** — 开环/半闭环/全闭环，核心是"反馈来源是否独立于执行者"
3. **触发确定性** — 确定性 > 条件性 > 概率性 > 祈祷式
4. **层次正确性** — 编译层只做编译，审计层只做审计，工具层不替代人工决策

## 三级模型：Capture → Compile → Promote

### Capture（采集）

**角色**：标签驱动的"黑洞"，零成本入库

- 触发：`#wiki` 关键字（确定性）或 `wiki capture` 命令（确定性）
- 反馈：开环（采集本身不产生质量判断）
- 存在成本：零

### Compile（编译）

**角色**：静默的"堆肥机"，LLM 粗加工

- 触发：`wiki compile` + guard（确定性，无新文件不执行）
- 反馈：半闭环（Promote 拒绝信号回灌 compile_feedback.md）
- 存在成本：低（仅处理增量）

### Promote（晋升）

**角色**：人工闸门，唯一的决策节点

- 触发：`wiki promote`（条件性，需要人工介入）
- 反馈：全闭环（人工确认 + 拒绝信号回灌）
- 存在成本：低

### Ask（查询）

**角色**：标签驱动的"按需取用"，零存在成本

- 触发：`#ask` 关键字（确定性）或 `wiki query` 命令（确定性）
- 反馈：开环（查询不修改知识库）
- 存在成本：零（不查不消耗）

## 触发矩阵

| 模块 | 触发 | 确定性 | 反馈闭环 | 存在成本 |
|------|------|--------|----------|----------|
| Capture (#wiki) | 标签触发 | 确定性 | 开环 | 零 |
| Capture (CLI) | 手动命令 | 确定性 | 开环 | 零 |
| Compile | raw/ 有新文件 + guard | 确定性 | 半闭环 | 低 |
| Promote | 人工审核 | 条件性 | 全闭环 | 低 |
| Ask (#ask) | 标签触发 | 确定性 | 开环 | 零 |
| Ask (CLI) | 手动命令 | 确定性 | 开环 | 零 |
| GC | 手动触发 | 确定性 | 开环 | 零 |

## 角色定义

### Curator Agent

建议指定你最信任的 agent 作为知识库的主动 Curator，承担以下职责：

1. **入库把关** — 所有进入 `wiki/` 的内容，由 Curator 审核确认
2. **主动沉淀** — 在日常工作中，发现优质内容主动整理写入知识库
3. **横向连接** — 判断新知识与已有知识的关联，必要时合并或交叉引用
4. **质量维护** — 定期回顾知识库，发现过时或不准的内容及时修正

### Wiki CLI 是辅助工具

- Wiki CLI 的 LLM 编译仅作为"第一道粗加工"
- 产出草稿进入 compiled/ 暂存区，由 Curator 确认后才正式沉淀到 wiki/
- 工具为 Curator 服务，不是 Curator 为工具服务

## 运作流程

```
#wiki 标记 / wiki capture → raw/           ← Capture
wiki compile (+ guard)        → compiled/   ← Compile
wiki promote (人工确认)        → wiki/       ← Promote
#ask 标记 / wiki query        ← wiki/       ← Ask
```

## 原则

- Curator agent 对知识库内容有完整的读写和管理权限
- 其他 agent 只读，不得直接执行 promote
- 频率只做排序，不做筛选（真正的闸门是人工确认）
- raw/ 不可变（Capture 写入后不修改，仅 GC 可归档/删除）
- 编译产出不直接写入 wiki/，必须经过 Promote
- `compile_feedback.md` 的拒绝信号必须回灌到 Compile 的 LLM prompt
- compile_feedback.md 是人类可读文件，用户可以直接查看和编辑

## 数据生命周期

- raw/ 文件 90 天未编译 → 归档到 raw/archive/
- raw/archive/ 文件再过 90 天 → 删除
- compiled/ 草稿 180 天未审核 → 自动拒绝，写入 compile_feedback.md
