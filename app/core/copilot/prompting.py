# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Prompt construction and turn-intent helpers for copilot."""

from __future__ import annotations

import re
from string import Template
from typing import Any

from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.language import get_language_fallback_chain
from app.models import WorldEntity, WorldRelationship, WorldSystem

_QUICK_ACTION_FOCUS_ZH: dict[str, str] = {
    "scan_world_gaps": "重点找出世界模型中尚未覆盖但章节反复提到的设定、组织或概念。",
    "trace_recurring_signals": "重点追踪章节中反复出现但尚未入模的高频信号和规律。",
    "find_world_conflicts": "重点排查当前世界模型中可能存在的设定矛盾和冲突。",
    "complete_entity": "围绕目标实体，优先补全描述、属性、别名和约束。",
    "find_relations": "围绕目标实体，搜索章节中的关系线索并提出可确认的关系建议。",
    "collect_entity_evidence": "围绕目标实体，从章节中收集关键证据片段。",
    "label_relationships": "检查现有关系标签是否语义一致，提出统一建议。",
    "collect_interactions": "从章节中汇总与目标实体相关的互动场景。",
    "review_drafts": "审查草稿中最值得优先处理的条目。",
    "normalize_terms": "检查草稿中的命名一致性并提出统一建议。",
    "fill_missing_fields": "找出草稿中缺失的关键字段并给出补全建议。",
}
_QUICK_ACTION_FOCUS_EN: dict[str, str] = {
    "scan_world_gaps": "Focus on world details, organizations, or concepts that chapters mention repeatedly but the world model still does not cover.",
    "trace_recurring_signals": "Focus on recurring high-frequency signals and patterns that appear in chapters but are not yet modeled.",
    "find_world_conflicts": "Focus on possible setting contradictions or conflicts inside the current world model.",
    "complete_entity": "Focus on the target entity first: fill in description, attributes, aliases, and constraints.",
    "find_relations": "Focus on the target entity: search chapter evidence for relationship clues and propose confirmable relationships.",
    "collect_entity_evidence": "Focus on the target entity and collect key evidence snippets from chapters.",
    "label_relationships": "Check whether existing relationship labels are semantically consistent and propose a normalized naming scheme.",
    "collect_interactions": "Collect interaction scenes related to the target entity from across the chapters.",
    "review_drafts": "Review the draft rows that are most worth handling first.",
    "normalize_terms": "Check naming consistency in drafts and suggest normalization.",
    "fill_missing_fields": "Find key missing draft fields and propose concrete completions.",
}

_TASK_INTENT_HINTS = (
    "梳理", "整理", "补完", "补充", "查", "看看", "看下", "解释", "分析", "列出", "找出",
    "核查", "确认", "review", "inspect", "analyze", "explain", "help me", "find", "summarize",
)
_CAPABILITY_HINTS = (
    "你能做什么", "你可以做什么", "现在能做什么", "能帮我什么", "你会做什么", "当前界面",
    "我现在在哪", "这个页面你能干嘛", "what can you do", "what can you help", "where am i",
)
_GREETING_NORMALIZED = {
    "你好", "您好", "hi", "hello", "hey", "在吗", "早上好", "晚上好", "中午好", "thanks", "thankyou", "谢谢",
}
_PUNCTUATION_RE = re.compile(r"[\s\.,!?！？。，、~～…·`'\"“”‘’:：;；\-_/\(\)\[\]{}]+")

_SURFACE_LABELS = {
    "studio": "Studio",
    "atlas": "Atlas",
}
_STAGE_LABELS_ZH = {
    "entity": "实体检查",
    "relationship": "关系检查",
    "review": "草稿审核",
    "write": "写作工作台",
    "entities": "实体页",
    "relationships": "关系页",
    "systems": "体系页",
}
_STAGE_LABELS_EN = {
    "entity": "Entity review",
    "relationship": "Relationship review",
    "review": "Draft review",
    "write": "Writing workspace",
    "entities": "Entities",
    "relationships": "Relationships",
    "systems": "Systems",
}
_PROFILE_LABELS_ZH: dict[str, str] = {
    "focused_research": "聚焦研究",
    "draft_governance": "草稿治理",
    "broad_exploration": "全书探索",
}
_PROFILE_LABELS_EN: dict[str, str] = {
    "focused_research": "Focused research",
    "draft_governance": "Draft governance",
    "broad_exploration": "Whole-book exploration",
}
_FOCUS_LABELS_ZH = {
    "whole_book": "全书研究",
    "entity": "实体补完",
    "relationship": "关系梳理",
    "draft": "草稿整理",
}
_FOCUS_LABELS_EN = {
    "whole_book": "Whole-book research",
    "entity": "Entity completion",
    "relationship": "Relationship review",
    "draft": "Draft cleanup",
}
_FOCUS_CAPABILITIES_ZH: dict[str, list[str]] = {
    "whole_book": [
        "回答当前世界模型相关的问题",
        "指出值得继续研究的设定/线索",
        "按你的要求再进入全书级检索或建议模式",
    ],
    "entity": [
        "解释当前实体在这个界面下的已知信息",
        "围绕当前实体补充设定、属性和依据",
        "在你明确要求时生成实体建议卡",
    ],
    "relationship": [
        "解释当前关系视图里已有连接和含义",
        "围绕当前焦点梳理关系线索或缺口",
        "在你明确要求时生成关系建议卡",
    ],
    "draft": [
        "解释当前草稿整理界面能处理哪些问题",
        "帮助检查命名统一、缺失字段和弱候选",
        "在你明确要求时生成草稿整理建议卡",
    ],
}
_FOCUS_CAPABILITIES_EN: dict[str, list[str]] = {
    "whole_book": [
        "Answer questions about the current world model",
        "Point out settings or clues worth researching next",
        "Enter whole-book retrieval or suggestion mode when you ask for it",
    ],
    "entity": [
        "Explain what is already known about the current entity in this workspace",
        "Fill in the entity's setting details, attributes, and supporting evidence",
        "Generate entity suggestion cards when you explicitly ask for them",
    ],
    "relationship": [
        "Explain the existing connections and meanings in the current relationship view",
        "Trace relationship clues or gaps around the current focus",
        "Generate relationship suggestion cards when you explicitly ask for them",
    ],
    "draft": [
        "Explain what this draft-cleanup workspace can help with",
        "Check naming consistency, missing fields, and weak candidates",
        "Generate draft-cleanup suggestion cards when you explicitly ask for them",
    ],
}
_PROFILE_INSTRUCTIONS_ZH: dict[str, str] = {
    "broad_exploration": (
        "当前运行 profile 是全书探索。把 auto-preload 视为一层薄概览，而不是完整证据。"
        "默认先用工具扩大检索范围，再决定是否形成建议。不要因为薄概览就武断下结论。"
    ),
    "focused_research": (
        "当前运行 profile 是聚焦研究。把当前焦点实体及其直接相关对象当作主工作集。"
        "不要主动把无关的全局体系、远距离实体或其他话题拖进回答；如确实需要扩展，先通过工具检索再说明理由。"
    ),
    "draft_governance": (
        "当前运行 profile 是草稿治理。把当前 draft rows 当作主工作集。"
        "优先做命名统一、字段补全和弱候选审查，不要漂移到全书发散探索，也不要给 confirmed 行产出直接可应用的编辑。"
    ),
}
_PROFILE_INSTRUCTIONS_EN: dict[str, str] = {
    "broad_exploration": (
        "The current run profile is whole-book exploration. Treat auto-preload as a thin overview, not as complete evidence. "
        "Default to using tools to widen retrieval before deciding whether suggestions are justified. Do not jump to conclusions from the thin overview alone."
    ),
    "focused_research": (
        "The current run profile is focused research. Treat the current focus entity and its directly related objects as the main working set. "
        "Do not pull in unrelated global systems, distant entities, or off-topic material unless tools show they are needed."
    ),
    "draft_governance": (
        "The current run profile is draft governance. Treat the current draft rows as the main working set. "
        "Prioritize naming normalization, field completion, and weak-candidate review. Do not drift into whole-book exploration and do not produce directly applicable edits for confirmed rows."
    ),
}
_FOCUS_INSTRUCTIONS_ZH: dict[str, str] = {
    "whole_book": (
        "用户正在进行全书研究。从全局角度分析世界模型状态。"
        "重点关注：设定缺口、高频线索、冲突风险。"
        "默认以分析和证据为主。只有当你发现有足够证据支撑的具体修改建议时，才输出 suggestions。"
        "没有 suggestions 也是正常结果。"
    ),
    "entity": (
        "用户正在研究一个特定实体。围绕该实体进行补完和核查。"
        "实体不只包括人物，也可能是势力、地点、组织、物件、概念或规则载体。"
        "重点关注：类别、别名、描述、属性（key-value对）、约束、关系线索。"
        "只有当证据明确指向人物时才使用 Character；否则请选择更贴切的类型。"
        "优先基于章节证据给出具体的补完建议。"
    ),
    "relationship": (
        "用户正在研究实体的关系网络。围绕中心实体梳理关系。"
        "重点关注：缺失连接、关系标签统一、互动证据、关系描述补全。"
        "给出少量可信、有证据支撑的关系建议。"
        "suggestions 应以 update_relationship 或 create_relationship 为主。"
    ),
    "draft": (
        "用户正在整理草稿。审查草稿行并提出改善建议。"
        "重点关注：命名统一、缺失字段补全、弱候选标记。"
        "只能对已有草稿行做非破坏性的局部编辑建议。不要建议删除、合并或拆分。"
        "你的 suggestions 里的 target_id 必须指向草稿行的 ID。"
        "不要创建新实体（create_entity），只更新现有草稿。"
    ),
}
_FOCUS_INSTRUCTIONS_EN: dict[str, str] = {
    "whole_book": (
        "The user is researching the novel as a whole. Analyze the world model from a global perspective. "
        "Focus on setting gaps, recurring signals, and conflict risk. Default to analysis plus evidence. Only output suggestions when the evidence clearly supports concrete edits. No suggestions is a normal outcome."
    ),
    "entity": (
        "The user is researching a specific entity. Fill in and verify that entity. "
        "Entities are not limited to people; they can also be factions, locations, organizations, objects, concepts, or rule-bearing constructs. "
        "Focus on type, aliases, description, attributes (key-value pairs), constraints, and relationship clues. Only use Character when the evidence clearly points to a person."
    ),
    "relationship": (
        "The user is researching an entity's relationship graph. Organize relationships around the central entity. "
        "Focus on missing links, label normalization, interaction evidence, and relationship-description completion. "
        "Provide a small number of trustworthy relationship suggestions backed by evidence. Suggestions should primarily be update_relationship or create_relationship."
    ),
    "draft": (
        "The user is cleaning up drafts. Review draft rows and propose improvements. "
        "Focus on naming normalization, missing-field completion, and weak-candidate marking. "
        "Only make non-destructive local edit suggestions against existing draft rows. Do not suggest delete, merge, or split operations. target_id values in suggestions must point to draft-row IDs, and you must not create new entities in this mode."
    ),
}
_FOCUS_WORKFLOW_HINTS_ZH: dict[str, str] = {
    "whole_book": (
        "1. 先浏览 auto-preload 中的薄概览，不要把它当作完整证据\n"
        "2. 用 find(query=<关键词>, scope='all') 搜索感兴趣的主题\n"
        "3. 用 open(pack_id) 展开关键证据\n"
        "4. 收集足够证据后输出最终回答"
    ),
    "entity": (
        "1. 先浏览 auto-preload 中的目标实体信息\n"
        "2. 用 find(query=<实体名>) 搜索章节证据\n"
        "3. 用 read(target_refs=[...]) 读取实体当前完整状态\n"
        "4. 用 open(pack_id) 展开关键证据段落\n"
        "5. 基于证据输出补完建议"
    ),
    "relationship": (
        "1. 先浏览 auto-preload 中的关系列表\n"
        "2. 用 find(query=<中心实体名>) 搜索与该实体相关的章节证据\n"
        "3. 用 read(target_refs=[...]) 读取相关实体和已有关系\n"
        "4. 基于证据提出关系补全或修正建议"
    ),
    "draft": (
        "1. 先浏览 auto-preload 中的 Draft entities/relationships/systems 列表\n"
        "2. 用 find(query=<草稿名称>, scope='drafts') 查找草稿质量信号\n"
        "3. 用 find(query=<草稿名称>, scope='story_text') 搜索正文证据来补全草稿\n"
        "4. 用 read(target_refs=[...]) 读取草稿行的完整状态\n"
        "5. 基于证据对草稿提出命名统一、字段补全建议"
    ),
}
_FOCUS_WORKFLOW_HINTS_EN: dict[str, str] = {
    "whole_book": (
        "1. Start with the thin auto-preload overview; do not treat it as complete evidence\n"
        "2. Use find(query=<keywords>, scope='all') to search interesting topics\n"
        "3. Use open(pack_id) to expand key evidence\n"
        "4. After collecting enough evidence, produce the final answer"
    ),
    "entity": (
        "1. Review the target-entity information in auto-preload\n"
        "2. Use find(query=<entity name>) to search chapter evidence\n"
        "3. Use read(target_refs=[...]) to inspect the entity's current state\n"
        "4. Use open(pack_id) to expand key evidence passages\n"
        "5. Produce completion suggestions based on evidence"
    ),
    "relationship": (
        "1. Review the relationship list in auto-preload\n"
        "2. Use find(query=<central entity name>) to search related chapter evidence\n"
        "3. Use read(target_refs=[...]) to inspect relevant entities and existing relationships\n"
        "4. Propose relationship completions or corrections based on evidence"
    ),
    "draft": (
        "1. Review the Draft entities / relationships / systems list in auto-preload\n"
        "2. Use find(query=<draft name>, scope='drafts') to inspect draft-quality signals\n"
        "3. Use find(query=<draft name>, scope='story_text') to search prose evidence that can complete the draft\n"
        "4. Use read(target_refs=[...]) to inspect the draft row's current state\n"
        "5. Propose naming-normalization or missing-field edits based on evidence"
    ),
}

_PROMPT_LOCALE_REGISTRY: dict[str, dict[str, Any]] = {
    "zh": {
        "maps": {
            "quick_action_focus": _QUICK_ACTION_FOCUS_ZH,
            "stage_labels": _STAGE_LABELS_ZH,
            "profile_labels": _PROFILE_LABELS_ZH,
            "focus_labels": _FOCUS_LABELS_ZH,
            "focus_capabilities": _FOCUS_CAPABILITIES_ZH,
            "profile_instructions": _PROFILE_INSTRUCTIONS_ZH,
            "focus_instructions": _FOCUS_INSTRUCTIONS_ZH,
            "focus_workflow_hints": _FOCUS_WORKFLOW_HINTS_ZH,
        },
        "texts": {
            "quick_action_prefix": "[研究重点: {focus}]",
            "current_workspace": "当前工作区",
            "surface_line": "- 当前界面：{surface} / {stage}",
            "profile_line": "- 当前 copilot profile：{profile}",
            "scenario_line": "- 当前 copilot 场景：{scenario}",
            "focus_line": "- 当前焦点：{focus}",
            "focus_entity_id_line": "- 当前焦点实体 ID：{entity_id}",
            "capabilities_header": "- 你在这个界面可做的事：",
            "intent_smalltalk": (
                "当前输入更像寒暄或轻聊天。优先自然接话，并简短说明你知道自己处在哪个工作台、"
                "当前能帮上的 2-4 件事情。不要主动生成 suggestions，不要主动展开大量世界知识或依据。"
            ),
            "intent_capability_query": (
                "当前输入是在询问你在这个界面能做什么。优先围绕当前工作台、焦点和能力边界作答，"
                "可以列出 2-4 件你现在就能做的事情。不要主动生成 suggestions，不要主动倾倒大段世界知识。"
            ),
            "intent_task_query": "当前输入是任务型问题。允许结合当前场景进行分析、检索和建议，但仍要先围绕当前工作台焦点回答。",
            "entity_draft_tag": " [草稿]",
            "entity_description_line": "  描述: {text}",
            "entity_aliases_line": "  别名: {aliases}",
            "entity_attribute_line": "  属性 {key}: {surface}{visibility}",
            "relationship_draft_tag": " [草稿]",
            "system_draft_tag": " [草稿]",
            "system_description_line": "  描述: {text}",
            "system_constraints_line": "  约束: {constraints}",
            "name_separator": "、",
            "none_entities": "（暂无实体）",
            "none_relationships": "（暂无关系）",
            "none_systems": "（暂无体系）",
            "none_generic": "（暂无）",
            "no_evidence": "（暂无证据）",
            "section_entities": "### 实体",
            "section_relationships": "### 关系",
            "section_systems": "### 体系",
            "section_draft_entities": "### Draft 实体\n",
            "section_draft_relationships": "### Draft 关系\n",
            "section_draft_systems": "### Draft 体系\n",
            "section_related_confirmed_entities": "### 关联已确认实体（仅供定位）\n",
            "language_interaction_rule": (
                "用户交互语言是 {interaction_locale}，请用该语言回答。"
                "但所有 canonical 名称、标签和证据引用必须保持小说原语言（{novel_lang}）。"
            ),
            "language_novel_rule": "请用小说语言（{novel_lang}）回答。",
            "broad_loaded": "已加载全书概览：{entity_count} 个实体，{relationship_count} 条关系，{system_count} 个体系。",
            "broad_entity_samples": "实体样本：{samples}",
            "broad_relationship_samples": "关系样本：{samples}",
            "broad_system_samples": "体系样本：{samples}",
            "broad_draft_counts": "草稿计数：实体 {entity_count} / 关系 {relationship_count} / 体系 {system_count}",
            "broad_on_demand_hint": "默认不在首轮展开全部世界行；需要细节时请优先按需检索或展开证据。",
            "draft_workset_intro": "当前是草稿治理工作集。优先关注 draft 行本身；已确认实体只用于定位关系端点，不要把它们当成新的研究主题。",
            "draft_counts": "草稿计数：实体 {entity_count} / 关系 {relationship_count} / 体系 {system_count}",
            "whole_book_overview_loaded": "已加载全书概览（薄上下文）：{entity_count} 个实体，{relationship_count} 条关系，{system_count} 个体系，{draft_count} 个草稿。",
            "whole_book_entity_examples": "实体示例：{samples}",
            "whole_book_relationship_examples": "关系示例：{samples}",
            "whole_book_system_examples": "体系示例：{samples}",
            "whole_book_draft_detail_hint": "如需草稿细节，请切到草稿治理或用工具检查具体条目。",
            "whole_book_thin_hint": "这个 profile 故意只做薄加载，请按需检索或展开证据。",
            "focused_context_loaded": "已加载聚焦研究上下文：{entity_count} 个实体，{relationship_count} 条关系，{system_count} 个体系被自动预载。",
            "focused_current_entity": "当前焦点实体：[Entity#{entity_id}] {entity_name} ({entity_type})",
            "focus_attributes_label": "焦点属性：",
            "loaded_entities": "已加载实体：{entities}",
            "direct_relationships_label": "直接关系：\n",
            "focused_expand_hint": "这个 profile 不会自动塞入全局体系和远距离实体；如需扩展，请按需调用工具。",
            "draft_governance_loaded": "已加载草稿治理工作集：{entity_count} 个草稿实体，{relationship_count} 条草稿关系，{system_count} 个草稿体系。",
            "draft_no_description_suffix": " — (无描述)",
            "draft_confirmed_rows_hint": "这里只有在草稿关系需要端点标签时才会额外带入 confirmed 行；请把注意力保持在草稿工作集内。",
            "workflow_hint_light": (
                "1. 先根据当前工作台上下文自然接话\n"
                "2. 简短说明你知道自己在哪个界面、现在能帮什么\n"
                "3. 这一轮默认不要主动调用工具，也不要主动生成 suggestions\n"
                "4. 若用户继续提出明确任务，再转入研究/检索模式"
            ),
        },
        "templates": {
            "workbench_assistant": Template(
                """你是一个小说世界模型工作台助手（Copilot）。

## 当前任务
$runtime_instr

## 当前工作台上下文
$workbench_context

## 当前轮次行为要求
$intent_behavior

## 语言规则
$locale_instr
canonical 名称/标签必须保持小说原语言。

## 输出要求（JSON）
{
  "answer": "（必填）自然语言回答",
  "cited_evidence_indices": [],
  "suggestions": []
}

## 规则
1. 当前轮次不要主动生成 suggestions
2. 不要假装自己看到了大量章节证据；若用户后续提出具体任务，再进入检索/研究模式
3. 回答里要体现你知道当前处在哪个工作台，以及你现在能帮什么
"""
            ),
            "research_assistant": Template(
                """你是一个小说世界模型研究助手（Copilot）。

## 当前任务
$runtime_instr

## 当前工作台上下文
$workbench_context

## 当前轮次行为要求
$intent_behavior

## 语言规则
$locale_instr
canonical 名称/标签必须保持小说原语言。

## 世界模型
$world_model_text

## 后端已检索的证据
以下证据由后端从章节和世界模型中检索。你只能引用这些证据，不能编造新证据。
$evidence_text

## 输出要求（JSON）
{
  "answer": "（必填）自然语言分析/回答",
  "cited_evidence_indices": [0, 1],
  "suggestions": [
    {
      "kind": "update_entity | create_entity | update_relationship | create_relationship | update_system | create_system",
      "title": "建议标题",
      "summary": "一句话说明",
      "cited_evidence_indices": [0],
      "target_resource": "entity | relationship | system",
      "target_id": "整数ID（update 类必填；create 类为 null）",
      "delta": {
        "name": "（可选）",
        "entity_type": "（可选）",
        "description": "（可选）",
        "aliases": ["（可选）"],
        "label": "（可选，relationship）",
        "source_id": "（可选，relationship create）",
        "target_id": "（可选，relationship create）",
        "source_name": "（可选，relationship create；当关系涉及新实体时填写名称）",
        "target_name": "（可选，relationship create；当关系涉及新实体时填写名称）",
        "source_entity_type": "（可选，relationship create；当 source_name 是新实体时填写类型）",
        "target_entity_type": "（可选，relationship create；当 target_name 是新实体时填写类型）",
        "constraints": ["（可选，system）"],
        "display_type": "（可选，system）",
        "attributes": [
          {"key": "属性名", "surface": "可见值"}
        ]
      }
    }
  ]
}

## 规则
1. cited_evidence_indices 必须引用 [Evidence#N] 的索引，不能编造证据
2. suggestions 只在有充分证据时才生成；没有 suggestions 是正常结果
3. target_id 必须引用上面的 [Entity#ID] / [Rel#ID] / [System#ID]
4. delta 中只包含需要修改/新增的字段
5. 不要建议删除、合并或拆分操作
6. attributes 数组用于建议新增或更新实体属性（key-value对）
7. 如果 create_relationship 涉及尚未存在的新实体，必须同时生成对应的 create_entity 建议，并在关系 delta 里填写 source_name / target_name
8. 实体不只包括人物，也包括势力、组织、地点、物件、概念、规则等；不要把所有新实体默认写成人物
"""
            ),
            "tool_loop": Template(
                """你是一个小说世界模型研究助手（Copilot）。你可以使用工具来检索证据。

## 当前任务
$runtime_instr

## 当前工作台上下文
$workbench_context

## 当前轮次行为要求
$intent_behavior

## 语言规则
$locale_instr
canonical 名称/标签必须保持小说原语言。

## 工具
- load_scope_snapshot(): 重新加载世界模型状态（一般不需要，已自动加载）
- find(query, scope?): 搜索证据。scope 可选: "story_text"（正文片段）、"world_rows"（实体/关系/体系）、"drafts"（草稿质量审查）、"all"（默认）
- open(pack_id): 展开某个证据包的完整内容
- read(target_refs): 读取实体/关系/体系的当前状态。参数: [{"type": "entity"|"relationship"|"system", "id": 整数}]

## 建议工作流程
$workflow_hint

## 最终回答格式（JSON）
{
  "answer": "（必填）自然语言分析/回答",
  "cited_evidence_indices": [],
  "suggestions": [
    {
      "kind": "update_entity | create_entity | update_relationship | create_relationship | update_system | create_system",
      "title": "建议标题",
      "summary": "一句话说明",
      "cited_evidence_indices": [],
      "target_resource": "entity | relationship | system",
      "target_id": "整数ID（update 类必填；create 类为 null）",
      "delta": {
        "name": "（可选）",
        "entity_type": "（可选）",
        "description": "（可选）",
        "aliases": ["（可选）"],
        "label": "（可选，relationship）",
        "source_id": "（可选，relationship create）",
        "target_id": "（可选，relationship create）",
        "source_name": "（可选，relationship create；当关系涉及新实体时填写名称）",
        "target_name": "（可选，relationship create；当关系涉及新实体时填写名称）",
        "source_entity_type": "（可选，relationship create；当 source_name 是新实体时填写类型）",
        "target_entity_type": "（可选，relationship create；当 target_name 是新实体时填写类型）",
        "constraints": ["（可选，system）"],
        "display_type": "（可选，system）",
        "attributes": [
          {"key": "属性名", "surface": "可见值"}
        ]
      }
    }
  ]
}

## 规则
1. 只能基于工具返回的证据提出建议，不能编造
2. 没有 suggestions 也是正常结果；若当前轮次是闲聊/能力询问，应默认返回空 suggestions
3. target_id 必须引用已知的实体/关系/体系 ID
4. delta 中只包含需要修改/新增的字段
5. 不要建议删除、合并或拆分
6. attributes 数组用于建议新增或更新实体属性（key-value对）
7. 如果 create_relationship 涉及尚未存在的新实体，必须同时生成对应的 create_entity 建议，并在关系 delta 里填写 source_name / target_name
8. 实体不只包括人物，也包括势力、组织、地点、物件、概念、规则等；不要把所有新实体默认写成人物
"""
            ),
        },
    },
    "en": {
        "maps": {
            "quick_action_focus": _QUICK_ACTION_FOCUS_EN,
            "stage_labels": _STAGE_LABELS_EN,
            "profile_labels": _PROFILE_LABELS_EN,
            "focus_labels": _FOCUS_LABELS_EN,
            "focus_capabilities": _FOCUS_CAPABILITIES_EN,
            "profile_instructions": _PROFILE_INSTRUCTIONS_EN,
            "focus_instructions": _FOCUS_INSTRUCTIONS_EN,
            "focus_workflow_hints": _FOCUS_WORKFLOW_HINTS_EN,
        },
        "texts": {
            "quick_action_prefix": "[Research focus: {focus}]",
            "current_workspace": "Current workspace",
            "surface_line": "- Current surface: {surface} / {stage}",
            "profile_line": "- Current copilot profile: {profile}",
            "scenario_line": "- Current copilot scenario: {scenario}",
            "focus_line": "- Current focus: {focus}",
            "focus_entity_id_line": "- Current focus entity ID: {entity_id}",
            "capabilities_header": "- What you can do here:",
            "intent_smalltalk": "The current input looks like small talk. Reply naturally, mention which workspace you are in, and briefly list 2-4 things you can help with right now. Do not proactively generate suggestions or dump large amounts of world knowledge.",
            "intent_capability_query": "The user is asking what you can do in this workspace. Answer around the current workbench, focus, and capability boundaries, and list 2-4 concrete things you can do right now. Do not proactively generate suggestions or dump large world-model summaries.",
            "intent_task_query": "The current input is task-oriented. You may analyze, retrieve evidence, and propose suggestions within the current scenario, but anchor the response in the current workspace focus first.",
            "entity_draft_tag": " [draft]",
            "entity_description_line": "  Description: {text}",
            "entity_aliases_line": "  Aliases: {aliases}",
            "entity_attribute_line": "  Attribute {key}: {surface}{visibility}",
            "relationship_draft_tag": " [draft]",
            "system_draft_tag": " [draft]",
            "system_description_line": "  Description: {text}",
            "system_constraints_line": "  Constraints: {constraints}",
            "name_separator": ", ",
            "none_entities": "(No entities yet)",
            "none_relationships": "(No relationships yet)",
            "none_systems": "(No systems yet)",
            "none_generic": "(None)",
            "no_evidence": "(No evidence yet)",
            "section_entities": "### Entities",
            "section_relationships": "### Relationships",
            "section_systems": "### Systems",
            "section_draft_entities": "### Draft entities\n",
            "section_draft_relationships": "### Draft relationships\n",
            "section_draft_systems": "### Draft systems\n",
            "section_related_confirmed_entities": "### Related confirmed entities (reference only)\n",
            "language_interaction_rule": "The user's interaction language is {interaction_locale}. Respond in that language, but keep all canonical names, labels, and evidence references in the novel's original language ({novel_lang}).",
            "language_novel_rule": "Respond in the novel's language ({novel_lang}).",
            "broad_loaded": "Loaded whole-book overview: {entity_count} entities, {relationship_count} relationships, and {system_count} systems.",
            "broad_entity_samples": "Entity samples: {samples}",
            "broad_relationship_samples": "Relationship samples: {samples}",
            "broad_system_samples": "System samples: {samples}",
            "broad_draft_counts": "Draft counts: entities {entity_count} / relationships {relationship_count} / systems {system_count}",
            "broad_on_demand_hint": "Do not expand every world row in the first pass. Retrieve or expand evidence on demand when details are needed.",
            "draft_workset_intro": "This is the draft-governance workset. Focus on the draft rows themselves. Confirmed entities are included only to identify relationship endpoints and should not become new research topics.",
            "draft_counts": "Draft counts: entities {entity_count} / relationships {relationship_count} / systems {system_count}",
            "whole_book_overview_loaded": "Loaded whole-book overview (thin context): {entity_count} entities, {relationship_count} relationships, {system_count} systems, and {draft_count} draft rows.",
            "whole_book_entity_examples": "Entity examples: {samples}",
            "whole_book_relationship_examples": "Relationship examples: {samples}",
            "whole_book_system_examples": "System examples: {samples}",
            "whole_book_draft_detail_hint": "If you need draft details, switch to draft governance or inspect specific rows with tools.",
            "whole_book_thin_hint": "This profile intentionally stays thin; retrieve or expand evidence on demand.",
            "focused_context_loaded": "Loaded focused-research context: {entity_count} entities, {relationship_count} relationships, and {system_count} systems were auto-preloaded.",
            "focused_current_entity": "Current focus entity: [Entity#{entity_id}] {entity_name} ({entity_type})",
            "focus_attributes_label": "Focus attributes:",
            "loaded_entities": "Loaded entities: {entities}",
            "direct_relationships_label": "Direct relationships:\n",
            "focused_expand_hint": "This profile does not auto-load global systems or distant entities. Use tools if you need to expand further.",
            "draft_governance_loaded": "Loaded draft-governance workset: {entity_count} draft entities, {relationship_count} draft relationships, and {system_count} draft systems.",
            "draft_no_description_suffix": " — (No description)",
            "draft_confirmed_rows_hint": "Confirmed rows are only brought in here when a draft relationship needs endpoint labels. Keep your attention inside the draft workset.",
            "workflow_hint_light": (
                "1. Start by replying naturally from the current workbench context\n"
                "2. Briefly show that you know which workspace you are in and what you can help with\n"
                "3. Do not proactively call tools or generate suggestions in this turn\n"
                "4. If the user follows up with a concrete task, then switch into retrieval or research mode"
            ),
        },
        "templates": {
            "workbench_assistant": Template(
                """You are a novel world-model workbench assistant (Copilot).

## Current task
$runtime_instr

## Current workbench context
$workbench_context

## Behavior for this turn
$intent_behavior

## Language rules
$locale_instr
Canonical names and labels must remain in the novel's original language.

## Output format (JSON)
{
  "answer": "Natural-language answer (required)",
  "cited_evidence_indices": [],
  "suggestions": []
}

## Rules
1. Do not proactively generate suggestions in this turn
2. Do not pretend you have already seen large amounts of chapter evidence; wait for a concrete task before entering retrieval or research mode
3. Make it clear that you know which workspace you are in and what you can help with right now
"""
            ),
            "research_assistant": Template(
                """You are a novel world-model research assistant (Copilot).

## Current task
$runtime_instr

## Current workbench context
$workbench_context

## Behavior for this turn
$intent_behavior

## Language rules
$locale_instr
Canonical names and labels must remain in the novel's original language.

## World model
$world_model_text

## Evidence retrieved by the backend
The evidence below was retrieved from chapters and the world model by the backend. You may only cite this evidence and must not invent new evidence.
$evidence_text

## Output format (JSON)
{
  "answer": "Natural-language analysis or answer (required)",
  "cited_evidence_indices": [0, 1],
  "suggestions": [
    {
      "kind": "update_entity | create_entity | update_relationship | create_relationship | update_system | create_system",
      "title": "Suggestion title",
      "summary": "One-sentence explanation",
      "cited_evidence_indices": [0],
      "target_resource": "entity | relationship | system",
      "target_id": "Integer ID (required for update kinds; null for create kinds)",
      "delta": {
        "name": "(optional)",
        "entity_type": "(optional)",
        "description": "(optional)",
        "aliases": ["(optional)"],
        "label": "(optional, relationship)",
        "source_id": "(optional, relationship create)",
        "target_id": "(optional, relationship create)",
        "source_name": "(optional, relationship create; required when the relationship refers to a new entity)",
        "target_name": "(optional, relationship create; required when the relationship refers to a new entity)",
        "source_entity_type": "(optional, relationship create; required when source_name is a new entity)",
        "target_entity_type": "(optional, relationship create; required when target_name is a new entity)",
        "constraints": ["(optional, system)"],
        "display_type": "(optional, system)",
        "attributes": [
          {"key": "Attribute name", "surface": "Visible value"}
        ]
      }
    }
  ]
}

## Rules
1. cited_evidence_indices must reference [Evidence#N] entries that actually exist
2. Generate suggestions only when evidence is sufficient; no suggestions is a normal outcome
3. target_id values must reference the [Entity#ID] / [Rel#ID] / [System#ID] entries above
4. delta must include only fields that need to be added or changed
5. Do not suggest delete, merge, or split operations
6. The attributes array is only for proposing added or updated entity attributes (key-value pairs)
7. If create_relationship introduces a not-yet-existing entity, you must also emit the matching create_entity suggestion and fill source_name / target_name in the relationship delta
8. Entities are not limited to people; they can also be factions, organizations, locations, objects, concepts, and rules. Do not default every new entity to Character
"""
            ),
            "tool_loop": Template(
                """You are a novel world-model research assistant (Copilot). You may use tools to retrieve evidence.

## Current task
$runtime_instr

## Current workbench context
$workbench_context

## Behavior for this turn
$intent_behavior

## Language rules
$locale_instr
Canonical names and labels must remain in the novel's original language.

## Tools
- load_scope_snapshot(): Reload world-model state (entities, relationships, systems, drafts). Usually unnecessary because it is already loaded.
- find(query, scope?): Search evidence. Optional scope values: "story_text" (chapter excerpts), "world_rows" (entities / relationships / systems), "drafts" (draft-quality review), "all" (default)
- open(pack_id): Expand the full contents of an evidence pack
- read(target_refs): Read the current live state of entities / relationships / systems. Argument shape: [{"type": "entity"|"relationship"|"system", "id": integer}]

## Suggested workflow
$workflow_hint

## Final answer format (JSON)
{
  "answer": "Natural-language analysis or answer (required)",
  "cited_evidence_indices": [],
  "suggestions": [
    {
      "kind": "update_entity | create_entity | update_relationship | create_relationship | update_system | create_system",
      "title": "Suggestion title",
      "summary": "One-sentence explanation",
      "cited_evidence_indices": [],
      "target_resource": "entity | relationship | system",
      "target_id": "Integer ID (required for update kinds; null for create kinds)",
      "delta": {
        "name": "(optional)",
        "entity_type": "(optional)",
        "description": "(optional)",
        "aliases": ["(optional)"],
        "label": "(optional, relationship)",
        "source_id": "(optional, relationship create)",
        "target_id": "(optional, relationship create)",
        "source_name": "(optional, relationship create; required when the relationship refers to a new entity)",
        "target_name": "(optional, relationship create; required when the relationship refers to a new entity)",
        "source_entity_type": "(optional, relationship create; required when source_name is a new entity)",
        "target_entity_type": "(optional, relationship create; required when target_name is a new entity)",
        "constraints": ["(optional, system)"],
        "display_type": "(optional, system)",
        "attributes": [
          {"key": "Attribute name", "surface": "Visible value"}
        ]
      }
    }
  ]
}

## Rules
1. You may only propose suggestions based on evidence returned by tools
2. No suggestions is a normal result. For small talk or capability questions, default to an empty suggestions array
3. target_id values must reference known entity / relationship / system IDs
4. delta must include only fields that need to be added or changed
5. Do not suggest delete, merge, or split operations
6. The attributes array is only for proposing added or updated entity attributes (key-value pairs)
7. If create_relationship introduces a not-yet-existing entity, you must also emit the matching create_entity suggestion and fill source_name / target_name in the relationship delta
8. Entities are not limited to people; they can also be factions, organizations, locations, objects, concepts, and rules. Do not default every new entity to Character
"""
            ),
        },
    },
}


def _prompt_map(locale: str | None, map_name: str, item_key: str, *, fallback_key: str | None = None) -> Any:
    for lookup_key in (item_key, fallback_key):
        if lookup_key is None:
            continue
        for candidate in get_language_fallback_chain(locale, default="zh"):
            bundle = _PROMPT_LOCALE_REGISTRY.get(candidate)
            if not bundle:
                continue
            mapping = bundle.get("maps", {}).get(map_name, {})
            if lookup_key in mapping:
                return mapping[lookup_key]
    raise KeyError(f"Missing prompt map value {map_name}.{item_key}")


def _prompt_text(locale: str | None, key: str, **params: object) -> str:
    for candidate in get_language_fallback_chain(locale, default="zh"):
        bundle = _PROMPT_LOCALE_REGISTRY.get(candidate)
        if not bundle:
            continue
        template = bundle.get("texts", {}).get(key)
        if template is not None:
            return str(template).format(**params)
    raise KeyError(f"Missing prompt text {key}")


def _prompt_template(locale: str | None, key: str, **params: object) -> str:
    for candidate in get_language_fallback_chain(locale, default="zh"):
        bundle = _PROMPT_LOCALE_REGISTRY.get(candidate)
        if not bundle:
            continue
        template = bundle.get("templates", {}).get(key)
        if template is not None:
            return template.substitute(**params)
    raise KeyError(f"Missing prompt template {key}")


def _strip_quick_action_prefix(prompt: str) -> str:
    for prefix in ("[研究重点:", "[Research focus:"):
        if prompt.startswith(prefix):
            closing = prompt.find("]")
            if closing != -1:
                return prompt[closing + 1 :].strip()
    return prompt.strip()


def apply_quick_action_prompt(
    prompt: str,
    quick_action_id: str | None,
    interaction_locale: str = "zh",
) -> str:
    """Prefix the user prompt with an internal quick-action research focus."""
    if not quick_action_id:
        return prompt
    try:
        focus = _prompt_map(interaction_locale, "quick_action_focus", quick_action_id)
    except KeyError:
        return prompt
    prefix = _prompt_text(interaction_locale, "quick_action_prefix", focus=focus)
    return f"{prefix}\n\n{prompt}"


def classify_turn_intent(prompt: str) -> str:
    """Classify the current user turn."""
    raw = _strip_quick_action_prefix(prompt)
    if not raw:
        return "smalltalk"

    lowered = raw.casefold()
    normalized = _PUNCTUATION_RE.sub("", lowered)

    if any(hint in lowered for hint in _CAPABILITY_HINTS):
        return "capability_query"

    if normalized in _GREETING_NORMALIZED:
        return "smalltalk"

    if any(hint in lowered for hint in _TASK_INTENT_HINTS):
        return "task_query"

    if len(normalized) <= 6 and any(token in normalized for token in ("你好", "您好", "在吗", "谢谢", "hi", "hello", "hey")):
        return "smalltalk"

    return "task_query"


def should_preload_world_context(turn_intent: str) -> bool:
    return turn_intent == "task_query"


def _resolve_focus_label(snapshot: ScopeSnapshot, session_data: dict[str, Any]) -> str | None:
    display_title = str(session_data.get("display_title", "") or "").strip()
    if display_title:
        return display_title

    context = session_data.get("context_json") or {}
    entity_id = context.get("entity_id")
    if entity_id is not None:
        entity = snapshot.entities_by_id.get(entity_id)
        if entity:
            return entity.name
    return None


def _build_workbench_context_text(
    snapshot: ScopeSnapshot,
    scenario: str,
    session_data: dict[str, Any],
    interaction_locale: str = "zh",
) -> str:
    context = session_data.get("context_json") or {}
    surface_label = _SURFACE_LABELS.get(str(context.get("surface") or "").lower(), "Novel Copilot")
    if str(context.get("surface") or "").lower() == "atlas":
        stage_key = str(context.get("tab") or "").lower()
    else:
        stage_key = str(context.get("stage") or context.get("tab") or "").lower()
    try:
        stage_label = _prompt_map(interaction_locale, "stage_labels", stage_key)
    except KeyError:
        stage_label = _prompt_text(interaction_locale, "current_workspace")
    focus_label = _resolve_focus_label(snapshot, session_data)

    lines = [
        _prompt_text(interaction_locale, "surface_line", surface=surface_label, stage=stage_label),
        _prompt_text(
            interaction_locale,
            "profile_line",
            profile=_prompt_map(interaction_locale, "profile_labels", snapshot.profile, fallback_key=snapshot.profile),
        ),
        _prompt_text(
            interaction_locale,
            "scenario_line",
            scenario=_prompt_map(interaction_locale, "focus_labels", snapshot.focus_variant or scenario, fallback_key=scenario),
        ),
    ]
    if focus_label:
        lines.append(_prompt_text(interaction_locale, "focus_line", focus=focus_label))
    focus_entity_id = snapshot.focus_entity_id if isinstance(snapshot.focus_entity_id, int) else context.get("entity_id")
    if isinstance(focus_entity_id, int):
        lines.append(_prompt_text(interaction_locale, "focus_entity_id_line", entity_id=focus_entity_id))

    capabilities = _prompt_map(
        interaction_locale,
        "focus_capabilities",
        snapshot.focus_variant or "whole_book",
        fallback_key="whole_book",
    )
    lines.append(_prompt_text(interaction_locale, "capabilities_header"))
    lines.extend(f"  {idx}. {item}" for idx, item in enumerate(capabilities, start=1))
    return "\n".join(lines)


def _build_intent_behavior_text(turn_intent: str, interaction_locale: str = "zh") -> str:
    if turn_intent == "smalltalk":
        return _prompt_text(interaction_locale, "intent_smalltalk")
    if turn_intent == "capability_query":
        return _prompt_text(interaction_locale, "intent_capability_query")
    return _prompt_text(interaction_locale, "intent_task_query")


def _build_runtime_instruction_text(
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str = "zh",
) -> str:
    profile_instr = _prompt_map(
        interaction_locale,
        "profile_instructions",
        snapshot.profile,
        fallback_key=snapshot.profile,
    )
    focus_key = snapshot.focus_variant or scenario
    focus_instr = _prompt_map(
        interaction_locale,
        "focus_instructions",
        focus_key,
        fallback_key="entity",
    )
    return f"{profile_instr}\n{focus_instr}".strip()


def _format_entity_rows_for_prompt(
    entities: list[WorldEntity],
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for entity in entities:
        draft_tag = _prompt_text(interaction_locale, "entity_draft_tag") if entity.status == "draft" else ""
        parts = [f"[Entity#{entity.id}]{draft_tag} {entity.name} ({entity.entity_type})"]
        if entity.description:
            parts.append(_prompt_text(interaction_locale, "entity_description_line", text=entity.description[:300]))
        if entity.aliases:
            parts.append(_prompt_text(interaction_locale, "entity_aliases_line", aliases=", ".join(entity.aliases[:5])))
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        for attr in attrs[:8]:
            vis = f" [{attr.visibility}]" if attr.visibility != "active" else ""
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "entity_attribute_line",
                    key=attr.key,
                    surface=attr.surface[:200],
                    visibility=vis,
                )
            )
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _format_entities_for_prompt(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    return _format_entity_rows_for_prompt(snapshot.entities, snapshot, interaction_locale)


def _format_relationship_rows_for_prompt(
    relationships: list[WorldRelationship],
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for relationship in relationships:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        src_name = src.name if src else f"Entity#{relationship.source_id}"
        tgt_name = tgt.name if tgt else f"Entity#{relationship.target_id}"
        draft_tag = _prompt_text(interaction_locale, "relationship_draft_tag") if relationship.status == "draft" else ""
        desc = f" — {relationship.description[:200]}" if relationship.description else ""
        lines.append(f"[Rel#{relationship.id}]{draft_tag} {src_name} --[{relationship.label}]--> {tgt_name}{desc}")
    return "\n".join(lines)


def _format_relationships_for_prompt(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    return _format_relationship_rows_for_prompt(snapshot.relationships, snapshot, interaction_locale)


def _format_system_rows_for_prompt(
    systems: list[WorldSystem],
    interaction_locale: str = "zh",
) -> str:
    lines: list[str] = []
    for system in systems:
        draft_tag = _prompt_text(interaction_locale, "system_draft_tag") if system.status == "draft" else ""
        parts = [f"[System#{system.id}]{draft_tag} {system.name} ({system.display_type})"]
        if system.description:
            parts.append(_prompt_text(interaction_locale, "system_description_line", text=system.description[:300]))
        if system.constraints:
            parts.append(_prompt_text(
                interaction_locale,
                "system_constraints_line",
                constraints="; ".join(str(constraint)[:100] for constraint in system.constraints[:5]),
            ))
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _format_systems_for_prompt(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    return _format_system_rows_for_prompt(snapshot.systems, interaction_locale)


def _format_evidence_for_prompt(evidence: list[EvidenceItem]) -> str:
    parts: list[str] = []
    for index, item in enumerate(evidence):
        parts.append(f"[Evidence#{index}] ({item.source_type}) {item.title}\n{item.excerpt}")
    return "\n\n---\n\n".join(parts)


def _build_broad_exploration_world_overview(
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    name_separator = _prompt_text(interaction_locale, "name_separator")
    entity_samples = name_separator.join(entity.name for entity in snapshot.entities[:6]) or _prompt_text(interaction_locale, "none_entities")
    relationship_samples = []
    for relationship in snapshot.relationships[:4]:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        relationship_samples.append(
            f"{src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
        )
    system_samples = (
        name_separator.join(system.name for system in snapshot.systems[:4])
        if snapshot.systems
        else _prompt_text(interaction_locale, "none_systems")
    )
    draft_count = len(snapshot.draft_entities) + len(snapshot.draft_relationships) + len(snapshot.draft_systems)

    parts = [
        _prompt_text(
            interaction_locale,
            "broad_loaded",
            entity_count=len(snapshot.entities),
            relationship_count=len(snapshot.relationships),
            system_count=len(snapshot.systems),
        ),
        _prompt_text(interaction_locale, "broad_entity_samples", samples=entity_samples),
    ]
    if relationship_samples:
        parts.append(_prompt_text(interaction_locale, "broad_relationship_samples", samples="; ".join(relationship_samples)))
    if snapshot.systems:
        parts.append(_prompt_text(interaction_locale, "broad_system_samples", samples=system_samples))
    if draft_count:
        parts.append(_prompt_text(
            interaction_locale,
            "broad_draft_counts",
            entity_count=len(snapshot.draft_entities),
            relationship_count=len(snapshot.draft_relationships),
            system_count=len(snapshot.draft_systems),
        ))
    parts.append(_prompt_text(interaction_locale, "broad_on_demand_hint"))
    return "\n".join(parts)


def _build_draft_governance_world_context(
    snapshot: ScopeSnapshot,
    interaction_locale: str = "zh",
) -> str:
    supporting_entities = [entity for entity in snapshot.entities if entity.status != "draft"]
    parts = [
        _prompt_text(interaction_locale, "draft_workset_intro"),
        _prompt_text(
            interaction_locale,
            "draft_counts",
            entity_count=len(snapshot.draft_entities),
            relationship_count=len(snapshot.draft_relationships),
            system_count=len(snapshot.draft_systems),
        ),
    ]
    if snapshot.draft_entities:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_entities")
            + (
                _format_entity_rows_for_prompt(snapshot.draft_entities, snapshot, interaction_locale)
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if snapshot.draft_relationships:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_relationships")
            + (
                _format_relationship_rows_for_prompt(snapshot.draft_relationships, snapshot, interaction_locale)
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if snapshot.draft_systems:
        parts.append(
            _prompt_text(interaction_locale, "section_draft_systems")
            + (
                _format_system_rows_for_prompt(snapshot.draft_systems, interaction_locale)
                or _prompt_text(interaction_locale, "none_generic")
            )
        )
    if supporting_entities:
        lines = [f"- {entity.name} ({entity.entity_type})" for entity in supporting_entities[:8]]
        parts.append(
            _prompt_text(interaction_locale, "section_related_confirmed_entities")
            + "\n".join(lines)
        )
    return "\n\n".join(parts)


def _build_world_model_prompt_block(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    if snapshot.profile == "broad_exploration":
        return _build_broad_exploration_world_overview(snapshot, interaction_locale)
    if snapshot.profile == "draft_governance":
        return _build_draft_governance_world_context(snapshot, interaction_locale)

    entities_text = _format_entities_for_prompt(snapshot, interaction_locale) or _prompt_text(interaction_locale, "none_entities")
    relationships_text = _format_relationships_for_prompt(snapshot, interaction_locale) or _prompt_text(interaction_locale, "none_relationships")
    parts = [
        _prompt_text(interaction_locale, "section_entities"),
        entities_text,
        "",
        _prompt_text(interaction_locale, "section_relationships"),
        relationships_text,
    ]
    if snapshot.systems:
        parts.extend([
            "",
            _prompt_text(interaction_locale, "section_systems"),
            _format_systems_for_prompt(snapshot, interaction_locale) or _prompt_text(interaction_locale, "none_systems"),
        ])
    return "\n".join(parts)


def build_copilot_system_prompt(
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> str:
    novel_lang = snapshot.novel_language
    runtime_instr = _build_runtime_instruction_text(snapshot, scenario, interaction_locale)
    workbench_context = _build_workbench_context_text(snapshot, scenario, session_data, interaction_locale)
    intent_behavior = _build_intent_behavior_text(turn_intent, interaction_locale)

    if interaction_locale and interaction_locale != novel_lang:
        locale_instr = _prompt_text(
            interaction_locale,
            "language_interaction_rule",
            interaction_locale=interaction_locale,
            novel_lang=novel_lang,
        )
    else:
        locale_instr = _prompt_text(interaction_locale, "language_novel_rule", novel_lang=novel_lang)

    world_model_text = _build_world_model_prompt_block(snapshot, interaction_locale)
    evidence_text = _format_evidence_for_prompt(evidence) or _prompt_text(interaction_locale, "no_evidence")

    if not should_preload_world_context(turn_intent):
        return _prompt_template(
            interaction_locale,
            "workbench_assistant",
            runtime_instr=runtime_instr,
            workbench_context=workbench_context,
            intent_behavior=intent_behavior,
            locale_instr=locale_instr,
        )

    return _prompt_template(
        interaction_locale,
        "research_assistant",
        runtime_instr=runtime_instr,
        workbench_context=workbench_context,
        intent_behavior=intent_behavior,
        locale_instr=locale_instr,
        world_model_text=world_model_text,
        evidence_text=evidence_text,
    )


def build_auto_preload(snapshot: ScopeSnapshot, interaction_locale: str = "zh") -> str:
    """Build a minimal snapshot summary for the first message."""
    if snapshot.profile == "focused_research":
        focus_entity = snapshot.entities_by_id.get(snapshot.focus_entity_id or -1)
        entity_names = [
            f"{entity.name}({entity.entity_type})"
            + (_prompt_text(interaction_locale, "entity_draft_tag") if entity.status == "draft" else "")
            for entity in snapshot.entities[:12]
        ]
        relationship_lines: list[str] = []
        for relationship in snapshot.relationships[:12]:
            src = snapshot.entities_by_id.get(relationship.source_id)
            tgt = snapshot.entities_by_id.get(relationship.target_id)
            relationship_lines.append(
                f"  [Rel#{relationship.id}] {src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
            )

        parts = [
            _prompt_text(
                interaction_locale,
                "focused_context_loaded",
                entity_count=len(snapshot.entities),
                relationship_count=len(snapshot.relationships),
                system_count=len(snapshot.systems),
            ),
        ]
        if focus_entity:
            parts.append(
                _prompt_text(
                    interaction_locale,
                    "focused_current_entity",
                    entity_id=focus_entity.id,
                    entity_name=focus_entity.name,
                    entity_type=focus_entity.entity_type,
                )
            )
            attrs = snapshot.attributes_by_entity.get(focus_entity.id, [])
            if attrs:
                parts.append(
                    _prompt_text(interaction_locale, "focus_attributes_label")
                    + "; ".join(f"{attr.key}={attr.surface[:80]}" for attr in attrs[:6])
                )
        if entity_names:
            parts.append(
                _prompt_text(interaction_locale, "loaded_entities", entities=", ".join(entity_names))
            )
        if relationship_lines:
            parts.append(_prompt_text(interaction_locale, "direct_relationships_label") + "\n".join(relationship_lines))
        parts.append(_prompt_text(interaction_locale, "focused_expand_hint"))
        return "\n".join(parts)

    if snapshot.profile == "draft_governance":
        parts = [
            _prompt_text(
                interaction_locale,
                "draft_governance_loaded",
                entity_count=len(snapshot.draft_entities),
                relationship_count=len(snapshot.draft_relationships),
                system_count=len(snapshot.draft_systems),
            ),
        ]
        if snapshot.draft_entities:
            draft_lines = []
            for entity in snapshot.draft_entities[:12]:
                desc = (entity.description or "").strip()
                desc_note = f" — {desc[:80]}" if desc else _prompt_text(interaction_locale, "draft_no_description_suffix")
                draft_lines.append(f"  [Entity#{entity.id}] {entity.name} ({entity.entity_type}){desc_note}")
            parts.append(_prompt_text(interaction_locale, "section_draft_entities") + "\n".join(draft_lines))
        if snapshot.draft_relationships:
            draft_relationships = []
            for relationship in snapshot.draft_relationships[:10]:
                src = snapshot.entities_by_id.get(relationship.source_id)
                tgt = snapshot.entities_by_id.get(relationship.target_id)
                draft_relationships.append(
                    f"  [Rel#{relationship.id}] {src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}"
                )
            parts.append(_prompt_text(interaction_locale, "section_draft_relationships") + "\n".join(draft_relationships))
        if snapshot.draft_systems:
            draft_systems = [f"  [System#{system.id}] {system.name}" for system in snapshot.draft_systems[:10]]
            parts.append(_prompt_text(interaction_locale, "section_draft_systems") + "\n".join(draft_systems))
        parts.append(_prompt_text(interaction_locale, "draft_confirmed_rows_hint"))
        return "\n".join(parts)

    entity_names = [
        f"{entity.name}({entity.entity_type})"
        + (_prompt_text(interaction_locale, "entity_draft_tag") if entity.status == "draft" else "")
        for entity in snapshot.entities[:30]
    ]
    relationship_summaries = []
    for relationship in snapshot.relationships[:15]:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        relationship_summaries.append(f"{src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'}")
    system_names = [system.name for system in snapshot.systems]
    draft_count = len(snapshot.draft_entities) + len(snapshot.draft_relationships) + len(snapshot.draft_systems)
    parts = [
        _prompt_text(
            interaction_locale,
            "whole_book_overview_loaded",
            entity_count=len(snapshot.entities),
            relationship_count=len(snapshot.relationships),
            system_count=len(snapshot.systems),
            draft_count=draft_count,
        ),
    ]
    if entity_names:
        parts.append(
            _prompt_text(interaction_locale, "whole_book_entity_examples", samples=", ".join(entity_names[:12]))
        )
    if relationship_summaries:
        parts.append(
            _prompt_text(interaction_locale, "whole_book_relationship_examples", samples="; ".join(relationship_summaries[:8]))
        )
    if system_names:
        parts.append(
            _prompt_text(interaction_locale, "whole_book_system_examples", samples=", ".join(system_names[:8]))
        )
    if draft_count:
        parts.append(_prompt_text(interaction_locale, "whole_book_draft_detail_hint"))
    parts.append(_prompt_text(interaction_locale, "whole_book_thin_hint"))
    return "\n".join(parts)


def build_tool_loop_system_prompt(
    snapshot: ScopeSnapshot,
    scenario: str,
    interaction_locale: str,
    session_data: dict[str, Any],
    turn_intent: str,
) -> str:
    """Build the system prompt for the tool-loop agent."""
    novel_lang = snapshot.novel_language
    runtime_instr = _build_runtime_instruction_text(snapshot, scenario, interaction_locale)
    workbench_context = _build_workbench_context_text(snapshot, scenario, session_data, interaction_locale)
    intent_behavior = _build_intent_behavior_text(turn_intent, interaction_locale)

    if interaction_locale and interaction_locale != novel_lang:
        locale_instr = _prompt_text(
            interaction_locale,
            "language_interaction_rule",
            interaction_locale=interaction_locale,
            novel_lang=novel_lang,
        )
    else:
        locale_instr = _prompt_text(interaction_locale, "language_novel_rule", novel_lang=novel_lang)

    if should_preload_world_context(turn_intent):
        workflow_hint = _prompt_map(
            interaction_locale,
            "focus_workflow_hints",
            snapshot.focus_variant or "entity",
            fallback_key="entity",
        )
    else:
        workflow_hint = _prompt_text(interaction_locale, "workflow_hint_light")

    return _prompt_template(
        interaction_locale,
        "tool_loop",
        runtime_instr=runtime_instr,
        workbench_context=workbench_context,
        intent_behavior=intent_behavior,
        locale_instr=locale_instr,
        workflow_hint=workflow_hint,
    )
