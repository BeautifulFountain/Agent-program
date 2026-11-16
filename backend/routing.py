from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteRule:
    agent_id: str
    keywords: tuple[str, ...]
    reason: str


REQUIRED = {
    "requirements": "必要节点：澄清任务范围、约束和交付标准",
    "writer": "必要节点：整合中间成果并生成最终文档",
    "reviewer": "必要节点：按照统一量表验证最终结果",
}

RULES = (
    RouteRule("planner", ("复杂", "方案", "计划", "框架", "流程", "实施", "项目", "多阶段"), "任务包含方案设计或多个交付步骤，需要拆解依赖"),
    RouteRule("literature", ("文献", "综述", "政策", "法规", "来源", "证据", "治理", "风险", "合规"), "任务需要可追溯资料、政策或证据支持"),
    RouteRule("analyst", ("数据", "统计", "调查", "样本", "变量", "指标", "计算", "实验", "对比"), "任务涉及数据、变量、样本或统计方法"),
    RouteRule("fact-checker", ("报告", "简报", "事实", "核验", "引用", "来源", "政策", "法规", "风险", "合规", "正式"), "正式成果或风险结论需要独立事实核验"),
)

ORDER = ("requirements", "planner", "literature", "analyst", "writer", "fact-checker", "reviewer")


def recommend_agents(task: str, available_ids: set[str]) -> dict:
    """Return an explainable minimum agent set without calling an LLM."""
    text = task.strip().lower()
    chosen = {agent_id for agent_id in REQUIRED if agent_id in available_ids}
    reasons = {agent_id: reason for agent_id, reason in REQUIRED.items() if agent_id in available_ids}
    matches: dict[str, list[str]] = {}
    for rule in RULES:
        hits = [word for word in rule.keywords if word.lower() in text]
        if hits and rule.agent_id in available_ids:
            chosen.add(rule.agent_id)
            reasons[rule.agent_id] = rule.reason
            matches[rule.agent_id] = hits[:4]
    if len(text) >= 80 and "planner" in available_ids:
        chosen.add("planner")
        reasons.setdefault("planner", "任务描述较长且约束较多，需要统一规划")
        matches.setdefault("planner", ["多约束任务"])
    agent_ids = [agent_id for agent_id in ORDER if agent_id in chosen]
    return {
        "agent_ids": agent_ids,
        "reasons": reasons,
        "matched_keywords": matches,
        "strategy": "最小必要组合" if len(agent_ids) <= 4 else "按任务特征组合",
        "llm_called": False,
    }
